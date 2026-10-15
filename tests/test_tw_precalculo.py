"""La tarea `tw_precalcular` (spec 2026-10-15-rendimiento-sumas-precalculadas): después de la última copia de Triple
Whale del proyecto, el worker corre la pestaña grabando las sumas pesadas; la pestaña sale igual y lee menos."""
import sqlalchemy as sa
from sqlalchemy import event

import cola
import db
import tareas
import worker
from tareas import triple_whale as t
from tests.test_rendimiento_destacados import _catalogo, _llave_de_cifrado, _sembrar_anuncios, _tienda  # noqa: F401
from tests.test_rutas_configuracion import app  # noqa: F401  (fixture)


def _consultas_a_la_copia(fn):
    n = []

    def contar(_c, _cur, sql, *_a):
        if "tw_anuncio_dia" in sql or "tw_tienda_dia" in sql:
            n.append(sql)
    event.listen(sa.engine.Engine, "before_cursor_execute", contar)
    try:
        return fn(), len(n)
    finally:
        event.remove(sa.engine.Engine, "before_cursor_execute", contar)


def _memo():
    with db.conectar() as con:
        return con.execute(sa.select(db.tw_memo.c.cliente, db.tw_memo.c.funcion)).all()


def _panel(app, q=""):  # noqa: F811
    r = app["c"].get("/cliente/acme/rendimiento/panel" + q)
    assert r.status_code == 200
    return r.data.decode()


def test_con_el_precalculo_la_pestana_sale_igual_y_lee_menos_la_copia(app):  # noqa: F811
    tid = _tienda()
    _sembrar_anuncios(tid, n=8)
    _catalogo()
    vistas = ("", "?entrada=NO", "?dias=30", "?entrada=NO&dias=365")
    antes = {q: _consultas_a_la_copia(lambda: _panel(app, q)) for q in vistas}
    respuesta = t.tw_precalcular({"payload": {"cliente": "acme"}, "job_id": t.job_id_precalcular("acme")})
    assert "listo" in respuesta.lower(), respuesta
    for q in vistas:
        despues, n_despues = _consultas_a_la_copia(lambda: _panel(app, q))
        assert despues == antes[q][0], q
        assert n_despues < antes[q][1], (q, antes[q][1], n_despues)
    assert {f for c, f in _memo() if c == "acme"} >= {"totales_por_anuncio", "serie_tienda", "cohortes", "canales"}


def test_con_un_canal_elegido_se_calcula_en_vivo(app):  # noqa: F811
    tid = _tienda()
    _sembrar_anuncios(tid, n=4)
    t.tw_precalcular({"payload": {"cliente": "acme"}, "job_id": t.job_id_precalcular("acme")})
    _, n = _consultas_a_la_copia(lambda: _panel(app, "?entrada=NO&canal=facebook-ads"))
    _, n_sin = _consultas_a_la_copia(lambda: _panel(app, "?entrada=NO"))
    assert n > n_sin


def test_la_ultima_copia_del_proyecto_pide_el_precalculo_una_vez(base_temporal, monkeypatch):
    import triple_whale_tiendas as tt
    monkeypatch.setenv("FLASK_SECRET_KEY", "test_secret_key_12345678")
    se = tt.agregar("acme", "llave-se", "acme-se.myshopify.com", pais="SE")  # llave-de-prueba
    no = tt.agregar("acme", "llave-no", "acme-no.myshopify.com", pais="NO")  # llave-de-prueba
    monkeypatch.setattr(t.sync, "sincronizar", lambda *a, **k: {"anuncios": 1, "dias_tienda": 1, "desde": "2026-10-01",
                                                                "hasta": "2026-10-01", "fallos": {}})
    monkeypatch.setattr(t.avisos, "revisar_y_avisar", lambda c: None)
    t.encolar_sync("acme")
    for tid in (se, no):
        t.tw_sincronizar({"payload": {"cliente": "acme", "tienda_id": tid}, "job_id": t.job_id_sync("acme", tid)})
        cola.terminar(cola.consultar_por_job(t.job_id_sync("acme", tid))["id"])
    with db.conectar() as con:
        tipos = [r[0] for r in con.execute(sa.select(db.tarea.c.tipo).where(db.tarea.c.cliente == "acme"))]
    assert tipos.count(t.TIPO_PRECALCULAR) == 1


def test_va_en_el_carril_de_lectura_y_no_cobra():
    assert t.TIPO_PRECALCULAR in worker.CARRIL_LECTURA
    assert t.TIPO_PRECALCULAR in tareas.TIPOS_EXENTOS_DE_COBRO
    assert t.TIPO_PRECALCULAR not in tareas.TIPOS_QUE_COBRAN


def test_quitar_las_tiendas_borra_lo_grabado(app):  # noqa: F811
    import triple_whale_tiendas as tt
    tid = _tienda()
    _sembrar_anuncios(tid, n=3)
    t.tw_precalcular({"payload": {"cliente": "acme"}, "job_id": t.job_id_precalcular("acme")})
    assert _memo()
    tt.quitar("acme", tid)
    assert _memo() == []


# ------------------------------------------------------------------- un año de historia (2026-10-15) ---

def test_la_copia_puede_traer_la_historia_desde_una_fecha(base_temporal, monkeypatch):
    """Daniel pidió un año: `tw_sincronizar` con `desde` en el pedido copia desde ahí hasta hoy (por tramos, como la
    primera copia); un `desde` raro o futuro se ignora y copia lo de siempre."""
    from datetime import date, timedelta

    import triple_whale_tiendas as tt
    monkeypatch.setenv("FLASK_SECRET_KEY", "test_secret_key_12345678")
    se = tt.agregar("acme", "llave-se", "acme-se.myshopify.com", pais="SE")  # llave-de-prueba
    pedidos = []

    def sincronizar(cliente, tienda_id, desde=None, hasta=None, on_progreso=None, hoy=None):
        pedidos.append((desde, hasta))
        return {"anuncios": 1, "dias_tienda": 1, "desde": desde or "x", "hasta": hasta or "x", "fallos": {}}
    monkeypatch.setattr(t.sync, "sincronizar", sincronizar)
    monkeypatch.setattr(t.avisos, "revisar_y_avisar", lambda c: None)
    hace_un_ano = (date.today() - timedelta(days=364)).isoformat()
    for desde in (hace_un_ano, "2025-13-40", "ayer", (date.today() + timedelta(days=3)).isoformat()):
        t.tw_sincronizar({"payload": {"cliente": "acme", "tienda_id": se, "desde": desde}, "job_id": "j"})
    assert pedidos[0] == (hace_un_ano, date.today().isoformat())
    assert pedidos[1:] == [(None, None)] * 3


def test_encolar_la_historia_pide_una_copia_por_tienda_con_su_desde(base_temporal, monkeypatch):
    from datetime import date, timedelta

    import triple_whale_tiendas as tt
    monkeypatch.setenv("FLASK_SECRET_KEY", "test_secret_key_12345678")
    se = tt.agregar("acme", "llave-se", "acme-se.myshopify.com", pais="SE")  # llave-de-prueba
    no = tt.agregar("acme", "llave-no", "acme-no.myshopify.com", pais="NO")  # llave-de-prueba
    assert t.encolar_historia("acme", dias=365) == 2
    assert t.encolar_historia("acme", dias=365) == 0                      # ya hay copias vivas: no duplica
    desde = (date.today() - timedelta(days=364)).isoformat()
    for tid in (se, no):
        tarea = cola.consultar_por_job(t.job_id_sync("acme", tid))
        assert tarea["payload"]["desde"] == desde and tarea["tipo"] == t.TIPO_SYNC
