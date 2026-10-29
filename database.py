"""إدارة قاعدة البيانات المحلية (SQLite): جدول الأدوية المصرية + حفظ واسترجاع الروشتات."""
import hashlib
import shutil
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Iterator
import pandas as pd

from matcher import normalize_text

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS medicines (
    medicine_id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_name_ar TEXT NOT NULL,
    trade_name_en TEXT NOT NULL,
    active_ingredient TEXT DEFAULT '',
    dosage_form TEXT DEFAULT '',
    concentration TEXT DEFAULT '',
    manufacturer TEXT DEFAULT '',
    price_egp REAL DEFAULT 0.0,
    normalized_ar TEXT NOT NULL,
    normalized_en TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prescriptions (
    prescription_id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    clinic_name TEXT NOT NULL,
    clinic_address TEXT DEFAULT '',
    doctor_name TEXT NOT NULL,
    doctor_specialty TEXT DEFAULT '',
    doctor_reg_no TEXT DEFAULT '',
    patient_name TEXT NOT NULL,
    patient_age TEXT DEFAULT '',
    patient_gender TEXT DEFAULT '',
    prescription_date TEXT NOT NULL,
    diagnosis_notes TEXT DEFAULT '',
    saved_html_path TEXT DEFAULT '',
    saved_pdf_path TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS prescription_items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    prescription_id INTEGER NOT NULL,
    medicine_id INTEGER,
    medicine_name TEXT NOT NULL,
    concentration TEXT DEFAULT '',
    dosage_form TEXT DEFAULT '',
    dose TEXT NOT NULL,
    frequency TEXT NOT NULL,
    duration TEXT NOT NULL,
    route TEXT DEFAULT '',
    instructions TEXT DEFAULT '',
    original_input_text TEXT DEFAULT '',
    similarity_score REAL DEFAULT 0.0,
    doctor_confirmed INTEGER DEFAULT 1,
    FOREIGN KEY(prescription_id) REFERENCES prescriptions(prescription_id)
);
"""


class ClinicDatabase:
    """واجهة التعامل مع قاعدة بيانات العيادة (الأدوية والروشتات المحفوظة)."""

    def __init__(self, db_path: Path, csv_seed_path: Optional[Path] = None):
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        path_hash = hashlib.md5(str(self.db_path).encode("utf-8")).hexdigest()[:10]
        self._staging_path = Path(tempfile.gettempdir()) / f"clinic_db_{path_hash}.sqlite"
        self._use_staging = str(self.db_path).startswith("/working_dir")
        self._init_db()
        if csv_seed_path and Path(csv_seed_path).exists() and self.count_medicines() == 0:
            self.import_medicines_csv(Path(csv_seed_path))

    @contextmanager
    def _conn(self, write: bool = False) -> Iterator[sqlite3.Connection]:
        target = self._staging_path if self._use_staging else self.db_path
        if self._use_staging and self.db_path.exists() and not self._staging_path.exists():
            shutil.copyfile(self.db_path, self._staging_path)
        conn = sqlite3.connect(str(target))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            if write:
                conn.commit()
        finally:
            conn.close()
            if write and self._use_staging and self._staging_path.exists():
                shutil.copyfile(self._staging_path, self.db_path)

    def _init_db(self) -> None:
        if not self._use_staging:
            try:
                conn = sqlite3.connect(str(self.db_path))
                conn.executescript(SCHEMA_SQL)
                conn.commit()
                conn.close()
                return
            except sqlite3.OperationalError:
                self._use_staging = True
        with self._conn(write=True) as conn:
            conn.executescript(SCHEMA_SQL)

    def count_medicines(self) -> int:
        with self._conn(write=False) as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM medicines").fetchone()
            return int(row["c"]) if row else 0

    def import_medicines_csv(self, csv_path: Path) -> int:
        df = pd.read_csv(csv_path, encoding="utf-8", dtype=str).fillna("")
        count = 0
        with self._conn(write=True) as conn:
            conn.execute("DELETE FROM medicines")
            for _, r in df.iterrows():
                ar = str(r.get("trade_name_ar", "")).strip()
                en = str(r.get("trade_name_en", "")).strip()
                if not ar and not en:
                    continue
                try:
                    price = float(str(r.get("price_egp", "0")).strip() or 0.0)
                except ValueError:
                    price = 0.0
                conn.execute(
                    """
                    INSERT INTO medicines (
                        medicine_id, trade_name_ar, trade_name_en, active_ingredient,
                        dosage_form, concentration, manufacturer, price_egp,
                        normalized_ar, normalized_en
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(r["medicine_id"]) if str(r.get("medicine_id", "")).isdigit() else None,
                        ar,
                        en,
                        str(r.get("active_ingredient", "")).strip(),
                        str(r.get("dosage_form", "")).strip(),
                        str(r.get("concentration", "")).strip(),
                        str(r.get("manufacturer", "")).strip(),
                        price,
                        normalize_text(ar),
                        normalize_text(en),
                    ),
                )
                count += 1
        return count

    def get_all_medicines(self) -> List[Dict[str, Any]]:
        with self._conn(write=False) as conn:
            rows = conn.execute("SELECT * FROM medicines ORDER BY medicine_id ASC").fetchall()
            return [dict(r) for r in rows]

    def save_prescription(
        self,
        metadata: Dict[str, str],
        items: List[Dict[str, Any]],
        saved_html_path: str = "",
        saved_pdf_path: str = "",
    ) -> int:
        """حفظ الروشتة وجميع أدويتها في قاعدة البيانات وإرجاع رقم الروشتة."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._conn(write=True) as conn:
            cur = conn.execute(
                """
                INSERT INTO prescriptions (
                    created_at, clinic_name, clinic_address, doctor_name,
                    doctor_specialty, doctor_reg_no, patient_name, patient_age,
                    patient_gender, prescription_date, diagnosis_notes,
                    saved_html_path, saved_pdf_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now_str,
                    metadata.get("clinic_name", "عيادة طبية تخصصية").strip(),
                    metadata.get("clinic_address", "").strip(),
                    metadata.get("doctor_name", "").strip(),
                    metadata.get("doctor_specialty", "").strip(),
                    metadata.get("doctor_reg_no", "").strip(),
                    metadata.get("patient_name", "").strip(),
                    metadata.get("patient_age", "").strip(),
                    metadata.get("patient_gender", "").strip(),
                    metadata.get("prescription_date", now_str[:10]).strip(),
                    metadata.get("diagnosis_notes", "").strip(),
                    saved_html_path,
                    saved_pdf_path,
                ),
            )
            rx_id = int(cur.lastrowid)
            for item in items:
                conn.execute(
                    """
                    INSERT INTO prescription_items (
                        prescription_id, medicine_id, medicine_name, concentration,
                        dosage_form, dose, frequency, duration, route,
                        instructions, original_input_text, similarity_score, doctor_confirmed
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rx_id,
                        item.get("medicine_id"),
                        item.get("medicine_name", ""),
                        item.get("concentration", ""),
                        item.get("dosage_form", ""),
                        item.get("dose", ""),
                        item.get("frequency", ""),
                        item.get("duration", ""),
                        item.get("route", ""),
                        item.get("instructions", ""),
                        item.get("original_input_text", ""),
                        float(item.get("similarity_score", 0.0)),
                        1 if item.get("doctor_confirmed", True) else 0,
                    ),
                )
            return rx_id

    def update_prescription_files(self, rx_id: int, html_path: str, pdf_path: str) -> None:
        with self._conn(write=True) as conn:
            conn.execute(
                "UPDATE prescriptions SET saved_html_path = ?, saved_pdf_path = ? WHERE prescription_id = ?",
                (html_path, pdf_path, rx_id),
            )

    def list_saved_prescriptions(self) -> List[Dict[str, Any]]:
        """استرجاع جميع الروشتات المحفوظة مع الأدوية الخاصة بكل روشتة."""
        with self._conn(write=False) as conn:
            rx_rows = conn.execute(
                "SELECT * FROM prescriptions ORDER BY prescription_id DESC"
            ).fetchall()
            result = []
            for r in rx_rows:
                rx_dict = dict(r)
                items = conn.execute(
                    "SELECT * FROM prescription_items WHERE prescription_id = ? ORDER BY item_id ASC",
                    (rx_dict["prescription_id"],),
                ).fetchall()
                rx_dict["items"] = [dict(it) for it in items]
                result.append(rx_dict)
            return result
