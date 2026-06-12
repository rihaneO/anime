# 🛡️ Neuro-Shield — Assistant de conformité NGAP pour orthophonistes

Neuro-Shield analyse des notes d'actes (texte libre) et vérifie leur conformité
à la **NGAP** (Nomenclature Générale des Actes Professionnels) **avant** la
facturation, pour réduire les rejets de la CPAM et le risque d'indu.

> ⚠️ **Statut : prototype / preuve de concept.** Le référentiel de règles est
> partiel et à visée de démonstration. Il doit être validé par un·e
> orthophoniste ou un·e conseil en gestion de cabinet avant tout usage réel.
> Voir [`docs/STRATEGIE.md`](docs/STRATEGIE.md) pour l'analyse marché, le
> positionnement et la feuille de route.

## Ce que ça fait

1. **Extraction** (`nlp_parser.py`) : repère les codes d'actes (`AMO ...`), la
   date et l'âge du patient dans un texte libre.
2. **Contrôle** (`checker.py`) : applique un moteur de règles **typé et
   versionné** (voir plus bas) et renvoie des alertes `BLOCKING` (rejet) ou
   `WARNING` (à vérifier).
3. **Historique** (`db.py`) : stocke les actes en SQLite pour détecter les
   renouvellements de bilan à moins d'un an (décote -30 %).
4. **Interface** (`app.py`) : application Streamlit.

## Architecture

```
rules.json          Référentiel versionné (actes, coefficients, règles datées)
src/
  nlp_parser.py     Extraction texte libre -> codes / date / âge
  checker.py        Moteur de règles typé (AUCUN eval) + calcul de montant
  db.py             Historique patient (SQLite)
  app.py            Interface Streamlit
tests/              Tests unitaires (pytest)
docs/STRATEGIE.md   Analyse marché, concurrence, positionnement, GTM, roadmap
```

## Moteur de règles (v2)

- **Aucun `eval()`.** Chaque règle porte un `type` (`age_max`,
  `renouvellement`, `cumul_bilan_seance`, `cumul_seances_meme_jour`) évalué par
  une méthode Python dédiée. Plus de risque d'exécution de code arbitraire.
- **Versionnement par date d'effet.** Chaque règle a une `date_effet` / une
  `date_fin`. Le moteur n'applique que les règles en vigueur **à la date de
  l'acte** — indispensable dans un domaine où la nomenclature change à chaque
  avenant. Le référentiel est à jour de l'**avenant 21** (en vigueur le
  23/02/2026 : valeur AMO 2,60 €, nouvelles règles de cumul).

## Installation & lancement

```bash
pip install -r requirements.txt
streamlit run src/app.py
```

## Tests

```bash
python -m pytest -q
```

## Limites connues (prototype)

- Le référentiel ne couvre que quelques actes : **pas** la NGAP complète.
- Le parser de texte libre est heuristique (les codes sans préfixe `AMO`
  reposent sur des heuristiques fragiles).
- Pas d'intégration **SESAM-Vitale / FSE** : l'outil contrôle, il ne facture
  pas. La facturation réelle reste à faire dans le logiciel agréé du cabinet.
- Stockage local non chiffré : non conforme à un hébergement de données de
  santé (**HDS**) en cloud. À traiter avant toute mise en ligne.

## Licence

GPL-3.0 (voir `LICENSE`).
