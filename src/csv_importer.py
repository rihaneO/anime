"""
CSVImporter — import d'historiques de facturation en CSV.

Cible : exports bruts des logiciels cabinet (VEGA, Orthomax, etc.)
ou saisies manuelles. Format completement variable ; le module detecte
automatiquement l'encodage, le separateur et le schema de colonnes.

Architecture :
- DetectedSchema     : resultat de la detection de colonnes.
- ImportRow          : une ligne normalisee et validee.
- ImportResult       : rapport complet de l'import (lignes OK + erreurs).
- CSVImporter        : orchestrateur.

Points techniques :
- Detection d'encodage : chardet si disponible, sinon fallback sequentiel
  (utf-8-sig -> utf-8 -> latin-1 -> cp1252). Couvre 99 % des exports
  de logiciels francais.
- Detection du separateur : scoring sur les 5 premieres lignes pour
  les candidats ; , ; \\t | . Pas de lib externe requise.
- Detection de schema : normalisation des noms de colonnes (lower + sans
  accents) et correspondance contre des sets d'alias connus.
- Detection de format de date : 8 patterns couvrant DD/MM/YYYY,
  YYYY-MM-DD, D/M/YY, etc.
- Collecte d'erreurs non-fatale : toutes les erreurs de lignes sont
  rapportees avec numero de ligne, colonne et raison.
- Normalisation des codes : via Referential.resolve() -> zero hardcode.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import IO, Iterator, Optional

from referential import Referential


# ------------------------------------------------------------------ #
# Constantes de detection de schema
# ------------------------------------------------------------------ #

_PATIENT_ALIASES = frozenset({
    "patient", "nom", "name", "patient_name", "nom_patient",
    "nom_prenom", "identifiant", "id_patient", "ref_patient",
    "beneficiaire", "assuré", "assure",
})

_CODE_ALIASES = frozenset({
    "code", "acte", "cotation", "act_code", "code_acte",
    "code_amo", "amo", "nomenclature", "libelle_acte",
    "actes", "cotations",
})

_DATE_ALIASES = frozenset({
    "date", "date_acte", "act_date", "date_soin", "date_seance",
    "date_bilan", "date_facture", "date_facturation", "date_prestation",
    "jour", "day",
})

# Formats de date supportes, du plus specifique au plus ambigu
_DATE_FORMATS = [
    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
    "%Y-%m-%d", "%Y/%m/%d",
    "%d/%m/%y", "%d-%m-%y",
    "%Y%m%d",
]

# Candidats separateurs ; l'ordre n'a pas d'importance (on vote)
_SEP_CANDIDATES = [";", ",", "\t", "|"]

# Encodages testes dans l'ordre
_ENCODINGS = ["utf-8-sig", "utf-8", "latin-1", "cp1252"]


# ------------------------------------------------------------------ #
# Types
# ------------------------------------------------------------------ #

@dataclass(frozen=True)
class DetectedSchema:
    patient_col: Optional[str]
    code_col: Optional[str]
    date_col: Optional[str]
    extra_cols: list[str]


@dataclass(frozen=True)
class ImportRow:
    line_number: int
    patient_id: str
    act_code: str           # code canonique (resolu via referentiel)
    act_date: date
    raw: dict[str, str]     # ligne originale avant transformation


@dataclass
class RowError:
    line_number: int
    field: str
    value: str
    reason: str


@dataclass
class ImportResult:
    rows: list[ImportRow] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
    schema: Optional[DetectedSchema] = None
    encoding: str = "unknown"
    separator: str = ","
    total_lines: int = 0

    @property
    def ok_count(self) -> int:
        return len(self.rows)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def unresolved_codes(self) -> list[str]:
        """Codes extraits non reconnus par le referentiel."""
        return list({r.act_code for r in self.rows if r.act_code.startswith("_UNK_")})

    def summary(self) -> str:
        return (
            f"{self.total_lines} lignes lues · {self.ok_count} importees · "
            f"{self.error_count} erreurs · "
            f"encodage={self.encoding} sep={repr(self.separator)}"
        )


# ------------------------------------------------------------------ #
# Fonctions utilitaires
# ------------------------------------------------------------------ #

def _normalize_colname(name: str) -> str:
    """Lowercase + suppression accents + suppression espaces/tirets."""
    nfkd = unicodedata.normalize("NFKD", name.lower())
    ascii_s = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[\s\-_]+", "_", ascii_s).strip("_")


def _detect_encoding(raw_bytes: bytes) -> str:
    """
    Tente chardet d'abord (si disponible), sinon essaie la liste _ENCODINGS
    en sequence et retourne le premier qui decode sans erreur.
    """
    try:
        import chardet
        result = chardet.detect(raw_bytes[:4096])
        if result and result.get("confidence", 0) > 0.75:
            return result["encoding"] or "utf-8"
    except ImportError:
        pass

    for enc in _ENCODINGS:
        try:
            raw_bytes.decode(enc)
            return enc
        except (UnicodeDecodeError, LookupError):
            continue
    return "utf-8"  # fallback ultime


def _detect_separator(sample_lines: list[str]) -> str:
    """
    Vote par comptage de consistance :
    pour chaque candidat, calcule l'ecart-type du nombre d'occurrences
    par ligne. Le candidat le plus consistant (ecart-type minimal) et
    avec au moins 1 occurrence par ligne gagne.
    """
    import statistics

    best_sep = ","
    best_score = float("inf")

    for sep in _SEP_CANDIDATES:
        counts = [line.count(sep) for line in sample_lines if line.strip()]
        if not counts or max(counts) == 0:
            continue
        avg = statistics.mean(counts)
        if avg < 1:
            continue
        stddev = statistics.pstdev(counts)
        # Score = ecart-type / moyenne (coefficient de variation, plus bas = meilleur)
        cv = stddev / avg if avg else float("inf")
        if cv < best_score:
            best_score = cv
            best_sep = sep

    return best_sep


def _parse_date(value: str) -> Optional[date]:
    """Essaie les formats de date connus dans l'ordre. Retourne None si aucun match."""
    value = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _detect_schema(headers: list[str]) -> DetectedSchema:
    """
    Mappe les noms de colonnes bruts vers les roles semantiques attendus.
    Utilise la normalisation pour etre tolerant a la casse / accents.
    """
    norm_to_raw: dict[str, str] = {_normalize_colname(h): h for h in headers}
    extra: list[str] = []

    def find(aliases: frozenset[str]) -> Optional[str]:
        for norm, raw in norm_to_raw.items():
            if norm in aliases:
                return raw
        return None

    patient_col = find(_PATIENT_ALIASES)
    code_col = find(_CODE_ALIASES)
    date_col = find(_DATE_ALIASES)

    mapped = {c for c in (patient_col, code_col, date_col) if c}
    extra = [h for h in headers if h not in mapped]

    return DetectedSchema(
        patient_col=patient_col,
        code_col=code_col,
        date_col=date_col,
        extra_cols=extra,
    )


# ------------------------------------------------------------------ #
# CSVImporter
# ------------------------------------------------------------------ #

class CSVImporter:
    """
    Importe un fichier CSV d'historique de facturation.

    Usage :
        importer = CSVImporter(ref)
        result = importer.import_bytes(raw_bytes)
        # ou
        result = importer.import_file("export.csv")
    """

    def __init__(self, ref: Referential) -> None:
        self._ref = ref

    # ------------------------------------------------------------------ #
    # API publique
    # ------------------------------------------------------------------ #

    def import_bytes(self, raw: bytes) -> ImportResult:
        """Importe depuis des bytes bruts (utile avec st.file_uploader)."""
        encoding = _detect_encoding(raw)
        text = raw.decode(encoding, errors="replace")
        return self._import_text(text, encoding=encoding)

    def import_file(self, path: str) -> ImportResult:
        """Importe depuis un chemin de fichier."""
        with open(path, "rb") as fh:
            raw = fh.read()
        return self.import_bytes(raw)

    def import_stream(self, stream: IO[bytes]) -> ImportResult:
        """Importe depuis un stream binaire."""
        return self.import_bytes(stream.read())

    # ------------------------------------------------------------------ #
    # Pipeline interne
    # ------------------------------------------------------------------ #

    def _import_text(self, text: str, encoding: str = "utf-8") -> ImportResult:
        result = ImportResult(encoding=encoding)
        lines = text.splitlines()

        # Cas degenere : fichier vide
        if not lines:
            result.errors.append(RowError(0, "file", "", "Fichier vide."))
            return result

        # Detection separateur sur les 10 premieres lignes
        sep = _detect_separator(lines[:10])
        result.separator = sep

        reader = csv.DictReader(io.StringIO(text), delimiter=sep)

        # Recupere les en-tetes (DictReader les resout a la premiere iteration)
        try:
            headers = reader.fieldnames or []
        except Exception as exc:
            result.errors.append(RowError(1, "header", "", f"Erreur lecture en-tete : {exc}"))
            return result

        schema = _detect_schema(list(headers))
        result.schema = schema

        # Validation schema : au minimum code + date sont requis
        missing = []
        if not schema.code_col:
            missing.append("colonne code acte")
        if not schema.date_col:
            missing.append("colonne date")
        if missing:
            result.errors.append(RowError(
                1, "schema", str(headers),
                f"Schema incomplet : colonnes manquantes : {', '.join(missing)}. "
                f"Colonnes detectees : {', '.join(str(h) for h in headers)}."
            ))
            return result

        # Iteration ligne par ligne
        for line_no, row in enumerate(reader, start=2):
            result.total_lines += 1
            parsed = self._parse_row(line_no, row, schema)
            if isinstance(parsed, ImportRow):
                result.rows.append(parsed)
            else:
                result.errors.extend(parsed)

        return result

    def _parse_row(
        self,
        line_no: int,
        row: dict[str, str],
        schema: DetectedSchema,
    ) -> ImportRow | list[RowError]:
        """
        Parse une ligne et retourne soit un ImportRow valide, soit une liste
        d'erreurs. Collecte toutes les erreurs de la ligne (ne fail-fast pas).
        """
        errors: list[RowError] = []

        # Patient ID
        patient_id = ""
        if schema.patient_col:
            patient_id = (row.get(schema.patient_col) or "").strip()
        if not patient_id:
            patient_id = f"_INCONNU_L{line_no}"  # pas bloquant, on continue

        # Code acte
        raw_code = (row.get(schema.code_col or "") or "").strip()
        if not raw_code:
            errors.append(RowError(line_no, "code", raw_code, "Code acte vide."))
        else:
            # Normalise : AMO 34 -> AMO_34 -> resolve -> AMO_34.02
            normalized_input = re.sub(r"(?i)^amo[\s_]*", "AMO_", raw_code)
            canonical = self._ref.resolve(normalized_input) or self._ref.resolve(raw_code)
            if canonical:
                raw_code = canonical
            # Si inconnu, on garde le code brut avec prefixe sentinelle pour tracking
            elif not re.match(r"^AMO_", raw_code, re.IGNORECASE):
                raw_code = f"_UNK_{raw_code}"

        # Date
        raw_date = (row.get(schema.date_col or "") or "").strip()
        act_date: Optional[date] = None
        if not raw_date:
            errors.append(RowError(line_no, "date", raw_date, "Date vide."))
        else:
            act_date = _parse_date(raw_date)
            if act_date is None:
                errors.append(RowError(
                    line_no, "date", raw_date,
                    f"Format de date non reconnu. Formats supportes : {_DATE_FORMATS}."
                ))

        if errors:
            return errors

        return ImportRow(
            line_number=line_no,
            patient_id=patient_id,
            act_code=raw_code,
            act_date=act_date,  # type: ignore[arg-type]  # garanti non-None si pas d'erreur
            raw=dict(row),
        )
