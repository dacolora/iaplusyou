"""Ganchos de Triple Whale (spec 2026-10-09 §4.2): la tabla tw_gancho y su único escritor."""
import pytest
import sqlalchemy as sa
from sqlalchemy import event

from triple_whale import datos

GANCHOS_T = [{"n": 1, "texto": "Uno", "prompt": "Push in", "fotograma_s": 2.0},
             {"n": 3, "texto": "Tres", "prompt": "Pan left", "fotograma_s": None}]


def _analisis(cliente="acme"):
    return datos.crear_analisis(cliente, None, "facebook-ads", "p1", "2026-09-01", "2026-09-30", "USD", {})


def test_crear_tanda_numera_y_no_deja_pedir_otra_mientras_vive(base_temporal):
    aid = _analisis()
    filas = datos.crear_tanda("acme", aid, GANCHOS_T, pedido_por="admin")
    assert [(f["tanda"], f["n"], f["estado"]) for f in filas] == [(1, 1, "preparando"), (1, 3, "preparando")]
    assert filas[0]["texto"] == "Uno" and filas[0]["fotograma_s"] == 2.0 and filas[1]["fotograma_s"] is None
    assert filas[0]["pedido_por"] == "admin" and filas[0]["cliente"] == "acme" and filas[0]["cf_id"] is None
    with pytest.raises(datos.TandaViva):
        datos.crear_tanda("acme", aid, GANCHOS_T)
    for f in filas:
        assert datos.mover(f["id"], "preparando", "error", error="se cortó")
    assert [(f["tanda"], f["n"]) for f in datos.crear_tanda("acme", aid, GANCHOS_T[:1])] == [(2, 1)]
    otro = _analisis()
    assert datos.crear_tanda("acme", otro, GANCHOS_T[:1])[0]["tanda"] == 1      # cada análisis numera sus tandas
    with pytest.raises(ValueError):
        datos.crear_tanda("acme", otro, [])


def test_una_variante_viva_bloquea_y_las_terminadas_no(base_temporal):
    aid = _analisis()
    f1, f2 = datos.crear_tanda("acme", aid, GANCHOS_T)
    assert datos.mover(f1["id"], "preparando", "lista", url_final="https://r2.test/a.mp4")
    assert datos.mover(f2["id"], "preparando", "produciendo")
    with pytest.raises(datos.TandaViva):
        datos.crear_tanda("acme", aid, GANCHOS_T)
    assert datos.mover(f2["id"], "produciendo", "error", error="falló")
    assert datos.crear_tanda("acme", aid, GANCHOS_T)[0]["tanda"] == 2


def test_crear_tanda_toma_el_candado_antes_de_leer(base_temporal, escritor_en_medio):
    """Regla 5: dos clics a la vez no pueden leer los dos «sin tanda viva». Justo antes de la primera lectura otra
    conexión (otro hilo de gunicorn) intenta meter una fila viva: con el candado ya tomado queda bloqueada."""
    aid = _analisis()
    estado = escritor_en_medio(
        "FROM tw_gancho",
        "INSERT INTO tw_gancho (cliente, creado_en, actualizado_en, analisis_id, tanda, n, estado) "
        f"VALUES ('acme', 'x', 'x', {aid}, 9, 1, 'preparando')")
    datos.crear_tanda("acme", aid, GANCHOS_T)
    assert estado["hecho"] and estado["resultado"].startswith("bloqueado")


def test_mover_no_avanza_dos_veces_la_misma_variante(base_temporal):
    aid = _analisis()
    f1, _ = datos.crear_tanda("acme", aid, GANCHOS_T)
    assert datos.mover(f1["id"], "preparando", "generando", cf_id="cf_1", job_id="acme__cf_1__creative_flow")
    assert not datos.mover(f1["id"], "preparando", "generando", cf_id="cf_2")      # ya no está en preparando
    g = datos.gancho("acme", f1["id"])
    assert g["estado"] == "generando" and g["cf_id"] == "cf_1" and g["job_id"] == "acme__cf_1__creative_flow"
    with pytest.raises(ValueError):
        datos.mover(f1["id"], "generando", "raro")
    with pytest.raises(ValueError):
        datos.actualizar_gancho(f1["id"], estado="lista")          # el estado solo cambia con mover
    with pytest.raises(ValueError):
        datos.mover(f1["id"], "generando", "armando", texto="otro")  # el texto del gancho no se reescribe
    assert datos.actualizar_gancho(f1["id"], frame_url="https://r2.test/f.jpg")
    assert datos.gancho("acme", f1["id"])["frame_url"] == "https://r2.test/f.jpg"
    assert datos.gancho("otro", f1["id"]) is None


def test_lecturas_filtran_por_proyecto_y_son_una_consulta(base_temporal):
    a1, a2 = _analisis(), _analisis("otro")
    for f in datos.crear_tanda("acme", a1, GANCHOS_T):
        datos.mover(f["id"], "preparando", "error", error="x")
    datos.crear_tanda("acme", a1, GANCHOS_T)
    datos.crear_tanda("otro", a2, GANCHOS_T)
    consultas = []
    contar = lambda conn, cursor, statement, *a: consultas.append(statement)  # noqa: E731
    event.listen(sa.engine.Engine, "before_cursor_execute", contar)
    try:
        filas = datos.ganchos_de_analisis("acme", a1)
        vivos = datos.ganchos_vivos()
    finally:
        event.remove(sa.engine.Engine, "before_cursor_execute", contar)
    assert len(consultas) == 2
    assert [(f["tanda"], f["n"]) for f in filas] == [(2, 1), (2, 3), (1, 1), (1, 3)]
    assert datos.ganchos_de_analisis("otro", a1) == []
    assert sorted((f["cliente"], f["tanda"]) for f in vivos) == [("acme", 2), ("acme", 2), ("otro", 1), ("otro", 1)]


# --------------------------------------- endurecimiento: aislamiento y errores honestos (revisión de la tarea 1) ---
def _filas(cliente=None):
    import db
    with db.conectar() as con:
        q = sa.select(sa.func.count()).select_from(db.tw_gancho)
        if cliente:
            q = q.where(db.tw_gancho.c.cliente == cliente)
        return con.execute(q).scalar()


def test_un_n_repetido_es_un_dato_malo_no_una_tanda_en_curso(base_temporal):
    """Dos ganchos con el mismo `n` chocan con uq_tw_gancho_tanda, pero no porque haya otra tanda viva: es una lista
    mal armada. Se rechaza antes de tomar el candado, con su palabra, y no queda ninguna fila."""
    aid = _analisis()
    malos = [dict(GANCHOS_T[0]), dict(GANCHOS_T[0])]
    with pytest.raises(ValueError, match="repetido"):
        datos.crear_tanda("acme", aid, malos)
    assert _filas() == 0
    assert datos.crear_tanda("acme", aid, GANCHOS_T)[0]["tanda"] == 1      # nada quedó a medias


def test_un_error_de_la_base_que_no_es_la_tanda_sale_tal_cual(base_temporal, monkeypatch):
    """Un NOT NULL (aquí `creado_en` sin fecha) no es «ya hay una tanda en curso»: se re-lanza como IntegrityError
    y la transacción entera se deshace."""
    aid = _analisis()
    monkeypatch.setattr(datos.db, "ahora", lambda: None)
    with pytest.raises(sa.exc.IntegrityError) as e:
        datos.crear_tanda("acme", aid, GANCHOS_T)
    assert not isinstance(e.value, datos.TandaViva) and "creado_en" in str(e.value.orig)
    assert _filas() == 0


def test_el_analisis_de_otro_proyecto_no_se_toca(base_temporal):
    """Aislamiento entre proyectos: `otro` no puede colgar una tanda del análisis de `acme` (ni bloquearlo)."""
    aid = _analisis("acme")
    with pytest.raises(datos.AnalisisAjeno):
        datos.crear_tanda("otro", aid, GANCHOS_T)
    assert issubclass(datos.AnalisisAjeno, LookupError)
    assert _filas() == 0
    with pytest.raises(LookupError):                               # un análisis que no existe es lo mismo
        datos.crear_tanda("acme", aid + 99, GANCHOS_T)
    assert _filas() == 0
    filas = datos.crear_tanda("acme", aid, GANCHOS_T)             # el dueño sigue pudiendo pedir la suya
    assert [(f["cliente"], f["tanda"]) for f in filas] == [("acme", 1), ("acme", 1)]
    assert datos.ganchos_de_analisis("otro", aid) == []


def test_un_choque_real_del_unique_si_es_tanda_viva(base_temporal):
    """De punta a punta: justo antes del INSERT de la tanda otra fila ocupa (análisis, tanda, n) dentro de la misma
    transacción (algo que el candado impide en la práctica). El UNIQUE de SQLite salta y se traduce a TandaViva."""
    import db
    aid = _analisis()
    estado = {"hecho": False}

    @sa.event.listens_for(db.engine(), "before_cursor_execute")
    def _meter_la_fila(conn, cursor, statement, params, context, executemany):
        if estado["hecho"] or not statement.lstrip().upper().startswith("INSERT INTO TW_GANCHO"):
            return
        estado["hecho"] = True
        conn.exec_driver_sql(
            "INSERT INTO tw_gancho (cliente, creado_en, actualizado_en, analisis_id, tanda, n, estado) "
            f"VALUES ('acme', 'x', 'x', {aid}, 1, 1, 'error')")
    try:
        with pytest.raises(datos.TandaViva):
            datos.crear_tanda("acme", aid, GANCHOS_T)
    finally:
        sa.event.remove(db.engine(), "before_cursor_execute", _meter_la_fila)
    assert estado["hecho"] and _filas() == 0                       # la transacción entera se deshizo


def test_es_choque_de_tanda_solo_reconoce_el_unique_de_la_tanda(base_temporal):
    import db
    t = db.tw_gancho
    fila = dict(cliente="acme", creado_en="x", actualizado_en="x", analisis_id=1, tanda=1, n=1, estado="error")
    with db.conectar() as con:
        con.execute(t.insert().values(**fila))
    with pytest.raises(sa.exc.IntegrityError) as unico:                       # el mensaje real de SQLite
        with db.conectar() as con:
            con.execute(t.insert().values(**fila))
    with pytest.raises(sa.exc.IntegrityError) as vacio:
        with db.conectar() as con:
            con.execute(t.insert().values(**{**fila, "creado_en": None}))
    assert datos._es_choque_de_tanda(unico.value) is True
    assert datos._es_choque_de_tanda(vacio.value) is False
    texto = "UNIQUE constraint failed: tw_gancho.analisis_id, tw_gancho.tanda, tw_gancho.n"
    assert datos._es_choque_de_tanda(Exception(texto)) is True
    assert datos._es_choque_de_tanda(Exception("UNIQUE constraint failed: tw_gancho.id")) is False
    assert datos._es_choque_de_tanda(Exception("UNIQUE constraint failed: tw_gancho.tanda, tw_gancho.n")) is False
    assert datos._es_choque_de_tanda(Exception("NOT NULL constraint failed: tw_gancho.cliente")) is False
    # el texto ajeno que viaja en los parámetros (segunda línea) no hace pasar a otro error por el de la tanda
    ajeno = "NOT NULL constraint failed: tw_gancho.cliente\n[parameters: ('uq_tw_gancho_tanda',)]"
    assert datos._es_choque_de_tanda(Exception(ajeno)) is False
    assert datos._es_choque_de_tanda(Exception("constraint uq_tw_gancho_tanda failed")) is True   # otro motor, por nombre


def test_mover_puede_exigir_columnas_vacias(base_temporal):
    """Revisión de la tarea 5: el cf_id de una variante se anota solo si todavía no tiene uno (otra corrida no lo pisa)."""
    aid = _analisis()
    f1, _ = datos.crear_tanda("acme", aid, GANCHOS_T)
    assert datos.mover(f1["id"], "preparando", "preparando", vacios=("cf_id",), cf_id="cf_a")
    assert not datos.mover(f1["id"], "preparando", "preparando", vacios=("cf_id",), cf_id="cf_b")
    assert datos.gancho("acme", f1["id"])["cf_id"] == "cf_a"
    with pytest.raises(ValueError):
        datos.mover(f1["id"], "preparando", "preparando", vacios=("texto",), cf_id="cf_c")
