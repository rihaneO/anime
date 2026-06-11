import pytest
import os
from datetime import date
from src.db import Database
from src.checker import Checker
from src.audit import build_patient_report

BILAN_CODES = ["AMO_20", "AMO_24", "AMO_30", "AMO_34.02"]


@pytest.fixture
def db(tmp_path):
    d = Database(str(tmp_path / "test.db"))
    yield d


@pytest.fixture
def checker(db):
    # Le checker doit avoir la DB pour que RT1 consulte l'historique.
    return Checker(rules_path="rules.json", db=db)


def test_normalize_alias(checker):
    # "AMO 34" produit "AMO_34" — doit se resoudre en "AMO_34.02"
    assert checker.normalize_codes(["AMO_34"]) == ["AMO_34.02"]
    assert checker.normalize_codes(["AMO_13.5"]) == ["AMO_13.5"]
    assert checker.normalize_codes(["AMO_20"]) == ["AMO_20"]
    # Code inconnu passe tel quel (sans crash)
    assert checker.normalize_codes(["AMO_999"]) == ["AMO_999"]


def test_r16_via_normalized_codes(checker):
    # Le bug original : "AMO_34" (non resolu) + "AMO_13.5" ne declenchait pas R16
    # Apres normalisation, il doit se declencher.
    codes = checker.normalize_codes(["AMO_34", "AMO_13.5"])
    assert "AMO_34.02" in codes
    parsed = {"codes": codes, "date": date(2026, 3, 1), "age_months": 60}
    results = checker.check(parsed)
    assert any(r["id"] == "R16" for r in results), "R16 doit se declencher apres normalisation"


def test_audit_empty_history(db, checker):
    report = build_patient_report("Inconnu", db, checker)
    assert report.total_acts == 0
    assert len(report.risks) == 0
    assert report.risk_score == 0


def test_audit_detects_doublon(db, checker):
    db.save_report("Thomas", ["AMO_34.02"], date(2026, 3, 1), "note 1")
    db.save_report("Thomas", ["AMO_34.02"], date(2026, 3, 1), "note 2")  # doublon
    report = build_patient_report("Thomas", db, checker)
    assert any(r.rule_id == "DOUBLON" for r in report.risks)
    assert any(r.severity == "BLOCKING" for r in report.risks)


def test_audit_detects_rt1_in_history(db, checker):
    # Premier bilan
    db.save_report("Marie", ["AMO_34.02"], date(2025, 6, 1), "bilan 1")
    # Renouvellement < 12 mois
    db.save_report("Marie", ["AMO_34.02"], date(2025, 10, 1), "bilan 2")
    report = build_patient_report("Marie", db, checker)
    assert any(r.rule_id == "RT1" for r in report.risks)


def test_audit_clean_history(db, checker):
    # Un seul bilan suivi d'une seance plusieurs jours apres = conforme
    db.save_report("Claire", ["AMO_34.02"], date(2025, 1, 1), "bilan")
    db.save_report("Claire", ["AMO_13.5"], date(2025, 1, 8), "seance")
    report = build_patient_report("Claire", db, checker)
    blocking = [r for r in report.risks if r.severity == "BLOCKING"]
    assert len(blocking) == 0
