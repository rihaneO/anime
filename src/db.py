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

    def get_last_bilan_date(self, patient_name, bilan_codes=None):
        """
        Retourne la date du dernier bilan du patient.

        `bilan_codes` est fourni par le Checker a partir du referentiel
        (rules.json), ce qui evite tout couplage en dur entre la base et la
        nomenclature : quand un avenant ajoute un code de bilan, rien a
        changer ici. Une liste de repli est utilisee si rien n'est passe.
        """
        if not bilan_codes:
            bilan_codes = ['AMO_20', 'AMO_24', 'AMO_30', 'AMO_34.02']

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
