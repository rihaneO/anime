"""
Module d'audit anti-indu — Wedge B de Neuro-Shield.

Analyse l'historique de facturation d'un patient (ou d'un cabinet) pour
identifier les actes a risque d'indu AVANT un controle CPAM, en appliquant
le moteur de regles a chaque date d'acte passee.

Usage programmatique:
    from audit import build_patient_report
    rapport = build_patient_report("Thomas", db, checker)

Principales sources de risque detectees :
- Bilan et seance factures le meme jour (R16)
- Renouvellement de bilan < 1 an sans decote -30 % (RT1)
- Limite d'age non respectee (R1)
- Doublon : meme code facture deux fois la meme date
"""

from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class InduRisk:
    date: str
    codes: list
    rule_id: str
    severity: str
    message: str


@dataclass
class AuditReport:
    patient_id: str
    generated_at: str
    total_acts: int
    risks: list = field(default_factory=list)

    @property
    def blocking_count(self):
        return sum(1 for r in self.risks if r.severity == "BLOCKING")

    @property
    def warning_count(self):
        return sum(1 for r in self.risks if r.severity == "WARNING")

    @property
    def risk_score(self):
        """Score de risque global : 0 = aucun, >0 = a examiner."""
        return self.blocking_count * 3 + self.warning_count


def build_patient_report(patient_id: str, db, checker) -> AuditReport:
    """
    Construit un rapport d'audit pour un patient a partir de son historique.

    1. Recupere tout l'historique depuis la base.
    2. Regroupe les actes par date.
    3. Applique le Checker sur chaque groupe (en simulant la date de l'acte).
    4. Detecte aussi les doublons (meme code, meme date).
    """
    history = db.get_history(patient_id)   # [(act_code, act_date, raw_text), ...]

    report = AuditReport(
        patient_id=patient_id,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        total_acts=len(history),
    )

    if not history:
        return report

    # Regroupe par date
    by_date = {}
    for act_code, act_date_str, _ in history:
        by_date.setdefault(act_date_str, []).append(act_code)

    # Detecte les doublons au passage
    for date_str, codes in sorted(by_date.items()):
        seen = set()
        for c in codes:
            if c in seen:
                report.risks.append(InduRisk(
                    date=date_str,
                    codes=[c],
                    rule_id="DOUBLON",
                    severity="BLOCKING",
                    message=f"REJET probable: le code {c} est facture plus d'une fois le {date_str}.",
                ))
            seen.add(c)

    # Applique le moteur de regles sur chaque date
    # On a besoin d'une vue « DB simulee » pointant vers l'historique AVANT cette date
    for date_str, codes in sorted(by_date.items()):
        try:
            act_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue

        normalized = checker.normalize_codes(codes)
        parsed_data = {
            "codes": normalized,
            "date": act_date,
            "age_months": None,  # l'historique ne stocke pas l'age
        }

        # On passe patient_id pour que le checker puisse interroger l'historique
        # avant cette date (la DB retourne le MAX(act_date) < date courante naturellement
        # car elle renvoie toutes les dates, y compris la courante — on accepte cette
        # approximation dans le contexte d'un audit retrospectif).
        results = checker.check(parsed_data, patient_id=patient_id)

        for r in results:
            report.risks.append(InduRisk(
                date=date_str,
                codes=normalized,
                rule_id=r["id"],
                severity=r["severity"],
                message=r["message"],
            ))

    return report


def format_report_text(report: AuditReport) -> str:
    """Formatage texte du rapport (pour CLI ou Streamlit)."""
    lines = [
        f"=== Rapport d'audit anti-indu — Patient : {report.patient_id} ===",
        f"Genere le : {report.generated_at}",
        f"Actes analyses : {report.total_acts}",
        f"Risques detectes : {len(report.risks)} "
        f"({report.blocking_count} REJET / {report.warning_count} ALERTE)",
        f"Score de risque global : {report.risk_score}",
        "",
    ]
    if not report.risks:
        lines.append("Aucun risque detecte. Historique conforme.")
        return "\n".join(lines)

    lines.append("--- Detail des risques ---")
    for r in sorted(report.risks, key=lambda x: (x.severity, x.date)):
        icon = "REJET" if r.severity == "BLOCKING" else "ALERTE"
        lines.append(f"[{icon}] {r.date} | {', '.join(r.codes)} | {r.rule_id}")
        lines.append(f"        {r.message}")
    return "\n".join(lines)
