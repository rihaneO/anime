"""
Moteur de conformite NGAP pour orthophonistes.

Conception (v2) :
- AUCUN `eval()`. Les regles sont typees et evaluees par un dispatch Python.
  Chaque regle a un `type` qui correspond a une methode `_rule_<type>`.
- Les regles sont versionnees par date d'effet (`date_effet` / `date_fin`),
  ce qui permet d'absorber les avenants successifs sans casser l'historique.
- Le referentiel des actes porte les coefficients, ce qui permet de calculer
  le montant theorique (coefficient x valeur de la lettre-cle AMO).
"""

import json
import os
from datetime import datetime, date


def _parse_iso(d):
    """Parse une date ISO 'YYYY-MM-DD' en date, ou None."""
    if not d:
        return None
    if isinstance(d, date):
        return d
    return datetime.strptime(d, "%Y-%m-%d").date()


class Checker:
    def __init__(self, rules_path="rules.json", db=None):
        self.rules = self._load_rules(rules_path)
        self.db = db
        self.actes = self.rules.get("actes", {})
        # Dispatch : type de regle -> methode d'evaluation. Pas d'eval().
        self._dispatch = {
            "age_max": self._rule_age_max,
            "renouvellement": self._rule_renouvellement,
            "cumul_bilan_seance": self._rule_cumul_bilan_seance,
            "cumul_seances_meme_jour": self._rule_cumul_seances_meme_jour,
        }

    # ------------------------------------------------------------------ #
    # Chargement
    # ------------------------------------------------------------------ #
    def _load_rules(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError(f"Rules file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    # ------------------------------------------------------------------ #
    # API publique
    # ------------------------------------------------------------------ #
    def check(self, parsed_data, patient_id=None):
        """
        parsed_data: {
            'codes': ['AMO_34.02', 'AMO_13.5'],
            'date': datetime.date,
            'age_months': int | None
        }
        patient_id: identifiant pour la recherche d'historique en base.

        Retourne une liste de dict :
            {'id', 'message', 'severity'}.
        """
        results = []
        ctx = self._build_context(parsed_data, patient_id)

        for rule in self.rules.get("regles", []):
            if not self._rule_is_active(rule, ctx["current_date"]):
                continue
            handler = self._dispatch.get(rule.get("type"))
            if handler is None:
                # Type de regle inconnu : on ignore plutot que de planter.
                continue
            if handler(rule, ctx):
                results.append({
                    "id": rule["id"],
                    "message": rule["message"],
                    "severity": rule["severite"],
                })
        return results

    def compute_amount(self, codes, decote_pct=0):
        """
        Calcule le montant theorique total : somme(coefficient x valeur AMO),
        avec decote optionnelle (en %). Retourne un float arrondi au centime.
        """
        valeur = (
            self.rules.get("lettre_cle", {})
            .get("valeur_eur", {})
            .get("metropole", 0)
        )
        total = 0.0
        for code in codes:
            acte = self.actes.get(code)
            if acte and acte.get("coefficient") is not None:
                total += acte["coefficient"] * valeur
        if decote_pct:
            total *= (1 - decote_pct / 100.0)
        return round(total, 2)

    # ------------------------------------------------------------------ #
    # Contexte
    # ------------------------------------------------------------------ #
    def _build_context(self, parsed_data, patient_id):
        current_date = parsed_data.get("date") or datetime.now().date()
        input_codes = parsed_data.get("codes", []) or []

        bilan_codes = [c for c in input_codes if self._get_act_type(c) == "bilan"]
        seance_codes = [c for c in input_codes if self._get_act_type(c) == "reeducation"]

        last_bilan_date = None
        if self.db and patient_id and bilan_codes:
            last_bilan_date = self.db.get_last_bilan_date(
                patient_id, self.get_bilan_codes()
            )

        return {
            "current_date": current_date,
            "age_patient_mois": parsed_data.get("age_months"),
            "input_codes": input_codes,
            "bilan_codes": bilan_codes,
            "seance_codes": seance_codes,
            "last_bilan_date": last_bilan_date,
        }

    # ------------------------------------------------------------------ #
    # Helpers referentiel
    # ------------------------------------------------------------------ #
    def _get_act_type(self, code):
        acte = self.actes.get(code)
        return acte.get("type") if acte else None

    def get_bilan_codes(self):
        """Liste des codes de type 'bilan' connus dans le referentiel."""
        return [c for c, a in self.actes.items() if a.get("type") == "bilan"]

    def _rule_is_active(self, rule, on_date):
        """Vrai si la regle est en vigueur a la date de l'acte."""
        debut = _parse_iso(rule.get("date_effet"))
        fin = _parse_iso(rule.get("date_fin"))
        if debut and on_date < debut:
            return False
        if fin and on_date > fin:
            return False
        return True

    # ------------------------------------------------------------------ #
    # Evaluateurs de regles (un par type) — aucun eval()
    # ------------------------------------------------------------------ #
    def _rule_age_max(self, rule, ctx):
        p = rule.get("params", {})
        code = p.get("code")
        age = ctx["age_patient_mois"]
        if code not in ctx["input_codes"]:
            return False
        if age is None:  # age inconnu => on ne peut pas rejeter (fail-safe)
            return False
        return age > p.get("age_max_mois", float("inf"))

    def _rule_renouvellement(self, rule, ctx):
        p = rule.get("params", {})
        if not ctx["bilan_codes"]:
            return False
        last = ctx["last_bilan_date"]
        if last is None:
            return False
        delta = (ctx["current_date"] - last).days
        return delta < p.get("delai_jours", 365)

    def _rule_cumul_bilan_seance(self, rule, ctx):
        # Bilan + seance le meme jour (le rapport d'entree porte sur une seule date).
        return bool(ctx["bilan_codes"]) and bool(ctx["seance_codes"])

    def _rule_cumul_seances_meme_jour(self, rule, ctx):
        # Avenant 21 : 2 seances de reeducation distinctes le meme jour =>
        # autorise sous 3 conditions non verifiables automatiquement => WARNING.
        return len(set(ctx["seance_codes"])) >= 2
