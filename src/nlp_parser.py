"""
NLPParser — extraction d'actes NGAP, dates et ages en texte libre.

Architecture multi-pass :
  0. Isolation des "spans parasites" (dates, annees, ages explicites)
     -> masquage pour eviter les faux positifs lors de la detection de codes.
  A. Codes AMO explicites : regex AMO\\s*[\\d.,]+ -> normalise via Referential.
  B. Detection par libelle : score IDF-like sur les tokens du texte vs
     l'index inverse du Referential.
  Deduplication + tri par confiance decroissante.

Design decisions :
- Zero code AMO hardcode dans ce module : tout vient du Referential.
- Les fonctions module-level (extract_act_codes / extract_date /
  extract_patient_age_months) sont conservees pour la compat ascendante
  avec les tests existants ; elles deleguent vers la nouvelle API.
- Confiance [0.0 - 1.0] retournee par match : diagnostique d'extraction
  consultable dans les logs et les tests.
- Les spans AMO et les spans dates/ages ne se chevauchent jamais par
  construction (masquage en phase 0).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Literal, Optional
from dateutil.relativedelta import relativedelta

from referential import Referential, normalize_text, tokenize


# ------------------------------------------------------------------ #
# Types
# ------------------------------------------------------------------ #

Source = Literal["explicit_amo", "alias_resolved", "libelle"]
LIBELLE_CONFIDENCE_THRESHOLD = 0.55  # seuil IDF normalise


@dataclass(frozen=True)
class ExtractionMatch:
    """
    Un match de code detecte dans le texte.
    - source : canal de detection
    - confidence : 1.0 pour AMO explicite, IDF-normalise pour libelle
    - span : (start, end) dans le texte original
    """
    code: str
    source: Source
    confidence: float
    span: tuple[int, int]


@dataclass
class ParseResult:
    codes: list[str]
    act_date: Optional[date]
    age_months: Optional[int]
    matches: list[ExtractionMatch] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ #
# Patterns precompiles (module-level = un seul compile par processus)
# ------------------------------------------------------------------ #

# AMO suivi du coefficient ; gere separateur espace/tiret bas/rien,
# et virgule decimale francaise ("AMO 34,02" -> "AMO_34.02")
_RE_AMO = re.compile(
    r"\b(?:AMO)[\s_]*(\d+(?:[.,]\d+)?)\b",
    re.IGNORECASE,
)

# Date d'acte : DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY (avec annee sur 2 ou 4 chiffres)
_RE_DATE = re.compile(r"\b(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})\b")

# Date de naissance : "né le", "née le", "DOB :", etc.
_RE_DOB = re.compile(
    r"\bn[ée]{1,2}e?(?:\s+le)?\s*:?\s*(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})\b"
    r"|"
    r"\bdob\s*:?\s*(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})\b",
    re.IGNORECASE,
)

# Age en annees avec optionnel "et X mois"
_RE_AGE_ANS = re.compile(r"\b(\d{1,2})\s*ans?\b", re.IGNORECASE)
_RE_AGE_MOIS_SUFFIX = re.compile(r"\bet\s+(\d{1,2})\s*mois\b", re.IGNORECASE)
_RE_AGE_MOIS_SEUL = re.compile(r"\b(\d{1,3})\s*mois\b", re.IGNORECASE)

# Annees a 4 chiffres (19xx / 20xx) -> parasite a masquer
_RE_YEAR_4 = re.compile(r"\b(?:19|20)\d{2}\b")


def _mask_spans(text: str, spans: list[tuple[int, int]]) -> str:
    """Remplace les caracteres des spans par le marqueur NULL (preserve les positions)."""
    chars = list(text)
    for s, e in spans:
        for i in range(s, min(e, len(chars))):
            chars[i] = "\x00"
    return "".join(chars)


def _year2(y: str) -> int:
    return int("20" + y) if len(y) == 2 else int(y)


# ------------------------------------------------------------------ #
# NLPParser
# ------------------------------------------------------------------ #

class NLPParser:
    """
    Parser pilote par un Referential.
    Aucun code AMO n'est hardcode dans cette classe.
    """

    def __init__(self, ref: Referential) -> None:
        self._ref = ref

    # ------------------------------------------------------------------ #
    # API principale
    # ------------------------------------------------------------------ #

    def parse(self, text: str) -> ParseResult:
        warnings: list[str] = []

        # --- Phase 0 : date d'acte et age (inchanges par masquage) ---
        act_date = self._extract_act_date(text)
        ref_date = act_date or datetime.now().date()
        age = self._extract_age(text, ref_date)

        if act_date is None:
            warnings.append("Date non detectee : date du jour utilisee par defaut.")
        if age is None:
            warnings.append("Age patient non detecte.")

        # --- Phase 1 : construire le masque des spans parasites ---
        parasite = list(self._parasite_spans(text))
        masked = _mask_spans(text, parasite)

        # --- Phase 2 : extraction des codes ---
        matches: list[ExtractionMatch] = []
        matches.extend(self._pass_explicit_amo(masked))

        found_codes = {m.code for m in matches}
        libelle_matches = [
            m for m in self._pass_libelle(text)
            if m.code not in found_codes
        ]
        matches.extend(libelle_matches)

        # --- Phase 3 : deduplication par code, tri confiance desc ---
        deduped = _deduplicate(matches)

        # Avertit sur les codes inconnus du referentiel
        for m in deduped:
            if self._ref.get_acte(m.code) is None:
                warnings.append(
                    f"Code '{m.code}' extrait mais absent du referentiel "
                    f"(score {m.confidence:.2f}, source={m.source})."
                )

        return ParseResult(
            codes=[m.code for m in deduped],
            act_date=act_date,
            age_months=age,
            matches=deduped,
            warnings=warnings,
        )

    # ------------------------------------------------------------------ #
    # Phase 0 : extraction date et age
    # ------------------------------------------------------------------ #

    def _extract_act_date(self, text: str) -> Optional[date]:
        """
        Retourne la premiere date du texte qui n'est pas une date de naissance.
        En cas d'ambiguite, la date precedee de "fait le", "le", etc. prime.
        """
        dob_spans = {m.span() for m in _RE_DOB.finditer(text)}

        # Essaie les dates avec contexte "fait le / du" en priorite
        priority = re.compile(
            r"(?:fait\s+le|du|le|en\s+date\s+du)\s+"
            r"(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})\b",
            re.IGNORECASE,
        )
        for m in priority.finditer(text):
            if any(ds[0] <= m.start() <= ds[1] for ds in dob_spans):
                continue
            try:
                d, mo, y = int(m.group(1)), int(m.group(2)), _year2(m.group(3))
                return date(y, mo, d)
            except ValueError:
                continue

        # Fallback : premiere date hors DOB
        for m in _RE_DATE.finditer(text):
            if any(ds[0] <= m.start() <= ds[1] for ds in dob_spans):
                continue
            try:
                d, mo, y = int(m.group(1)), int(m.group(2)), _year2(m.group(3))
                return date(y, mo, d)
            except ValueError:
                continue
        return None

    def _extract_age(self, text: str, ref_date: date) -> Optional[int]:
        """
        Extraction dans l'ordre de precision decroissante :
        1. "X ans [et Y mois]"
        2. "X mois" seul
        3. "Né le DD/MM/YYYY"
        """
        # 1. Age en annees
        m_ans = _RE_AGE_ANS.search(text)
        if m_ans:
            years = int(m_ans.group(1))
            m_mo = _RE_AGE_MOIS_SUFFIX.search(text[m_ans.end(): m_ans.end() + 30])
            months = int(m_mo.group(1)) if m_mo else 0
            return years * 12 + months

        # 2. Age en mois seul
        m_mo = _RE_AGE_MOIS_SEUL.search(text)
        if m_mo:
            return int(m_mo.group(1))

        # 3. Date de naissance
        m_dob = _RE_DOB.search(text)
        if m_dob:
            # Le pattern a 2 alternatives (nee / dob) -> choisit les groupes non-None
            groups = [g for g in m_dob.groups() if g is not None]
            if len(groups) == 3:
                try:
                    dob = date(_year2(groups[2]), int(groups[1]), int(groups[0]))
                    delta = relativedelta(ref_date, dob)
                    return delta.years * 12 + delta.months
                except ValueError:
                    pass
        return None

    # ------------------------------------------------------------------ #
    # Phase 1 : spans parasites
    # ------------------------------------------------------------------ #

    def _parasite_spans(self, text: str):
        """
        Genere les spans a masquer avant la detection de codes AMO :
        dates, annees a 4 chiffres, ages numeriques.
        Utilise un generateur pour eviter de materialiser une grande liste.
        """
        seen: set[tuple[int, int]] = set()

        def emit(span: tuple[int, int]):
            if span not in seen:
                seen.add(span)
                return span
            return None

        for m in _RE_DATE.finditer(text):
            s = emit(m.span())
            if s:
                yield s
        for m in _RE_YEAR_4.finditer(text):
            s = emit(m.span())
            if s:
                yield s
        for m in _RE_AGE_ANS.finditer(text):
            s = emit(m.span())
            if s:
                yield s
        for m in _RE_AGE_MOIS_SEUL.finditer(text):
            s = emit(m.span())
            if s:
                yield s

    # ------------------------------------------------------------------ #
    # Pass A : AMO explicites
    # ------------------------------------------------------------------ #

    def _pass_explicit_amo(self, masked: str) -> list[ExtractionMatch]:
        """
        Detecte les patterns AMO explicites dans le texte masque.
        Normalise via Referential.resolve() pour obtenir le code canonique.
        Confiance = 1.0 si le code est dans le referentiel, 0.75 sinon.
        """
        results: list[ExtractionMatch] = []
        for m in _RE_AMO.finditer(masked):
            raw_num = m.group(1).replace(",", ".")
            raw_code = f"AMO_{raw_num}"
            canonical = self._ref.resolve(raw_code)
            if canonical:
                source: Source = (
                    "explicit_amo" if raw_code == canonical else "alias_resolved"
                )
                results.append(ExtractionMatch(
                    code=canonical,
                    source=source,
                    confidence=1.0,
                    span=m.span(),
                ))
            else:
                # Code inconnu : on le garde avec confiance reduite
                results.append(ExtractionMatch(
                    code=raw_code,
                    source="explicit_amo",
                    confidence=0.75,
                    span=m.span(),
                ))
        return results

    # ------------------------------------------------------------------ #
    # Pass B : detection par libelle (IDF-like)
    # ------------------------------------------------------------------ #

    def _pass_libelle(self, text: str) -> list[ExtractionMatch]:
        """
        Calcule un score IDF-like pour chaque acte du referentiel en cherchant
        ses tokens dans le texte.

        score(code) = sum(IDF(t) for t in tokens_text & tokens_libelle(code))

        On normalise par le score max pour obtenir une confiance [0, 1].
        Un seuil (LIBELLE_CONFIDENCE_THRESHOLD) filtre le bruit.
        """
        text_tokens = tokenize(text)
        if not text_tokens:
            return []

        idx = self._ref.token_index()
        scores: dict[str, float] = {}
        for token in text_tokens:
            for code, weight in idx.get(token, []):
                scores[code] = scores.get(code, 0.0) + weight

        if not scores:
            return []

        max_score = max(scores.values())
        results: list[ExtractionMatch] = []
        for code, score in scores.items():
            conf = score / max_score
            if conf >= LIBELLE_CONFIDENCE_THRESHOLD:
                results.append(ExtractionMatch(
                    code=code,
                    source="libelle",
                    confidence=round(conf, 4),
                    span=(0, len(text)),
                ))
        return results


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _deduplicate(matches: list[ExtractionMatch]) -> list[ExtractionMatch]:
    """
    Deduplication par code canonique.
    En cas de doublon, garde le match de confiance la plus elevee.
    """
    best: dict[str, ExtractionMatch] = {}
    for m in matches:
        if m.code not in best or m.confidence > best[m.code].confidence:
            best[m.code] = m
    return sorted(best.values(), key=lambda x: -x.confidence)


# ------------------------------------------------------------------ #
# API module-level (compat ascendante avec les anciens tests et app.py)
# ------------------------------------------------------------------ #

import os
import functools


@functools.lru_cache(maxsize=1)
def _default_ref() -> Referential:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return Referential(os.path.join(base, "rules.json"))


def extract_act_codes(text: str, ref: Optional[Referential] = None) -> list[str]:
    """Compat. Preferer NLPParser(ref).parse(text).codes directement."""
    return NLPParser(ref or _default_ref()).parse(text).codes


def extract_date(text: str) -> Optional[date]:
    return NLPParser(_default_ref())._extract_act_date(text)


def extract_patient_age_months(
    text: str, ref_date: Optional[date] = None
) -> Optional[int]:
    if ref_date is None:
        ref_date = datetime.now().date()
    return NLPParser(_default_ref())._extract_age(text, ref_date)
