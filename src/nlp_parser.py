import re
from datetime import datetime
from dateutil.relativedelta import relativedelta

def extract_act_codes(text):
    """
    Extracts act codes like AMO_34, AMO 34, 13.5, AMO 13.5.
    Returns a list of standardized codes (e.g., 'AMO_34').
    """
    # Pattern to match AMO followed by space or underscore and then number/dots
    # Or just numbers if explicitly labeled (though the prompt says "Code: Pattern AMO\s*[\d\.]+ or just numbers if explicitly labeled")
    # Let's try to match "AMO" optionally followed by space/underscore, then digits/dots.
    # Also handle standalone numbers that look like codes if they are common, but based on examples:
    # "AMO 34", "13.5" (in "Séance rééducation 13.5"), "AMO 30".

    # We will look for "AMO" followed by number, OR numbers that are likely act codes.
    # Given the examples: "AMO 34", "13.5".

    # Regex for "AMO" prefix. Capture digits, optionally followed by .digits
    amo_pattern = r"(?:AMO|amo)[\s_]*(\d+(?:\.\d+)?)"
    amo_matches = re.findall(amo_pattern, text, re.IGNORECASE)

    # Regex for standalone numbers might be tricky without context, but let's look at the example "Séance rééducation 13.5".
    # If we just match all numbers, we might get ages.
    # "Patient Thomas, 4 ans" -> 4 is age.
    # "13.5" is code.
    # Let's assume codes are either prefixed with AMO OR are float-like (contain dot) OR are specifically known integers if we had a full list.
    # For now, let's stick to explicit AMO prefix OR numbers that look like codes in specific context?
    # The prompt says: "Pattern AMO\s*[\d\.]+ or just numbers if explicitly labeled."
    # Let's capture "AMO X" and normalize to "AMO_X".

    codes = []
    for match in amo_matches:
        codes.append(f"AMO_{match}")

    # Example 2: "Séance rééducation 13.5".
    # If "AMO" is missing, it might be hard to distinguish from age/date parts if not careful.
    # But usually age is integer. 13.5 is float.
    # Let's look for numbers that appear to be acts.
    # Maybe we can look for specific numbers if we know them from rules.json?
    # But the parser should be generic.

    # Let's try to find numbers that are NOT part of a date or age string.
    # This is getting complex.
    # Let's refine the approach:
    # 1. Look for AMO-prefixed codes.
    # 2. Look for "standalone" numbers that might be codes.
    #    In "Séance rééducation 13.5", "13.5" is the code.
    #    In "Bilan 34", "34" is the code.

    # Let's search for patterns that look like codes.
    # \b\d+(\.\d+)?\b
    # But exclude if followed by "ans", "mois", "an".
    # And exclude if it looks like a year (4 digits, start with 19 or 20) or day (1-31).

    # Let's try a simpler approach first: specific regex for the examples provided.
    # "13.5" -> `\b\d+\.\d+\b` (likely a code like 13.5, 12.1)
    # "34" -> `\b\d+\b` (could be anything).

    # Let's trust the "AMO" prefix for now, and maybe a lookbehind for words like "Bilan", "Séance"?
    # "Bilan 34" -> Code 34.
    # "Séance ... 13.5" -> Code 13.5.

    # Improved regex strategy:
    # 1. `AMO[\s_]*([\d\.]+)`
    # 2. `(?:Bilan|Séance|Cotation)[\s\w]*\s+([\d\.]+)` ??

    # Let's look at Example 2: "Séance rééducation 13.5 + Bilan 34."
    # We can match `\b(\d+(?:\.\d+)?)\b` and filter.

    potential_numbers = re.finditer(r"\b(\d+(?:\.\d+)?)\b", text)

    for match in potential_numbers:
        num_str = match.group(1)
        start, end = match.span()

        # Check context
        context_after = text[end:end+10].lower()
        context_before = text[max(0, start-10):start].lower()

        # Ignore if follows "AMO" (already caught)
        if re.search(r"amo[\s_]*$", context_before):
            continue

        # Ignore if followed by "ans", "mois", "an" (Age)
        if re.match(r"\s*(ans?|mois?)", context_after):
            continue

        # Ignore if part of a date (XX/XX/XX)
        # Check if surrounded by slashes
        if (start > 0 and text[start-1] == '/') or (end < len(text) and text[end] == '/'):
            continue

        # Ignore years (19XX, 20XX) if they seem to be dates?
        # A code could be 2026? Unlikely for acts.
        if len(num_str) == 4 and (num_str.startswith("19") or num_str.startswith("20")):
             # Check if it looks like a year in a date context
             continue

        # Ignore small integers that might be day/month unless clearly a code?
        # "Patient Thomas, 4 ans." -> 4 handled by age check.
        # "Fait le 12..." -> 12 handled by date check.

        # If it's a float like 13.5, it's likely a code.
        if '.' in num_str:
            code = f"AMO_{num_str}"
            if code not in codes:
                codes.append(code)
        elif num_str in ["34", "30", "20", "10", "15"]:
            # Heuristic: Common AMO codes without prefix
            # If "Bilan" or "Séance" appears nearby?
            # "Bilan 34"
            if "bilan" in context_before or "séance" in context_before or "seance" in context_before or "cotation" in context_before:
                 code = f"AMO_{num_str}"
                 if code not in codes:
                     codes.append(code)

            # Additional heuristic from Example 2: "Séance rééducation 13.5 + Bilan 34"
            # If we missed it, let's just be permissive for now?
            # No, false positives are bad.

    return list(set(codes))

def extract_date(text):
    """
    Extracts date: DD/MM/YYYY or DD/MM/YY.
    Returns datetime object or None.
    """
    # Regex for date
    date_pattern = r"\b(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{2,4})\b"
    match = re.search(date_pattern, text)

    if match:
        day, month, year = match.groups()
        if len(year) == 2:
            year = "20" + year # Assume 20xx

        try:
            return datetime(int(year), int(month), int(day)).date()
        except ValueError:
            return None
    return None

def extract_patient_age_months(text, ref_date=None):
    """
    Extracts age in months.
    Can come from "X ans", "X mois", or DOB "Né le...".
    ref_date: datetime.date to calculate age from DOB. Defaults to today.
    """
    if ref_date is None:
        ref_date = datetime.now().date()

    text_lower = text.lower()

    # 1. Explicit Age: "X ans", "X mois"
    # "4 ans"
    ans_match = re.search(r"(\d+)[\s]*(?:ans?|a\b)", text_lower)
    if ans_match:
        years = int(ans_match.group(1))
        # Look for months too: "4 ans et 6 mois"
        mois_match = re.search(r"(\d+)[\s]*mois", text_lower[ans_match.end():])
        months = int(mois_match.group(1)) if mois_match else 0
        return years * 12 + months

    # "X mois" (only if ans wasn't found first to avoid double count if logic was different, but here ans takes precedence)
    # If "4 ans" is not found, look for "X mois"
    mois_only_match = re.search(r"(\d+)[\s]*mois", text_lower)
    if mois_only_match:
        return int(mois_only_match.group(1))

    # 2. DOB: "Né le DD/MM/YYYY" or "Né(e) le..."
    dob_pattern = r"(?:n[ée]+(?:\s+le)?|dob)\s*[:\s]*(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{2,4})"
    dob_match = re.search(dob_pattern, text_lower)

    if dob_match:
        day, month, year = dob_match.groups()
        if len(year) == 2:
            year = "20" + year

        try:
            dob = datetime(int(year), int(month), int(day)).date()
            # Calculate delta in months
            delta = relativedelta(ref_date, dob)
            return delta.years * 12 + delta.months
        except ValueError:
            pass

    return None
