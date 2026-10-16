"""PND-334 (decisión 2026-10-15, lote 2): `material_transcribir` lanzaba si un archivo fallaba y el worker devolvía
los cobros de TODO el trabajo, también los de las transcripciones que sí llegaron. Ahora se cobra lo entregado y se
devuelve solo lo que falló: la tarea termina en error con `tareas.EntregaParcial` (el worker no revierte la cadena)
y cada archivo que fal cobró sin entregar se anota con `entregado=False`, también si lo que falla es guardarlo."""
import os

import pytest
import sqlalchemy as sa

pytestmark = pytest.mark.usefixtures("margen_1_5")


@pytest.fixture()
def entorno(base_temporal, monkeypatch, tmp_path):
    import cobros.avisos as av
    import idiomas
    import tareas
    import worker
    from cobros import libro
    from storage import r2_uploader
    tareas.cargar_todas()
    monkeypatch.setenv("CREATV_SALIDAS", str(tmp_path / "salidas"))
    monkeypatch.setattr(worker, "PERIODICAS", [])
    monkeypatch.setattr(idiomas, "de_proyecto", lambda cliente: "es")
    monkeypatch.setattr(av, "pieza_no_cobrada", lambda *a, **k: None)
    monkeypatch.setattr(r2_uploader, "upload_file", lambda p, k, ct: f"https://r2/{k}")
    monkeypatch.setattr(r2_uploader, "delete_file", lambda k: None)
    libro.configurar("acme", usuario="admin", cobrar=True)
    with base_temporal.conectar() as con:
        libro.acreditar(con, "acme", "ajuste", 5000, "ajuste", usuario="admin", detalle="prueba")
    return base_temporal


def _audio(hash_, ms=60000):
    import materiales
    return materiales.registrar("acme", tipo="audio", origen="voz", url=f"https://r2/{hash_}.mp3", hash=hash_, bytes=1,
                                duracion_ms=ms)


def _movimientos(db, tipo):
    m = db.movimiento_saldo
    with db.conectar() as con:
        return [dict(r._mapping) for r in con.execute(sa.select(m).where(m.c.cliente == "acme", m.c.tipo == tipo))]


def _correr(material_ids):
    import cola
    import worker
    tid = cola.encolar("material_transcribir", {"cliente": "acme", "edicion_id": 1, "material_ids": material_ids,
                                                "idioma": "es"}, cliente="acme", job_id="acme__ed1__subtitulos",
                      max_intentos=1)
    tarea = cola.reclamar()
    assert tarea["id"] == tid
    worker._correr(tarea)
    return tarea, cola.consultar_por_id(tid)


def _whisper(monkeypatch, falla_en):
    from providers import fal_audio, fal_client

    def _transcribir(url, idioma, on_progreso=None, duracion_ms=None):
        if any(h in url for h in falla_en):
            e = fal_client.EsperaAgotadaFal("fal-ai/whisper", "req-1", "IN_PROGRESS", True)
            e.costo_usd = fal_audio.costo_whisper(duracion_ms or 0)
            raise e
        return {"texto": "hola", "palabras": [{"inicio": 0.0, "fin": 0.5, "texto": "hola"}], "costo_usd": 0.002}
    monkeypatch.setattr(fal_audio, "transcribir_palabras", _transcribir)


def test_se_cobra_lo_entregado_y_se_devuelve_solo_lo_que_fallo(entorno, monkeypatch):
    import gastos
    import materiales
    a, b = _audio("bien"), _audio("mal")
    _whisper(monkeypatch, falla_en=("mal",))
    tarea, fila = _correr([a["id"], b["id"]])
    assert fila["estado"] == "error" and "No se pudo transcribir 1 archivo." in (fila["error"] or "")
    assert materiales.obtener("acme", a["id"])["extra"]["palabras"]               # la que llegó, guardada
    cobro, = _movimientos(entorno, "cobro")
    assert cobro["gasto_id"] == gastos.por_referencia("acme", f"transcripcion:{a['id']}:t{tarea['id']}")["id"]
    assert _movimientos(entorno, "reverso") == []                                # lo entregado no se devuelve
    no_cobrado, = _movimientos(entorno, "no_cobrado")                            # lo que falló no se cobró
    assert no_cobrado["gasto_id"] == gastos.por_referencia("acme", f"transcripcion:{b['id']}:t{tarea['id']}")["id"]


def test_si_todo_falla_el_trabajo_falla_como_siempre(entorno, monkeypatch):
    b = _audio("mal")
    _whisper(monkeypatch, falla_en=("mal",))
    _, fila = _correr([b["id"]])
    assert fila["estado"] == "error" and _movimientos(entorno, "cobro") == []
    assert len(_movimientos(entorno, "no_cobrado")) == 1


def test_un_guardado_que_falla_despues_de_cobrar_no_se_cobra(entorno, monkeypatch):
    """Whisper cobró y respondió, pero guardar las palabras falló: el archivo no llegó y su cobro se devuelve; el otro,
    que sí llegó, queda cobrado."""
    import materiales
    a, b = _audio("bien"), _audio("guardar")
    _whisper(monkeypatch, falla_en=())
    original = materiales.actualizar_extra

    def _actualizar(cliente, mid, **campos):
        if mid == b["id"] and "palabras" in campos:
            raise RuntimeError("disco lleno")
        return original(cliente, mid, **campos)
    monkeypatch.setattr(materiales, "actualizar_extra", _actualizar)
    tarea, fila = _correr([a["id"], b["id"]])
    import gastos
    gasto_a = gastos.por_referencia("acme", f"transcripcion:{a['id']}:t{tarea['id']}")["id"]
    gasto_b = gastos.por_referencia("acme", f"transcripcion:{b['id']}:t{tarea['id']}")["id"]
    assert fila["estado"] == "error"
    assert {c["gasto_id"] for c in _movimientos(entorno, "cobro")} == {gasto_a, gasto_b}
    assert [r["gasto_id"] for r in _movimientos(entorno, "reverso")] == [gasto_b]   # solo el que no llegó


def test_el_worker_no_devuelve_la_cadena_de_una_entrega_parcial(base_temporal, monkeypatch):
    """`tareas.EntregaParcial`: la tarea queda en error, pero lo que cobró se queda (quien la lanza ya anotó con
    `entregado=False` lo que no llegó)."""
    import cola
    import gastos
    import tareas
    import worker
    from cobros import libro
    monkeypatch.setattr(worker, "PERIODICAS", [])
    monkeypatch.setattr(tareas, "TIPOS_QUE_COBRAN", frozenset({"parcial"}))
    libro.configurar("acme", usuario="admin", cobrar=True)
    with base_temporal.conectar() as con:
        libro.acreditar(con, "acme", "ajuste", 5000, "ajuste", usuario="admin", detalle="prueba")

    def fn(tarea):
        gastos.registrar("acme", "video", 1.0, f"video:1:t{tarea['id']}")
        raise tareas.EntregaParcial("se entregó una parte")
    monkeypatch.setitem(tareas.REGISTRO, "parcial", fn)
    tid = cola.encolar("parcial", {}, cliente="acme", job_id="j-parcial", max_intentos=1)
    worker._correr(cola.reclamar())
    assert cola.consultar_por_id(tid)["estado"] == "error"
    assert len(_movimientos(base_temporal, "cobro")) == 1 and _movimientos(base_temporal, "reverso") == []
