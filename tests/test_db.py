import pytest
from datetime import date
from src.db import Database


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))

BILAN_CODES = ['AMO_20', 'AMO_24', 'AMO_30', 'AMO_34.02']

def test_save_and_retrieve(db):
    patient = "Thomas"
    db.save_report(patient, ['AMO_34.02'], date(2025, 1, 1), "Raw text")

    last_date = db.get_last_bilan_date(patient, BILAN_CODES)
    assert last_date == date(2025, 1, 1)

    # Add a newer one
    db.save_report(patient, ['AMO_20'], date(2026, 1, 1), "Raw text 2")
    last_date = db.get_last_bilan_date(patient, BILAN_CODES)
    assert last_date == date(2026, 1, 1)

def test_non_bilan_ignored(db):
    patient = "Thomas"
    # AMO_13.5 = reeducation, pas un bilan
    db.save_report(patient, ['AMO_13.5'], date(2026, 1, 1), "Raw text")

    last_date = db.get_last_bilan_date(patient, BILAN_CODES)
    assert last_date is None

def test_history(db):
    patient = "Jules"
    db.save_report(patient, ['AMO_34.02'], date(2025, 1, 1), "Text 1")
    db.save_report(patient, ['AMO_13.5'], date(2025, 2, 1), "Text 2")

    history = db.get_history(patient)
    assert len(history) == 2
    assert history[0][0] == 'AMO_13.5'  # Ordered by date DESC


def test_sql_injection_safe(db):
    """Patient names with SQL metacharacters must not corrupt the DB."""
    evil = "Robert'); DROP TABLE acts_history; --"
    db.save_report(evil, ['AMO_34.02'], date(2026, 1, 1), "text")
    assert db.get_last_bilan_date(evil, BILAN_CODES) == date(2026, 1, 1)
    # DB must still be intact
    assert db.get_history(evil) != []


def test_empty_patient_noop(db):
    db.save_report("", ['AMO_34.02'], date(2026, 1, 1), "text")
    assert db.get_history("") == []


def test_act_date_as_string(db):
    db.save_report("Marie", ['AMO_24'], "2025-06-01", "text")
    assert db.get_last_bilan_date("Marie", BILAN_CODES) == date(2025, 6, 1)


def test_multi_patient_isolation(db):
    db.save_report("Alice", ['AMO_34.02'], date(2026, 1, 1), "a")
    db.save_report("Bob", ['AMO_20'], date(2025, 1, 1), "b")
    assert db.get_last_bilan_date("Alice", BILAN_CODES) == date(2026, 1, 1)
    assert db.get_last_bilan_date("Bob", BILAN_CODES) == date(2025, 1, 1)
    assert db.get_last_bilan_date("Charlie", BILAN_CODES) is None
