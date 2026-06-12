"""
Module d'audit anti-indu — Wedge B strategique de Neuro-Shield.

Deux modes d'audit :
  1. audit_from_db()   : analyse l'historique interne (SQLite).
  2. audit_from_csv()  : importe un export CSV (VEGA, Orthomax, manuel)
                         et produit le meme rapport.

Architecture :
- InduRisk     : un risque detecte (regle, date, codes concernes).
- AuditReport  : agregat de risques avec score global.
- Fonctions    : build_patient_report / build_csv_report (API haute).

Score de risque :
  score = BLOCKING × 3 + WARNING × 1
  > 0 -> a examiner ; 0 -> historique conforme.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional

from csv_importer import CSVImporter, ImportResult


# ------------------------------------------------------------------ #
# Types
# ------------------------------------------------------------------ #

@dataclass(frozen=True)
class InduRisk:
    act_date: str
    codes: tuple[str, ...]
    rule_id: str
    severity: str     # "BLOCKING" | "WARNING"
    message: str


@dataclass
class AuditReport:
    patient_id: str
    generated_at: str
    total_acts: int
    risks: list[InduRisk] = field(default_factory=list)
    import_errors: list[str] = field(default_factory=list)  # erreurs CSV si applicable

    @property
    def blocking_count(self) -> int:
        return sum(1 for r in self.risks if r.severity == "BLOCKING")

    @property
    def warning_count(self) -> int:
        return sum(1 for r in self.risks if r.severity == "WARNING")

    @property
    def risk_score(self) -> int:
        return self.blocking_count * 3 + self.warning_count

    @property
    def is_clean(self) -> bool:
        return self.risk_score == 0


# ------------------------------------------------------------------ #
# Noyau d'analyse (partage entre les deux modes)
# ------------------------------------------------------------------ #

def _analyze_acts(
    acts: list[tuple[str, date]],  # [(code_canonique, date), ...]
    checker,
    patient_id: str,
) -> list[InduRisk]:
    """
    Groupe les actes par date, applique le moteur de regles sur chaque groupe,
    detecte aussi les doublons (meme code, meme date).
    Retourne la liste de risques detectes.
    """
    risks: list[InduRisk] = []

    # Groupe par date
    by_date: dict[date, list[str]] = {}
    for code, act_date in acts:
        by_date.setdefault(act_date, []).append(code)

    for act_date in sorted(by_date):
        codes = by_date[act_date]
        date_str = act_date.isoformat()

        # Detection des doublons (meme code, meme date)
        seen: set[str] = set()
        for c in codes:
            if c in seen:
                risks.append(InduRisk(
                    act_date=date_str,
                    codes=(c,),
                    rule_id="DOUBLON",
                    severity="BLOCKING",
                    message=(
                        f"REJET probable : '{c}' facture plusieurs fois le {date_str}. "
                        "Un doublon de facture est un motif d'indu systematique."
                    ),
                ))
            seen.add(c)

        # Appel au moteur de regles
        parsed = {
            "codes": list(dict.fromkeys(codes)),  # deduplique pour eviter double-trigger
            "date": act_date,
            "age_months": None,  # l'historique ne stocke pas l'age
        }
        rule_results = checker.check(parsed, patient_id=patient_id)
        for r in rule_results:
            risks.append(InduRisk(
                act_date=date_str,
                codes=tuple(dict.fromkeys(codes)),
                rule_id=r["id"],
                severity=r["severity"],
                message=r["message"],
            ))

    return risks


def _make_report(
    patient_id: str,
    acts: list[tuple[str, date]],
    checker,
    import_errors: Optional[list[str]] = None,
) -> AuditReport:
    report = AuditReport(
        patient_id=patient_id,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        total_acts=len(acts),
        import_errors=import_errors or [],
    )
    if acts:
        report.risks = _analyze_acts(acts, checker, patient_id)
    return report


# ------------------------------------------------------------------ #
# API publique — mode DB interne
# ------------------------------------------------------------------ #

def build_patient_report(patient_id: str, db, checker) -> AuditReport:
    """
    Audite un patient a partir de l'historique SQLite interne.
    Le checker doit avoir la DB injectee pour que la regle RT1 fonctionne.
    """
    history = db.get_history(patient_id)  # [(code, date_str, raw_text), ...]

    acts: list[tuple[str, date]] = []
    for code, date_str, _ in history:
        try:
            acts.append((code, datetime.strptime(date_str, "%Y-%m-%d").date()))
        except ValueError:
            pass  # date malformee en base : on l'ignore

    return _make_report(patient_id, acts, checker)


# ------------------------------------------------------------------ #
# API publique — mode import CSV
# ------------------------------------------------------------------ #

def build_csv_report(
    raw_bytes: bytes,
    patient_filter: Optional[str],
    db,
    checker,
) -> tuple[AuditReport, ImportResult]:
    """
    Importe un CSV et audite les actes.

    patient_filter : si fourni, ne garde que ce patient.
                     Si None, audite toutes les lignes (multi-patients).

    Retourne (AuditReport, ImportResult) pour que l'UI puisse afficher
    les erreurs d'import separement du rapport d'audit.
    """
    importer = CSVImporter(checker._ref)
    result = importer.import_bytes(raw_bytes)

    rows = result.rows
    if patient_filter:
        rows = [r for r in rows if r.patient_id == patient_filter]

    acts: list[tuple[str, date]] = [(r.act_code, r.act_date) for r in rows]
    import_error_msgs = [
        f"Ligne {e.line_number} [{e.field}={repr(e.value)}] : {e.reason}"
        for e in result.errors
    ]

    label = patient_filter or "TOUS"
    report = _make_report(label, acts, checker, import_errors=import_error_msgs)

    # Injecte les actes CSV dans la DB pour enrichir l'historique
    # (si patient unique, pour beneficier de la regle RT1 sur la DB)
    if patient_filter and db:
        for row in rows:
            db.save_report(row.patient_id, [row.act_code], row.act_date, "csv_import")

    return report, result


# ------------------------------------------------------------------ #
# Formattage (pour CLI ou export texte dans Streamlit)
# ------------------------------------------------------------------ #

def format_report_text(report: AuditReport) -> str:
    lines = [
        f"=== Rapport d'audit anti-indu ===",
        f"Patient     : {report.patient_id}",
        f"Genere le   : {report.generated_at}",
        f"Actes       : {report.total_acts}",
        f"Risques     : {len(report.risks)} "
        f"({report.blocking_count} REJET / {report.warning_count} ALERTE)",
        f"Score       : {report.risk_score}",
    ]
    if report.import_errors:
        lines += ["", "--- Erreurs d'import ---"]
        lines += [f"  {e}" for e in report.import_errors]

    if not report.risks:
        lines += ["", "Aucun risque detecte. Historique conforme."]
        return "\n".join(lines)

    lines += ["", "--- Detail des risques (REJET > ALERTE, puis date) ---"]
    for r in sorted(report.risks, key=lambda x: (x.severity == "WARNING", x.act_date)):
        icon = "REJET " if r.severity == "BLOCKING" else "ALERTE"
        lines.append(f"[{icon}] {r.act_date} | {', '.join(r.codes)} | {r.rule_id}")
        lines.append(f"         {r.message}")
    return "\n".join(lines)
