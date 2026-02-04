import json
import os
from datetime import datetime

class Checker:
    def __init__(self, rules_path='rules.json', db=None):
        self.rules = self._load_rules(rules_path)
        self.db = db

    def _load_rules(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError(f"Rules file not found: {path}")
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def check(self, parsed_data, patient_id=None):
        """
        parsed_data: {
            'codes': ['AMO_34', 'AMO_13.5'],
            'date': datetime.date object,
            'age_months': int or None
        }
        patient_id: str/int identifier to check history in DB
        """
        results = []

        # Prepare context variables
        current_date = parsed_data.get('date') or datetime.now().date()
        age_patient_mois = parsed_data.get('age_months')
        input_codes = parsed_data.get('codes', [])

        # Identify types of acts in input
        bilan_codes = [c for c in input_codes if self._get_act_type(c) == 'bilan']
        seance_codes = [c for c in input_codes if self._get_act_type(c) == 'reeducation'] # Assuming 'reeducation' is the type for seance
        # Note: rules.json says "reeducation" for AMO_13.5

        bilan_in_input = len(bilan_codes) > 0
        seance_in_input = len(seance_codes) > 0
        date_bilan = current_date # Simplified: we assume input text is for one date
        date_seance = current_date

        # Retrieve history if needed (for RT1)
        last_bilan_date = None
        if self.db and patient_id and bilan_in_input:
             # Check the last bilan date for the specific bilan code(s) or any bilan?
             # Rule RT1 says "Bilan déjà facturé". Usually implies checking history of bilans.
             # We'll check the most recent bilan for the patient.
             last_bilan_date = self.db.get_last_bilan_date(patient_id)

        # Context for evaluation
        context = {
            "age_patient_mois": age_patient_mois,
            "current_date": current_date,
            "last_bilan_date": last_bilan_date,
            "bilan_in_input": bilan_in_input,
            "seance_in_input": seance_in_input,
            "date_bilan": date_bilan,
            "date_seance": date_seance
        }

        # Iterate over Transversal Rules
        for rule in self.rules.get('regles_transversales', []):
            condition = rule['condition']
            test_expr = condition['test']

            # Special handling for "code_concerne" rules (like R1)
            if 'code_concerne' in condition:
                code_concerne = condition['code_concerne']
                if code_concerne in input_codes:
                    # Evaluate rule specific to this code
                    if self._evaluate(test_expr, context):
                        results.append({
                            "id": rule['id'],
                            "message": rule['message'],
                        "severity": rule['severite']
                        })
            else:
                # Global rules (like RT1, R16)
                if self._evaluate(test_expr, context):
                    results.append({
                        "id": rule['id'],
                        "message": rule['message'],
                        "severity": rule['severite']
                    })

        return results

    def _get_act_type(self, code):
        act_def = self.rules.get('actes', {}).get(code)
        if act_def:
            return act_def.get('type')
        return None

    def _evaluate(self, expr, context):
        """
        Safely evaluate the expression with the given context.
        """
        # We need to handle 'days' property of timedelta in the expression: (d1 - d2).days
        # Python's eval works if objects support it.
        # But `age_patient_mois` might be None if parser failed.

        # If a variable required in expr is None, we generally skip the check or fail safe?
        # For R1: if age is unknown, we can't reject.

        try:
            # Check if all variables in expression are available
            # This is a simple heuristic.
            if "age_patient_mois" in expr and context.get("age_patient_mois") is None:
                return False
            # RT1 special handling: if last_bilan_date is used but None, AND the expression checks for IS NOT NULL, we should proceed.
            # But if it is None and we try to do arithmetic, it will fail.
            # The replacement `is not None` allows `last_bilan_date is not None` to evaluate to False, so the AND short-circuits.

            # Prepare safe locals
            # We map the string logic to Python logic
            # "IS NOT NULL" -> "is not None"
            expr_python = expr.replace("IS NOT NULL", "is not None")
            expr_python = expr_python.replace("AND", "and").replace("OR", "or")

            return eval(expr_python, {}, context)
        except Exception as e:
            # print(f"Error evaluating rule {expr}: {e}")
            return False
