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


def test_serie_diaria_cruza_el_cambio_de_mes(base_temporal, sin_red):
    """Ventana de 4 días que empieza en agosto: los cortes de día son
    aritmética de fechas, no de texto, y el snapshot anterior a la ventana
    (31/08 mañana) es la base del delta del primer día."""
    import experimentos as ex
    import tablero
    eid = _experimento(base_temporal)
    ep = _pieza_en(base_temporal, eid)
    ex.snapshot(ep, {"gasto": 50}, tomado_en="2026-08-29T12:00:00")     # antes de la ventana: base
    ex.snapshot(ep, {"gasto": 80}, tomado_en="2026-08-31T20:00:00")     # 31/08: +30
    ex.snapshot(ep, {"gasto": 100}, tomado_en="2026-09-01T08:00:00")    # 01/09: +20
    ex.snapshot(ep, {"gasto": 140}, tomado_en="2026-09-02T23:59:59")    # 02/09: +40
    s = tablero.serie_diaria("acme", dias=4, ahora_iso="2026-09-02T23:59:59")
    assert [d["dia"] for d in s["dias"]] == ["2026-08-30", "2026-08-31", "2026-09-01", "2026-09-02"]
    assert [d["gasto"] for d in s["dias"]] == [0.0, 30.0, 20.0, 40.0]


# ---------- carga compartida / Serie ----------

def test_serie_indexada_equivale_a_la_lista_cruda():
    import tablero
    snaps = [_snap("2026-09-03T08:00:00", gasto=240.0),
             _snap("2026-09-01T08:00:00", gasto=100.0),   # desordenado a propósito
             _snap("2026-09-02T08:00:00", gasto=250.0)]
    serie = tablero.Serie(snaps)
    assert serie.claves == ["2026-09-01T08:00:00", "2026-09-02T08:00:00", "2026-09-03T08:00:00"]
    for instante in ("2026-08-31T00:00:00", "2026-09-01T08:00:00", "2026-09-02T12:00:00", "2026-09-09T00:00:00"):
        assert tablero.valor_en(serie, instante, "gasto") == tablero.valor_en(snaps, instante, "gasto")
    assert tablero.delta(serie, "2026-09-01T12:00:00", "2026-09-02T12:00:00", "gasto") == 150.0
    assert tablero.Serie([]).en("2026-09-01T00:00:00") is None


def test_snapshots_con_desde_trae_la_ventana_y_la_base(base_temporal):
    import experimentos as ex
    eid = _experimento(base_temporal)
    ep = _pieza_en(base_temporal, eid)
    for t, g in (("2026-08-20T08:00:00", 10), ("2026-08-30T08:00:00", 20), ("2026-08-31T08:00:00", 30),
                 ("2026-09-01T00:00:00", 40), ("2026-09-05T08:00:00", 50)):
        ex.snapshot(ep, {"gasto": g}, tomado_en=t)
    todos = ex.snapshots(ep)
    assert [s["gasto"] for s in todos] == [10.0, 20.0, 30.0, 40.0, 50.0]
    ventana = ex.snapshots(ep, desde="2026-09-01T00:00:00")
    # La última anterior a `desde` (31/08, base del delta) + las de la ventana (>= desde).
    assert [s["gasto"] for s in ventana] == [30.0, 40.0, 50.0]
    assert ex.snapshots(ep, desde="2026-08-01T00:00:00") == todos          # nada antes: sin base
    assert [s["gasto"] for s in ex.snapshots(ep, desde="2026-09-30T00:00:00")] == [50.0]   # solo la base
    assert ex.snapshots(ep + 999, desde="2026-09-01T00:00:00") == []


def test_cargar_datos_una_vez_y_contexto(base_temporal, sin_red, monkeypatch):
    """`contexto` deriva todas las partes de UNA carga: experimentos.cargar
    y experimentos.snapshots se llaman una vez (por proyecto / por pieza),
    y el resultado coincide con las funciones sueltas."""
    import experimentos as ex
    import tablero
    eid = _experimento(base_temporal, "Cojín")
    ep = _pieza_en(base_temporal, eid, veredicto="ganador")
    ex.snapshot(ep, {"gasto": 100, "compras": 1, "ingresos": 5000, "fuente_ventas": "meta"},
                tomado_en="2026-07-01T08:00:00")     # viejo: solo entra como base
    ex.snapshot(ep, {"gasto": 350, "compras": 3, "ingresos": 12000, "fuente_ventas": "meta"},
                tomado_en="2026-09-15T23:00:00")
    sueltas = {"resumen": tablero.resumen_mes("acme", AHORA), "serie": tablero.serie_diaria("acme", 30, AHORA),
               "top": tablero.top_ganadoras("acme"), "alertas": tablero.alertas("acme", AHORA),
               "csv": tablero.csv_mes("acme", AHORA)}
    llamadas = {"cargar": 0, "snapshots": []}
    cargar, snapshots = ex.cargar, ex.snapshots

    def _cargar(cliente):
        llamadas["cargar"] += 1
        return cargar(cliente)

    def _snapshots(ep_id, desde=None):
        llamadas["snapshots"].append(desde)
        return snapshots(ep_id, desde=desde)
    monkeypatch.setattr(ex, "cargar", _cargar)
    monkeypatch.setattr(ex, "snapshots", _snapshots)
    ctx = tablero.contexto("acme", AHORA)
    assert llamadas["cargar"] == 1
    # Una consulta por pieza, acotada a lo más temprano entre el mes y los 30 días.
    assert llamadas["snapshots"] == ["2026-08-18T00:00:00"]
    assert ctx["ahora"] == AHORA
    for parte, valor in sueltas.items():
        assert ctx[parte] == valor, parte
    assert ctx["resumen"]["por_moneda"]["COP"]["gasto"] == 250.0
    assert ctx["top"][0]["experimento_estado"] == "corriendo"
    # Con `datos` cargados para otra ventana más corta, una parte que necesite
    # empezar antes vuelve a cargar (no se queda sin base del delta).
    datos = tablero.cargar_datos("acme", AHORA, desde="2026-09-10T00:00:00")
    assert datos.desde == "2026-09-10T00:00:00"
    llamadas["snapshots"].clear()
    r = tablero.resumen_periodo("acme", "2026-09-01T00:00:00", AHORA, datos=datos)
    assert llamadas["snapshots"] == ["2026-09-01T00:00:00"] and r["por_moneda"]["COP"]["gasto"] == 250.0
    llamadas["snapshots"].clear()
    r2 = tablero.resumen_periodo("acme", "2026-09-12T00:00:00", AHORA, datos=datos)
    assert llamadas["snapshots"] == [] and r2["por_moneda"]["COP"]["gasto"] == 250.0


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
        ("productos_sin_experimento", "baja", "catalogo"),
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
    roas = str(round(7000 / 250.5, 2)).replace(".", ",")
    assert lineas[1] == f"Cojín;CO;Final es_CO;ganador;3000;30;250,50;2;7000;{roas};COP"
    assert len(lineas) == 2


def test_csv_mes_neutraliza_formulas(base_temporal, sin_red):
    """Un nombre que empiece por =, +, -, @, tab o CR se abriría como fórmula
    en Excel: va con `'` delante. Los números no se tocan."""
    import csv
    import io
    import experimentos as ex
    import tablero
    nombre = '=HYPERLINK("http://malo.example/x";"Cojín")'
    eid = _experimento(base_temporal, nombre)
    # Pieza clon: su nombre sale del legado_id (texto que no escribe el dueño).
    pid = _pieza(base_temporal, tipo="video", legado="-2+3")
    ep = ex.agregar_pieza("acme", eid, pid, "CO")
    ex.actualizar_pieza("acme", ep, estado="activo", veredicto="ganador")
    ex.snapshot(ep, {"gasto": 10, "impresiones": 100}, tomado_en="2026-09-15T23:00:00")
    texto = tablero.csv_mes("acme", ahora_iso=AHORA).lstrip("﻿")
    filas = list(csv.reader(io.StringIO(texto), delimiter=";"))
    assert filas[1] == ["'" + nombre, "CO", "'-2+3", "ganador", "100", "0", "10", "0", "0", "0", "COP"]
    assert "\n'=HYPERLINK" not in texto and '"\'=HYPERLINK' in texto   # csv.writer entrecomilla por las `"` y el `;`
    for v, esperado in (("=1+1", "'=1+1"), ("+1", "'+1"), ("-1", "'-1"), ("@x", "'@x"), ("\tx", "'\tx"),
                        ("\rx", "'\rx"), ("Cojín", "Cojín"), ("", ""), (None, "")):
        assert tablero._celda(v) == esperado


def test_alerta_sin_metricas_redondea_las_horas(base_temporal, sin_red):
    import experimentos as ex
    import tablero
    eid = _experimento(base_temporal, "Cojín")
    ep = _pieza_en(base_temporal, eid)
    ex.snapshot(ep, {"gasto": 1}, tomado_en="2026-09-16T03:24:00")   # 6,6 h antes de AHORA: «7 h», no «6 h»
    a = [x for x in tablero.alertas("acme", ahora_iso=AHORA) if x["tipo"] == "sin_metricas"]
    assert len(a) == 1 and "lleva 7 h sin métricas" in a[0]["texto"]


def test_csv_mes_sin_piezas(base_temporal, sin_red):
    import tablero
    assert tablero.csv_mes("acme", ahora_iso=AHORA).lstrip("﻿").splitlines() == [
        ";".join(tablero.ENCABEZADO_CSV)]
