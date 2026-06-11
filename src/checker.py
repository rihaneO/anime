"""
Moteur de conformite NGAP — v3.

Changements v3 :
- Pilote par Referential (objet type) au lieu de charger rules.json directement.
  Le Checker accepte soit un Referential deja construit, soit un rules_path
  pour la compat ascendante.
- Aucun eval(). Dispatch Python par type de regle (Regle.rule_type).
- Versionnement temporel : _rule_is_active() filtre les regles selon la date
  de l'acte vs date_effet/date_fin de la regle.
- normalize_codes() : resolution des alias via Referential.
- compute_amount() : coefficient × valeur lettre-cle AMO (avec decote opt.).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from referential import Referential, Regle


def _today() -> date:
    return datetime.now().date()


class Checker:

    def __init__(
        self,
        rules_path: Optional[str] = None,
        db=None,
        ref: Optional[Referential] = None,
    ) -> None:
        if ref is not None:
            self._ref = ref
        elif rules_path is not None:
            self._ref = Referential(rules_path)
        else:
            raise ValueError("Fournir rules_path ou ref.")

        self.db = db

        # Compat ascendante : certains tests accdent checker.rules directement.
        self.rules = self._ref.raw()
        self.actes = self.rules.get("actes", {})

        # Dispatch rule_type -> handler
        self._dispatch: dict[str, Any] = {
            "age_max": self._rule_age_max,
            "renouvellement": self._rule_renouvellement,
            "cumul_bilan_seance": self._rule_cumul_bilan_seance,
            "cumul_seances_meme_jour": self._rule_cumul_seances_meme_jour,
        }

    # ------------------------------------------------------------------ #
    # API publique
    # ------------------------------------------------------------------ #

    def check(self, parsed_data: dict, patient_id: Optional[str] = None) -> list[dict]:
        """
        parsed_data: {
            'codes': list[str],   # codes canoniques (apres normalize_codes)
            'date': date | None,
            'age_months': int | None
        }
        Retourne : [{'id', 'message', 'severity'}, ...]
        """
        ctx = self._build_context(parsed_data, patient_id)
        results = []
        for regle in self._ref.regles():
            if not self._rule_is_active(regle, ctx["current_date"]):
                continue
            handler = self._dispatch.get(regle.rule_type)
            if handler is None:
                continue
            if handler(regle, ctx):
                results.append({
                    "id": regle.id,
                    "message": regle.message,
                    "severity": regle.severite,
                })
        return results

    def normalize_codes(self, codes: list[str]) -> list[str]:
        """
        Resout les codes bruts (issus du parser) vers les codes canoniques
        du referentiel via la table d'aliases.
        Les doublons sont elimines (ordre de premiere apparition conserve).
        """
        seen: set[str] = set()
        out: list[str] = []
        for code in codes:
            canonical = self._ref.resolve(code) or code
            if canonical not in seen:
                seen.add(canonical)
                out.append(canonical)
        return out

    def compute_amount(self, codes: list[str], decote_pct: float = 0) -> float:
        """
        Montant theorique : sum(coefficient × valeur_AMO) avec decote opt. (%).
        """
        valeur = self._ref.lettre_cle().valeur_metropole
        total = sum(
            (self._ref.get_acte(c).coefficient if self._ref.get_acte(c) else 0)
            for c in codes
        )
        if decote_pct:
            total *= 1 - decote_pct / 100.0
        return round(total * valeur, 2)

    def get_bilan_codes(self) -> list[str]:
        return self._ref.actes_by_type("bilan")

    # ------------------------------------------------------------------ #
    # Contexte
    # ------------------------------------------------------------------ #

    def _build_context(self, parsed_data: dict, patient_id: Optional[str]) -> dict:
        current_date = parsed_data.get("date") or _today()
        input_codes = parsed_data.get("codes") or []

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
    # Helpers
    # ------------------------------------------------------------------ #

    def _get_act_type(self, code: str) -> Optional[str]:
        acte = self._ref.get_acte(code)
        return acte.act_type if acte else None

    @staticmethod
    def _rule_is_active(regle: Regle, on_date: date) -> bool:
        if regle.date_effet and on_date < regle.date_effet:
            return False
        if regle.date_fin and on_date > regle.date_fin:
            return False
        return True

    # ------------------------------------------------------------------ #
    # Evaluateurs (un par rule_type) — aucun eval()
    # ------------------------------------------------------------------ #

    def _rule_age_max(self, regle: Regle, ctx: dict) -> bool:
        p = regle.params
        code = p.get("code")
        age = ctx["age_patient_mois"]
        if code not in ctx["input_codes"]:
            return False
        if age is None:
            return False  # age inconnu -> pas de rejet (fail-safe)
        return age > p.get("age_max_mois", float("inf"))

    def _rule_renouvellement(self, regle: Regle, ctx: dict) -> bool:
        if not ctx["bilan_codes"]:
            return False
        last = ctx["last_bilan_date"]
        if last is None:
            return False
        return (ctx["current_date"] - last).days < regle.params.get("delai_jours", 365)

    def _rule_cumul_bilan_seance(self, regle: Regle, ctx: dict) -> bool:
        return bool(ctx["bilan_codes"]) and bool(ctx["seance_codes"])

    def _rule_cumul_seances_meme_jour(self, regle: Regle, ctx: dict) -> bool:
        # Avenant 21 : 2 seances distinctes le meme jour = WARNING (3 conditions)
        return len(set(ctx["seance_codes"])) >= 2
