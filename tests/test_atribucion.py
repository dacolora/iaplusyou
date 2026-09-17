"""Atribución por tienda (atribucion.py): pedidos con utm → experimento_pieza,
ventas desde activado_en, mezcla en lanzador.refrescar y la atribución
sugerida al crear experimentos."""
import pytest

from tests.test_experimentos_db import PAISES, _pieza
from tests.test_lanzador import entorno  # noqa: F401 — fixture reutilizada


@pytest.fixture()
def tienda(base_temporal, monkeypatch):
    import tiendas
    monkeypatch.setenv("FLASK_SECRET_KEY", "clave-de-prueba-larga-1234567890")
    return tiendas.conectar("acme", "shopify", {"token": "t1"}, nombre="Acme", dominio="acme.myshopify.com")


def _pedidos(tid, *pedidos, cliente="acme", moneda="COP", fecha=None):
    import db
    import tiendas
    filas = []
    for i, (utm, total) in enumerate(pedidos):
        filas.append({"fuente_id": f"o{tid}_{i}_{utm}_{fecha or ''}", "fecha": fecha or db.ahora(), "total": total,
                      "moneda": moneda, "utm_content": utm})
    return tiendas.guardar_pedidos(cliente, tid, filas)


def _experimento(cliente="acme", atribucion="tienda"):
    import experimentos as ex
    return ex.crear(cliente, "Cojín", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP", atribucion=atribucion)


# --- resolver_pendientes ------------------------------------------------------

def test_resolver_pendientes_liga_por_experimento_pieza_id(base_temporal, tienda):
    """F2: el mismo clon en CO y MX son dos eps con dos anuncios; el utm
    lleva el ep id, así cada venta cae en el país que la generó."""
    import atribucion
    import experimentos as ex
    import tiendas
    pieza = _pieza(base_temporal, tipo="video", pais=None, idioma=None, legado="cf_1")
    eid = _experimento()
    ep_co = ex.agregar_pieza("acme", eid, pieza, "CO")
    ep_mx = ex.agregar_pieza("acme", eid, pieza, "MX")
    _pedidos(tienda, (str(ep_co), 30.0), (str(ep_mx), 20.0), (str(ep_mx), 5.0))
    assert atribucion.resolver_pendientes("acme") == 3
    assert tiendas.pedidos_sin_resolver("acme") == []
    assert tiendas.ventas_por_pieza("acme", ep_co, "2000-01-01T00:00:00") == {"compras": 1, "ingresos": 30.0, "monedas": ["COP"]}
    assert tiendas.ventas_por_pieza("acme", ep_mx, "2000-01-01T00:00:00") == {"compras": 2, "ingresos": 25.0, "monedas": ["COP"]}
    assert atribucion.resolver_pendientes("acme") == 0


def test_resolver_pendientes_ep_de_experimento_cerrado_queda_pendiente(base_temporal, tienda):
    """Un ep real cuyo experimento cerró no se reinterpreta como pieza.id
    aunque exista una pieza con ese número en otro experimento abierto."""
    import atribucion
    import experimentos as ex
    import tiendas
    pieza = _pieza(base_temporal)          # pieza.id == 1
    e1 = _experimento()
    ep1 = ex.agregar_pieza("acme", e1, pieza, "CO")   # ep.id == 1 también
    assert ep1 == pieza
    ex.actualizar("acme", e1, estado="cerrado")
    e2 = _experimento()
    ep2 = ex.agregar_pieza("acme", e2, pieza, "CO")
    _pedidos(tienda, (str(ep1), 30.0))
    assert atribucion.resolver_pendientes("acme") == 0
    assert len(tiendas.pedidos_sin_resolver("acme")) == 1
    assert tiendas.ventas_por_pieza("acme", ep2, "2000-01-01T00:00:00")["compras"] == 0


def test_resolver_pendientes_fallback_pieza_id_elige_el_experimento_abierto_mas_reciente(base_temporal, tienda):
    """Links viejos (utm_content=pieza.id): si ningún ep tiene ese id, se
    lee como pieza y va al experimento abierto más reciente."""
    import atribucion
    import experimentos as ex
    import tiendas
    for _ in range(4):                      # gasta ids de pieza: la de interés será la 5
        _pieza(base_temporal)
    pieza = _pieza(base_temporal)
    e_cerrado = _experimento()
    ep_cerrado = ex.agregar_pieza("acme", e_cerrado, pieza, "CO")
    ex.actualizar("acme", e_cerrado, estado="cerrado")
    e_viejo = _experimento()
    ep_viejo = ex.agregar_pieza("acme", e_viejo, pieza, "CO")
    e_nuevo = _experimento()
    ep_nuevo = ex.agregar_pieza("acme", e_nuevo, pieza, "CO")
    assert pieza not in (ep_cerrado, ep_viejo, ep_nuevo)   # el utm no coincide con ningún ep
    _pedidos(tienda, (str(pieza), 30.0), (str(pieza), 20.0))
    assert atribucion.resolver_pendientes("acme") == 2
    assert tiendas.pedidos_sin_resolver("acme") == []
    assert tiendas.ventas_por_pieza("acme", ep_nuevo, "2000-01-01T00:00:00") == {"compras": 2, "ingresos": 50.0, "monedas": ["COP"]}
    assert tiendas.ventas_por_pieza("acme", ep_viejo, "2000-01-01T00:00:00")["compras"] == 0
    assert tiendas.ventas_por_pieza("acme", ep_cerrado, "2000-01-01T00:00:00")["compras"] == 0
    # segunda pasada: no hay nada pendiente
    assert atribucion.resolver_pendientes("acme") == 0


def test_resolver_pendientes_salta_utm_no_numerico_y_piezas_sin_experimento(base_temporal, tienda):
    import atribucion
    import tiendas
    pieza = _pieza(base_temporal)   # existe, pero no está en ningún experimento (y no hay ep con ese id)
    _pedidos(tienda, ("ep_1", 10.0), (None, 10.0), ("99999", 10.0), (str(pieza), 10.0))
    assert atribucion.resolver_pendientes("acme") == 0
    # los tres con utm quedan en cola (sin utm no hay nada que resolver)
    assert sorted(p["utm_content"] for p in tiendas.pedidos_sin_resolver("acme")) == sorted(["99999", "ep_1", str(pieza)])


def test_resolver_pendientes_no_atribuye_a_pieza_de_otro_cliente(base_temporal, tienda):
    import atribucion
    import experimentos as ex
    import tiendas
    pieza_ajena = _pieza(base_temporal, cliente="otro")
    e_otro = _experimento(cliente="otro")
    ep_otro = ex.agregar_pieza("otro", e_otro, pieza_ajena, "CO")
    _pedidos(tienda, (str(ep_otro), 40.0), (str(pieza_ajena), 40.0))   # pedidos de acme con ids de otro (ep y pieza)
    assert atribucion.resolver_pendientes("acme") == 0
    assert len(tiendas.pedidos_sin_resolver("acme")) == 2
    assert tiendas.ventas_por_pieza("otro", ep_otro, "2000-01-01T00:00:00")["compras"] == 0


def test_resolver_pendientes_sin_pedidos(base_temporal):
    import atribucion
    assert atribucion.resolver_pendientes("acme") == 0


def test_pedidos_sin_resolver_ignora_los_de_mas_de_30_dias(base_temporal, tienda):
    """F5: un utm que nunca se pudo ligar deja de reescanearse en cada sync."""
    import tiendas
    _pedidos(tienda, ("77777", 10.0), fecha="2000-01-01T00:00:00")
    _pedidos(tienda, ("77777", 10.0))
    assert [p["fecha"] for p in tiendas.pedidos_sin_resolver("acme")] != ["2000-01-01T00:00:00"]
    assert len(tiendas.pedidos_sin_resolver("acme")) == 1
    assert len(tiendas.pedidos_sin_resolver("acme", dias=20000)) == 2


# --- ventas_tienda ------------------------------------------------------------

def test_ventas_tienda_cuenta_desde_activado_en(base_temporal, tienda):
    import atribucion
    import experimentos as ex
    pieza = _pieza(base_temporal)
    eid = _experimento()
    ep_id = ex.agregar_pieza("acme", eid, pieza, "CO")
    _pedidos(tienda, (str(ep_id), 30.0), (str(ep_id), 20.0))
    assert atribucion.resolver_pendientes("acme") == 2
    pz = ex.piezas("acme", eid)[0]
    # sin activado_en: desde creado_en de la pieza en el experimento
    assert atribucion.ventas_tienda("acme", pz) == {"compras": 2, "ingresos": 50.0, "monedas": ["COP"]}
    # activada "en el futuro": los pedidos anteriores no cuentan
    ex.marcar_pieza("acme", ep_id, activado_en="2999-01-01T00:00:00")
    pz = ex.piezas("acme", eid)[0]
    assert pz["extra"]["activado_en"] == "2999-01-01T00:00:00"
    assert atribucion.ventas_tienda("acme", pz) == {"compras": 0, "ingresos": 0.0, "monedas": []}
    # activada en el pasado: vuelven a contar
    ex.marcar_pieza("acme", ep_id, activado_en="2000-01-01T00:00:00")
    assert atribucion.ventas_tienda("acme", ex.piezas("acme", eid)[0])["compras"] == 2


# --- lanzador.refrescar con atribución por tienda ------------------------------

def test_refrescar_con_atribucion_tienda_mezcla_ventas(entorno, tienda):
    import atribucion
    ex, lz, eid = entorno["ex"], entorno["lanzador"], entorno["eid"]
    ex.actualizar("acme", eid, atribucion="tienda")
    lz.lanzar("acme", eid)
    pz0 = ex.obtener("acme", eid)["piezas"][0]
    _pedidos(tienda, (str(pz0["id"]), 30.0), (str(pz0["id"]), 20.0))   # misma moneda que la cuenta (COP)
    assert atribucion.resolver_pendientes("acme") == 2
    assert lz.refrescar("acme", eid) == 3
    e = ex.obtener("acme", eid)
    m = e["piezas"][0]["metricas"]
    # Meta reportó compras=0/ingresos=0; la tienda manda: 2 compras, 50 de ingresos sobre 2.0 de gasto
    assert m["compras"] == 2 and m["ingresos"] == 50.0
    assert m["roas"] == 25.0 and m["cpa"] == 1.0 and m["fuente_ventas"] == "tienda"
    assert m["impresiones"] == 100 and m["gasto"] == 2.0   # el resto sigue viniendo de Meta
    m1 = e["piezas"][1]["metricas"]
    assert m1["compras"] == 0 and m1["ingresos"] == 0.0 and m1["roas"] == 0.0 and m1["cpa"] == 0.0
    assert m1["fuente_ventas"] == "tienda"
    assert e["gasto_acumulado"] == 6.0
    assert not any(ev["tipo"] == "atribucion" for ev in e["eventos"]) and not e["extra"].get("aviso_moneda")


def test_refrescar_con_ventas_en_otra_moneda_deja_roas_en_cero_y_avisa_una_vez(entorno, tienda):
    """F1: ventas en USD sobre una cuenta en COP — el ROAS (ingresos/gasto)
    no es comparable con el umbral absoluto del decisor: queda 0.0, el CPA
    (gasto/compras, moneda de la cuenta) sigue, y hay UN evento por
    experimento, no uno por refresco."""
    import atribucion
    ex, lz, eid = entorno["ex"], entorno["lanzador"], entorno["eid"]
    ex.actualizar("acme", eid, atribucion="tienda")
    lz.lanzar("acme", eid)
    pz0 = ex.obtener("acme", eid)["piezas"][0]
    _pedidos(tienda, (str(pz0["id"]), 30.0), (str(pz0["id"]), 20.0), moneda="USD")
    assert atribucion.resolver_pendientes("acme") == 2
    lz.refrescar("acme", eid)
    e = ex.obtener("acme", eid)
    m = e["piezas"][0]["metricas"]
    assert m["compras"] == 2 and m["ingresos"] == 50.0 and m["fuente_ventas"] == "tienda"
    assert m["roas"] == 0.0 and m["cpa"] == 1.0
    avisos = [ev for ev in e["eventos"] if ev["tipo"] == "atribucion"]
    assert len(avisos) == 1
    assert avisos[0]["mensaje"] == "Ventas en USD, cuenta en COP: ROAS no comparable, se usa CPA"
    assert e["extra"]["aviso_moneda"] == "USD"
    lz.refrescar("acme", eid)
    e = ex.obtener("acme", eid)
    assert len([ev for ev in e["eventos"] if ev["tipo"] == "atribucion"]) == 1
    assert e["piezas"][0]["metricas"]["roas"] == 0.0


def test_refrescar_con_atribucion_pixel_deja_lo_de_meta(entorno, tienda):
    import atribucion
    ex, lz, eid = entorno["ex"], entorno["lanzador"], entorno["eid"]
    ex.actualizar("acme", eid, atribucion="pixel")
    lz.lanzar("acme", eid)
    pz0 = ex.obtener("acme", eid)["piezas"][0]
    _pedidos(tienda, (str(pz0["id"]), 30.0))
    atribucion.resolver_pendientes("acme")
    lz.refrescar("acme", eid)
    m = ex.obtener("acme", eid)["piezas"][0]["metricas"]
    assert m["compras"] == 0 and m["ingresos"] == 0.0 and m["fuente_ventas"] == "ninguna"


def test_refrescar_con_pixel_marca_fuente_meta_cuando_hay_compras(entorno):
    import types
    ex, lz, eid = entorno["ex"], entorno["lanzador"], entorno["eid"]
    ex.actualizar("acme", eid, atribucion="pixel")
    lz.lanzar("acme", eid)
    entorno["monkeypatch"].setattr(lz, "meta_insights", types.SimpleNamespace(
        obtener_resultados=lambda ad_id, objetivo=None: {"impresiones": 10, "gasto_usd": 4.0, "compras": 2,
                                                          "ingresos": 40.0, "roas": 10.0, "estado_meta": "ACTIVE"}))
    lz.refrescar("acme", eid)
    m = ex.obtener("acme", eid)["piezas"][0]["metricas"]
    assert m["compras"] == 2 and m["ingresos"] == 40.0 and m["roas"] == 10.0 and m["fuente_ventas"] == "meta"


# --- atribucion_sugerida / crear -------------------------------------------------

def _pixel(monkeypatch, estado):
    import meta_conexion
    monkeypatch.setattr(meta_conexion, "estado_pixel",
                        lambda c, solo_cache=False: None if estado is None else {"estado": estado})


def test_atribucion_sugerida_solo_mira_el_pixel_en_cache(base_temporal, monkeypatch, tienda):
    """F6: crear experimento corre en un POST — sin caché del Pixel no se va
    a Graph: la sugerencia cae a tienda/ninguna."""
    import experimentos as ex
    import meta_conexion
    llamadas = []
    monkeypatch.setattr(meta_conexion, "_listar_pixels_con_credenciales", lambda c: llamadas.append(c) or [])
    monkeypatch.setattr(meta_conexion, "estado", lambda c: {"estado": "conectado"})
    assert ex.atribucion_sugerida("acme") == "tienda"
    assert llamadas == []
    meta_conexion.estado_pixel("acme")           # la página de ajustes llena el caché (sin_pixel)
    assert llamadas == ["acme"]
    assert ex.atribucion_sugerida("acme") == "tienda"
    meta_conexion._cache_pixel["acme"] = (meta_conexion.time.time(), {"estado": "ok"})
    assert ex.atribucion_sugerida("acme") == "pixel"
    assert llamadas == ["acme"]


def test_atribucion_sugerida_pixel_si_el_pixel_dispara(base_temporal, monkeypatch, tienda):
    import experimentos as ex
    _pixel(monkeypatch, "ok")
    assert ex.atribucion_sugerida("acme") == "pixel"


def test_atribucion_sugerida_tienda_si_hay_shopify_o_woo_conectada(base_temporal, monkeypatch, tienda):
    import experimentos as ex
    import tiendas
    _pixel(monkeypatch, "sin_datos")
    assert ex.atribucion_sugerida("acme") == "tienda"
    tiendas.actualizar("acme", tienda, estado="rota")
    assert ex.atribucion_sugerida("acme") == "ninguna"
    tiendas.actualizar("acme", tienda, estado="conectada")
    # una tienda de otro cliente no cuenta
    assert ex.atribucion_sugerida("otro") == "ninguna"


def test_atribucion_sugerida_ninguna_con_meli_o_sin_tiendas(base_temporal, monkeypatch):
    import experimentos as ex
    import tiendas
    _pixel(monkeypatch, "sin_conexion")
    assert ex.atribucion_sugerida("acme") == "ninguna"
    monkeypatch.setenv("FLASK_SECRET_KEY", "clave-de-prueba-larga-1234567890")
    tiendas.conectar("acme", "meli", {"token": "t"})   # MELI no expone utm: no sirve para atribuir
    assert ex.atribucion_sugerida("acme") == "ninguna"


def test_crear_usa_la_sugerida_y_valida(base_temporal, monkeypatch, tienda):
    import experimentos as ex
    _pixel(monkeypatch, "sin_pixel")
    eid = ex.crear("acme", "Cojín", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    assert ex.obtener("acme", eid)["atribucion"] == "tienda"
    _pixel(monkeypatch, "ok")
    eid = ex.crear("acme", "Cojín", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    assert ex.obtener("acme", eid)["atribucion"] == "pixel"
    eid = ex.crear("acme", "Cojín", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP", atribucion="ninguna")
    assert ex.obtener("acme", eid)["atribucion"] == "ninguna"
    with pytest.raises(ValueError):
        ex.crear("acme", "Cojín", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP", atribucion="magia")
    # un hijo hereda la atribución del padre, no la sugerida de hoy
    hijo = ex.crear_hijo("acme", eid, "Hijo", 1)
    assert ex.obtener("acme", hijo)["atribucion"] == "ninguna"
