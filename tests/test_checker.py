import pytest
from datetime import date, timedelta
from src.checker import Checker

# Mock DB
class MockDB:
    def __init__(self, last_bilan_date=None):
        self.last_bilan_date = last_bilan_date

    def get_last_bilan_date(self, patient_id):
        return self.last_bilan_date

@pytest.fixture
def checker():
    return Checker(rules_path='rules.json')

def test_rule_r1_age_limit(checker):
    # R1: AMO_20 forbidden if > 36 months
    parsed_data = {
        'codes': ['AMO_20'],
        'age_months': 40,
        'date': date(2026, 1, 1)
    }
    results = checker.check(parsed_data)
    assert any(r['id'] == 'R1' for r in results)

    # Valid age
    parsed_data['age_months'] = 20
    results = checker.check(parsed_data)
    assert not any(r['id'] == 'R1' for r in results)

def test_rule_r16_cumul(checker):
    # R16: Bilan (AMO_34) + Seance (AMO_13.5) on same day forbidden
    parsed_data = {
        'codes': ['AMO_34', 'AMO_13.5'],
        'date': date(2026, 1, 1),
        'age_months': 60
    }
    results = checker.check(parsed_data)
    assert any(r['id'] == 'R16' for r in results)

    # Only Bilan
    parsed_data['codes'] = ['AMO_34']
    results = checker.check(parsed_data)
    assert not any(r['id'] == 'R16' for r in results)

def test_rule_rt1_renewal():
    # RT1: Warning if last bilan < 365 days
    current = date(2026, 1, 1)
    recent_bilan = date(2025, 6, 1) # < 1 year
    old_bilan = date(2024, 1, 1) # > 1 year

    # Case 1: Renewal too soon
    db = MockDB(last_bilan_date=recent_bilan)
    checker = Checker(rules_path='rules.json', db=db)
    parsed_data = {
        'codes': ['AMO_34'],
        'date': current,
        'age_months': 60
    }
    # Need patient_id to trigger DB lookup
    results = checker.check(parsed_data, patient_id="Thomas")
    assert any(r['id'] == 'RT1' for r in results)

    # Case 2: Renewal OK
    db = MockDB(last_bilan_date=old_bilan)
    checker = Checker(rules_path='rules.json', db=db)
    results = checker.check(parsed_data, patient_id="Thomas")
    assert not any(r['id'] == 'RT1' for r in results)

    # Case 3: First Bilan (no history)
    db = MockDB(last_bilan_date=None)
    checker = Checker(rules_path='rules.json', db=db)
    results = checker.check(parsed_data, patient_id="Thomas")
    assert not any(r['id'] == 'RT1' for r in results)
