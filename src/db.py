import sqlite3
import os
from datetime import datetime

class Database:
    def __init__(self, db_path='neuro_shield.db'):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS acts_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_name TEXT NOT NULL,
                act_code TEXT NOT NULL,
                act_date DATE NOT NULL,
                raw_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()

    def save_report(self, patient_name, act_codes, act_date, raw_text):
        """
        Saves the extracted acts to the history.
        act_codes: list of strings (e.g. ['AMO_34', 'AMO_13.5'])
        act_date: datetime.date object
        """
        if not patient_name or not act_codes:
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        for code in act_codes:
            cursor.execute('''
                INSERT INTO acts_history (patient_name, act_code, act_date, raw_text)
                VALUES (?, ?, ?, ?)
            ''', (patient_name, code, act_date, raw_text))

        conn.commit()
        conn.close()

    def get_last_bilan_date(self, patient_name):
        """
        Returns the date of the last bilan for the patient.
        We assume 'bilan' codes are known or we query for specific codes.
        To be robust, we should probably check against a list of known bilan codes.
        However, if we don't want to couple DB with Rules too tightly here,
        we can fetch all acts for patient and filter, or just query for codes starting with 'AMO_34', 'AMO_30', 'AMO_20' etc.

        But the cleanest way is:
        SELECT MAX(act_date) FROM acts_history WHERE patient_name = ? AND act_code IN (...)

        For MVP, I will hardcode common Bilan codes or make it generic.
        Let's look at rules.json content provided: AMO_20, AMO_34 are 'bilan'.
        I will query for these.
        """
        # Ideally this list comes from rules.json.
        # But for DB class, let's keep it simple or allow passing codes.
        # But Checker calls `db.get_last_bilan_date(patient_id)`.
        # I'll update Checker to pass the list of bilan codes?
        # Or I'll just check "AMO_34", "AMO_30", "AMO_20", "AMO_24" etc.
        # Let's try to query all acts for patient and filter in python? No, SQL is better.

        # Let's assume we want any act that IS a bilan.
        # I'll hardcode the list of Bilan codes from the spec for now.
        bilan_codes = ['AMO_20', 'AMO_34', 'AMO_30', 'AMO_24', 'AMO_22'] # Expanded list based on typical NGAP, but strict to MVP.

        placeholders = ','.join(['?'] * len(bilan_codes))
        query = f'''
            SELECT MAX(act_date)
            FROM acts_history
            WHERE patient_name = ?
            AND act_code IN ({placeholders})
        '''

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(query, [patient_name] + bilan_codes)
        result = cursor.fetchone()
        conn.close()

        if result and result[0]:
            # SQLite stores dates as strings usually 'YYYY-MM-DD'
            return datetime.strptime(result[0], '%Y-%m-%d').date()
        return None

    def get_history(self, patient_name):
        """
        Returns all history for a patient.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT act_code, act_date, raw_text
            FROM acts_history
            WHERE patient_name = ?
            ORDER BY act_date DESC
        ''', (patient_name,))
        rows = cursor.fetchall()
        conn.close()
        return rows
