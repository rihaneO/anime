import pytest
from datetime import date
from src.nlp_parser import extract_act_codes, extract_date, extract_patient_age_months

def test_extract_act_codes():
    text1 = "Bilan langage oral AMO 34. Patient Thomas"
    assert "AMO_34" in extract_act_codes(text1)

    text2 = "Séance rééducation 13.5 + Bilan 34."
    codes = extract_act_codes(text2)
    assert "AMO_13.5" in codes
    assert "AMO_34" in codes

    text3 = "Renouvellement bilan AMO 30."
    assert "AMO_30" in extract_act_codes(text3)

    text4 = "AMO_20"
    assert "AMO_20" in extract_act_codes(text4)

def test_extract_date():
    assert extract_date("Fait le 12/02/2026") == date(2026, 2, 12)
    assert extract_date("Date 12/02/26") == date(2026, 2, 12)
    assert extract_date("15/02/2026") == date(2026, 2, 15)
    assert extract_date("No date here") is None

def test_extract_patient_age_months():
    ref_date = date(2026, 2, 12)

    # "4 ans" -> 48 months
    assert extract_patient_age_months("Patient Thomas, 4 ans.", ref_date) == 48

    # "18 mois"
    assert extract_patient_age_months("Bébé, 18 mois", ref_date) == 18

    # "4 ans et 6 mois" (Optional logic, but let's see if our parser handles "4 ans" which is 48)
    # The current regex `(\d+)[\s]*(?:ans?|a\b)` just captures years.
    # The parser implementation `years * 12 + months` attempts to capture extra months.
    assert extract_patient_age_months("4 ans et 6 mois", ref_date) == 54

    # DOB "Né le 01/01/2020" -> Age on 2026-02-12
    # 2020 to 2026 is 6 years. 1 month to 2 month is 1 month. Total 6*12 + 1 = 73 months.
    assert extract_patient_age_months("Né le 01/01/2020", ref_date) == 73

    # "Né le 12/02/2026" (newborn) -> 0 months
    assert extract_patient_age_months("Né le 12/02/2026", ref_date) == 0
