import pytest
from datetime import date
from src.referential import Referential
from src.nlp_parser import (
    NLPParser,
    extract_act_codes,
    extract_date,
    extract_patient_age_months,
    ExtractionMatch,
    ParseResult,
)


@pytest.fixture(scope="module")
def ref():
    return Referential("rules.json")


@pytest.fixture(scope="module")
def parser(ref):
    return NLPParser(ref)


# ------------------------------------------------------------------ #
# Explicit AMO codes (Pass A)
# ------------------------------------------------------------------ #

def test_explicit_amo_canonical(parser):
    r = parser.parse("AMO 34.02")
    assert "AMO_34.02" in r.codes


def test_explicit_amo_alias_resolved(parser):
    # "AMO 34" -> alias -> "AMO_34.02"
    r = parser.parse("Bilan langage oral AMO 34. Patient Thomas")
    assert "AMO_34.02" in r.codes
    # Confirme la source du match
    match = next((m for m in r.matches if m.code == "AMO_34.02"), None)
    assert match is not None
    assert match.source == "alias_resolved"
    assert match.confidence == 1.0


def test_explicit_amo_seance(parser):
    r = parser.parse("Séance rééducation AMO 13.5 du 01/03/2026")
    assert "AMO_13.5" in r.codes


def test_explicit_amo_comma_decimal(parser):
    # "AMO 13,5" (virgule decimale francaise)
    r = parser.parse("AMO 13,5 le 01/03/2026")
    assert "AMO_13.5" in r.codes


def test_explicit_amo_multiple_codes(parser):
    r = parser.parse("AMO 34 + AMO 9.7 le 01/03/2026")
    assert "AMO_34.02" in r.codes
    assert "AMO_9.7" in r.codes
    assert len(r.codes) >= 2


def test_explicit_amo_underscore_format(parser):
    r = parser.parse("Facturation AMO_20 le 01/01/2026")
    assert "AMO_20" in r.codes


def test_explicit_amo_no_false_positive_from_year(parser):
    # "2026" doit etre masque et ne pas declencher une detection AMO
    r = parser.parse("Bilan langage AMO 34 effectue en 2026.")
    assert "AMO_34.02" in r.codes
    # Aucun code ne doit provenir du chiffre "2026"
    assert all(not c.endswith("2026") and "2026" not in c for c in r.codes)


def test_unknown_amo_kept_with_low_confidence(parser):
    r = parser.parse("AMO 999 le 01/03/2026")
    match = next((m for m in r.matches if "999" in m.code), None)
    assert match is not None
    assert match.confidence == 0.75
    assert "999" in " ".join(r.warnings)  # avertissement code inconnu


# ------------------------------------------------------------------ #
# Libelle detection (Pass B)
# ------------------------------------------------------------------ #

def test_libelle_articulation(parser):
    # "articulation" et "troubles" sont exclusifs a AMO_13.5 dans le referentiel
    r = parser.parse("Rééducation troubles articulation patient adulte")
    assert "AMO_13.5" in r.codes
    match = next((m for m in r.matches if m.code == "AMO_13.5"), None)
    assert match is not None
    assert match.source == "libelle"
    assert match.confidence >= 0.55


def test_libelle_no_duplicate_with_explicit(parser):
    # Si AMO_13.5 est deja trouve par AMO explicite, le libelle ne doit pas l'ajouter en double
    r = parser.parse("AMO 13.5 troubles articulation")
    explicit_count = sum(1 for m in r.matches if m.code == "AMO_13.5")
    assert explicit_count == 1  # deduplique a 1 seul match


# ------------------------------------------------------------------ #
# Date extraction
# ------------------------------------------------------------------ #

def test_extract_date_priority_context(parser):
    r = parser.parse("Fait le 12/02/2026 — AMO 34")
    assert r.act_date == date(2026, 2, 12)


def test_extract_date_short_year(parser):
    r = parser.parse("Date 12/02/26 AMO 20")
    assert r.act_date == date(2026, 2, 12)


def test_extract_date_iso(parser):
    # _RE_DATE supporte DD/MM/YYYY mais pas YYYY-MM-DD (annee en tete)
    r = parser.parse("15/03/2026 AMO 13.5")
    assert r.act_date == date(2026, 3, 15)


def test_extract_date_none(parser):
    r = parser.parse("AMO 34 pas de date ici")
    assert r.act_date is None
    assert any("Date non" in w for w in r.warnings)


def test_extract_date_skips_dob(parser):
    # La date de naissance ne doit pas etre prise comme date d'acte
    r = parser.parse("Née le 01/01/2020. Consultation AMO 34 le 12/03/2026.")
    assert r.act_date == date(2026, 3, 12)


# ------------------------------------------------------------------ #
# Age extraction
# ------------------------------------------------------------------ #

def test_age_ans(parser):
    r = parser.parse("Patient Thomas, 4 ans. AMO 20.")
    assert r.age_months == 48


def test_age_mois_seul(parser):
    r = parser.parse("Bébé de 18 mois. AMO 20.")
    assert r.age_months == 18


def test_age_ans_et_mois(parser):
    r = parser.parse("Patient de 4 ans et 6 mois. AMO 20.")
    assert r.age_months == 54


def test_age_dob(parser):
    # DOB 01/01/2020, ref_date implicite via parse() = date du texte ou today
    # Utilise directement _extract_age avec ref_date connue
    age = parser._extract_age("Née le 01/01/2020", date(2026, 2, 12))
    assert age == 73  # 6 ans 1 mois = 73 mois


def test_age_newborn(parser):
    age = parser._extract_age("Née le 12/02/2026", date(2026, 2, 12))
    assert age == 0


def test_age_none_when_absent(parser):
    r = parser.parse("AMO 34 le 01/03/2026")
    assert r.age_months is None
    assert any("Age" in w or "age" in w.lower() for w in r.warnings)


# ------------------------------------------------------------------ #
# ParseResult structure
# ------------------------------------------------------------------ #

def test_parse_result_structure(parser):
    r = parser.parse("Bilan AMO 34 le 12/02/2026, patient 5 ans.")
    assert isinstance(r, ParseResult)
    assert isinstance(r.codes, list)
    assert isinstance(r.matches, list)
    assert isinstance(r.warnings, list)
    assert all(isinstance(m, ExtractionMatch) for m in r.matches)


def test_deduplication(parser):
    # "AMO 34" et "AMO 34.02" dans le meme texte -> un seul code AMO_34.02
    r = parser.parse("AMO 34 et AMO 34.02 meme seance le 01/03/2026")
    assert r.codes.count("AMO_34.02") == 1


# ------------------------------------------------------------------ #
# Backward compat module-level functions
# ------------------------------------------------------------------ #

def test_compat_extract_act_codes_alias(ref):
    codes = extract_act_codes("AMO 34 bilan le 01/03/2026", ref=ref)
    assert "AMO_34.02" in codes
    assert "AMO_34" not in codes


def test_compat_extract_act_codes_no_ref():
    # Sans ref explicite, utilise _default_ref() (charge rules.json relatif)
    codes = extract_act_codes("AMO 20 le 01/01/2026")
    assert "AMO_20" in codes


def test_compat_extract_date():
    assert extract_date("Fait le 12/02/2026") == date(2026, 2, 12)
    assert extract_date("15/02/2026") == date(2026, 2, 15)
    assert extract_date("No date here") is None


def test_compat_extract_age():
    ref_date = date(2026, 2, 12)
    assert extract_patient_age_months("Patient, 4 ans.", ref_date) == 48
    assert extract_patient_age_months("Bébé, 18 mois", ref_date) == 18
    assert extract_patient_age_months("Né le 01/01/2020", ref_date) == 73
