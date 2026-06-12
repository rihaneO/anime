import sqlite3
import logging
from datetime import datetime, date
from typing import Optional

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str = "neuro_shield.db") -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")  # Lecture concurrente sans verrou exclusif
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS acts_history (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    patient_name TEXT NOT NULL,
                    act_code    TEXT NOT NULL,
                    act_date    TEXT NOT NULL,
                    raw_text    TEXT,
                    created_at  TEXT DEFAULT (datetime('now'))
                )
            """)
            # Index pour accelérer les requêtes fréquentes
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_acts_patient_date
                ON acts_history (patient_name, act_date)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_acts_code
                ON acts_history (act_code)
            """)

    def save_report(
        self,
        patient_name: str,
        act_codes: list[str],
        act_date,
        raw_text: str,
    ) -> None:
        """
        Persiste une liste d'actes pour un patient.
        act_date accepte datetime.date ou string ISO 'YYYY-MM-DD'.
        """
        if not patient_name or not act_codes:
            return

        if isinstance(act_date, date):
            act_date_str = act_date.isoformat()
        else:
            # Valide et normalise le format
            datetime.strptime(str(act_date), "%Y-%m-%d")
            act_date_str = str(act_date)

        try:
            with self._connect() as conn:
                conn.executemany(
                    """
                    INSERT INTO acts_history (patient_name, act_code, act_date, raw_text)
                    VALUES (?, ?, ?, ?)
                    """,
                    [(patient_name, code, act_date_str, raw_text) for code in act_codes],
                )
        except sqlite3.Error as exc:
            logger.error("save_report failed: patient=%s date=%s — %s", patient_name, act_date_str, exc)
            raise

    def get_last_bilan_date(
        self,
        patient_name: str,
        bilan_codes: Optional[list[str]] = None,
    ) -> Optional[date]:
        """
        Retourne la date du dernier bilan pour ce patient.
        bilan_codes doit être fourni par le Checker via Referential — évite tout couplage dur
        à la nomenclature. Un fallback hardcodé est conservé uniquement pour compatibilité
        avec les appels directs (tests anciens, CLI).
        """
        if not bilan_codes:
            bilan_codes = ["AMO_20", "AMO_24", "AMO_30", "AMO_34.02"]

        placeholders = ",".join("?" * len(bilan_codes))
        query = f"""
            SELECT MAX(act_date)
            FROM acts_history
            WHERE patient_name = ?
              AND act_code IN ({placeholders})
        """

        try:
            with self._connect() as conn:
                row = conn.execute(query, [patient_name] + bilan_codes).fetchone()
        except sqlite3.Error as exc:
            logger.error("get_last_bilan_date failed: patient=%s — %s", patient_name, exc)
            raise

        if row and row[0]:
            return datetime.strptime(row[0], "%Y-%m-%d").date()
        return None

    def get_history(self, patient_name: str) -> list[tuple]:
        """Retourne tous les actes d'un patient, triés du plus récent au plus ancien."""
        try:
            with self._connect() as conn:
                return conn.execute(
                    """
                    SELECT act_code, act_date, raw_text
                    FROM acts_history
                    WHERE patient_name = ?
                    ORDER BY act_date DESC
                    """,
                    (patient_name,),
                ).fetchall()
        except sqlite3.Error as exc:
            logger.error("get_history failed: patient=%s — %s", patient_name, exc)
            raise
