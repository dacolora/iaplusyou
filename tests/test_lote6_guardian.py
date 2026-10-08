"""Escenarios del guardián del gasto en la re-revisión del lote 6A (2026-10-08): tienda con Triple Whale conectado,
pausa por tope con datos viejos, el saldo del último día con varios países, escalar sin margen, inconclusas que
vuelven al reactivar y una pieza sin dato de Triple Whale que no se juzga por las ventas de su vecina."""
from datetime import datetime, timedelta

import pytest

from tests.test_lanzador import entorno, _tw_conectado  # noqa: F401
from tests.test_atribucion import tienda, _pedidos  # noqa: F401

BUENO = {"impresiones": 5000, "clics_enlace": 150, "ctr": 3.0, "cpc": 0.2, "gasto_usd": 30.0, "thruplay_rate": 0.5,
         "compras": 0, "ingresos": 0.0, "roas": 0.0, "estado_meta": "ACTIVE", "estado_meta_texto": "Activo"}


def _sin_ruido(monkeypatch):
    from tareas import experimentos as te
    for nombre in ("_diagnosticar", "_aprender", "_avisar_resultado"):
        monkeypatch.setattr(te, nombre, lambda *a, **k: None)
    monkeypatch.setattr(te, "_canales_organicos", lambda *a: [])
    return te


# ---------------------------------------------------------------- R2 ---
@pytest.mark.parametrize("legado", [False, True])
def test_R2_tienda_con_tw_conectado_suma_pedidos_y_decide(entorno, tienda, monkeypatch, legado):
    import atribucion
    ex, lz, eid = entorno["ex"], entorno["lanzador"], entorno["eid"]
    ex.actualizar("acme", eid, atribucion="tienda")
    _tw_conectado(lz, monkeypatch, dominio="acme-co.myshopify.com", pais="CO")   # TW conectado: no debe mandar
    monkeypatch.setattr(lz.tw_datos, "totales_anuncio", lambda *a, **k: pytest.fail("leyó Triple Whale en un experimento de tienda"))
    lz.lanzar("acme", eid)
    assert ex.obtener("acme", eid)["extra"]["fuente_ventas_fija"] == "tienda"
    if legado:   # como lo dejaba el lote 6A original
        ex.actualizar_extra("acme", eid, lambda x: {**x, "fuente_ventas_fija": "triple_whale"})
    monkeypatch.setattr(lz.meta_insights, "obtener_resultados", lambda ad_id, objetivo=None: dict(BUENO))
    pz0 = ex.obtener("acme", eid)["piezas"][0]
    _pedidos(tienda, (str(pz0["id"]), 30.0), (str(pz0["id"]), 20.0), (str(pz0["id"]), 10.0))
    assert atribucion.resolver_pendientes("acme") == 3
    lz.refrescar("acme", eid)
    e = ex.obtener("acme", eid)
    assert e["extra"]["fuente_ventas_fija"] == "tienda"
    m = e["piezas"][0]["metricas"]
    print("\nmetricas tienda:", {k: m.get(k) for k in ("compras", "ingresos", "roas", "fuente_ventas", "ventas_no_disponibles")})
    assert m["compras"] == 3 and m["ingresos"] == 60.0 and m["fuente_ventas"] == "tienda"
    assert not m.get("ventas_no_disponibles")
    # el decisor ve las 3 compras del país
    te = _sin_ruido(monkeypatch)
    ctxs = []
    decidir = te.decisor.decidir
    monkeypatch.setattr(te.decisor, "decidir", lambda s, r, c: (ctxs.append(c), decidir(s, r, c))[1])
    monkeypatch.setattr(te.acciones, "pedir", lambda *a: ("ejecutada", "ok"))
    ex.actualizar("acme", eid, estado="corriendo")
    for p in e["piezas"]:
        ex.actualizar_pieza("acme", p["id"], estado="activo")
        ex.marcar_pieza("acme", p["id"], activado_en=(datetime.now() - timedelta(hours=100)).isoformat())
    te.exp_decidir({"payload": {"cliente": "acme", "experimento_id": eid}})
    co = [c for c in ctxs if c["presupuesto_dia"] and c.get("compras_pais") is not None]
    print("compras_pais vistas:", [c["compras_pais"] for c in ctxs])
    assert 3 in [c["compras_pais"] for c in ctxs]


# ---------------------------------------------------------------- R4 ---
def _viejo(entorno, tope_alcanzado):
    ex, lz, eid = entorno["ex"], entorno["lanzador"], entorno["eid"]
    lz.lanzar("acme", eid)
    lz.cambiar_estado("acme", eid, "ACTIVE")
    tope = ex.obtener("acme", eid)["tope_total"]
    ex.actualizar("acme", eid, estado="corriendo", gasto_acumulado=tope if tope_alcanzado else tope / 2)
    for p in ex.obtener("acme", eid)["piezas"]:
        ex.marcar_pieza("acme", p["id"], activado_en=(datetime.now() - timedelta(hours=100)).isoformat())
        ex.snapshot(p["id"], {"impresiones": 5000, "ctr": 0.1, "cpc": 5, "gasto": 100},
                    tomado_en=(datetime.now() - timedelta(hours=7)).isoformat())
    return ex, lz, eid


def test_R4_tope_con_datos_viejos_pausa_de_verdad(entorno, monkeypatch):
    te = _sin_ruido(monkeypatch)
    ex, lz, eid = _viejo(entorno, True)
    assert ex.datos_viejos(ex.obtener("acme", eid))
    n = len(entorno["meta"].llamadas)
    salida = te.exp_decidir({"payload": {"cliente": "acme", "experimento_id": eid}})
    nuevas = entorno["meta"].llamadas[n:]
    print("\nsalida:", salida, "| llamadas a Meta:", nuevas)
    assert any(t == "estado" and kw["status"] == "PAUSED" for t, kw in nuevas)
    assert ex.obtener("acme", eid)["estado"] == "pausado"
    assert any(e["tipo"] == "tope" for e in ex.eventos("acme", eid))


def test_R4_sin_tope_y_datos_viejos_no_toca_nada(entorno, monkeypatch):
    te = _sin_ruido(monkeypatch)
    ex, lz, eid = _viejo(entorno, False)
    monkeypatch.setattr(te.acciones, "pedir", lambda *a: pytest.fail("acción con datos viejos"))
    n, ne = len(entorno["meta"].llamadas), len(ex.eventos("acme", eid))
    salida = te.exp_decidir({"payload": {"cliente": "acme", "experimento_id": eid}})
    print("\nsalida:", salida)
    assert entorno["meta"].llamadas[n:] == [] and len(ex.eventos("acme", eid)) == ne
    assert ex.obtener("acme", eid)["estado"] == "corriendo"


# ---------------------------------------------------------------- R5 ---
@pytest.mark.parametrize("horas", [1, 6, 23, 24, 30, 48])
def test_R5_suma_de_maximos_no_pasa_el_saldo(horas):
    import presupuesto_experimentos as p
    for paises in ([("CO", 5)], [("CO", 5), ("MX", 5)], [("CO", 0), ("MX", 9)]):
        e = {"moneda": "USD", "tope_total": 50, "gasto_acumulado": 40, "dias": 7,
             "extra": {"fin_primera_activacion": 1000 + horas * 3600},
             "paises": [{"pais": a, "presupuesto_dia": b} for a, b in paises]}
        for pais, _ in paises:
            lim = p.limite_diario(e, pais, ahora=1000)
            otros = sum(b for a, b in paises if a != pais)
            assert lim["maximo"] + otros <= max(lim["saldo"], otros) + 1e-9, (horas, paises, lim)
            assert lim["maximo"] * max(lim["dias"], 1) + otros * max(lim["dias"], 1) <= lim["saldo"] * max(1, lim["dias"]) + 1e-6


# ---------------------------------------------------------- revisor ---
def test_REV_escalar_sin_margen_en_auto_eventos(entorno, monkeypatch):
    te = _sin_ruido(monkeypatch)
    ex, lz, eid = entorno["ex"], entorno["lanzador"], entorno["eid"]
    lz.lanzar("acme", eid)
    diario = sum(p["presupuesto_dia"] for p in ex.obtener("acme", eid)["paises"])
    ex.actualizar("acme", eid, tope_total=diario * 7, modo="auto", atribucion="ninguna")
    lz.cambiar_estado("acme", eid, "ACTIVE")
    ex.actualizar_extra("acme", eid, lambda x: {**x, "derivaciones": []})
    for p in ex.obtener("acme", eid)["piezas"]:
        ex.marcar_pieza("acme", p["id"], activado_en="2000-01-01T00:00:00", derivado=True)
        ex.snapshot(p["id"], {"impresiones": 5000, "gasto": 30, "ctr": 3, "cpc": .2, "thruplay_rate": .5})
    n = len(entorno["meta"].llamadas)
    te.exp_decidir({"payload": {"cliente": "acme", "experimento_id": eid}})
    evs = [(e["tipo"], e["mensaje"]) for e in ex.eventos("acme", eid)]
    print("\nllamadas presupuesto:", [c for c in entorno["meta"].llamadas[n:] if c[0] == "presupuesto"])
    for t, m in evs:
        if t in ("accion", "presupuesto", "error"):
            print("  ", t, "|", m)
    assert not [c for c in entorno["meta"].llamadas[n:] if c[0] == "presupuesto"]
    assert not any(t == "error" for t, _ in evs)


def test_REV_reactivar_inconclusas_del_decisor(entorno, monkeypatch):
    te = _sin_ruido(monkeypatch)
    ex, lz, eid = entorno["ex"], entorno["lanzador"], entorno["eid"]
    ex.actualizar("acme", eid, atribucion="pixel")
    lz.lanzar("acme", eid)
    lz.cambiar_estado("acme", eid, "ACTIVE")
    ex.actualizar("acme", eid, estado="corriendo")
    monkeypatch.setattr(te.acciones, "pedir", lambda *a: ("ejecutada", "ok"))
    for p in ex.obtener("acme", eid)["piezas"]:
        ex.marcar_pieza("acme", p["id"], activado_en="2000-01-01T00:00:00")
        ex.snapshot(p["id"], {"impresiones": 5000, "gasto": 30, "ctr": 3, "cpc": .2, "thruplay_rate": .5, "compras": 0, "fuente_ventas": "meta"})
    te.exp_decidir({"payload": {"cliente": "acme", "experimento_id": eid}})
    piezas = ex.obtener("acme", eid)["piezas"]
    print("\nveredictos:", [(p["veredicto"], (p["extra"] or {}).get("muestra_ventas_insuficiente"), p["estado"]) for p in piezas])
    assert all(p["veredicto"] == "inconcluso" for p in piezas)
    lz.cambiar_estado("acme", eid, "PAUSED")
    n = len(entorno["meta"].llamadas)
    lz.cambiar_estado("acme", eid, "ACTIVE")
    piezas = ex.obtener("acme", eid)["piezas"]
    activadas = [kw["oid"] for t, kw in entorno["meta"].llamadas[n:] if t == "estado" and kw["status"] == "ACTIVE"]
    print("estados:", [p["estado"] for p in piezas], "| ACTIVE a Meta:", activadas)
    assert [p["estado"] for p in piezas] == ["activo"] * 3
    assert all(p["meta_ad_id"] in activadas for p in piezas)


# ------------------------------------------------ R1 (puerta de ventas) ---
def test_R1b_pieza_sin_dato_tw_no_se_juzga_por_ventas_de_su_vecina(entorno, monkeypatch):
    """CO con tienda TW: la pieza A tiene 3 pedidos en TW; la B todavía no aparece en el Pixel.
    compras_pais = 3 → B NO puede salir «perdedor» por ventas (roas 0 de relleno) ni rescatarse."""
    te = _sin_ruido(monkeypatch)
    ex, lz, eid = entorno["ex"], entorno["lanzador"], entorno["eid"]
    ex.actualizar("acme", eid, atribucion="triple_whale", modo="auto")
    _tw_conectado(lz, monkeypatch, dominio="acme-co.myshopify.com", pais="CO")
    lz.lanzar("acme", eid)
    piezas = ex.obtener("acme", eid)["piezas"]
    a, b = piezas[0], piezas[1]
    monkeypatch.setattr(lz.tw_datos, "totales_anuncio", lambda c, t, canal, ad_id, desde:
                        {"con_pixel": True, "pedidos": 3, "ingresos": 90.0} if ad_id == a["meta_ad_id"] else None)
    monkeypatch.setattr(lz.meta_insights, "obtener_resultados", lambda ad_id, objetivo=None: dict(BUENO))
    lz.refrescar("acme", eid)
    ex.actualizar("acme", eid, estado="corriendo")
    for p in piezas:
        ex.actualizar_pieza("acme", p["id"], estado="activo")
        ex.marcar_pieza("acme", p["id"], activado_en=(datetime.now() - timedelta(hours=100)).isoformat())
    pedidas = []
    monkeypatch.setattr(te.acciones, "pedir", lambda *x: (pedidas.append((x[2], x[3].get("ep_id"))), ("ejecutada", "ok"))[1])
    te.exp_decidir({"payload": {"cliente": "acme", "experimento_id": eid}})
    e = ex.obtener("acme", eid)
    estado = {p["id"]: (p["pais"], p["veredicto"], (p["metricas"] or {}).get("ventas_no_disponibles")) for p in e["piezas"]}
    print("\npiezas:", estado, "| pedidas:", pedidas)
    assert estado[b["id"]][2] is True
    assert estado[b["id"]][1] == "pendiente", "la pieza sin dato de TW se juzgó por ventas"
    assert not [x for x in pedidas if x[1] == b["id"]]
