"""PND-319 (2026-10-13): los presupuestos en COP salían hacia Meta 100 veces más altos.

Estas pruebas comparan con la tabla OFICIAL de Meta (no con nuestra propia cuenta, que es lo que dejó pasar el error) y
fijan los cuatro frenos: la moneda y su unidad se comprueban contra la cuenta antes de mandar un monto, cada
presupuesto y tope se lee de vuelta, sin tope en Meta los conjuntos se apagan solos al alcanzarlo, y la vigilancia del
gasto pausa por tope o por ritmo.
"""
import pytest

from tests.test_experimentos_db import _pieza
from tests.test_lanzador import MetaFalsa, entorno  # noqa: F401 — `entorno` es un fixture

import monedas_meta

# https://developers.facebook.com/docs/marketing-api/currencies (consultada 2026-10-13): las de offset 1.
OFFSET_1_DE_META = {"CLP", "COP", "CRC", "HUF", "ISK", "IDR", "JPY", "KRW", "PYG", "TWD", "VND"}
URL = "https://tienda.co/p"


# ---------- la tabla ----------

def test_la_tabla_es_la_oficial_de_meta():
    assert monedas_meta.SIN_DECIMALES == OFFSET_1_DE_META
    assert not monedas_meta.SIN_DECIMALES & monedas_meta.CON_DECIMALES
    assert {"USD", "EUR", "SEK", "NOK", "MXN", "BRL", "ARS", "PEN"} <= monedas_meta.CON_DECIMALES


@pytest.mark.parametrize("moneda,monto,unidades", [
    ("COP", 4000, 4000), ("COP", 400000, 400000), ("CLP", 1003, 1003), ("JPY", 500, 500),
    ("USD", 14.28, 1428), ("SEK", 150, 15000), ("NOK", 15, 1500), ("EUR", 1, 100), ("MXN", 20, 2000)])
def test_unidad_de_meta(moneda, monto, unidades):
    assert monedas_meta.a_unidad_meta(monto, moneda) == unidades
    assert monedas_meta.desde_unidad_meta(unidades, moneda) == pytest.approx(monto)


@pytest.mark.parametrize("moneda", ["UGX", "XAF", "ZZZ", "", None])
def test_una_moneda_fuera_de_la_tabla_no_se_adivina(moneda):
    with pytest.raises(monedas_meta.MonedaNoSoportada):
        monedas_meta.a_unidad_meta(100, moneda)


def test_todas_las_copias_usan_la_misma_tabla():
    import presupuesto_experimentos as pe
    import tareas.meta
    from meta_rendimiento import sync
    assert tareas.meta.MONEDAS_SIN_DECIMALES is monedas_meta.SIN_DECIMALES
    assert sync.MONEDAS_SIN_DECIMALES is monedas_meta.SIN_DECIMALES
    assert pe.SIN_DECIMALES == set(monedas_meta.SIN_DECIMALES)
    # Rendimiento lee el diario de una cuenta COP tal cual (antes lo dividía entre 100 y escondía el error)
    cop = sync.objetos_de([{"id": "c1", "daily_budget": "400000"}], [], [], moneda="COP")
    assert cop[0]["presupuesto_diario"] == 400000.0
    sek = sync.objetos_de([{"id": "c2", "daily_budget": "15000"}], [], [], moneda="SEK")
    assert sek[0]["presupuesto_diario"] == 150.0


# ---------- la cuenta, antes de mandar un monto ----------

def test_comprobar_moneda_con_la_cuenta_real_de_forja():
    import lanzador
    lanzador.comprobar_moneda({"currency": "COP", "min_daily_budget": 3322}, "COP")


@pytest.mark.parametrize("cuenta,moneda", [
    ({"currency": "USD", "min_daily_budget": 100}, "COP"),   # la cuenta factura en otra moneda
    ({"min_daily_budget": 3322}, "COP"),                      # no se pudo leer la moneda
    ({"currency": "COP", "min_daily_budget": 332200}, "COP"),  # la unidad no cuadra: ×100
    ({"currency": "SEK", "min_daily_budget": 11}, "SEK"),      # al revés: ÷100
])
def test_comprobar_moneda_frena(cuenta, moneda):
    import lanzador
    with pytest.raises(lanzador.PresupuestoNoCoincide):
        lanzador.comprobar_moneda(cuenta, moneda)


def test_con_la_lista_vieja_el_lanzamiento_se_habria_frenado(monkeypatch):
    """La comprobación contra la cuenta no depende de nuestra tabla: con la lista vieja (COP ×100) frena igual."""
    import lanzador
    monkeypatch.setattr(lanzador, "centavos", lambda monto, moneda: int(round(float(monto) * 100)))
    with pytest.raises(lanzador.PresupuestoNoCoincide):
        lanzador.comprobar_moneda({"currency": "COP", "min_daily_budget": 3322}, "COP")


def test_lanzar_no_crea_nada_si_la_cuenta_factura_en_otra_moneda(entorno):
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    meta.cuenta = {"currency": "USD", "min_daily_budget": 100, "min_campaign_group_spend_cap": "10000"}
    with pytest.raises(lz.PresupuestoNoCoincide):
        lz.lanzar("acme", eid)
    assert not [t for t, _ in meta.llamadas if t in ("campaign", "adset", "ad")]
    assert ex.obtener("acme", eid)["estado"] == "error"


# ---------- lo que Meta guardó, leído de vuelta ----------

def test_un_diario_que_meta_guarda_distinto_frena_el_lanzamiento(entorno):
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    original = meta._adset

    def adset_que_guarda_otro(*a, **kw):
        r = original(*a, **kw)
        meta.presupuestos[r["id"]] *= 100      # Meta se queda con otro monto
        return r
    meta._adset = adset_que_guarda_otro
    campaign, adset, creative, ad, insights, auth = meta.modulos()
    entorno["monkeypatch"].setattr(lz, "meta_adset", adset)
    with pytest.raises(lz.PresupuestoNoCoincide):
        lz.lanzar("acme", eid)
    assert ("estado", {"oid": "adset_2", "status": "PAUSED"}) in meta.llamadas
    assert not [t for t, _ in meta.llamadas if t == "ad"]
    assert ex.obtener("acme", eid)["estado"] == "error"


def test_un_conjunto_lanzado_antes_del_arreglo_no_se_enciende(entorno):
    """Como el experimento 5 de colorado_forja: en Meta quedó con 100 veces el diario. Activar no lo enciende."""
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    lz.lanzar("acme", eid)
    adset_co = ex.obtener("acme", eid)["paises"][0]["meta_adset_id"]
    meta.presupuestos[adset_co] *= 100
    meta.llamadas.clear()
    with pytest.raises(lz.PresupuestoNoCoincide):
        lz.cambiar_estado("acme", eid, "ACTIVE")
    assert not [kw for t, kw in meta.llamadas if t == "estado" and kw["status"] == "ACTIVE"]
    assert ("estado", {"oid": adset_co, "status": "PAUSED"}) in meta.llamadas
    assert ex.obtener("acme", eid)["estado"] != "corriendo"
    with pytest.raises(lz.PresupuestoNoCoincide):   # tampoco por la pieza
        lz.activar_pieza("acme", ex.obtener("acme", eid)["piezas"][0]["id"])
    assert not [kw for t, kw in meta.llamadas if t == "estado" and kw["status"] == "ACTIVE"]


def test_cambiar_el_diario_lee_de_vuelta_y_pausa_el_pais_si_no_coincide(entorno):
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    lz.lanzar("acme", eid)
    lz.cambiar_estado("acme", eid, "ACTIVE")
    original = meta._presupuesto

    def guarda_otro(oid, c, dry_run=False):
        r = original(oid, c)
        meta.presupuestos[oid] = int(c) * 100
        return r
    meta._presupuesto = guarda_otro
    campaign, adset, creative, ad, insights, auth = meta.modulos()
    entorno["monkeypatch"].setattr(lz, "meta_adset", adset)
    with pytest.raises(lz.PresupuestoNoCoincide):
        lz.cambiar_presupuesto_pais("acme", eid, "CO", 25000)
    adset_co = ex.obtener("acme", eid)["paises"][0]["meta_adset_id"]
    assert ("estado", {"oid": adset_co, "status": "PAUSED"}) in meta.llamadas
    assert ex.obtener("acme", eid)["paises"][0]["estado"] == "pausado"


def test_el_tope_que_meta_guarda_distinto_pausa_la_campana(entorno):
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    original = meta._campaign

    def campana_que_guarda_otro(*a, **kw):
        r = original(*a, **kw)
        meta.topes[r["id"]] = 1
        return r
    meta._campaign = campana_que_guarda_otro
    campaign, adset, creative, ad, insights, auth = meta.modulos()
    entorno["monkeypatch"].setattr(lz, "meta_campaign", campaign)
    with pytest.raises(lz.PresupuestoNoCoincide):
        lz.lanzar("acme", eid)
    assert ("estado", {"oid": "campaign_1", "status": "PAUSED"}) in meta.llamadas
    assert not [t for t, _ in meta.llamadas if t == "adset"]


# ---------- el freno que cumple Meta ----------

def _experimento(base_temporal, ex, tope, dias=7, diario=4000.0):
    eid = ex.crear("acme", "Prueba", [{"pais": "CO", "idioma": "es", "presupuesto_dia": diario}], "OUTCOME_TRAFFIC",
                   dias, tope, URL, "COP")
    ex.agregar_pieza("acme", eid, _pieza(base_temporal), "CO")
    return eid


def test_sin_tope_en_meta_los_conjuntos_se_apagan_al_alcanzarlo(entorno, base_temporal):
    """El experimento 3 de colorado_forja: tope 4 000, diario 4 000, 7 días. Meta no acepta un tope de 4 000
    (su mínimo es 200 000), así que el conjunto se crea para 1 día: más allá, Meta lo apaga solo."""
    ex, lz, meta = entorno["ex"], entorno["lanzador"], entorno["meta"]
    eid = _experimento(base_temporal, ex, tope=4000.0)
    meta.llamadas.clear()
    lz.lanzar("acme", eid)
    campana = [kw for t, kw in meta.llamadas if t == "campaign"][0]
    conjunto = [kw for t, kw in meta.llamadas if t == "adset"][0]
    assert campana["spend_cap"] is None and conjunto["dias"] == 1 and conjunto["centavos"] == 4000
    assert any("se apagan solos en 1 días" in e["mensaje"] for e in ex.eventos("acme", eid))


def test_con_tope_aceptado_va_a_la_campana_y_los_dias_no_cambian(entorno, base_temporal):
    ex, lz, meta = entorno["ex"], entorno["lanzador"], entorno["meta"]
    eid = _experimento(base_temporal, ex, tope=280000.0, diario=40000.0)
    meta.llamadas.clear()
    lz.lanzar("acme", eid)
    campana = [kw for t, kw in meta.llamadas if t == "campaign"][0]
    conjunto = [kw for t, kw in meta.llamadas if t == "adset"][0]
    assert campana["spend_cap"] == 280000 and conjunto["dias"] == 7


def test_el_minimo_del_tope_es_el_de_la_cuenta(entorno, base_temporal):
    """Meta dijo 200 000 COP para la cuenta de Forja; la tabla vieja suponía 400 000."""
    ex, lz, meta = entorno["ex"], entorno["lanzador"], entorno["meta"]
    eid = _experimento(base_temporal, ex, tope=210000.0, diario=30000.0)
    meta.llamadas.clear()
    lz.lanzar("acme", eid)
    assert [kw for t, kw in meta.llamadas if t == "campaign"][0]["spend_cap"] == 210000


# ---------- la vigilancia del gasto ----------

def _corriendo(entorno, base_temporal, tope=28000.0, diario=4000.0):
    ex, lz = entorno["ex"], entorno["lanzador"]
    eid = _experimento(base_temporal, ex, tope=tope, diario=diario)
    lz.lanzar("acme", eid)
    lz.cambiar_estado("acme", eid, "ACTIVE")
    entorno["meta"].llamadas.clear()
    return eid, ex.obtener("acme", eid)["meta_campaign_id"]


def test_la_vigilancia_no_toca_un_experimento_que_va_bien(entorno, base_temporal):
    ex, lz, meta = entorno["ex"], entorno["lanzador"], entorno["meta"]
    eid, cid = _corriendo(entorno, base_temporal)
    meta.gastos[cid] = (5000.0, 3000.0)
    assert lz.vigilar_gasto("acme", eid) is None
    assert not [t for t, _ in meta.llamadas if t == "estado"]
    assert ex.obtener("acme", eid)["estado"] == "corriendo" and ex.obtener("acme", eid)["gasto_acumulado"] == 5000.0


def test_la_vigilancia_pausa_al_llegar_al_tope(entorno, base_temporal):
    ex, lz, meta = entorno["ex"], entorno["lanzador"], entorno["meta"]
    eid, cid = _corriendo(entorno, base_temporal)
    meta.gastos[cid] = (28000.0, 4000.0)
    assert "tope" in lz.vigilar_gasto("acme", eid)
    assert ("estado", {"oid": cid, "status": "PAUSED"}) in meta.llamadas
    assert ex.obtener("acme", eid)["estado"] == "pausado"


def test_la_vigilancia_pausa_si_gasta_mas_del_doble_de_su_diario(entorno, base_temporal):
    """Lo que pasó el 2026-10-08: 42 498 COP en dos horas con un diario de 8 000. Se frena en 10 minutos."""
    ex, lz, meta = entorno["ex"], entorno["lanzador"], entorno["meta"]
    eid, cid = _corriendo(entorno, base_temporal, tope=280000.0)
    meta.gastos[cid] = (9000.0, 9000.0)
    assert "doble" in lz.vigilar_gasto("acme", eid)
    assert ex.obtener("acme", eid)["estado"] == "pausado"


def test_la_periodica_vigila_cada_10_minutos_y_uno_que_falla_no_frena_a_los_demas(entorno, base_temporal, monkeypatch):
    import worker
    from tareas import experimentos as tex
    assert ("exp_vigilar_gasto", 600) in worker.PERIODICAS
    ex, lz, meta = entorno["ex"], entorno["lanzador"], entorno["meta"]
    eid, cid = _corriendo(entorno, base_temporal)
    otro, cid2 = _corriendo(entorno, base_temporal)
    meta.gastos[cid2] = (28000.0, 0.0)
    real = lz.vigilar_gasto

    def falla_el_primero(cliente, experimento_id):
        if experimento_id == eid:
            raise RuntimeError("Meta no contestó")
        return real(cliente, experimento_id)
    monkeypatch.setattr(lz, "vigilar_gasto", falla_el_primero)
    texto = tex.exp_vigilar_gasto({})
    assert "1 pausados" in texto
    assert ex.obtener("acme", otro)["estado"] == "pausado"
    assert any("No se pudo vigilar" in e["mensaje"] for e in ex.eventos("acme", eid))
