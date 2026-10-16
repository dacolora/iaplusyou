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
    """El panel en frío: sin la caché del Tablero ni la de alertas del proceso (la primera petición las llena y las
    siguientes leen menos haya o no precálculo: así la comparación no se engaña)."""
    d = app["dashboard"]
    d._TABLERO_CACHE.clear()
    d.invalidar_alertas("acme")
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


# ------------------------------------------------------- revisión final (2026-10-15): que no se pierda ---

def test_si_una_copia_termina_en_medio_el_precalculo_se_vuelve_a_pedir(app, monkeypatch):  # noqa: F811
    from triple_whale import memo
    tid = _tienda()
    _sembrar_anuncios(tid, n=3)
    real = memo._version
    llamadas = []

    def version_que_cambia(cliente):
        llamadas.append(cliente)
        return real(cliente) + ("x" if len(llamadas) % 2 == 0 else "")
    monkeypatch.setattr(memo, "_version", version_que_cambia)
    r = t.tw_precalcular({"payload": {"cliente": "acme"}, "job_id": t.job_id_precalcular("acme")})
    assert isinstance(r, tareas.Continuar) and r.tipo == t.TIPO_PRECALCULAR
    assert r.payload == {"cliente": "acme", "vueltas": 1}
    final = t.tw_precalcular({"payload": {"cliente": "acme", "vueltas": t.VUELTAS_PRECALCULO},
                              "job_id": t.job_id_precalcular("acme")})
    assert isinstance(final, str)


def test_la_copia_en_linea_de_probar_anuncios_tambien_pide_el_precalculo(base_temporal, monkeypatch):
    import triple_whale_tiendas as tt
    from triple_whale import sync
    monkeypatch.setenv("FLASK_SECRET_KEY", "test_secret_key_12345678")
    se = tt.agregar("acme", "llave-se", "acme-se.myshopify.com", pais="SE")  # llave-de-prueba
    monkeypatch.setattr(sync, "sincronizar", lambda *a, **k: {"anuncios": 1})
    sync.sincronizar_si_hace_falta("acme", se)
    assert cola.consultar_por_job(t.job_id_precalcular("acme"))["tipo"] == t.TIPO_PRECALCULAR


def _faltas_en_lo_guardado(app, monkeypatch, q):  # noqa: F811
    """(html, cuántas sumas pesadas de esa vista NO estaban en lo guardado)."""
    from triple_whale import memo
    faltas = []
    leer = memo._leer

    def contar(*args):
        r = leer(*args)
        if r is memo._NADA:
            faltas.append(args[1])
        return r
    monkeypatch.setattr(memo, "_leer", contar)
    try:
        return _panel(app, q), len(faltas)
    finally:
        monkeypatch.setattr(memo, "_leer", leer)


def test_con_dos_tiendas_cada_pais_y_cada_periodo_quedan_precalculados(app, monkeypatch):  # noqa: F811
    import triple_whale_tiendas as tt
    no = _tienda()
    se = tt.agregar("acme", "tw_llave_se", "acme-se.myshopify.com", "SE", moneda="USD")  # llave-de-prueba
    _sembrar_anuncios(no, n=3)
    _sembrar_anuncios(se, n=4)
    vistas = [f"?entrada={e}&dias={d}" for e in ("", "NO", "SE") for d in (0, 15, 365)]
    antes = {}
    for q in vistas:
        antes[q], faltas = _faltas_en_lo_guardado(app, monkeypatch, q)
        assert faltas > 0, q                                   # sin precálculo, todo se calcula en vivo
    t.tw_precalcular({"payload": {"cliente": "acme"}, "job_id": t.job_id_precalcular("acme")})
    for q in vistas:
        html, faltas = _faltas_en_lo_guardado(app, monkeypatch, q)
        assert html == antes[q] and faltas == 0, (q, faltas)
