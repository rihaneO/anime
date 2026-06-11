# Neuro-Shield — Analyse stratégique, positionnement & go-to-market

> Document de travail. Toutes les données marché ci-dessous ont été vérifiées
> par recherche web en juin 2026 ; les sources sont listées en fin de document.
> Les chiffres réglementaires (NGAP / avenant 21) doivent être reconfirmés
> auprès des sources officielles avant toute décision.

---

## 1. Résumé exécutif (le verdict)

Neuro-Shield s'attaque à un **vrai problème** : les orthophonistes libéraux
subissent des **rejets de facturation** et des **demandes d'indus** de la CPAM
liés à des erreurs de cotation NGAP. Mais trois constats tempèrent fortement
l'opportunité telle que le prototype la formule :

1. **Le « contrôle de cotation avant facturation » n'est pas neuf.** Il est déjà
   une fonctionnalité **mature et déployée** chez les concurrents — notamment
   **Albus** (infirmiers) dont le « moteur de cotations intelligent » fait
   exactement cela, et **Topaze** (kiné/ortho) qui signale les incompatibilités
   NGAP immédiatement. Chez les orthophonistes, **VEGA**, **Orthomax**,
   **Ortho+4000** et **Acteur.fr** intègrent la cotation NGAP.
2. **Le marché est une niche** : ~21 400 orthophonistes libéraux en France,
   croissance ~1 %/an. Plafond de revenu réaliste limité.
3. **Le prototype est déjà périmé** : il code des règles d'avant l'**avenant 21**
   (en vigueur le 23/02/2026), qui a changé la valeur AMO (2,60 €) et les règles
   de cumul.

**Conclusion :** attaquer le contrôle de cotation « en saisie » de face = suicide
concurrentiel. Le seul angle défendable est un **second avis indépendant
anti-indu, a posteriori**, distribué via la communauté professionnelle, en
surfant la confusion réglementaire de l'avenant 21.

---

## 2. Marché (chiffres vérifiés)

| Indicateur | Valeur | Source |
|---|---|---|
| Orthophonistes (exercice total, fin 2024) | 25 161 | DREES |
| Dont activité libérale ou mixte | 21 418 | DREES / Assurance Maladie |
| Croissance annuelle des effectifs | ~1 %/an | Assurance Maladie |
| Quotas étudiants 2024 → 2030 | 975 → 1 463 | Proposition de loi démographie |

**Taille de marché (ordre de grandeur).** À 20–40 €/mois/praticien et même en
captant une part agressive (irréaliste face aux incumbents), le plafond se
compte en **quelques millions d'euros d'ARR**. Ce n'est **pas** un marché de
licorne. Deux options stratégiques :

- **Bootstrap rentable de niche** : viser quelques milliers d'orthophonistes,
  produit ultra-spécialisé, coûts maîtrisés.
- **Tête de pont** : l'ortho comme point d'entrée vers IDEL / kiné /
  sages-femmes (même logique NGAP, marchés 5–10× plus gros) — mais Albus et
  Topaze y sont déjà installés.

---

## 3. Le problème (réel et documenté)

Motifs récurrents de **rejets** et d'**indus** en orthophonie (sources FNO,
Recouv-lib) :

- Cotation erronée / décalée du diagnostic (acte complexe facturé pour un
  tableau qui ne le justifie pas, ou inversement).
- Fréquence facturée incohérente avec le projet thérapeutique (ex. 3 séances/
  semaine quand le bilan en prévoit 1).
- Doublons de facture ; facturation pendant une hospitalisation ; erreur de date.
- Non-respect des règles de télésoin.
- Renouvellement de bilan sans la **décote de 30 %**.

Un **indu** est une somme déjà versée que la CPAM réclame après contrôle. La
douleur est donc double : **trésorerie** (rejet immédiat) et **risque rétroactif**
(indu sur plusieurs mois/années). C'est ce second volet qui est **mal couvert**
par les logiciels de saisie — et c'est là que se trouve l'angle.

---

## 4. Concurrence (vérifiée)

| Catégorie | Acteurs | Ce qu'ils font | Menace |
|---|---|---|---|
| Logiciels cabinet ortho | VEGA, Orthomax (Topaze), Ortho+4000 (Cegedim), Acteur.fr, DrSanté | Agenda + FSE + télétransmission SESAM-Vitale + cotation NGAP | 🔴 Frontale |
| Moteurs de cotation « intelligents » | **Albus** (IDEL), Topaze (kiné) | Contrôle de conformité temps réel avant télétransmission | 🔴 = cœur de Neuro-Shield, déjà fait |
| Vague IA ortho 2026 | myCR, OrthoVox, Orthomax SmartOrdo | **Rédaction de bilans** par IA, scan d'ordonnance | 🟠 Adjacente (capte l'attention/budget « IA ») |

**Insight clé :** la vague IA 2026 chez les orthophonistes vise la **rédaction de
bilans** (réduire 2 h → 20 min), **pas** la conformité de facturation. Le terrain
« IA + conformité NGAP ortho » en standalone est donc relativement vide — mais
le contrôle de cotation « en saisie » est, lui, déjà couvert par les logiciels
cabinet. D'où le positionnement « audit a posteriori » plutôt que « saisie ».

---

## 5. Positionnement recommandé (les deux wedges)

### Wedge A — La fenêtre « Avenant 21 » (porte d'entrée, temporaire)
Toute la profession est dans la confusion depuis le 23/02/2026 (nouvelles règles
de cumul, nouvelles durées de séance, nouveaux coefficients, AMO à 2,60 €). Un
outil **gratuit, single-purpose** — « ta cotation est-elle conforme post-avenant
21 ? » — répond à une douleur **aiguë et datée**, et **viralise** dans les
groupes de la profession. Objectif : acquisition d'emails, pas monétisation.

### Wedge B — L'audit anti-indu indépendant (produit pérenne)
Les logiciels cabinet vérifient ce que l'on **saisit dans leur formulaire**.
Personne ne propose un **second avis indépendant** qui analyse une facturation
**déjà émise** ou des notes brutes pour détecter le risque d'**indu avant un
contrôle CPAM**. Value prop : *« Sur tes 3 derniers mois, voici les N cotations à
risque d'indu, et pourquoi. »* C'est ici que l'**input texte libre** devient un
**atout** (analyser l'existant) plutôt qu'un handicap (re-saisir ce que le
logiciel cabinet structure déjà).

> **Règle d'or de positionnement :** ne pas concurrencer la *saisie* (perdu
> d'avance contre VEGA/Albus/Topaze). Se placer en *couche d'audit/assurance*
> au-dessus de l'existant.

---

## 6. Le produit : MVP réel de A à Z

Le prototype actuel est une **bonne preuve d'architecture** (couches séparées,
tests, règles externalisées) mais ~5 % d'un produit. MVP commercialisable :

### Doit avoir (P0)
- **Référentiel NGAP versionné** par date d'effet (fait : `rules.json` v2,
  moteur sans `eval`). À **étendre** à la nomenclature réelle, **validé par un
  expert métier**.
- **Couverture des vrais motifs d'indu** (cf. §3), pas seulement 3 règles.
- **Mode audit a posteriori** : importer un historique d'actes (CSV/export du
  logiciel cabinet) et produire un rapport de risque.
- **Authentification** + isolation des données par praticien.
- **Conformité données de santé** (voir §8).

### Devrait avoir (P1)
- Calcul de montant et de décote (fait : `compute_amount`).
- Explication pédagogique de chaque alerte (texte + référence réglementaire).
- Mise à jour des règles **sans redéploiement** (le versionnement le permet déjà).

### Pourrait avoir (P2)
- Import direct depuis les exports VEGA/Orthomax.
- Veille réglementaire automatique (alerte quand un avenant change une règle).

### Ne fera pas (au moins au départ)
- **Pas** de facturation / télétransmission SESAM-Vitale (chasse gardée des
  logiciels agréés ; coût d'agrément prohibitif). Neuro-Shield **contrôle**, il
  ne **facture pas**.

---

## 7. Feuille de route

| Phase | Durée indic. | Livrable | Objectif |
|---|---|---|---|
| 0 — Assainissement | fait | Sécurité (`eval` supprimé), deps, `.gitignore`, référentiel v2 versionné, tests verts | Base saine |
| 1 — Wedge A | 2–4 sem. | Calculateur « conformité avenant 21 » gratuit + capture email | Acquisition + validation du pain |
| 2 — Validation métier | 1–2 mois | Référentiel élargi **validé par un·e ortho-conseil** | Crédibilité réglementaire |
| 3 — Wedge B (MVP payant) | 2–4 mois | Audit a posteriori (import historique → rapport d'indu) + auth + HDS | Premier produit monétisable |
| 4 — Distribution | continu | Partenariat FNO / communautés, contenu | Croissance |

---

## 8. Conformité (bloquants légaux)

- **HDS (Hébergeur de Données de Santé)** : obligatoire dès qu'on **stocke/traite
  des données patients en cloud**. Le stockage local (SQLite) en est exempt mais
  **interdit le SaaS**. → héberger chez un hébergeur **certifié HDS** avant toute
  mise en ligne avec données réelles.
- **RGPD** : données de santé = catégorie particulière (registre, base légale,
  durées de conservation, DPO selon volume).
- **AI Act** : échéance du 2 août 2026 pour les systèmes à haut risque. Un
  **moteur de règles déterministe** (notre choix) **évite** la qualification
  « IA à haut risque » ; argument fort pour **rester sur des règles**, pas du ML
  opaque, sur la partie conformité.
- **Anonymisation au possible** : pour le mode audit, travailler sur des
  identifiants pseudonymisés réduit fortement la surface réglementaire.

---

## 9. Go-to-market

- **Canal n°1 : la communauté.** La **FNO** (Fédération Nationale des
  Orthophonistes) et les groupes Facebook de la profession sont le levier
  d'acquisition. Communauté soudée, bouche-à-oreille fort.
- **Acquisition par l'outil gratuit** (Wedge A) → liste d'emails qualifiés →
  conversion vers l'audit payant (Wedge B).
- **Tarification** : freemium. Gratuit = vérification ponctuelle ; payant =
  audit d'historique + suivi + mises à jour réglementaires. Cible 20–40 €/mois.
- **Contenu** : guides « éviter les indus », décryptage des avenants — capte le
  SEO sur des requêtes à forte intention (cf. l'écosystème de blogs existant).
- **Le vrai risque** : VEGA/Topaze peuvent ajouter la feature en une release. Le
  seul *moat* possible = spécialisation extrême + rapidité de mise à jour
  réglementaire + confiance communautaire.

---

## 10. Risques principaux

| Risque | Gravité | Mitigation |
|---|---|---|
| Incumbents intègrent l'audit anti-indu | Élevée | Vitesse, communauté, focus mono-métier |
| Référentiel faux → faux rejets → perte de confiance | Critique | Validation experte obligatoire ; afficher le caractère « aide à la décision » |
| Marché trop petit pour financer la R&D | Élevée | Bootstrap ; extension multi-métiers à terme |
| Contraintes HDS/RGPD ralentissent le SaaS | Moyenne | Démarrer local/pseudonymisé ; HDS en phase 3 |
| Dépendance à la stabilité réglementaire | Moyenne | Versionnement par date d'effet (déjà en place) |

---

## 11. Sources (vérifiées, juin 2026)

- Assurance Maladie / DREES — démographie des orthophonistes libéraux :
  https://www.assurance-maladie.ameli.fr/etudes-et-donnees/zoom-ps-orthophonistes-liberaux
- ameli.fr — NGAP orthophonistes (facturation & codage) :
  https://www.ameli.fr/orthophoniste/exercice-liberal/facturation-remuneration/ngap
- ameli.fr — Avenant 21, entrée en vigueur le 23/02/2026 :
  https://www.ameli.fr/orthophoniste/actualites/convention-nationale-entree-en-vigueur-des-mesures-de-l-avenant-21
- Légifrance — Avis relatif à l'avenant n°21 :
  https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000052178355
- FNO — La NGAP / Les demandes d'indus de la CPAM :
  https://fno.fr/la-nomenclature-generale-des-actes-professionnels-ngap/ ·
  https://fno.fr/les-demandes-dindus-de-la-cpam/
- Recouv-lib — Indus CPAM & rejets/impayés en orthophonie :
  https://www.recouv-lib.fr/indus-cpam-comment-les-eviter-et-les-gerer-en-tant-que-professionnel-de-sante/ ·
  https://www.recouv-lib.fr/rejets-impayes-orthophonie/
- Albus — moteur de cotations intelligent (concurrent clé, IDEL) :
  https://www.albus.fr/fonctionnalites/moteur-de-cotations/
- Topaze — logiciel ortho/kiné, incompatibilités NGAP :
  https://www.topaze.com/
- VEGA — logiciel orthophoniste & cotation :
  https://www.vega-logiciel.fr/orthophoniste/
- Comparatifs logiciels orthophonistes 2026 :
  https://www.lonasante.com/logiciel-orthophoniste/ ·
  https://bilan-ortho.fr/blog/logiciels-orthophonistes-2026
- Vague IA ortho 2026 (rédaction de bilans) : myCR, OrthoVox, Orthomax SmartOrdo
  (cf. https://orthovox.fr/ , https://mycr.fr/blog/meilleur-logiciel-orthophoniste-2026)
