import pytest
from datetime import date
from src.checker import Checker


# Mock DB : signature alignee sur le nouveau Checker (bilan_codes optionnel).
class MockDB:
    def __init__(self, last_bilan_date=None):
        self.last_bilan_date = last_bilan_date

    def get_last_bilan_date(self, patient_id, bilan_codes=None):
        return self.last_bilan_date


@pytest.fixture
def checker():
    return Checker(rules_path='rules.json')


def test_rule_r1_age_limit(checker):
    # R1 : AMO_20 interdit si > 36 mois
    parsed_data = {'codes': ['AMO_20'], 'age_months': 40, 'date': date(2026, 3, 1)}
    results = checker.check(parsed_data)
    assert any(r['id'] == 'R1' for r in results)

    # Age valide
    parsed_data['age_months'] = 20
    results = checker.check(parsed_data)
    assert not any(r['id'] == 'R1' for r in results)

    # Age inconnu => pas de rejet (fail-safe)
    parsed_data['age_months'] = None
    results = checker.check(parsed_data)
    assert not any(r['id'] == 'R1' for r in results)


def test_rule_r16_cumul_bilan_seance(checker):
    # R16 : Bilan + Seance le meme jour interdit
    parsed_data = {
        'codes': ['AMO_34.02', 'AMO_13.5'],
        'date': date(2026, 3, 1),
        'age_months': 60,
    }
    results = checker.check(parsed_data)
    assert any(r['id'] == 'R16' for r in results)

    # Bilan seul => OK
    parsed_data['codes'] = ['AMO_34.02']
    results = checker.check(parsed_data)
    assert not any(r['id'] == 'R16' for r in results)


def test_rule_rt1_renewal():
    current = date(2026, 3, 1)
    recent_bilan = date(2025, 9, 1)   # < 1 an
    old_bilan = date(2024, 1, 1)      # > 1 an
    parsed_data = {'codes': ['AMO_34.02'], 'date': current, 'age_months': 60}

    # Renouvellement trop tot => WARNING
    checker = Checker(rules_path='rules.json', db=MockDB(recent_bilan))
    results = checker.check(parsed_data, patient_id="Thomas")
    assert any(r['id'] == 'RT1' for r in results)

    # Renouvellement OK (> 1 an)
    checker = Checker(rules_path='rules.json', db=MockDB(old_bilan))
    results = checker.check(parsed_data, patient_id="Thomas")
    assert not any(r['id'] == 'RT1' for r in results)

    # Premier bilan (pas d'historique)
    checker = Checker(rules_path='rules.json', db=MockDB(None))
    results = checker.check(parsed_data, patient_id="Thomas")
    assert not any(r['id'] == 'RT1' for r in results)


def test_avenant21_versioning(checker):
    # La regle A21_CUMUL (cumul 2 seances) n'est active qu'a partir du 23/02/2026.
    two_seances = ['AMO_13.5', 'AMO_9.7']

    # Avant l'avenant 21 : regle inactive
    before = {'codes': two_seances, 'date': date(2026, 1, 1), 'age_months': 60}
    results = checker.check(before)
    assert not any(r['id'] == 'A21_CUMUL' for r in results)

    # Apres l'avenant 21 : WARNING (3 conditions a verifier)
    after = {'codes': two_seances, 'date': date(2026, 3, 1), 'age_months': 60}
    results = checker.check(after)
    assert any(r['id'] == 'A21_CUMUL' for r in results)
    assert all(r['severity'] == 'WARNING' for r in results if r['id'] == 'A21_CUMUL')


def test_compute_amount(checker):
    # AMO 34.02 x 2.60 EUR = 88.452 -> 88.45
    assert checker.compute_amount(['AMO_34.02']) == 88.45

    # Decote renouvellement -30%
    assert checker.compute_amount(['AMO_34.02'], decote_pct=30) == 61.92

    # Code inconnu ignore dans le calcul
    assert checker.compute_amount(['CODE_INEXISTANT']) == 0.0


def test_get_bilan_codes(checker):
    bilans = checker.get_bilan_codes()
    assert 'AMO_34.02' in bilans
    assert 'AMO_20' in bilans
    assert 'AMO_13.5' not in bilans  # reeducation, pas bilan
