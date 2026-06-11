import pytest
from datetime import date
from src.referential import Referential, Acte, Regle, LettreCle


@pytest.fixture(scope="module")
def ref():
    return Referential("rules.json")


# ------------------------------------------------------------------ #
# resolve()
# ------------------------------------------------------------------ #

def test_resolve_canonical_code(ref):
    assert ref.resolve("AMO_34.02") == "AMO_34.02"
    assert ref.resolve("AMO_20") == "AMO_20"
    assert ref.resolve("AMO_13.5") == "AMO_13.5"


def test_resolve_alias(ref):
    # aliases table: "AMO_34" -> "AMO_34.02"
    assert ref.resolve("AMO_34") == "AMO_34.02"
    # numeric aliases
    assert ref.resolve("34") == "AMO_34.02"
    assert ref.resolve("34.02") == "AMO_34.02"
    assert ref.resolve("13.5") == "AMO_13.5"
    assert ref.resolve("9.7") == "AMO_9.7"
    assert ref.resolve("9.8") == "AMO_9.7"   # alias pointe sur AMO_9.7


def test_resolve_unknown_returns_none(ref):
    assert ref.resolve("AMO_999") is None
    assert ref.resolve("UNKNOWN") is None
    assert ref.resolve("") is None


# ------------------------------------------------------------------ #
# get_acte()
# ------------------------------------------------------------------ #

def test_get_acte_bilan(ref):
    acte = ref.get_acte("AMO_34.02")
    assert acte is not None
    assert isinstance(acte, Acte)
    assert acte.code == "AMO_34.02"
    assert acte.act_type == "bilan"
    assert acte.coefficient == pytest.approx(34.02)


def test_get_acte_reeducation(ref):
    acte = ref.get_acte("AMO_13.5")
    assert acte is not None
    assert acte.act_type == "reeducation"
    assert acte.coefficient == pytest.approx(13.5)
    assert acte.duree_min_m is None  # not set in rules.json


def test_get_acte_age_constraint(ref):
    acte = ref.get_acte("AMO_20")
    assert acte is not None
    assert acte.age_max_mois == 36


def test_get_acte_unknown_returns_none(ref):
    assert ref.get_acte("AMO_999") is None


# ------------------------------------------------------------------ #
# actes_by_type()
# ------------------------------------------------------------------ #

def test_actes_by_type_bilan(ref):
    bilans = ref.actes_by_type("bilan")
    assert "AMO_34.02" in bilans
    assert "AMO_20" in bilans
    assert "AMO_24" in bilans
    assert "AMO_30" in bilans
    assert "AMO_13.5" not in bilans
    assert "AMO_9.7" not in bilans


def test_actes_by_type_reeducation(ref):
    seances = ref.actes_by_type("reeducation")
    assert "AMO_13.5" in seances
    assert "AMO_9.7" in seances
    assert "AMO_15.4" in seances
    assert "AMO_34.02" not in seances


# ------------------------------------------------------------------ #
# lettre_cle()
# ------------------------------------------------------------------ #

def test_lettre_cle_avenant21(ref):
    lc = ref.lettre_cle()
    assert isinstance(lc, LettreCle)
    assert lc.code == "AMO"
    assert lc.valeur_metropole == pytest.approx(2.60)
    assert lc.date_effet == date(2026, 2, 23)


# ------------------------------------------------------------------ #
# regles()
# ------------------------------------------------------------------ #

def test_regles_count_and_ids(ref):
    regles = ref.regles()
    ids = {r.id for r in regles}
    assert "R1" in ids
    assert "RT1" in ids
    assert "R16" in ids
    assert "A21_CUMUL" in ids


def test_regle_versioning(ref):
    regles = {r.id: r for r in ref.regles()}
    # A21_CUMUL est active depuis avenant 21
    a21 = regles["A21_CUMUL"]
    assert a21.date_effet == date(2026, 2, 23)
    assert a21.date_fin is None
    # RT1 est une regle historique sans date de fin
    rt1 = regles["RT1"]
    assert rt1.date_effet == date(1996, 10, 31)
    assert rt1.date_fin is None


# ------------------------------------------------------------------ #
# token_index() — IDF weights
# ------------------------------------------------------------------ #

def test_token_index_contains_distinctive_tokens(ref):
    idx = ref.token_index()
    # "articulation" n'apparait que dans AMO_13.5 -> poids IDF eleve
    # (l'apostrophe dans "d'articulation" est desormais un separateur)
    assert "articulation" in idx
    codes_for_articulation = {code for code, _ in idx["articulation"]}
    assert codes_for_articulation == {"AMO_13.5"}
    # "troubles" est aussi exclusif a AMO_13.5
    assert "troubles" in idx
    assert {code for code, _ in idx["troubles"]} == {"AMO_13.5"}


def test_token_index_idf_ordering(ref):
    idx = ref.token_index()
    # "langage" apparait dans AMO_24, AMO_30, AMO_34.02 (df=3)
    # "communication" apparait uniquement dans AMO_30 (df=1)
    # => IDF("communication") > IDF("langage")
    idf_langage = next((w for code, w in idx.get("langage", []) if code == "AMO_30"), None)
    idf_comm = next((w for code, w in idx.get("communication", []) if code == "AMO_30"), None)
    assert idf_langage is not None
    assert idf_comm is not None
    assert idf_comm > idf_langage  # token rare > token frequent


def test_schema_version(ref):
    assert ref.schema_version() == "2.0.0"
