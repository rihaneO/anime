import pytest
import os
from datetime import date
from src.db import Database

@pytest.fixture
def db():
    db_path = 'test_neuro_shield.db'
    if os.path.exists(db_path):
        os.remove(db_path)
    db = Database(db_path)
    yield db
    if os.path.exists(db_path):
        os.remove(db_path)

def test_save_and_retrieve(db):
    patient = "Thomas"
    db.save_report(patient, ['AMO_34'], date(2025, 1, 1), "Raw text")

    last_date = db.get_last_bilan_date(patient)
    assert last_date == date(2025, 1, 1)

    # Add a newer one
    db.save_report(patient, ['AMO_20'], date(2026, 1, 1), "Raw text 2")
    last_date = db.get_last_bilan_date(patient)
    assert last_date == date(2026, 1, 1)

def test_non_bilan_ignored(db):
    patient = "Thomas"
    # AMO_13.5 is reeducation, not bilan (in my hardcoded list)
    db.save_report(patient, ['AMO_13.5'], date(2026, 1, 1), "Raw text")

    last_date = db.get_last_bilan_date(patient)
    assert last_date is None

def test_history(db):
    patient = "Jules"
    db.save_report(patient, ['AMO_34'], date(2025, 1, 1), "Text 1")
    db.save_report(patient, ['AMO_13.5'], date(2025, 2, 1), "Text 2")

    history = db.get_history(patient)
    assert len(history) == 2
    assert history[0][0] == 'AMO_13.5' # Ordered by date DESC
