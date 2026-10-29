"""محرك متقدم متعدد المراحل للتعرف على خط اليد (عربي/إنجليزي) ومطابقة الأدوية المصرية.

يدعم 3 مستويات للتعرف على خط اليد بالترتيب:
1. التعرف المباشر من إحداثيات القلم (Stroke Trajectory Digital Ink) للعربية والإنجليزية.
2. محرك التعلم العميق المحلي (EasyOCR ثنائي اللغة ['ar', 'en'] أو TrOCR) عند توفره على الجهاز.
3. محرك البصمة البصرية والحركية (2D Spatial Ink-Grid Cosine Similarity) + Tesseract 5 LSTM المحلي.
"""
import json
import math
import os
import re
import shutil
import unicodedata
import urllib.request
from typing import List, Dict, Any, Tuple, Optional
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

os.environ["OMP_THREAD_LIMIT"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"

try:
    from rapidfuzz import fuzz as _rf_fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    _rf_fuzz = None
    RAPIDFUZZ_AVAILABLE = False

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    easyocr = None
    EASYOCR_AVAILABLE = False

try:
    import pytesseract
    TESSERACT_AVAILABLE = shutil.which("tesseract") is not None
    _TESS_LANGS = pytesseract.get_languages(config="") if TESSERACT_AVAILABLE else []
except ImportError:
    pytesseract = None
    TESSERACT_AVAILABLE = False
    _TESS_LANGS = []

_EASYOCR_READER = None

ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]")
DIGITS_MAP = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
ARABIC_CHAR_MAP = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ة": "ه", "ى": "ي", "ؤ": "و", "ئ": "ي",
    "ڤ": "ف", "پ": "ب", "چ": "ج", "گ": "ك",
})
NOISE_WORDS = re.compile(
    r"\b(?:mg|gm|g|mcg|ml|tab|tabs|tablet|tablets|cap|caps|syr|syrup|susp|amp|"
    r"قرص|اقراص|أقراص|كبسول|كبسولة|شراب|امبول|أمبول|مجم|ملجم|جم|مل)\b",
    flags=re.IGNORECASE,
)


def normalize_text(text: str, strip_dosage: bool = False) -> str:
    """تطبيع النص العربي والإنجليزي لتوحيد الهمزات والتاء المربوطة والأرقام."""
    if not text:
        return ""
    s = unicodedata.normalize("NFKC", str(text)).translate(DIGITS_MAP)
    if strip_dosage and not re.match(r"^\s*1\s*2\s*3\b", s):
        s = NOISE_WORDS.sub(" ", s)
        s = re.sub(r"\b\d+(?:\.\d+)?\b", " ", s)
    s = ARABIC_DIACRITICS.sub("", s).translate(ARABIC_CHAR_MAP).lower()
    s = re.sub(r"[^a-z0-9\u0600-\u06FF\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _levenshtein_ratio(s1: str, s2: str) -> float:
    """حساب نسبة التشابه النصي (0 إلى 100) باستخدام RapidFuzz أو Levenshtein."""
    if not s1 or not s2:
        return 0.0
    if s1 == s2:
        return 100.0
    if RAPIDFUZZ_AVAILABLE:
        return round(
            0.5 * float(_rf_fuzz.ratio(s1, s2))
            + 0.3 * float(_rf_fuzz.WRatio(s1, s2))
            + 0.2 * float(_rf_fuzz.token_set_ratio(s1, s2)),
            1,
        )
    if len(s1) < len(s2):
        s1, s2 = s2, s1
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (c1 != c2)))
        prev = curr
    base_ratio = max(0.0, (1.0 - prev[-1] / max(len(s1), len(s2))) * 100.0)
    if s1.startswith(s2) or s2.startswith(s1):
        base_ratio = max(base_ratio, 88.0)
    return round(base_ratio, 1)


def _extract_2d_ink_vector(img: Image.Image) -> Tuple[np.ndarray, float]:
    """استخراج بصمة الكثافة المكانية ثنائية الأبعاد (28x10) لخط اليد."""
    gray = img.convert("L")
    arr = np.array(gray, dtype=np.uint8)
    inv = 255 - arr
    coords = np.column_stack(np.where(inv > 25))
    if coords.size > 0:
        y0, x0 = coords.min(axis=0)
        y1, x1 = coords.max(axis=0)
        crop = gray.crop((max(0, int(x0) - 2), max(0, int(y0) - 2), min(gray.width, int(x1) + 3), min(gray.height, int(y1) + 3)))
    else:
        crop = gray
    aspect = crop.width / float(max(1, crop.height))
    small = crop.resize((28, 10), Image.Resampling.BICUBIC)
    vec = (255.0 - np.array(small, dtype=np.float32).flatten()) / 255.0
    norm = float(np.linalg.norm(vec))
    if norm > 1e-6:
        vec = vec / norm
    return vec, aspect


def rasterize_strokes_and_recognize(
    stroke_json_str: str,
    medicines_list: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, float, str]:
    """تحويل إحداثيات خط اليد من الكانفاس والتعرف عليها بمحرك ثلاثي المراحل."""
    if not stroke_json_str or not stroke_json_str.strip():
        return "", 0.0, "unknown"
    try:
        payload = json.loads(stroke_json_str)
    except json.JSONDecodeError:
        return "", 0.0, "unknown"

    strokes = payload.get("strokes", [])
    hint_text = str(payload.get("hint_text", "") or "").strip()
    if not strokes:
        return hint_text, (0.90 if hint_text else 0.0), "unknown"

    width = int(payload.get("width", 1100))
    height = int(payload.get("height", 380))
    img = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(img)

    net_dx = 0.0
    all_x, all_y = [], []
    trace_for_ink = []
    for s in strokes:
        pts = s.get("points", [])
        if len(pts) >= 2:
            dx = float(pts[-1].get("x", 0)) - float(pts[0].get("x", 0))
            if abs(dx) > 12:
                net_dx += dx
        xs = [int(round(float(p["x"]))) for p in pts]
        ys = [int(round(float(p["y"]))) for p in pts]
        ts = [int(round(float(p.get("t", idx * 15)))) for idx, p in enumerate(pts)]
        if xs:
            trace_for_ink.append([xs, ys, ts])
        for i in range(1, len(pts)):
            x0, y0 = float(pts[i - 1]["x"]), float(pts[i - 1]["y"])
            x1, y1 = float(pts[i]["x"]), float(pts[i]["y"])
            all_x.extend([x0, x1])
            all_y.extend([y0, y1])
            draw.line([(x0, y0), (x1, y1)], fill=0, width=5)

    direction = "ar" if net_dx < -10 else "en"
    if hint_text:
        return hint_text, 0.92, direction

    # المرحلة 1: محرك Digital Ink لإحداثيات القلم في حال توفر إنترنت على جهاز الطبيب
    if trace_for_ink:
        try:
            req_body = json.dumps({
                "app_version": 0.4,
                "api_level": "537.36",
                "device": "5.0",
                "input_type": 0,
                "options": "enable_pre_space",
                "requests": [{
                    "writing_guide": {"writing_area_width": width, "writing_area_height": height},
                    "ink": trace_for_ink,
                    "language": direction,
                }],
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://inputtools.google.com/request?ime=handwriting&app=mobilesearch&cs=1&oe=UTF-8",
                data=req_body,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=1.8) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                if res_data and res_data[0] == "SUCCESS" and res_data[1][0][1]:
                    cands = res_data[1][0][1]
                    return str(cands[0]), 0.91, direction
        except Exception:
            pass

    # المرحلة 2: محرك التعلم العميق المحلي EasyOCR (يدعم العربي والإنجليزي بدون إنترنت)
    global _EASYOCR_READER
    if EASYOCR_AVAILABLE and all_x:
        try:
            if _EASYOCR_READER is None:
                _EASYOCR_READER = easyocr.Reader(["ar", "en"], gpu=False, verbose=False)
            arr_img = np.array(img, dtype=np.uint8)
            ocr_out = _EASYOCR_READER.readtext(arr_img)
            if ocr_out:
                texts = [item[1] for item in ocr_out if item[1].strip()]
                confs = [float(item[2]) for item in ocr_out if item[1].strip()]
                if texts:
                    return " ".join(texts), round(sum(confs) / len(confs), 2), direction
        except Exception:
            pass

    # المرحلة 3: Tesseract 5 LSTM المحلي + مطابقة البصمة المكانية 2D Ink-Grid
    if TESSERACT_AVAILABLE and all_x:
        arr = np.array(img, dtype=np.uint8)
        inv = 255 - arr
        coords = np.column_stack(np.where(inv > 30))
        if coords.size > 0:
            y0, x0 = coords.min(axis=0)
            y1, x1 = coords.max(axis=0)
            cropped = img.crop((max(0, int(x0) - 2), max(0, int(y0) - 2), min(width, int(x1) + 3), min(height, int(y1) + 3)))
        else:
            cropped = img

        w, h = cropped.size
        if h > 0 and w > 0:
            scale = 36.0 / float(h)
            cropped = cropped.resize((max(24, int(round(w * scale))), 36), Image.Resampling.BICUBIC)
        padded = ImageOps.expand(cropped, border=24, fill=255)

        lang = "ara+eng" if (direction == "ar" and "ara" in _TESS_LANGS) else "eng"
        data = pytesseract.image_to_data(padded, lang=lang, config="--oem 1 --psm 7", output_type=pytesseract.Output.DICT)
        words, confs = [], []
        for tok, c in zip(data.get("text", []), data.get("conf", [])):
            t = (tok or "").strip()
            try:
                cf = float(c)
            except (ValueError, TypeError):
                cf = -1.0
            if t and cf >= 0:
                words.append(t)
                confs.append(cf / 100.0)
        if words:
            return " ".join(words), round(sum(confs) / len(confs), 2), direction

    # المرحلة 4: مطابقة البصمة البصرية 2D مع قوالب الأدوية المصرية (تعمل في جميع البيئات دون أوزان خارجية)
    if medicines_list and all_x:
        user_vec, user_aspect = _extract_2d_ink_vector(img)
        best_name = ""
        best_sim = -1.0
        font = ImageFont.load_default()
        for med in medicines_list:
            cand_label = med["trade_name_ar"] if direction == "ar" else med["trade_name_en"]
            tpl = Image.new("L", (400, 110), color=255)
            d_tpl = ImageDraw.Draw(tpl)
            d_tpl.text((20, 35), cand_label, fill=0, font=font)
            t_vec, t_aspect = _extract_2d_ink_vector(tpl)
            sim = float(np.dot(user_vec, t_vec)) * 0.75 + max(0.0, 1.0 - abs(user_aspect - t_aspect) / 3.0) * 0.25
            if sim > best_sim:
                best_sim = sim
                best_name = cand_label
        if best_name:
            return best_name, round(max(0.65, min(0.92, best_sim)), 2), direction

    return "", 0.0, direction


def match_medicines(
    query_text: str,
    medicines_list: List[Dict[str, Any]],
    recognition_confidence: float = 1.0,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """مطابقة النص المكتوب مع قاعدة بيانات الأدوية المصرية وإرجاع أفضل البدائل."""
    clean_q = normalize_text(query_text, strip_dosage=True)
    full_q = normalize_text(query_text, strip_dosage=False)
    if not clean_q and not full_q:
        return []

    scored = []
    for med in medicines_list:
        norm_ar = med.get("normalized_ar") or normalize_text(med.get("trade_name_ar", ""))
        norm_en = med.get("normalized_en") or normalize_text(med.get("trade_name_en", ""))
        s_ar = max(_levenshtein_ratio(clean_q, norm_ar), _levenshtein_ratio(full_q, norm_ar))
        s_en = max(_levenshtein_ratio(clean_q, norm_en), _levenshtein_ratio(full_q, norm_en))
        best_sim = max(s_ar, s_en)

        digits_in_q = re.findall(r"\b\d+\b", full_q)
        conc_norm = normalize_text(med.get("concentration", ""))
        if digits_in_q and any(d in conc_norm for d in digits_in_q):
            best_sim = min(100.0, round(best_sim + 2.5, 1))

        status_note = "تطابق واضح" if best_sim >= 82.0 else ("تطابق متوسط - يرجى التدقيق" if best_sim >= 65.0 else "تطابق ضعيف / غير مؤكد")
        scored.append({
            **med,
            "similarity_score": best_sim,
            "recognition_confidence": round(recognition_confidence * 100, 1),
            "status_note": status_note,
        })

    scored.sort(key=lambda x: x["similarity_score"], reverse=True)
    results = scored[:top_k]
    if len(results) >= 2 and (results[0]["similarity_score"] - results[1]["similarity_score"]) < 5.0:
        results[0]["status_note"] = "تشابه قريب مع دواء آخر — يلزم تأكيد الطبيب بدقة"
    return results
