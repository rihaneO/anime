"""
Referential — couche d'acces au referentiel NGAP (rules.json).

Responsabilite unique : encapsuler le fichier de regles et exposer
une API typee, immuable et pilotable par les tests.

Points techniques :
- Index inverse TF-IDF-like sur les libelles pour la detection en texte libre.
  Poids d'un token = N / df(token) : les tokens rares (distinctifs d'un seul
  acte) recoivent un poids eleve, les tokens frequents ("bilan", "reeducation")
  recoivent un poids faible.
- Aucune regex nommee, aucun code AMO hardcode dans ce module.
- Instanciation en O(N actes) ; toutes les structures de donnees sont buildees
  une seule fois a l'init et mises en cache (frozen dataclasses + dicts).
"""

from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional


# ------------------------------------------------------------------ #
# Normalisation texte (partagee avec NLPParser)
# ------------------------------------------------------------------ #

_WORD_SPLITTER = re.compile(r"[\s\(\)\[\]/,;:\.\-_'’‘]+")

_DOMAIN_STOPWORDS = frozenset({
    # Determinants / prepositions
    "de", "du", "la", "le", "les", "des", "et", "un", "une", "a", "en",
    "ou", "par", "sur", "dans", "avec", "pour", "qui", "que", "au", "aux",
    "d", "l", "an", "son", "ses", "leur",
    # Termes trop generiques dans ce referentiel
    "acte", "bilan", "reeducation", "seance", "min", "env",
})


def normalize_text(text: str) -> str:
    """Lowercase + suppression des accents Unicode."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def tokenize(text: str) -> frozenset[str]:
    """Tokenise le texte normalise et retire les stopwords et tokens courts."""
    words = _WORD_SPLITTER.split(normalize_text(text))
    return frozenset(w for w in words if w and w not in _DOMAIN_STOPWORDS and len(w) > 2)


# ------------------------------------------------------------------ #
# Dataclasses du referentiel
# ------------------------------------------------------------------ #

@dataclass(frozen=True)
class Acte:
    code: str
    libelle: str
    act_type: str              # "bilan" | "reeducation"
    coefficient: float
    duree_min_m: Optional[int]    # duree minimale en minutes
    duree_cible_m: Optional[int]  # duree cible en minutes
    age_max_mois: Optional[int]


@dataclass(frozen=True)
class Regle:
    id: str
    nom: str
    rule_type: str
    date_effet: Optional[date]
    date_fin: Optional[date]
    severite: str
    message: str
    params: dict


@dataclass(frozen=True)
class LettreCle:
    code: str
    valeur_metropole: float
    date_effet: Optional[date]


# ------------------------------------------------------------------ #
# Referentiel
# ------------------------------------------------------------------ #

class Referential:
    """
    Charge rules.json une fois, expose une API typee.
    Thread-safe en lecture (aucune mutation apres __init__).
    """

    def __init__(self, path: str) -> None:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Referentiel introuvable : {path}")
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)

        self._raw = raw
        self._aliases: dict[str, str] = raw.get("aliases", {})
        self._actes: dict[str, Acte] = self._parse_actes(raw)
        self._regles: list[Regle] = self._parse_regles(raw)
        self._lettre_cle: LettreCle = self._parse_lettre_cle(raw)

        # Index inverse libelles : token -> [(code, weight)]
        # Construit en O(N*T) avec N=actes, T=tokens par libelle.
        self._token_index: dict[str, list[tuple[str, float]]] = (
            self._build_token_index()
        )

    # ------------------------------------------------------------------ #
    # Parseurs internes
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_date(s: Optional[str]) -> Optional[date]:
        if not s:
            return None
        return datetime.strptime(s, "%Y-%m-%d").date()

    def _parse_actes(self, raw: dict) -> dict[str, Acte]:
        out: dict[str, Acte] = {}
        for code, d in raw.get("actes", {}).items():
            out[code] = Acte(
                code=code,
                libelle=d.get("libelle", ""),
                act_type=d.get("type", ""),
                coefficient=float(d.get("coefficient", 0)),
                duree_min_m=d.get("duree_minutes_min"),
                duree_cible_m=d.get("duree_minutes_cible"),
                age_max_mois=d.get("contraintes", {}).get("age_max_mois"),
            )
        return out

    def _parse_regles(self, raw: dict) -> list[Regle]:
        out: list[Regle] = []
        for r in raw.get("regles", []):
            out.append(Regle(
                id=r["id"],
                nom=r.get("nom", ""),
                rule_type=r.get("type", ""),
                date_effet=self._parse_date(r.get("date_effet")),
                date_fin=self._parse_date(r.get("date_fin")),
                severite=r.get("severite", "WARNING"),
                message=r.get("message", ""),
                params=r.get("params", {}),
            ))
        return out

    def _parse_lettre_cle(self, raw: dict) -> LettreCle:
        lc = raw.get("lettre_cle", {})
        return LettreCle(
            code=lc.get("code", "AMO"),
            valeur_metropole=float(lc.get("valeur_eur", {}).get("metropole", 0)),
            date_effet=self._parse_date(lc.get("date_effet")),
        )

    def _build_token_index(self) -> dict[str, list[tuple[str, float]]]:
        """
        Index inverse IDF : les tokens rares dans le corpus des libelles
        recoivent un poids eleve.

        IDF(t) = log(1 + N / df(t))
        ou N = nombre d'actes, df(t) = nombre d'actes contenant le token t.
        L'ajout de 1 dans le log lisse les tokens tres rares.
        """
        per_acte: dict[str, frozenset[str]] = {
            code: tokenize(acte.libelle)
            for code, acte in self._actes.items()
        }
        n = len(per_acte) or 1

        doc_freq: dict[str, int] = {}
        for tokens in per_acte.values():
            for t in tokens:
                doc_freq[t] = doc_freq.get(t, 0) + 1

        index: dict[str, list[tuple[str, float]]] = {}
        for code, tokens in per_acte.items():
            for token in tokens:
                idf = math.log(1 + n / doc_freq[token])
                index.setdefault(token, []).append((code, idf))
        return index

    # ------------------------------------------------------------------ #
    # API publique
    # ------------------------------------------------------------------ #

    def resolve(self, raw: str) -> Optional[str]:
        """
        Resout un code brut vers le code canonique du referentiel.

        Ordre de resolution :
        1. Le code est deja canonique (existe dans les actes).
        2. Alias exact.
        3. Alias sans prefixe "AMO_".
        Retourne None si aucune resolution possible.
        """
        if raw in self._actes:
            return raw
        canonical = self._aliases.get(raw)
        if canonical and canonical in self._actes:
            return canonical
        stripped = raw.removeprefix("AMO_")
        canonical = self._aliases.get(stripped)
        if canonical and canonical in self._actes:
            return canonical
        return None

    def get_acte(self, code: str) -> Optional[Acte]:
        return self._actes.get(code)

    def actes_by_type(self, act_type: str) -> list[str]:
        return [c for c, a in self._actes.items() if a.act_type == act_type]

    def all_codes(self) -> list[str]:
        return list(self._actes.keys())

    def regles(self) -> list[Regle]:
        return self._regles

    def lettre_cle(self) -> LettreCle:
        return self._lettre_cle

    def schema_version(self) -> str:
        return self._raw.get("schema_version", "?")

    def token_index(self) -> dict[str, list[tuple[str, float]]]:
        return self._token_index

    def raw(self) -> dict:
        return self._raw
