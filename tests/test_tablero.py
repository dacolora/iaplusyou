"""Tablero (Bloque 6): deltas sobre snapshots acumulados, resumen del mes,
serie diaria, top ganadoras, alertas y CSV. Sin red: meta_conexion y
tiendas se fingen con monkeypatch."""
import pytest

from tests.test_experimentos_db import PAISES, _pieza

AHORA = "2026-09-16T10:00:00"


def _snap(tomado_en, **m):
    return {"tomado_en": tomado_en, **m}


def _experimento(db, nombre="Cojín", moneda="COP", estado="corriendo", atribucion="ninguna", **campos):
    import experimentos as ex
    eid = ex.crear("acme", nombre, PAISES, "OUTCOME_TRAFFIC", 7, 500000.0, "https://t", moneda, atribucion=atribucion)
    ex.actualizar("acme", eid, estado=estado, **campos)
    return eid


def _pieza_en(db, eid, pais="CO", legado="cf_1__es_CO", estado="activo", **campos):
    import experimentos as ex
    pid = _pieza(db, legado=legado, pais=pais)
    ep = ex.agregar_pieza("acme", eid, pid, pais)
    ex.actualizar_pieza("acme", ep, estado=estado, **campos)
    return ep


@pytest.fixture
def sin_red(monkeypatch):
    """meta_conexion/tiendas sin tocar red ni disco."""
    import meta_conexion
    import tiendas
    monkeypatch.setattr(meta_conexion, "estado", lambda c: {"estado": "conectado", "detalle": {}, "verificado": True})
    monkeypatch.setattr(meta_conexion, "estado_pixel", lambda c, solo_cache=False: None)
    monkeypatch.setattr(tiendas, "listar", lambda c: [])
    return monkeypatch


# ---------- valor_en / delta ----------

def test_valor_en_y_delta_con_truncado():
    import tablero
    snaps = [_snap("2026-09-01T08:00:00", gasto=100.0, compras=1),
             _snap("2026-09-02T08:00:00", gasto=250.0, compras=3),
             _snap("2026-09-03T08:00:00", gasto=240.0, compras=3)]  # Meta corrigió hacia abajo
    assert tablero.valor_en(snaps, "2026-08-31T23:59:59", "gasto") == 0.0
    assert tablero.valor_en(snaps, "2026-09-01T08:00:00", "gasto") == 100.0
    assert tablero.valor_en(snaps, "2026-09-02T12:00:00", "gasto") == 250.0
    assert tablero.valor_en(snaps, "2026-09-09T00:00:00", "compras") == 3.0
    assert tablero.delta(snaps, "2026-09-01T00:00:00", "2026-09-02T12:00:00", "gasto") == 250.0
    assert tablero.delta(snaps, "2026-09-01T12:00:00", "2026-09-02T12:00:00", "gasto") == 150.0
    assert tablero.delta(snaps, "2026-09-02T12:00:00", "2026-09-03T12:00:00", "gasto") == 0.0  # negativo → 0
    assert tablero.delta([], "2026-09-01T00:00:00", "2026-09-30T00:00:00", "gasto") == 0.0


# ---------- resumen_mes ----------

def test_resumen_mes_excluye_lo_anterior_y_separa_fuentes(base_temporal, sin_red):
    import experimentos as ex
    import propuestas
    import tablero
    eid = _experimento(base_temporal)
    ep_meta = _pieza_en(base_temporal, eid, "CO")
    ep_tienda = _pieza_en(base_temporal, eid, "MX", legado="cf_2__es_MX")
    ep_sin = _pieza_en(base_temporal, eid, "CO", legado="cf_3__es_CO", estado="pausado")
    # Acumulado antes del mes: no debe contar.
    ex.snapshot(ep_meta, {"gasto": 1000, "compras": 5, "ingresos": 50000, "impresiones": 900, "clics_enlace": 30,
                          "fuente_ventas": "meta"}, tomado_en="2026-08-30T10:00:00")
    ex.snapshot(ep_meta, {"gasto": 1600, "compras": 8, "ingresos": 80000, "impresiones": 1500, "clics_enlace": 45,
                          "fuente_ventas": "meta"}, tomado_en="2026-09-10T10:00:00")
    ex.snapshot(ep_tienda, {"gasto": 400, "compras": 2, "ingresos": 30000, "impresiones": 300, "clics_enlace": 10,
                            "fuente_ventas": "tienda"}, tomado_en="2026-09-12T10:00:00")
    # Sin fuente de ventas: el gasto cuenta, los ingresos no.
    ex.snapshot(ep_sin, {"gasto": 100, "compras": 0, "ingresos": 9999, "impresiones": 50,
                         "fuente_ventas": "ninguna"}, tomado_en="2026-09-12T10:00:00")
    # Snapshot futuro respecto a `ahora`: tampoco cuenta.
    ex.snapshot(ep_meta, {"gasto": 9000, "compras": 99, "ingresos": 1, "fuente_ventas": "meta"},
                tomado_en="2026-09-20T10:00:00")
    propuestas.crear("acme", eid, "pausar", {"ep_id": ep_sin}, "CPC alto")

    r = tablero.resumen_mes("acme", ahora_iso=AHORA)
    assert r["desde"] == "2026-09-01T00:00:00" and r["hasta"] == AHORA
    assert list(r["por_moneda"]) == ["COP"]
    g = r["por_moneda"]["COP"]
    assert g["gasto"] == 600 + 400 + 100
    assert g["compras"] == 3 + 2
    assert g["ingresos"] == 30000 + 30000
    assert g["roas"] == round(60000 / 1100, 2)
    assert g["impresiones"] == 600 + 300 + 50 and g["clics_enlace"] == 15 + 10
    assert g["anuncios"] == 3
    assert r["experimentos_corriendo"] == 1
    assert r["propuestas_pendientes"] == 1
    assert r["piezas_activas"] == 2


def test_resumen_mes_agrupa_por_moneda(base_temporal, sin_red):
    import experimentos as ex
    import tablero
    e_cop = _experimento(base_temporal, "COP", moneda="COP")
    e_usd = _experimento(base_temporal, "USD", moneda="USD", estado="pausado")
    ep1 = _pieza_en(base_temporal, e_cop)
    ep2 = _pieza_en(base_temporal, e_usd, legado="cf_2__es_CO")
    ex.snapshot(ep1, {"gasto": 20000, "impresiones": 10}, tomado_en="2026-09-05T00:00:00")
    ex.snapshot(ep2, {"gasto": 12.5, "impresiones": 10}, tomado_en="2026-09-05T00:00:00")
    r = tablero.resumen_mes("acme", ahora_iso=AHORA)
    assert r["por_moneda"]["COP"]["gasto"] == 20000 and r["por_moneda"]["USD"]["gasto"] == 12.5
    assert r["por_moneda"]["USD"]["roas"] == 0.0
    assert r["experimentos_corriendo"] == 1


def test_resumen_mes_sin_experimentos(base_temporal, sin_red):
    import tablero
    r = tablero.resumen_mes("acme", ahora_iso=AHORA)
    assert r["por_moneda"] == {} and r["experimentos_corriendo"] == 0 and r["piezas_activas"] == 0


# ---------- serie_diaria ----------

def test_serie_diaria_tres_dias(base_temporal, sin_red):
    import experimentos as ex
    import tablero
    eid = _experimento(base_temporal)
    ep = _pieza_en(base_temporal, eid)
    ex.snapshot(ep, {"gasto": 100, "compras": 1, "ingresos": 1000, "fuente_ventas": "meta"},
                tomado_en="2026-09-14T09:00:00")
    ex.snapshot(ep, {"gasto": 180, "compras": 2, "ingresos": 2500, "fuente_ventas": "meta"},
                tomado_en="2026-09-14T20:00:00")
    ex.snapshot(ep, {"gasto": 300, "compras": 2, "ingresos": 2500, "fuente_ventas": "meta"},
                tomado_en="2026-09-16T08:00:00")
    # Otra moneda con menos gasto: la serie se queda con COP.
    e_usd = _experimento(base_temporal, "USD", moneda="USD")
    ep_usd = _pieza_en(base_temporal, e_usd, legado="cf_2__es_CO")
    ex.snapshot(ep_usd, {"gasto": 5}, tomado_en="2026-09-15T08:00:00")

    s = tablero.serie_diaria("acme", dias=3, ahora_iso=AHORA)
    assert s["moneda"] == "COP"
    assert [d["dia"] for d in s["dias"]] == ["2026-09-14", "2026-09-15", "2026-09-16"]
    assert s["dias"][0] == {"dia": "2026-09-14", "gasto": 180.0, "compras": 2, "ingresos": 2500.0}
    assert s["dias"][1] == {"dia": "2026-09-15", "gasto": 0.0, "compras": 0, "ingresos": 0.0}
    assert s["dias"][2] == {"dia": "2026-09-16", "gasto": 120.0, "compras": 0, "ingresos": 0.0}


def test_serie_diaria_vacia(base_temporal, sin_red):
    import tablero
    s = tablero.serie_diaria("acme", dias=2, ahora_iso=AHORA)
    assert s["moneda"] is None and len(s["dias"]) == 2 and s["dias"][-1]["gasto"] == 0.0


# ---------- top_ganadoras ----------

def test_top_ganadoras_ordena_por_roas_y_cpc(base_temporal, sin_red):
    import experimentos as ex
    import tablero
    eid = _experimento(base_temporal, "Ganadoras")
    cerrado = _experimento(base_temporal, "Viejo", estado="cerrado")
    a = _pieza_en(base_temporal, eid, veredicto="ganador", veredicto_motivo="ROAS 3", veredicto_en=AHORA)
    b = _pieza_en(base_temporal, eid, "MX", legado="cf_2__es_MX", veredicto="ganador", veredicto_motivo="CPC bajo")
    c = _pieza_en(base_temporal, eid, "CO", legado="cf_3__es_CO", veredicto="ganador", veredicto_motivo="CPC alto")
    d = _pieza_en(base_temporal, cerrado, "CO", legado="cf_4__es_CO", veredicto="ganador", escalon_rescate=1)
    _pieza_en(base_temporal, eid, "CO", legado="cf_5__es_CO", veredicto="perdedor")
    ex.snapshot(a, {"roas": 3.0, "cpc": 900}, tomado_en="2026-09-10T00:00:00")
    ex.snapshot(b, {"roas": 0, "cpc": 300}, tomado_en="2026-09-10T00:00:00")
    ex.snapshot(c, {"roas": 0, "cpc": 700}, tomado_en="2026-09-10T00:00:00")
    ex.snapshot(d, {"roas": 5.0, "cpc": 100}, tomado_en="2026-09-10T00:00:00")
    with base_temporal.conectar() as con:
        con.execute(base_temporal.pieza.update().values(url_miniatura="https://r2/mini.jpg"))

    top = tablero.top_ganadoras("acme")
    assert [t["ep_id"] for t in top] == [d, a, b, c]
    assert tablero.top_ganadoras("acme", n=2)[1]["ep_id"] == a
    primero = top[0]
    assert primero["experimento_id"] == cerrado and primero["experimento_nombre"] == "Viejo"
    assert primero["pais"] == "CO" and primero["nombre"].startswith("Final es_CO")
    assert primero["url_miniatura"] == "https://r2/mini.jpg" and primero["url_video"] == "https://r2/f.mp4"
    assert primero["metricas"]["roas"] == 5.0 and primero["escalon_rescate"] == 1
    assert top[1]["veredicto_motivo"] == "ROAS 3" and top[1]["veredicto_en"] == AHORA
    assert primero["moneda"] == "COP"


# ---------- alertas ----------

def test_alertas_vacias_cuando_todo_esta_bien(base_temporal, sin_red):
    import experimentos as ex
    import tablero
    eid = _experimento(base_temporal)
    ep = _pieza_en(base_temporal, eid)
    ex.snapshot(ep, {"gasto": 1}, tomado_en="2026-09-16T08:30:00")
    assert tablero.alertas("acme", ahora_iso=AHORA) == []


def test_alertas_meta_sin_conectar_y_rota(base_temporal, sin_red):
    import meta_conexion
    import tablero
    sin_red.setattr(meta_conexion, "estado", lambda c: {"estado": "sin_conectar"})
    a = tablero.alertas("acme", ahora_iso=AHORA)
    assert len(a) == 1 and a[0]["tipo"] == "meta_sin_conectar" and a[0]["nivel"] == "alta"
    assert a[0]["tab"] == "settings" and a[0]["experimento_id"] is None and "Configuración" in a[0]["texto"]
    sin_red.setattr(meta_conexion, "estado", lambda c: {"estado": "roto"})
    a = tablero.alertas("acme", ahora_iso=AHORA)
    assert [x["tipo"] for x in a] == ["meta_roto"] and a[0]["nivel"] == "alta"


def test_alertas_orden_y_tipos_de_experimento(base_temporal, sin_red):
    import experimentos as ex
    import propuestas
    import tablero
    e_err = _experimento(base_temporal, "Roto", estado="error", error="Meta dijo no")
    e_prop = _experimento(base_temporal, "Con propuestas")
    ep_prop = _pieza_en(base_temporal, e_prop)
    ex.snapshot(ep_prop, {"gasto": 1}, tomado_en="2026-09-16T09:00:00")
    propuestas.crear("acme", e_prop, "pausar", {"ep_id": ep_prop}, "x")
    propuestas.crear("acme", e_prop, "subir", {"ep_id": ep_prop, "pais": "CO"}, "y")
    e_rech = _experimento(base_temporal, "Rechazado", estado="pausado")
    ep_rech = _pieza_en(base_temporal, e_rech, legado="cf_2__es_CO", estado_meta="DISAPPROVED")
    ex.snapshot(ep_rech, {"gasto": 1}, tomado_en="2026-09-16T09:00:00")
    e_tope = _experimento(base_temporal, "Topado", gasto_acumulado=500000.0)
    ep_tope = _pieza_en(base_temporal, e_tope, legado="cf_3__es_CO")
    ex.snapshot(ep_tope, {"gasto": 500000}, tomado_en="2026-09-16T09:00:00")
    e_viejo = _experimento(base_temporal, "Sin datos")
    ep_viejo = _pieza_en(base_temporal, e_viejo, legado="cf_4__es_CO")
    ex.snapshot(ep_viejo, {"gasto": 10}, tomado_en="2026-09-16T03:00:00")  # 7 h antes
    e_nunca = _experimento(base_temporal, "Nunca medido")
    _pieza_en(base_temporal, e_nunca, legado="cf_5__es_CO")
    # Cerrado con tope: no alerta.
    _experimento(base_temporal, "Cerrado", estado="cerrado", gasto_acumulado=900000.0)

    a = tablero.alertas("acme", ahora_iso=AHORA)
    assert [(x["tipo"], x["nivel"], x["experimento_id"]) for x in a] == [
        ("experimento_error", "alta", e_err),
        ("propuestas_pendientes", "media", e_prop),
        ("anuncios_rechazados", "alta", e_rech),
        ("tope_alcanzado", "media", e_tope),
        ("sin_metricas", "baja", e_nunca),
        ("sin_metricas", "baja", e_viejo),
    ]
    assert all(x["tab"] == "experimentos" for x in a)
    assert "Meta dijo no" in a[0]["texto"]
    assert "2 propuestas" in a[1]["texto"]
    assert "1 anuncio " in a[2]["texto"] and "Rechazado" in a[2]["texto"]
    assert "500.000 COP" in a[3]["texto"]
    assert "todavía no tiene métricas" in a[4]["texto"]
    assert "7 h sin métricas" in a[5]["texto"]


def test_alertas_tienda_rota_pixel_y_productos(base_temporal, sin_red):
    import experimentos as ex
    import meta_conexion
    import tablero
    import tiendas
    sin_red.setattr(tiendas, "listar", lambda c: [
        {"id": 1, "tipo": "shopify", "nombre": "Mi tienda", "dominio": "x.myshopify.com", "estado": "rota",
         "error": "token vencido"},
        {"id": 2, "tipo": "woo", "nombre": "Ok", "dominio": None, "estado": "conectada", "error": None}])
    sin_red.setattr(meta_conexion, "estado_pixel",
                    lambda c, solo_cache=False: {"estado": "sin_datos", "pixel_id": "1"})
    # Experimento con atribución pixel, con métricas frescas (no dispara sin_metricas).
    e_px = _experimento(base_temporal, "Pixel", atribucion="pixel")
    ep = _pieza_en(base_temporal, e_px, legado="cf_1__es_CO")
    ex.snapshot(ep, {"gasto": 1}, tomado_en="2026-09-16T09:30:00")
    # Productos: uno en prueba dentro del experimento (por nombre en productos_ids
    # de la sesión cf_1), uno en prueba suelto, uno sin marcar, uno archivado.
    import creative_flow
    creative_flow.crear("acme", [], ["Cojín abrazable"], [], "abrazo", 15, "cálido", "A", legado_id="cf_1")
    p1 = tiendas.upsert_producto("acme", "csv", "1", {"nombre": "Cojín abrazable"})
    p2 = tiendas.upsert_producto("acme", "csv", "2", {"nombre": "Lámpara"})
    p3 = tiendas.upsert_producto("acme", "csv", "3", {"nombre": "Taza"})
    p4 = tiendas.upsert_producto("acme", "csv", "4", {"nombre": "Archivado"})
    tiendas.marcar_producto("acme", p1, en_prueba=True)
    tiendas.marcar_producto("acme", p2, en_prueba=True)
    tiendas.marcar_producto("acme", p4, en_prueba=True, archivado=True)
    assert p3

    a = tablero.alertas("acme", ahora_iso=AHORA)
    assert [(x["tipo"], x["nivel"], x["tab"]) for x in a] == [
        ("tienda_rota", "media", "settings"),
        ("pixel_sin_datos", "media", "settings"),
        ("productos_sin_experimento", "baja", "productos"),
    ]
    assert "shopify" in a[0]["texto"] and "Mi tienda" in a[0]["texto"] and "token vencido" in a[0]["texto"]
    assert "1 experimento mide" in a[1]["texto"]
    assert a[2]["texto"].startswith("1 producto marcado")

    # Sin experimentos con pixel no se consulta el Pixel; con caché vacía (None) tampoco alerta.
    ex.actualizar("acme", e_px, atribucion="tienda")
    assert "pixel_sin_datos" not in [x["tipo"] for x in tablero.alertas("acme", ahora_iso=AHORA)]
    ex.actualizar("acme", e_px, atribucion="pixel")
    sin_red.setattr(meta_conexion, "estado_pixel", lambda c, solo_cache=False: None)
    assert "pixel_sin_datos" not in [x["tipo"] for x in tablero.alertas("acme", ahora_iso=AHORA)]
    sin_red.setattr(meta_conexion, "estado_pixel", lambda c, solo_cache=False: {"estado": "sin_pixel"})
    px = [x for x in tablero.alertas("acme", ahora_iso=AHORA) if x["tipo"] == "pixel_sin_datos"]
    assert len(px) == 1 and "no tiene Pixel" in px[0]["texto"]


# ---------- csv_mes ----------

def test_csv_mes_cabecera_y_fila(base_temporal, sin_red):
    import experimentos as ex
    import tablero
    eid = _experimento(base_temporal, "Cojín")
    ep = _pieza_en(base_temporal, eid, veredicto="ganador")
    ex.snapshot(ep, {"gasto": 100, "impresiones": 1000, "clics_enlace": 10, "compras": 1, "ingresos": 5000,
                     "fuente_ventas": "meta"}, tomado_en="2026-08-31T23:00:00")
    ex.snapshot(ep, {"gasto": 350.5, "impresiones": 4000, "clics_enlace": 40, "compras": 3, "ingresos": 12000,
                     "fuente_ventas": "meta"}, tomado_en="2026-09-15T23:00:00")
    texto = tablero.csv_mes("acme", ahora_iso=AHORA)
    assert texto.startswith("﻿")
    lineas = texto.lstrip("﻿").splitlines()
    assert lineas[0] == "experimento;pais;pieza;veredicto;impresiones;clics;gasto;compras;ingresos;roas;moneda"
    assert lineas[1] == f"Cojín;CO;Final es_CO;ganador;3000;30;250.50;2;7000;{round(7000 / 250.5, 2)};COP"
    assert len(lineas) == 2


def test_csv_mes_sin_piezas(base_temporal, sin_red):
    import tablero
    assert tablero.csv_mes("acme", ahora_iso=AHORA).lstrip("﻿").splitlines() == [
        ";".join(tablero.ENCABEZADO_CSV)]
