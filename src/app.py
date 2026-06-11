import streamlit as st
from datetime import datetime
from referential import Referential
from nlp_parser import NLPParser
from checker import Checker
from db import Database
from audit import build_patient_report, build_csv_report, format_report_text
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES_PATH = os.path.join(BASE_DIR, "rules.json")
DB_PATH = os.path.join(BASE_DIR, "neuro_shield.db")

ref = Referential(RULES_PATH)
db = Database(db_path=DB_PATH)
checker = Checker(ref=ref, db=db)

st.set_page_config(page_title="Neuro-Shield", page_icon="🛡️", layout="wide")
st.title("🛡️ Neuro-Shield — Conformité NGAP")

lc = ref.lettre_cle()
st.caption(
    f"Référentiel v{ref.schema_version()} · "
    f"AMO métropole {lc.valeur_metropole} € · Avenant 21 (23/02/2026)"
)

# ------------------------------------------------------------------ #
# Sidebar — patient
# ------------------------------------------------------------------ #
st.sidebar.header("Patient")
patient_name = st.sidebar.text_input("Nom (pour historique)", value="")

if patient_name:
    history = db.get_history(patient_name)
    if history:
        st.sidebar.markdown(f"**Derniers actes de {patient_name} :**")
        for code, date_str, _ in history[:5]:
            st.sidebar.text(f"{date_str} · {code}")
    else:
        st.sidebar.info("Aucun historique.")

# ------------------------------------------------------------------ #
# Onglets
# ------------------------------------------------------------------ #
tab_check, tab_audit, tab_csv = st.tabs([
    "🔍 Vérifier une facturation",
    "📋 Audit anti-indu",
    "📂 Import CSV",
])

# ========== ONGLET 1 : vérification à la volée ==================== #
with tab_check:
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("Notes d'actes")
        raw_text = st.text_area(
            "Collez vos notes en texte libre",
            height=180,
            placeholder="Ex : Bilan langage oral AMO 34. Patient Thomas, 4 ans. Fait le 12/03/2026.",
        )
        analyze_btn = st.button("Analyser 🔍", type="primary")

    with col2:
        st.subheader("Résultat")
        result_box = st.container()

    if analyze_btn and raw_text:
        with st.spinner("Analyse..."):
            parsed = NLPParser(ref).parse(raw_text)
            codes = checker.normalize_codes(parsed.codes)
            date_obj = parsed.act_date or datetime.now().date()
            age_months = parsed.age_months

            if parsed.act_date is None:
                st.warning("Date non trouvée — date du jour utilisée.")

            for w in parsed.warnings:
                if "age" in w.lower() or "date" in w.lower():
                    continue  # deja affiche ci-dessus
                st.info(w)

            st.info(
                f"**Extraits** · Actes : {', '.join(codes) or 'Aucun'} · "
                f"Date : {date_obj} · "
                f"Âge : {f'{age_months} mois' if age_months is not None else 'non détecté'}"
            )

            parsed_data = {"codes": codes, "date": date_obj, "age_months": age_months}
            results = checker.check(parsed_data, patient_id=patient_name)

            decote = 30 if any(r["id"] == "RT1" for r in results) else 0
            montant = checker.compute_amount(codes, decote_pct=decote)
            if codes:
                label = f"Montant théorique : **{montant} €**"
                if decote:
                    label += " *(décote renouvellement −30 % appliquée)*"
                st.info(label)

            with result_box:
                if not results:
                    st.success("✅ CONFORME — aucune anomalie.")
                    if patient_name and codes:
                        db.save_report(patient_name, codes, date_obj, raw_text)
                        st.toast("Sauvegardé dans l'historique.")
                else:
                    has_blocking = any(r["severity"] == "BLOCKING" for r in results)
                    if has_blocking:
                        st.error("⛔ NON-CONFORME (REJET)")
                    else:
                        st.warning("⚠️ ATTENTION (à vérifier)")

                    for r in results:
                        icon = "⛔" if r["severity"] == "BLOCKING" else "⚠️"
                        st.markdown(f"{icon} {r['message']}")
                        st.caption(f"Règle : {r['id']}")

                    if not has_blocking and patient_name and codes:
                        db.save_report(patient_name, codes, date_obj, raw_text)
                        st.toast("Sauvegardé (avec avertissements).")

    elif analyze_btn:
        st.error("Entrez du texte à analyser.")

# ========== ONGLET 2 : audit anti-indu ========================== #
with tab_audit:
    st.subheader("Audit anti-indu — analyse rétrospective")
    st.markdown(
        "Analyse l'historique de facturation d'un patient pour détecter les "
        "actes à risque d'indu **avant** un contrôle CPAM."
    )

    audit_patient = st.text_input(
        "Nom du patient à auditer", value=patient_name, key="audit_patient"
    )
    audit_btn = st.button("Lancer l'audit 📋", type="secondary")

    if audit_btn and audit_patient:
        with st.spinner("Analyse de l'historique..."):
            report = build_patient_report(audit_patient, db, checker)

        st.markdown(
            f"**{report.total_acts} actes analysés** · "
            f"**{len(report.risks)} risques** détectés "
            f"({report.blocking_count} REJET / {report.warning_count} ALERTE)"
        )

        if report.risk_score == 0:
            st.success("✅ Aucun risque détecté dans l'historique.")
        else:
            score_color = "red" if report.blocking_count > 0 else "orange"
            st.markdown(
                f"<span style='color:{score_color};font-weight:bold'>"
                f"Score de risque : {report.risk_score}</span>",
                unsafe_allow_html=True,
            )
            for r in sorted(report.risks, key=lambda x: x.act_date):
                with st.expander(
                    f"{'⛔' if r.severity == 'BLOCKING' else '⚠️'} "
                    f"{r.act_date} · {', '.join(r.codes)} · {r.rule_id}"
                ):
                    st.write(r.message)

        st.text_area(
            "Rapport exportable",
            value=format_report_text(report),
            height=200,
            key="audit_export",
        )

    elif audit_btn:
        st.error("Entrez un nom de patient.")

# ========== ONGLET 3 : import CSV ================================ #
with tab_csv:
    st.subheader("Import CSV — audit multi-lignes")
    st.markdown(
        "Importez un export CSV (VEGA, Orthomax, saisie manuelle). "
        "Colonnes requises : **code acte** + **date**. Colonne patient optionnelle."
    )

    uploaded = st.file_uploader(
        "Fichier CSV",
        type=["csv", "txt"],
        help="Encodages supportés : UTF-8, UTF-8-BOM, Latin-1, CP1252. "
             "Séparateurs auto-détectés : ; , \\t |",
    )
    patient_filter_csv = st.text_input(
        "Filtrer par patient (laisser vide pour auditer tous)", value=""
    )
    csv_btn = st.button("Importer et auditer 📂", type="secondary", key="csv_btn")

    if csv_btn and uploaded:
        raw_bytes = uploaded.read()
        patient_filter = patient_filter_csv.strip() or None

        with st.spinner("Import et analyse CSV..."):
            report, result = build_csv_report(raw_bytes, patient_filter, db, checker)

        # Résumé import
        st.info(result.summary())

        col_imp, col_sch = st.columns(2)
        with col_imp:
            st.metric("Lignes importées", result.ok_count)
            st.metric("Erreurs d'import", result.error_count)
        with col_sch:
            if result.schema:
                st.metric("Colonne code", result.schema.code_col or "—")
                st.metric("Colonne date", result.schema.date_col or "—")

        if result.errors:
            with st.expander(f"⚠️ {result.error_count} erreur(s) d'import (non-fatales)"):
                for e in result.errors:
                    st.caption(
                        f"Ligne {e.line_number} · [{e.field}={repr(e.value)}] : {e.reason}"
                    )

        if result.unresolved_codes:
            st.warning(
                f"Codes non reconnus dans le référentiel : "
                f"{', '.join(result.unresolved_codes)}. "
                "Ces actes sont inclus mais les règles ne s'y appliquent pas."
            )

        st.divider()

        # Rapport d'audit
        patient_label = patient_filter or "TOUS"
        st.markdown(
            f"**Rapport pour : {patient_label}** · "
            f"{report.total_acts} actes · "
            f"{len(report.risks)} risques "
            f"({report.blocking_count} REJET / {report.warning_count} ALERTE)"
        )

        if report.risk_score == 0:
            st.success("✅ Aucun risque détecté.")
        else:
            score_color = "red" if report.blocking_count > 0 else "orange"
            st.markdown(
                f"<span style='color:{score_color};font-weight:bold'>"
                f"Score de risque : {report.risk_score}</span>",
                unsafe_allow_html=True,
            )
            for r in sorted(
                report.risks,
                key=lambda x: (x.severity == "WARNING", x.act_date),
            ):
                with st.expander(
                    f"{'⛔' if r.severity == 'BLOCKING' else '⚠️'} "
                    f"{r.act_date} · {', '.join(r.codes)} · {r.rule_id}"
                ):
                    st.write(r.message)

        st.text_area(
            "Rapport exportable",
            value=format_report_text(report),
            height=200,
            key="csv_report_export",
        )

    elif csv_btn:
        st.error("Uploadez un fichier CSV.")
