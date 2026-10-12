"""Noruega y Suecia en Experimentos, Sprints y Nicho (spec 2026-10-08, tarea 3). Sin red: Meta va con un doble."""
import pytest

from tests.test_lanzador import MetaFalsa
from tests.test_experimentos_db import _pieza
from tests.test_rutas_experimentos import FORM_PROBAR, app  # noqa: F401  (fixture `app`)


@pytest.fixture(autouse=True)
def _proyectos_en_tmp(monkeypatch, tmp_path):
    import proyectos
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))


# ---------- Experimentos ----------

def _clon(base_temporal):
    return _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_2")


def test_exp_probar_con_noruega_y_suecia_guarda_el_idioma_de_cada_pais(app, base_temporal):
    import experimentos as ex
    clon = _clon(base_temporal)
    datos = dict(FORM_PROBAR, paises=["NO", "SE"], presupuesto_NO="20000", presupuesto_SE="20000",
                 piezas=[str(clon)], combinaciones=[f"{clon}:NO", f"{clon}:SE"])
    datos.pop("presupuesto_CO"); datos.pop("presupuesto_MX")
    app["c"].post("/cliente/acme/experimentos/probar", data=datos)
    (e,) = ex.cargar("acme")
    assert [(p["pais"], p["idioma"]) for p in e["paises"]] == [("NO", "no"), ("SE", "sv")]
    assert sorted((p["pais"]) for p in e["piezas"]) == ["NO", "SE"]
    assert [t["tipo"] for t in app["encolados"]] == ["exp_lanzar"]


def test_exp_nuevo_con_noruega_y_suecia_guarda_el_idioma_de_cada_pais(app):
    import experimentos as ex
    form = {"nombre": "Nórdicos", "objetivo": "OUTCOME_TRAFFIC", "paises": ["NO", "SE"], "presupuesto_NO": "20000",
            "presupuesto_SE": "20000", "dias": "7", "tope_total": "500000", "destino_url": "https://tienda.no/p",
            "edad_min": "18", "edad_max": "55"}
    app["c"].post("/cliente/acme/experimentos/nuevo", data=form)
    (e,) = ex.cargar("acme")
    assert [(p["pais"], p["idioma"]) for p in e["paises"]] == [("NO", "no"), ("SE", "sv")]


def test_exp_probar_pide_el_minimo_en_coronas_si_la_cuenta_factura_en_nok(app, base_temporal, monkeypatch):
    import experimentos as ex
    from presupuesto_experimentos import PRESUPUESTO_MINIMO_DIARIO as minimos
    monkeypatch.setattr(app["dashboard"].meta_conexion, "cargar", lambda c: {"moneda": "NOK"})
    clon = _clon(base_temporal)
    base = dict(FORM_PROBAR, paises=["NO"], piezas=[str(clon)], combinaciones=[f"{clon}:NO"], tope_total="5000")
    app["c"].post("/cliente/acme/experimentos/probar", data=dict(base, presupuesto_NO=str(minimos["NOK"] - 1)))
    assert ex.cargar("acme") == []
    app["c"].post("/cliente/acme/experimentos/probar", data=dict(base, presupuesto_NO=str(minimos["NOK"])))
    (e,) = ex.cargar("acme")
    assert e["moneda"] == "NOK" and e["paises"][0]["idioma"] == "no"


def test_el_conjunto_de_meta_apunta_a_noruega_y_a_suecia(base_temporal, monkeypatch):
    import experimentos as ex
    import lanzador
    meta = MetaFalsa()
    campaign, adset, creative, ad, insights, auth = meta.modulos()
    for nombre, modulo in (("meta_campaign", campaign), ("meta_adset", adset), ("meta_creative", creative),
                           ("meta_ad", ad), ("meta_insights", insights), ("meta_auth", auth)):
        monkeypatch.setattr(lanzador, nombre, modulo)
    monkeypatch.setattr(lanzador.meta_conexion, "credenciales_ads",
                        lambda c: {"token": "t", "ad_account_id": "1", "page_id": "2", "ig_user_id": None})
    monkeypatch.setattr(lanzador.meta_conexion, "cargar", lambda c: {"moneda": "NOK"})
    monkeypatch.setattr(lanzador, "_miniatura_para_ad", lambda cliente, ad_id, url: "https://r2/mini.jpg")
    clon = _clon(base_temporal)
    paises = [{"pais": "NO", "idioma": "no", "presupuesto_dia": 100.0}, {"pais": "SE", "idioma": "sv", "presupuesto_dia": 100.0}]
    eid = ex.crear("acme", "Nórdicos", paises, "OUTCOME_TRAFFIC", 7, 2000.0, "https://tienda.no/p", "NOK")
    ex.agregar_pieza("acme", eid, clon, "NO")
    ex.agregar_pieza("acme", eid, clon, "SE")
    lanzador.lanzar("acme", eid)
    adsets = [kw for t, kw in meta.llamadas if t == "adset"]
    assert [a["targeting"]["geo_locations"]["countries"] for a in adsets] == [["NO"], ["SE"]]


# ---------- Sprints ----------

def test_calendario_de_noruega_trae_morsdag_en_febrero_y_el_resto_del_spec():
    from sprints import calendario
    assert calendario.tiene_calendario("NO")
    no = {p["clave"]: p for p in calendario.presets("NO", anio=2026)}
    assert (no["morsdag"]["inicio"], no["morsdag"]["fin"]) == ("2026-01-28", "2026-02-12")
    assert (no["valentinsdagen"]["inicio"], no["valentinsdagen"]["fin"]) == ("2026-02-01", "2026-02-14")
    assert (no["17_mai"]["inicio"], no["17_mai"]["fin"]) == ("2026-05-05", "2026-05-17")
    assert (no["fellesferie"]["inicio"], no["fellesferie"]["fin"]) == ("2026-06-20", "2026-07-31")
    assert (no["farsdag"]["inicio"], no["farsdag"]["fin"]) == ("2026-10-28", "2026-11-12")
    assert no["black_friday"]["inicio"] == "2026-11-20"
    assert (no["jul"]["inicio"], no["jul"]["fin"]) == ("2026-11-15", "2026-12-24")
    assert "dia_de_la_madre" not in no                                  # ya no cae al calendario de Colombia


def test_calendario_de_suecia_trae_midsommar_en_junio_y_el_resto_del_spec():
    from sprints import calendario
    assert calendario.tiene_calendario("SE")
    se = {p["clave"]: p for p in calendario.presets("SE", anio=2026)}
    assert (se["midsommar"]["inicio"], se["midsommar"]["fin"]) == ("2026-06-10", "2026-06-24")
    assert (se["alla_hjartans_dag"]["inicio"], se["alla_hjartans_dag"]["fin"]) == ("2026-02-01", "2026-02-14")
    assert (se["mors_dag"]["inicio"], se["mors_dag"]["fin"]) == ("2026-05-15", "2026-05-31")
    assert (se["semester"]["inicio"], se["semester"]["fin"]) == ("2026-06-20", "2026-07-31")
    assert (se["fars_dag"]["inicio"], se["fars_dag"]["fin"]) == ("2026-10-28", "2026-11-12")
    assert (se["jul"]["inicio"], se["jul"]["fin"]) == ("2026-11-15", "2026-12-24")
    assert "black_friday" in se


def test_cada_temporada_nordica_trae_contexto_y_mood_y_se_adopta_una_sola_vez(base_temporal):
    from sprints import calendario, datos
    for pais in ("NO", "SE"):
        for p in calendario.presets(pais, anio=2026):
            assert p["contexto"] and p["mood_visual"]["paleta"] and p["mood_visual"]["elementos"] and p["inicio"] < p["fin"]
    tid = calendario.adoptar("acme", "morsdag", pais="NO", anio=2026)
    assert datos.temporada("acme", tid)["inicio"] == "2026-01-28"
    assert calendario.adoptar("acme", "morsdag", pais="NO", anio=2026) == tid


def test_el_pais_del_proyecto_puede_ser_noruega_o_suecia(tmp_path, monkeypatch):
    import proyectos
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    proyectos.guardar_pais("acme", "NO")
    assert proyectos.pais("acme") == "NO"
    proyectos.guardar_pais("acme", "SE")
    assert proyectos.pais("acme") == "SE"


def test_una_idea_de_sprint_acepta_noruego_y_sueco_y_el_prompt_los_nombra():
    from sprints import datos, ideas
    assert datos._idioma("no") == "no" and datos._idioma("SV") == "sv"
    assert datos.IDIOMAS_NOMBRE["no"] == "noruego (bokmål)" and datos.IDIOMAS_NOMBRE["sv"] == "sueco"
    orden = ideas.orden_ideas("es", "no")
    assert "noruego (bokmål)" in orden
    ctx = {"mercado": {"pais": "NO", "idioma": "no"}}
    assert "noruego (bokmål)" in ideas._mercado_texto(ctx)


# ---------- Nicho ----------

def test_los_avatares_aceptan_noruego_y_sueco():
    from nicho import avatares
    assert avatares.nombre_idioma("no") == "noruego (bokmål)"
    assert avatares.nombre_idioma("sv") == "sueco"
    estudio = {"nombre": "Vask", "producto": "Kapsler", "tema": "vask hjemme, Norge", "idioma": "no"}
    assert "noruego (bokmål)" in avatares.armar_prompt_nucleos(estudio, [])


def test_la_investigacion_nombra_el_noruego_y_un_estudio_de_noruega_busca_en_noruego():
    from nicho import investigacion
    from nicho.fuentes import plataformas
    assert investigacion._idioma_texto("no") == "noruego (bokmål) (no)"
    assert plataformas.idioma("NO") == "no" and plataformas.idioma("SE") == "sv"


def test_una_corona_a_secas_es_noruega_en_noruega_y_sueca_en_suecia():
    from nicho.fuentes import plataformas
    assert plataformas._precio_moneda({"price": "299 kr", "loadedCountryCode": "NO"}) == (299.0, "NOK")
    assert plataformas._precio_moneda({"price": "299 kr", "loadedCountryCode": "SE"}) == (299.0, "SEK")
    assert plataformas._precio_moneda({"price": "299 kr"}) == (299.0, "SEK")                 # sin país: como antes
    assert plataformas._precio_moneda({"price": {"value": 299, "currency": "kr"}, "loadedCountryCode": "NO"}) == (299.0, "NOK")
