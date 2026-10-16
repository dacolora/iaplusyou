"""Sumas precalculadas de Triple Whale (spec 2026-10-15-rendimiento-sumas-precalculadas): el worker graba lo que
calculan las funciones pesadas de `triple_whale.datos` y la pestaña lo lee si es de la misma versión de los datos."""
from datetime import date, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy import event

import db
import triple_whale_tiendas as tt
from triple_whale import datos, memo

HOY = date.today()


def _hace(n):
    return (HOY - timedelta(days=n)).isoformat()


@pytest.fixture()
def dos(base_temporal, monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "test_secret_key_12345678")
    se = tt.agregar("acme", "llave-se", "acme-se.myshopify.com", pais="SE")  # llave-de-prueba
    no = tt.agregar("acme", "llave-no", "acme-no.myshopify.com", pais="NO")  # llave-de-prueba
    otro = tt.agregar("otro", "llave-otro", "otro.myshopify.com", pais="SE")  # llave-de-prueba
    for tid, cliente in ((se, "acme"), (no, "acme"), (otro, "otro")):
        for n in range(4):
            f = _hace(n)
            datos.reemplazar_anuncios_canal(cliente, tid, f, f, [
                {"canal": "facebook-ads", "ad_id": "A", "fecha": f, "anuncio": "Compartido", "gasto": 10 + n,
                 "impresiones": 1000, "clics": 30, "destino_url": "https://x/products/a"},
                {"canal": "google-ads", "ad_id": f"G{tid}", "fecha": f, "anuncio": "Marca", "gasto": 2}])
            datos.reemplazar_anuncios_pixel(cliente, tid, f, f, [
                {"canal": "facebook-ads", "ad_id": "A", "fecha": f, "pedidos": 1.5, "ingresos": 40.25,
                 "sesiones": 100, "nc_ingresos": 20}])
            datos.reemplazar_tienda(cliente, tid, f, f, [{"fecha": f, "gasto": 50, "ingresos": 120.5, "pedidos": 3}])
            datos.reemplazar_productos(cliente, tid, f, f, [{"fecha": f, "producto_id": "p1", "nombre": "Uno",
                                                              "unidades": 2, "ingresos": 60, "pedidos": 2}])
    return se, no, otro


LLAMADAS = [
    ("totales_por_anuncio", lambda t: datos.totales_por_anuncio("acme", t, _hace(3), _hace(0))),
    ("serie_tienda", lambda t: datos.serie_tienda("acme", t, _hace(3), _hace(0))),
    ("serie_anuncios", lambda t: datos.serie_anuncios("acme", t, _hace(3), _hace(0))),
    ("cohortes", lambda t: datos.cohortes("acme", t, _hace(3), _hace(0))),
    ("gasto_por_antiguedad", lambda t: datos.gasto_por_antiguedad("acme", t, _hace(3), _hace(0))),
    ("gasto_por_canal", lambda t: datos.gasto_por_canal("acme", t, _hace(3), _hace(0))),
    ("gasto_duplicado", lambda t: datos.gasto_duplicado("acme", _hace(3), _hace(0), t)),
    ("canales", lambda t: datos.canales("acme", t, _hace(3), _hace(0))),
    ("top_productos", lambda t: datos.top_productos("acme", t, _hace(3), _hace(0))),
]


def _lecturas_de_la_copia(fn):
    """(resultado, cuántas consultas tocaron tw_anuncio_dia, tw_tienda_dia o tw_producto_dia)."""
    n = []

    def contar(_c, _cur, sql, *_a):
        if any(t in sql for t in ("tw_anuncio_dia", "tw_tienda_dia", "tw_producto_dia")):
            n.append(sql)
    event.listen(sa.engine.Engine, "before_cursor_execute", contar)
    try:
        return fn(), len(n)
    finally:
        event.remove(sa.engine.Engine, "before_cursor_execute", contar)


def _filas_memo():
    with db.conectar() as con:
        return con.execute(sa.select(db.tw_memo.c.cliente, db.tw_memo.c.version)).all()


@pytest.mark.parametrize("nombre, llamar", LLAMADAS, ids=[n for n, _ in LLAMADAS])
@pytest.mark.parametrize("alcance", ["todas", "una"])
def test_lo_grabado_es_exactamente_lo_calculado_y_no_vuelve_a_leer_la_copia(dos, nombre, llamar, alcance):
    tienda = None if alcance == "todas" else dos[0]
    vivo, n_vivo = _lecturas_de_la_copia(lambda: llamar(tienda))
    assert n_vivo >= 1
    with memo.grabando("acme"):
        grabado_al_calcular = llamar(tienda)
    assert grabado_al_calcular == vivo
    leido, n_leido = _lecturas_de_la_copia(lambda: llamar(tienda))
    assert leido == vivo and type(leido) is type(vivo), nombre
    assert n_leido == 0, nombre


def test_una_copia_nueva_cambia_la_version_y_se_calcula_en_vivo(dos):
    se = dos[0]
    with memo.grabando("acme"):
        datos.totales_por_anuncio("acme", se, _hace(3), _hace(0))
    tt.actualizar_tienda("acme", se, ultima_sincronizacion="2099-01-01T00:00:00")
    _, n = _lecturas_de_la_copia(lambda: datos.totales_por_anuncio("acme", se, _hace(3), _hace(0)))
    assert n >= 1


def test_un_cambio_de_ajustes_tambien_cambia_la_version(dos):
    v = memo.version("acme")
    with db.conectar() as con:
        con.execute(db.triple_whale.update().where(db.triple_whale.c.cliente == "acme").values(ventana_atribucion="7_days"))
    assert memo.version("acme") != v


def test_otros_argumentos_u_otro_proyecto_se_calculan_en_vivo(dos):
    se, _, otro = dos
    with memo.grabando("acme"):
        datos.totales_por_anuncio("acme", se, _hace(3), _hace(0))
    _, n = _lecturas_de_la_copia(lambda: datos.totales_por_anuncio("acme", se, _hace(2), _hace(0)))
    assert n >= 1
    _, n = _lecturas_de_la_copia(lambda: datos.totales_por_anuncio("otro", otro, _hace(3), _hace(0)))
    assert n >= 1


def test_fuera_del_worker_nunca_se_escribe(dos):
    for _, llamar in LLAMADAS:
        llamar(None)
    assert _filas_memo() == []


def test_grabar_borra_lo_de_versiones_viejas_y_no_toca_otro_proyecto(dos):
    se, _, otro = dos
    with memo.grabando("otro"):
        datos.totales_por_anuncio("otro", otro, _hace(3), _hace(0))
    with memo.grabando("acme"):
        datos.totales_por_anuncio("acme", se, _hace(3), _hace(0))
    tt.actualizar_tienda("acme", se, ultima_sincronizacion="2099-01-01T00:00:00")
    with memo.grabando("acme"):
        datos.canales("acme", se, _hace(3), _hace(0))
    filas = _filas_memo()
    assert {c for c, _ in filas} == {"acme", "otro"}
    assert len({v for c, v in filas if c == "acme"}) == 1 and memo.version("acme") in {v for c, v in filas}


def test_si_los_datos_cambian_mientras_se_graba_no_se_guarda_nada(dos):
    se = dos[0]
    with memo.grabando("acme"):
        datos.totales_por_anuncio("acme", se, _hace(3), _hace(0))
        tt.actualizar_tienda("acme", se, ultima_sincronizacion="2099-01-01T00:00:00")   # una copia terminó en medio
    assert _filas_memo() == []


# ------------------------------------------------------------- revisión final (2026-10-15): plata y memoria ---

def test_grabar_comprime_al_capturar_y_escribe_en_tandas_cortas(dos):
    """El candado de escritura de SQLite no se toma mientras se arma el JSON ni se comprime (con un año eran ~3 s:
    un gasto ya pagado que se anota en ese momento recibía «database is locked» pasado el busy_timeout de 5 s)."""
    se, no, _ = dos
    with memo.grabando("acme") as g:
        for t in (None, se, no):
            for _, llamar in LLAMADAS:
                llamar(t)
        assert g["filas"] and all(isinstance(datos_, bytes) for _, datos_ in g["filas"].values())
    por_conexion, orden = {}, []

    def mirar(conn, _cur, sql, *_a):
        if "tw_memo" in sql and sql.lstrip().upper().startswith(("INSERT", "DELETE")):
            por_conexion[id(conn)] = por_conexion.get(id(conn), 0) + 1
            orden.append(sql.lstrip().split()[0].upper())
    tt.actualizar_tienda("acme", se, ultima_sincronizacion="2099-01-01T00:00:00")
    event.listen(sa.engine.Engine, "before_cursor_execute", mirar)
    try:
        with memo.grabando("acme"):
            for t in (None, se, no):
                for _, llamar in LLAMADAS:
                    llamar(t)
    finally:
        event.remove(sa.engine.Engine, "before_cursor_execute", mirar)
    assert max(por_conexion.values()) <= memo.TANDA * 2, por_conexion
    assert orden[-1] == "DELETE" and "INSERT" in orden


def test_cambiar_lo_que_devolvio_al_grabar_no_cambia_lo_grabado(dos):
    se = dos[0]
    with memo.grabando("acme"):
        filas = datos.totales_por_anuncio("acme", se, _hace(3), _hace(0))
        filas[0]["gasto"] = -1
        filas.append({"ad_id": "inventado"})
    leidas = datos.totales_por_anuncio("acme", se, _hace(3), _hace(0))
    assert leidas == datos.totales_por_anuncio.sin_memo("acme", se, _hace(3), _hace(0))


def test_grabar_dice_si_la_version_cambio_en_medio(dos):
    se = dos[0]
    with memo.grabando("acme") as g:
        datos.canales("acme", se, _hace(3), _hace(0))
        tt.actualizar_tienda("acme", se, ultima_sincronizacion="2099-01-01T00:00:00")
    assert g["version_cambio"] is True and g["guardadas"] == 0
