import streamlit as st
from datetime import datetime
from nlp_parser import extract_act_codes, extract_date, extract_patient_age_months
from checker import Checker
from db import Database
import os

# Initialize DB and Checker
# Path resolution to ensure files are found regardless of where app is run from
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES_PATH = os.path.join(BASE_DIR, 'rules.json')
DB_PATH = os.path.join(BASE_DIR, 'neuro_shield.db')

db = Database(db_path=DB_PATH)
checker = Checker(rules_path=RULES_PATH, db=db)

st.set_page_config(page_title="Neuro-Shield", page_icon="🛡️", layout="wide")

st.title("🛡️ Neuro-Shield: Assistant Conformité NGAP")
st.markdown("### Orthophonistes : Vérifiez vos facturations en un clic")

# Sidebar - History
st.sidebar.header("Historique Patient")
patient_name_input = st.sidebar.text_input("Nom du Patient (pour historique)", value="")

if patient_name_input:
    history = db.get_history(patient_name_input)
    if history:
        st.sidebar.markdown(f"**Derniers actes pour {patient_name_input}:**")
        for code, date_str, text in history[:5]: # Show last 5
            st.sidebar.text(f"{date_str}: {code}")
    else:
        st.sidebar.info("Aucun historique trouvé.")

# Main Interface
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Rapport Patient")
    raw_text = st.text_area(
        "Collez ici vos notes (Bilan, Séance, etc.)",
        height=200,
        placeholder="Ex: Bilan langage oral AMO 34. Patient Thomas, 4 ans. Fait le 12/02/2026."
    )

    analyze_btn = st.button("Lancer l'Analyse 🔍", type="primary")

with col2:
    st.subheader("Résultats")
    result_container = st.container()

if analyze_btn and raw_text:
    # 1. Parsing
    with st.spinner("Analyse en cours..."):
        codes = extract_act_codes(raw_text)
        date_obj = extract_date(raw_text)

        # If date is not found, default to today but warn?
        # Checker uses today if None.
        if not date_obj:
            date_obj = datetime.now().date()
            st.warning("Date non détectée, utilisation de la date du jour.")

        age_months = extract_patient_age_months(raw_text, ref_date=date_obj)

        parsed_data = {
            'codes': codes,
            'date': date_obj,
            'age_months': age_months
        }

        # Display parsed info
        st.info(f"**Données extraites :**\n\n"
                f"- Actes: {', '.join(codes) if codes else 'Aucun'}\n"
                f"- Date: {date_obj}\n"
                f"- Age: {f'{age_months} mois' if age_months is not None else 'Non détecté'}")

        # 2. Checking
        # We need patient_id for history check in Checker
        # If user didn't input name in sidebar, we can't check history reliably unless we parse name.
        # MVP: rely on sidebar input or maybe parsing name (complex).
        # Let's use sidebar input as the ID.

        results = checker.check(parsed_data, patient_id=patient_name_input)

        # 3. Display Results
        with result_container:
            if not results:
                st.success("✅ **CONFORME** - Aucune anomalie détectée.")
                # Save to DB if valid and we have patient name
                if patient_name_input and codes:
                    db.save_report(patient_name_input, codes, date_obj, raw_text)
                    st.toast("Rapport sauvegardé dans l'historique.")
            else:
                has_blocking = any(r['severity'] == 'BLOCKING' for r in results)

                if has_blocking:
                    st.error("⛔ **NON-CONFORME (REJET)**")
                else:
                    st.warning("⚠️ **ATTENTION (ALERTE)**")

                for r in results:
                    icon = "⛔" if r['severity'] == 'BLOCKING' else "⚠️"
                    st.markdown(f"**{icon} {r['message']}**")
                    st.caption(f"Règle: {r['id']}")

                # Still save to DB? Usually we only save executed acts.
                # If rejected, maybe not.
                # Prompt implies "Compliance Engine... before they send it".
                # Let's NOT save rejected ones to history (as they shouldn't happen),
                # OR save them with a flag?
                # DB `acts_history` implies valid history.
                # However, if it's just a warning (orange), they might proceed.
                # Let's save if only Warnings?
                if not has_blocking and patient_name_input and codes:
                     db.save_report(patient_name_input, codes, date_obj, raw_text)
                     st.toast("Rapport sauvegardé (avec avertissements).")

elif analyze_btn and not raw_text:
    st.error("Veuillez entrer du texte à analyser.")
