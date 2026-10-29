"""تطبيق الروشتة الطبية الذكية المطور (Streamlit)
- ربط تلقائي فوري عبر React 18 Fiber (__reactProps$) بين لوحة خط اليد وحقل البحث في Streamlit:
  بمجرد كتابة اسم الدواء باليد (مثل Pandol extra)، تنتقل الكلمة تلقائياً لخانة البحث في Streamlit ويتم تفعيل البحث فوراً لتظهر الأدوية الصحيحة (بانادول إكسترا) بدلاً من الأدوية الافتراضية القديمة.
- إزالة الدواء الافتراضي الوهمي (أوجمنتين) عند كون خانة البحث فارغة.
- مساحة كتابة موسعة (1100x360) + إضافة للروشتة بضغطة زر واحدة + حفظ تلقائي في قاعدة البيانات ومجلد saved_prescriptions.
"""
from datetime import date
from pathlib import Path
import json
import streamlit as st
import streamlit.components.v1 as components

from database import ClinicDatabase
from matcher import match_medicines
from printer import build_prescription_html, save_prescription_files

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "clinic.db"
CSV_PATH = BASE_DIR / "data" / "medicines.csv"
SAVED_DIR = BASE_DIR / "saved_prescriptions"

st.set_page_config(page_title="نظام الروشتة الطبية الذكية المطور", layout="wide", initial_sidebar_state="expanded")

db = ClinicDatabase(DB_PATH, csv_seed_path=CSV_PATH)
all_medicines = db.get_all_medicines()

if "current_page" not in st.session_state:
    st.session_state.current_page = "home"
if "current_rx_items" not in st.session_state:
    st.session_state.current_rx_items = []
if "last_saved_rx_id" not in st.session_state:
    st.session_state.last_saved_rx_id = None

# ---------------------------------------------------------
# الشاشة الأولى: الصفحة الرئيسية وسجل الروشتات المحفوظة
# ---------------------------------------------------------
if st.session_state.current_page == "home":
    st.title("نظام الروشتة الطبية الذكية والتعرف المتقدم على خط اليد")
    st.markdown("مرحباً بك يا دكتور. اضغط على **(اكتب روشتة جديدة الآن)** للدخول إلى مساحة الكتابة الموسعة، أو استعرض سجل الروشتات المحفوظة.")

    col_start, col_stats = st.columns([1.2, 1.8])
    with col_start:
        if st.button("اكتب روشتة جديدة الآن", type="primary", use_container_width=True):
            st.session_state.current_rx_items = []
            st.session_state.last_saved_rx_id = None
            st.session_state.current_page = "write_rx"
            st.rerun()

    saved_list = db.list_saved_prescriptions()
    with col_stats:
        st.info(f"إجمالي الأدوية المسجلة بالقاعدة: **{len(all_medicines)} دواء** | إجمالي الروشتات المحفوظة: **{len(saved_list)} روشتة**")

    st.subheader("سجل الروشتات المحفوظة")
    if not saved_list:
        st.caption("لا توجد روشتات محفوظة بعد. اضغط على (اكتب روشتة جديدة الآن) لإنشاء أول روشتة.")
    else:
        for rx in saved_list:
            with st.expander(f"روشتة #{rx['prescription_id']} — المريض: {rx['patient_name']} ({rx['patient_age']}) — د. {rx['doctor_name']} — {rx['prescription_date']}"):
                rx_html = build_prescription_html(rx, rx["items"], prescription_id=rx["prescription_id"])
                components.html(rx_html, height=440, scrolling=True)

# ---------------------------------------------------------
# الشاشة الثانية: القائمة الجانبية + مساحة كتابة موسعة مرتبطة تلقائياً بالبحث + إضافة للروشتة
# ---------------------------------------------------------
else:
    with st.sidebar:
        st.header("1. البيانات الأساسية للروشتة")
        if st.button("العودة للصفحة الرئيسية وسجل الروشتات", use_container_width=True):
            st.session_state.current_page = "home"
            st.rerun()

        clinic_name = st.text_input("اسم العيادة / المركز الطبي", value="عيادة الشفاء التخصصية")
        clinic_address = st.text_input("عنوان وتليفون العيادة", value="طنطا - شارع البحر")
        doctor_name = st.text_input("اسم الدكتور", value="")
        doctor_specialty = st.text_input("التخصص الوظيفي", value="استشاري الباطنة العامة")
        doctor_reg_no = st.text_input("رقم القيد بالنقابة", value="")
        st.divider()
        patient_name = st.text_input("اسم المريض", value="")
        col_age, col_gen = st.columns(2)
        with col_age:
            patient_age = st.text_input("العمر / السن", value="")
        with col_gen:
            patient_gender = st.selectbox("النوع", ["ذكر", "أنثى"])
        prescription_date = st.text_input("تاريخ الروشتة", value=str(date.today()))
        diagnosis_notes = st.text_input("التشخيص المبدئي / ملاحظات", value="")

    metadata = {
        "clinic_name": clinic_name,
        "clinic_address": clinic_address,
        "doctor_name": doctor_name,
        "doctor_specialty": doctor_specialty,
        "doctor_reg_no": doctor_reg_no,
        "patient_name": patient_name,
        "patient_age": patient_age,
        "patient_gender": patient_gender,
        "prescription_date": prescription_date,
        "diagnosis_notes": diagnosis_notes,
    }

    st.title("كتابة الأدوية بخط اليد أو الكيبورد وإصدار الروشتة")

    st.subheader("2. مساحة كتابة الأدوية الموسعة (بخط اليد أو بالكيبورد)")
    input_mode = st.radio(
        "اختر طريقة إدخال اسم الدواء:",
        ["كتابة بخط اليد في المساحة الموسعة + تعديل بالكيبورد", "كتابة مباشرة بالكيبورد"],
        horizontal=True,
    )

    if input_mode.startswith("كتابة بخط اليد"):
        meds_json_str = json.dumps(
            [{"ar": m["trade_name_ar"], "en": m["trade_name_en"], "conc": m["concentration"]} for m in all_medicines],
            ensure_ascii=False,
        )
        LARGE_CANVAS_WIDGET = f"""
        <div dir="rtl" style="border:2px solid #0f4c5c;border-radius:14px;padding:14px;background:#fff;font-family:Tahoma,sans-serif;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;flex-wrap:wrap;gap:8px;">
            <span style="font-size:14px;font-weight:700;color:#0f4c5c;">مساحة الكتابة الموسعة للطبيب (1100x360) — يتعرف تلقائياً ويحدث قائمة الأدوية بالأسفل فوراً</span>
            <span id="stStatus" style="font-size:12px;background:#0f4c5c;color:#fff;padding:4px 12px;border-radius:99px;font-weight:700;">جاهز للكتابة</span>
          </div>
          <canvas id="medCanvas" width="1100" height="360"
            style="width:100%;height:360px;border:2px dashed #0f4c5c;border-radius:10px;background:#ffffff;touch-action:none;cursor:crosshair;display:block;"></canvas>
          <div style="display:flex;justify-content:space-between;align-items:center;margin-top:10px;flex-wrap:wrap;gap:8px;">
            <div style="display:flex;gap:8px;">
              <button type="button" id="undoBtn" style="padding:8px 14px;border-radius:8px;border:1px solid #475569;background:#f8fafc;cursor:pointer;font-weight:700;">تراجع عن آخر خط</button>
              <button type="button" id="clearBtn" style="padding:8px 14px;border-radius:8px;border:1px solid #b91c1c;color:#b91c1c;background:#fef2f2;cursor:pointer;font-weight:700;">مسح المساحة البيضاء</button>
            </div>
            <button type="button" id="recBtn" style="padding:8px 18px;border-radius:8px;border:none;background:#059669;color:#ffffff;cursor:pointer;font-weight:700;">
              تحويل خط اليد إلى نص الآن
            </button>
          </div>
          <div style="margin-top:10px;padding:10px;background:#f0fdfa;border:1px solid #99f6e4;border-radius:8px;font-size:13px;display:flex;align-items:center;flex-wrap:wrap;gap:6px;">
            <strong style="color:#0f172a;">قراءات خط اليد المقترحة (اضغط على أي قراءة لتحديث الأدوية بالأسفل):</strong>
            <div id="recPillsContainer" style="display:flex;flex-wrap:wrap;gap:6px;">
              <span style="color:#64748b;">اكتب بالماوس أو القلم ليظهر النص المقروء وينتقل لقائمة الأدوية بالأسفل تلقائياً...</span>
            </div>
          </div>
        </div>
        <script>
        (function(){{
          const MEDS_DB = {meds_json_str};
          const c = document.getElementById('medCanvas');
          const ctx = c.getContext('2d');
          const stEl = document.getElementById('stStatus');
          const pillsEl = document.getElementById('recPillsContainer');
          let strokes = [], cur = null, drawing = false, timer = null, t0 = performance.now();

          // دالة إرسال النص المقروء مباشرة إلى حقل البحث في Streamlit بالأسفل وتفعيل حدث Enter في React 18
          function pushTextToStreamlitSearch(word) {{
            if (!word) return;
            try {{
              const parentDoc = window.parent.document;
              const inputs = parentDoc.querySelectorAll('input[type="text"]');
              let targetInput = null;
              for (const inp of inputs) {{
                const aria = inp.getAttribute('aria-label') || '';
                const ph = inp.getAttribute('placeholder') || '';
                if (aria.includes('النص المتعرف عليه') || ph.includes('Pandol')) {{
                  targetInput = inp;
                  break;
                }}
              }}
              if (targetInput) {{
                targetInput.focus();
                const nativeSetter = Object.getOwnPropertyDescriptor(window.parent.HTMLInputElement.prototype, 'value').set;
                nativeSetter.call(targetInput, word);
                targetInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                targetInput.dispatchEvent(new Event('change', {{ bubbles: true }}));

                // استدعاء معالجات React 18 الداخلية مباشرة لضمان تحديث Streamlit الفوري
                const reactPropsKey = Object.keys(targetInput).find(k => k.startsWith('__reactProps$'));
                if (reactPropsKey && targetInput[reactPropsKey]) {{
                  const rp = targetInput[reactPropsKey];
                  if (typeof rp.onChange === 'function') {{
                    rp.onChange({{ target: targetInput, currentTarget: targetInput }});
                  }}
                  if (typeof rp.onKeyDown === 'function') {{
                    rp.onKeyDown({{
                      key: 'Enter', code: 'Enter', keyCode: 13, which: 13,
                      target: targetInput, currentTarget: targetInput,
                      preventDefault: function(){{}}, stopPropagation: function(){{}}
                    }});
                  }}
                  if (typeof rp.onBlur === 'function') {{
                    rp.onBlur({{ target: targetInput, currentTarget: targetInput }});
                  }}
                }}

                targetInput.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }}));
                targetInput.dispatchEvent(new KeyboardEvent('keypress', {{ key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }}));
                targetInput.dispatchEvent(new KeyboardEvent('keyup', {{ key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }}));
                targetInput.blur();
              }}
            }} catch (err) {{
              console.warn('Streamlit sync error:', err);
            }}
          }}

          function renderSuggestionButtons(words) {{
            pillsEl.innerHTML = '';
            words.forEach((w, idx) => {{
              const b = document.createElement('button');
              b.type = 'button';
              b.textContent = (idx === 0 ? '★ ' : '') + w;
              b.style.cssText = idx === 0
                ? 'padding:5px 12px;border-radius:6px;border:none;background:#0f4c5c;color:#fff;font-weight:700;cursor:pointer;'
                : 'padding:5px 10px;border-radius:6px;border:1px solid #0f4c5c;background:#fff;color:#0f4c5c;font-weight:700;cursor:pointer;';
              b.onclick = () => {{
                stEl.textContent = 'تم اختيار: ' + w;
                pushTextToStreamlitSearch(w);
              }};
              pillsEl.appendChild(b);
            }});
          }}

          function redraw(){{
            ctx.fillStyle = '#fff'; ctx.fillRect(0,0,c.width,c.height);
            ctx.strokeStyle = '#e2e8f0'; ctx.lineWidth = 1.5;
            [125, 235, 325].forEach(y => {{ ctx.beginPath(); ctx.moveTo(24, y); ctx.lineTo(c.width-24, y); ctx.stroke(); }});
            ctx.strokeStyle = '#0f172a'; ctx.lineWidth = 5; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
            for(const s of strokes){{
              for(let i=1;i<s.points.length;i++){{
                ctx.beginPath(); ctx.moveTo(s.points[i-1].x, s.points[i-1].y); ctx.lineTo(s.points[i].x, s.points[i].y); ctx.stroke();
              }}
            }}
          }}

          async function recognizeInk(){{
            if(!strokes.length) return;
            let netDx = 0;
            strokes.forEach(s => {{ if(s.points.length>=2) netDx += (s.points[s.points.length-1].x - s.points[0].x); }});
            const lang = netDx < -8 ? 'ar' : 'en';
            stEl.textContent = 'جاري التعرف على الخط (' + (lang==='ar'?'عربي':'إنجليزي') + ')...';
            const trace = strokes.map(s => [s.points.map(p=>Math.round(p.x)), s.points.map(p=>Math.round(p.y)), s.points.map(p=>Math.round(p.t))]);
            try {{
              const r = await fetch('https://inputtools.google.com/request?ime=handwriting&app=mobilesearch&cs=1&oe=UTF-8', {{
                method: 'POST', headers: {{'Content-Type':'application/json'}},
                body: JSON.stringify({{app_version:0.4, api_level:'537.36', input_type:0, options:'enable_pre_space', requests:[{{writing_guide:{{writing_area_width:c.width, writing_area_height:c.height}}, ink:trace, language:lang}}]}})
              }});
              const d = await r.json();
              if(d && d[0]==='SUCCESS' && d[1][0][1]){{
                const words = d[1][0][1].slice(0,5);
                renderSuggestionButtons(words);
                stEl.textContent = 'تم التعرف: ' + words[0];
                pushTextToStreamlitSearch(words[0]);
                return;
              }}
            }} catch(e){{}}
            stEl.textContent = 'تم التقاط الخط (' + strokes.length + ' خطوط)';
          }}

          c.addEventListener('pointerdown', e => {{
            if(timer) clearTimeout(timer);
            const r = c.getBoundingClientRect();
            drawing = true;
            cur = {{points:[{{x:(e.clientX-r.left)*(c.width/r.width), y:(e.clientY-r.top)*(c.height/r.height), t:performance.now()-t0}}]}};
            strokes.push(cur); redraw();
          }});
          c.addEventListener('pointermove', e => {{
            if(!drawing || !cur) return;
            const r = c.getBoundingClientRect();
            cur.points.push({{x:(e.clientX-r.left)*(c.width/r.width), y:(e.clientY-r.top)*(c.height/r.height), t:performance.now()-t0}});
            redraw();
          }});
          c.addEventListener('pointerup', () => {{
            drawing = false; cur = null;
            timer = setTimeout(recognizeInk, 850);
          }});
          document.getElementById('undoBtn').onclick = () => {{ strokes.pop(); redraw(); if(strokes.length) recognizeInk(); }};
          document.getElementById('clearBtn').onclick = () => {{
            if(timer) clearTimeout(timer);
            strokes = [];
            pillsEl.innerHTML = '<span style="color:#64748b;">تم مسح اللوحة — اكتب اسم الدواء الجديد...</span>';
            stEl.textContent = 'جاهز للكتابة';
            redraw();
          }};
          document.getElementById('recBtn').onclick = recognizeInk;
          redraw();
        }})();
        </script>
        """
        components.html(LARGE_CANVAS_WIDGET, height=510)

    col_work, col_preview = st.columns([1.15, 1.0])

    with col_work:
        query_input = st.text_input(
            "النص المتعرف عليه / اكتب أو عدّل اسم الدواء بالكيبورد مباشرة (عربي أو إنجليزي):",
            placeholder="مثال: Pandol extra أو أوجمنتين 1000 أو كونترولوك...",
        )

        st.subheader("3. مقارنة الأدوية وإضافتها للروشتة بضغطة واحدة")
        d_col1, d_col2, d_col3, d_col4 = st.columns(4)
        with d_col1:
            dose_val = st.text_input("الجرعة", value="قرص واحد")
        with d_col2:
            freq_val = st.text_input("التكرار", value="كل 12 ساعة")
        with d_col3:
            dur_val = st.text_input("المدة", value="7 أيام")
        with d_col4:
            instr_val = st.text_input("التعليمات", value="بعد الأكل")

        if not query_input.strip():
            st.info("بمجرد كتابة اسم الدواء بخط يدك في اللوحة بالأعلى، سينتقل الاسم تلقائياً لخانة البحث وتظهر الأدوية المطابقة له هنا فوراً.")
        else:
            candidates = match_medicines(
                query_input.strip(),
                all_medicines,
                recognition_confidence=0.92,
                top_k=5,
            )

            for idx, cand in enumerate(candidates):
                row_c1, row_c2 = st.columns([3.5, 1.3])
                with row_c1:
                    st.markdown(
                        f"**{idx+1}. {cand['trade_name_ar']} ({cand['trade_name_en']})** — `{cand['concentration']}` "
                        f"[{cand['dosage_form']}] | تشابه: **{cand['similarity_score']}%**"
                    )
                with row_c2:
                    if st.button("+ أضف للروشتة فوراً", key=f"quick_add_{cand['medicine_id']}", type="primary" if idx == 0 else "secondary", use_container_width=True):
                        st.session_state.current_rx_items.append({
                            "medicine_id": cand["medicine_id"],
                            "medicine_name": f"{cand['trade_name_en']} ({cand['trade_name_ar']})",
                            "concentration": cand["concentration"],
                            "dosage_form": cand["dosage_form"],
                            "dose": dose_val.strip() or "قرص واحد",
                            "frequency": freq_val.strip() or "كل 12 ساعة",
                            "duration": dur_val.strip() or "7 أيام",
                            "route": cand["dosage_form"],
                            "instructions": instr_val.strip() or "بعد الأكل",
                            "original_input_text": query_input.strip(),
                            "similarity_score": cand["similarity_score"],
                            "doctor_confirmed": True,
                        })
                        st.success(f"تمت إضافة {cand['trade_name_ar']} ({cand['trade_name_en']}) إلى الروشتة بنجاح!")
                        st.rerun()

    with col_preview:
        st.subheader("4. معاينة الروشتة وحفظها وطباعتها (A4)")
        if st.session_state.current_rx_items:
            for idx, item in enumerate(list(st.session_state.current_rx_items)):
                r_col1, r_col2 = st.columns([4, 1])
                with r_col1:
                    st.markdown(f"**{idx+1}. {item['medicine_name']}** — `{item['dose']}` | `{item['frequency']}` | `{item['duration']}`")
                with r_col2:
                    if st.button("حذف", key=f"del_it_{idx}"):
                        st.session_state.current_rx_items.pop(idx)
                        st.rerun()

            if st.button("حفظ الروشتة وإعدادها للطباعة النهائية (A4)", type="primary", use_container_width=True):
                rx_id = db.save_prescription(metadata, st.session_state.current_rx_items)
                html_p, pdf_p = save_prescription_files(SAVED_DIR, rx_id, metadata, st.session_state.current_rx_items)
                db.update_prescription_files(rx_id, str(html_p), str(pdf_p))
                st.session_state.last_saved_rx_id = rx_id
                st.success(f"تم حفظ الروشتة رقم #{rx_id} تلقائياً في قاعدة البيانات وفي مجلد saved_prescriptions!")

        preview_html = build_prescription_html(
            metadata,
            st.session_state.current_rx_items,
            prescription_id=st.session_state.last_saved_rx_id or 0,
        )
        components.html(preview_html, height=580, scrolling=True)
