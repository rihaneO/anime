import pytest
from datetime import date
from src.referential import Referential
from src.csv_importer import (
    CSVImporter,
    ImportRow,
    ImportResult,
    RowError,
    DetectedSchema,
    _detect_encoding,
    _detect_separator,
    _parse_date,
    _detect_schema,
)


@pytest.fixture(scope="module")
def ref():
    return Referential("rules.json")


@pytest.fixture(scope="module")
def importer(ref):
    return CSVImporter(ref)


# ------------------------------------------------------------------ #
# Utilitaires isoles
# ------------------------------------------------------------------ #

class TestDetectSeparator:
    def test_semicolon(self):
        lines = ["code;date;patient", "AMO_34.02;01/03/2026;Thomas", "AMO_13.5;02/03/2026;Marie"]
        assert _detect_separator(lines) == ";"

    def test_comma(self):
        lines = ["code,date,patient", "AMO_34.02,01/03/2026,Thomas"]
        assert _detect_separator(lines) == ","

    def test_tab(self):
        lines = ["code\tdate\tpatient", "AMO_34.02\t01/03/2026\tThomas"]
        assert _detect_separator(lines) == "\t"


class TestParseDate:
    def test_dd_mm_yyyy(self):
        assert _parse_date("01/03/2026") == date(2026, 3, 1)

    def test_yyyy_mm_dd(self):
        assert _parse_date("2026-03-01") == date(2026, 3, 1)

    def test_dd_mm_yy(self):
        assert _parse_date("01/03/26") == date(2026, 3, 1)

    def test_dd_dot_mm_dot_yyyy(self):
        assert _parse_date("01.03.2026") == date(2026, 3, 1)

    def test_yyyymmdd(self):
        assert _parse_date("20260301") == date(2026, 3, 1)

    def test_invalid_returns_none(self):
        assert _parse_date("not-a-date") is None
        assert _parse_date("") is None
        assert _parse_date("32/01/2026") is None


class TestDetectSchema:
    def test_french_headers(self):
        schema = _detect_schema(["patient", "code", "date"])
        assert schema.patient_col == "patient"
        assert schema.code_col == "code"
        assert schema.date_col == "date"

    def test_alias_headers(self):
        schema = _detect_schema(["nom_patient", "cotation", "date_soin"])
        assert schema.patient_col == "nom_patient"
        assert schema.code_col == "cotation"
        assert schema.date_col == "date_soin"

    def test_partial_schema(self):
        # Pas de colonne patient -> patient_col None
        schema = _detect_schema(["acte", "date_acte"])
        assert schema.patient_col is None
        assert schema.code_col == "acte"
        assert schema.date_col == "date_acte"

    def test_extra_cols_captured(self):
        schema = _detect_schema(["code", "date", "montant", "remarque"])
        assert "montant" in schema.extra_cols
        assert "remarque" in schema.extra_cols


class TestDetectEncoding:
    def test_utf8(self):
        raw = "code,date\nAMO_34.02,01/03/2026".encode("utf-8")
        assert _detect_encoding(raw) in ("utf-8", "utf-8-sig")

    def test_latin1(self):
        raw = "prénom,code,date\nThéo,AMO_20,01/01/2026".encode("latin-1")
        enc = _detect_encoding(raw)
        assert enc in ("latin-1", "cp1252", "utf-8")  # any valid decoding


# ------------------------------------------------------------------ #
# CSVImporter — import_bytes()
# ------------------------------------------------------------------ #

class TestCSVImporterBasic:
    def test_empty_file(self, importer):
        result = importer.import_bytes(b"")
        assert result.error_count > 0
        assert result.ok_count == 0

    def test_minimal_valid_csv(self, importer):
        csv = "code,date\nAMO_13.5,01/03/2026\n"
        result = importer.import_bytes(csv.encode("utf-8"))
        assert result.ok_count == 1
        assert result.error_count == 0
        row = result.rows[0]
        assert row.act_code == "AMO_13.5"
        assert row.act_date == date(2026, 3, 1)

    def test_with_patient_column(self, importer):
        csv = "patient,code,date\nThomas,AMO_34.02,01/03/2026\n"
        result = importer.import_bytes(csv.encode("utf-8"))
        assert result.ok_count == 1
        assert result.rows[0].patient_id == "Thomas"

    def test_semicolon_separator(self, importer):
        csv = "code;date;patient\nAMO_20;01/01/2026;Marie\n"
        result = importer.import_bytes(csv.encode("utf-8"))
        assert result.separator == ";"
        assert result.ok_count == 1
        assert result.rows[0].act_code == "AMO_20"

    def test_missing_patient_sets_unknown_id(self, importer):
        csv = "code,date\nAMO_20,01/01/2026\n"
        result = importer.import_bytes(csv.encode("utf-8"))
        assert result.ok_count == 1
        assert result.rows[0].patient_id.startswith("_INCONNU_")

    def test_multiple_rows(self, importer):
        csv = (
            "patient,code,date\n"
            "Thomas,AMO_34.02,01/03/2026\n"
            "Marie,AMO_13.5,02/03/2026\n"
            "Jules,AMO_20,03/03/2026\n"
        )
        result = importer.import_bytes(csv.encode("utf-8"))
        assert result.ok_count == 3
        assert result.total_lines == 3


class TestCSVImporterErrors:
    def test_missing_code_column_is_fatal(self, importer):
        # Sans colonne code, le schema est invalide -> erreur fatale
        csv = "patient,date\nThomas,01/03/2026\n"
        result = importer.import_bytes(csv.encode("utf-8"))
        assert result.error_count > 0
        assert result.ok_count == 0

    def test_bad_date_is_non_fatal(self, importer):
        csv = (
            "code,date\n"
            "AMO_13.5,01/03/2026\n"
            "AMO_20,pas-une-date\n"   # erreur de date
        )
        result = importer.import_bytes(csv.encode("utf-8"))
        assert result.ok_count == 1        # premiere ligne OK
        assert result.error_count == 1     # deuxieme ligne en erreur
        assert result.errors[0].field == "date"

    def test_empty_code_is_non_fatal(self, importer):
        csv = (
            "code,date\n"
            "AMO_13.5,01/03/2026\n"
            ",02/03/2026\n"            # code vide
        )
        result = importer.import_bytes(csv.encode("utf-8"))
        assert result.ok_count == 1
        assert result.error_count == 1
        assert result.errors[0].field == "code"

    def test_import_error_has_line_number(self, importer):
        csv = "code,date\nAMO_13.5,mauvaise-date\n"
        result = importer.import_bytes(csv.encode("utf-8"))
        assert result.errors[0].line_number == 2  # header = 1, premiere data = 2


class TestCSVImporterCodeNormalization:
    def test_alias_amo34_resolved(self, importer):
        # "AMO_34" doit etre resolu en "AMO_34.02" via Referential
        csv = "code,date\nAMO_34,01/03/2026\n"
        result = importer.import_bytes(csv.encode("utf-8"))
        assert result.ok_count == 1
        assert result.rows[0].act_code == "AMO_34.02"

    def test_unknown_code_prefixed_unk(self, importer):
        # Code sans prefixe AMO_ et inconnu -> sentinelle _UNK_
        csv = "code,date\nCODE_INCONNU,01/03/2026\n"
        result = importer.import_bytes(csv.encode("utf-8"))
        assert result.ok_count == 1
        assert result.rows[0].act_code.startswith("_UNK_")
        assert result.unresolved_codes != []

    def test_known_code_not_in_unresolved(self, importer):
        csv = "code,date\nAMO_13.5,01/03/2026\n"
        result = importer.import_bytes(csv.encode("utf-8"))
        assert result.unresolved_codes == []


class TestCSVImporterSummary:
    def test_summary_string(self, importer):
        csv = "code,date\nAMO_13.5,01/03/2026\n"
        result = importer.import_bytes(csv.encode("utf-8"))
        s = result.summary()
        assert "1" in s
        assert "encodage" in s or "encoding" in s.lower() or "encodage" in s.lower()

    def test_schema_detected(self, importer):
        csv = "code,date\nAMO_13.5,01/03/2026\n"
        result = importer.import_bytes(csv.encode("utf-8"))
        assert result.schema is not None
        assert result.schema.code_col is not None
        assert result.schema.date_col is not None
