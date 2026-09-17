"""Bloque 6: OUTCOME_SALES con Pixel. Meta exige `promoted_object` (pixel +
evento PURCHASE) en cada conjunto de una campaña de ventas; el lanzador lo
arma a partir de meta_conexion.estado_pixel y aborta ANTES de crear nada si
el Pixel no está activo. La ruta exp_crear no deja crear un experimento de
compras sin atribución pixel, y el objetivo sugerido sigue a la atribución."""
import json

import pytest

from tests.test_lanzador import entorno  # noqa: F401 — fixture (MetaFalsa + experimento con piezas)
from tests.test_meta_ads_bloque3 import auth_falsa  # noqa: F401 — fixture (auth.llamar grabado)
from tests.test_rutas_experimentos import FORM, app  # noqa: F401 — fixture (test_client admin + Meta conectado)

PIXEL_OK = {"estado": "ok", "pixel_id": "px_77", "nombre": "Pixel tienda", "ultimo_disparo": "2026-09-15T00:00:00+0000", "detalle": ""}
PIXEL_SIN_DATOS = {"estado": "sin_datos", "pixel_id": "px_77", "nombre": "Pixel tienda", "ultimo_disparo": None,
                   "detalle": "El Pixel existe pero nunca ha disparado."}
PROMOTED = {"pixel_id": "px_77", "custom_event_type": "PURCHASE"}
TARGETING = {"geo_locations": {"countries": ["CO"]}, "age_min": 18, "age_max": 65}


# --- meta_ads.adset -------------------------------------------------------

def test_adset_sales_con_promoted_object(auth_falsa):  # noqa: F811
    from meta_ads import adset
    adset.crear_adset("X", "c1", "OUTCOME_SALES", TARGETING, 2500, 7, promoted_object=PROMOTED)
    metodo, edge, payload, _ = auth_falsa[-1]
    assert (metodo, edge) == ("POST", "act_123/adsets")
    assert payload["promoted_object"] == json.dumps(PROMOTED)
    assert payload["optimization_goal"] == "OFFSITE_CONVERSIONS"


def test_adset_sales_sin_promoted_object_es_error(auth_falsa):  # noqa: F811
    from meta_ads import adset
    with pytest.raises(ValueError) as e:
        adset.crear_adset("X", "c1", "OUTCOME_SALES", TARGETING, 2500, 7)
    assert "Pixel" in str(e.value)
    assert auth_falsa == []          # nunca llegó a Meta


def test_adset_traffic_sin_promoted_object(auth_falsa):  # noqa: F811
    from meta_ads import adset
    adset.crear_adset("X", "c1", "OUTCOME_TRAFFIC", TARGETING, 2500, 7)
    assert "promoted_object" not in auth_falsa[-1][2]


# --- lanzador.lanzar ------------------------------------------------------

def _a_ventas(entorno):  # noqa: F811
    entorno["ex"].actualizar("acme", entorno["eid"], objetivo_meta="OUTCOME_SALES", atribucion="pixel")


def test_lanzar_sales_con_pixel_ok_manda_promoted_object(entorno):  # noqa: F811
    ex, lz, meta, eid, mp = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"], entorno["monkeypatch"]
    _a_ventas(entorno)
    consultas = []
    mp.setattr(lz.meta_conexion, "estado_pixel", lambda c, solo_cache=False: (consultas.append(solo_cache), PIXEL_OK)[1])
    lz.lanzar("acme", eid)
    adsets = [kw for t, kw in meta.llamadas if t == "adset"]
    assert len(adsets) == 2 and all(kw["promoted_object"] == PROMOTED and kw["objetivo"] == "OUTCOME_SALES" for kw in adsets)
    e = ex.obtener("acme", eid)
    assert e["estado"] == "pausado"
    assert any(ev["tipo"] == "lanzamiento" and "px_77" in ev["mensaje"] for ev in e["eventos"])


def test_lanzar_sales_calcula_pixel_si_no_hay_cache(entorno):  # noqa: F811
    """El worker es otro proceso: su caché del Pixel casi siempre está vacío
    (solo_cache → None). Entonces se calcula (bloqueante, antes de crear nada)."""
    lz, meta, eid, mp = entorno["lanzador"], entorno["meta"], entorno["eid"], entorno["monkeypatch"]
    _a_ventas(entorno)
    consultas = []

    def estado_pixel(c, solo_cache=False):
        consultas.append(solo_cache)
        return None if solo_cache else PIXEL_OK
    mp.setattr(lz.meta_conexion, "estado_pixel", estado_pixel)
    lz.lanzar("acme", eid)
    assert consultas == [True, False]
    assert all(kw["promoted_object"] == PROMOTED for t, kw in meta.llamadas if t == "adset")


@pytest.mark.parametrize("pixel", [PIXEL_SIN_DATOS, {"estado": "sin_pixel", "pixel_id": None},
                                   {"estado": "error", "pixel_id": None, "detalle": "Graph caído"}])
def test_lanzar_sales_sin_pixel_activo_aborta_antes_de_meta(entorno, pixel):  # noqa: F811
    ex, lz, meta, eid, mp = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"], entorno["monkeypatch"]
    _a_ventas(entorno)
    ex.actualizar("acme", eid, estado="lanzando")   # como lo deja la ruta antes de encolar
    mp.setattr(lz.meta_conexion, "estado_pixel", lambda c, solo_cache=False: pixel)
    with pytest.raises(ValueError) as err:
        lz.lanzar("acme", eid)
    assert "Pixel" in str(err.value) and "compras" in str(err.value)
    assert meta.llamadas == []      # ni campaña ni conjuntos: nada que Meta rechace después
    e = ex.obtener("acme", eid)
    assert e["estado"] == "error" and "Pixel" in e["error"] and not e["meta_campaign_id"]
    assert all(not p.get("meta_adset_id") for p in e["paises"])


def test_lanzar_traffic_no_consulta_pixel_ni_manda_promoted_object(entorno):  # noqa: F811
    lz, meta, eid, mp = entorno["lanzador"], entorno["meta"], entorno["eid"], entorno["monkeypatch"]
    mp.setattr(lz.meta_conexion, "estado_pixel", lambda c, solo_cache=False: pytest.fail("no debía consultar el Pixel"))
    lz.lanzar("acme", eid)
    adsets = [kw for t, kw in meta.llamadas if t == "adset"]
    assert len(adsets) == 2 and all(kw["promoted_object"] is None for kw in adsets)


# --- experimentos.objetivo_sugerido --------------------------------------

def test_objetivo_sugerido_sigue_a_la_atribucion(base_temporal, monkeypatch):
    import experimentos as ex
    monkeypatch.setattr(ex, "atribucion_sugerida", lambda c: "pixel")
    assert ex.objetivo_sugerido("acme") == "OUTCOME_SALES"
    monkeypatch.setattr(ex, "atribucion_sugerida", lambda c: "tienda")
    assert ex.objetivo_sugerido("acme") == "OUTCOME_TRAFFIC"
    monkeypatch.setattr(ex, "atribucion_sugerida", lambda c: "ninguna")
    assert ex.objetivo_sugerido("acme") == "OUTCOME_TRAFFIC"


def test_objetivo_sugerido_desde_el_pixel_en_cache(base_temporal, monkeypatch):
    import experimentos as ex
    import meta_conexion
    import tiendas
    monkeypatch.setattr(tiendas, "listar", lambda c: [])
    monkeypatch.setattr(meta_conexion, "estado_pixel", lambda c, solo_cache=False: PIXEL_OK)
    assert ex.objetivo_sugerido("acme") == "OUTCOME_SALES"
    monkeypatch.setattr(meta_conexion, "estado_pixel", lambda c, solo_cache=False: None)
    assert ex.objetivo_sugerido("acme") == "OUTCOME_TRAFFIC"


# --- ruta exp_crear -------------------------------------------------------

def _pixel(app, monkeypatch, valor):  # noqa: F811
    monkeypatch.setattr(app["dashboard"].meta_conexion, "estado_pixel", lambda c, solo_cache=False: valor)


def test_exp_crear_rechaza_sales_sin_pixel(app, monkeypatch):  # noqa: F811
    import experimentos as ex
    _pixel(app, monkeypatch, PIXEL_SIN_DATOS)                       # sugerida: ninguna
    r = app["c"].post("/cliente/acme/experimentos/nuevo", data=dict(FORM, objetivo="OUTCOME_SALES"), follow_redirects=True)
    assert "requiere el Pixel activo" in r.get_data(as_text=True)
    assert ex.cargar("acme") == []
    # Pixel vivo pero la persona eligió otra atribución a mano: tampoco.
    _pixel(app, monkeypatch, PIXEL_OK)
    app["c"].post("/cliente/acme/experimentos/nuevo", data=dict(FORM, objetivo="OUTCOME_SALES", atribucion="tienda"))
    assert ex.cargar("acme") == []


def test_exp_crear_acepta_sales_con_pixel(app, monkeypatch):  # noqa: F811
    import experimentos as ex
    _pixel(app, monkeypatch, PIXEL_OK)
    app["c"].post("/cliente/acme/experimentos/nuevo", data=dict(FORM, objetivo="OUTCOME_SALES"))                      # sugerida: pixel
    app["c"].post("/cliente/acme/experimentos/nuevo", data=dict(FORM, objetivo="OUTCOME_SALES", atribucion="pixel"))  # explícita
    lista = ex.cargar("acme")
    assert [(e["objetivo_meta"], e["atribucion"]) for e in lista] == [("OUTCOME_SALES", "pixel")] * 2


def test_exp_crear_traffic_sin_pixel_sigue_igual(app, monkeypatch):  # noqa: F811
    import experimentos as ex
    _pixel(app, monkeypatch, None)
    app["c"].post("/cliente/acme/experimentos/nuevo", data=FORM)
    assert [(e["objetivo_meta"], e["atribucion"]) for e in ex.cargar("acme")] == [("OUTCOME_TRAFFIC", "ninguna")]


def test_form_preselecciona_objetivo_sugerido(app, monkeypatch):  # noqa: F811
    _pixel(app, monkeypatch, PIXEL_OK)
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert '<option value="OUTCOME_SALES" selected>' in html and "Compras (requiere Pixel)" in html
    _pixel(app, monkeypatch, None)
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert '<option value="OUTCOME_TRAFFIC" selected>' in html and "Tráfico (clics al enlace)" in html
