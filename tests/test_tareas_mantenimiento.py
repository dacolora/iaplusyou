"""Mantenimiento periódico (auditoría 2026-09-28): salidas/, cola y respaldos."""
import os
import sqlite3
import time
from datetime import datetime, timedelta

import pytest


def _tocar(ruta, dias):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "wb") as f:
        f.write(b"x" * 10)
    t = time.time() - dias * 86400
    os.utime(ruta, (t, t))


def test_salidas_limpiar_borra_solo_lo_viejo_y_las_carpetas_vacias(tmp_path, monkeypatch):
    from tareas import mantenimiento
    raiz = tmp_path / "salidas"
    monkeypatch.setenv("CREATV_SALIDAS", str(raiz))
    _tocar(str(raiz / "acme" / "cf_viejo.mp4"), 20)
    _tocar(str(raiz / "acme" / "cf_nuevo.mp4"), 2)
    _tocar(str(raiz / "acme" / "ediciones" / "borrador_x" / "voz.mp3"), 30)
    _tocar(str(raiz / "acme" / "swaps" / "reciente.png"), 1)
    _tocar(str(raiz / "referentes" / "a.jpg"), 40)
    n, total = mantenimiento.limpiar_salidas()
    assert (n, total) == (3, 30)
    assert not (raiz / "acme" / "cf_viejo.mp4").exists()
    assert (raiz / "acme" / "cf_nuevo.mp4").exists() and (raiz / "acme" / "swaps" / "reciente.png").exists()
    assert not (raiz / "acme" / "ediciones").exists()          # vacía debajo de salidas/<c>/: se va
    assert (raiz / "referentes").is_dir() and (raiz / "acme").is_dir()   # salidas/<c>/ se queda
    assert mantenimiento.ejecutar_salidas_limpiar({"payload": {}}).startswith("0 archivos")


def test_salidas_limpiar_sin_carpeta(tmp_path, monkeypatch):
    from tareas import mantenimiento
    monkeypatch.setenv("CREATV_SALIDAS", str(tmp_path / "no_existe"))
    assert mantenimiento.limpiar_salidas() == (0, 0)


def test_cola_limpiar_borra_cerradas_viejas_y_periodicas_pero_nunca_vivas(base_temporal):
    import cola
    from tareas import mantenimiento
    db = base_temporal
    hace = lambda d: (datetime.now() - timedelta(days=d)).isoformat(timespec="seconds")
    ids = {
        "viva_vieja": cola.encolar("flowplus_video", {}, job_id="acme__v", cliente="acme"),
        "hecha_vieja": cola.encolar("flowplus_video", {}, job_id="acme__h", cliente="acme"),
        "hecha_nueva": cola.encolar("flowplus_video", {}, job_id="acme__n", cliente="acme"),
        "error_vieja": cola.encolar("flowplus_video", {}, job_id="acme__e", cliente="acme"),
        "periodica_ayer": cola.encolar("sprint_qa_pendientes", {}, job_id="periodica__sprint_qa_pendientes"),
        "periodica_hoy": cola.encolar("exp_avanzar_todos", {}, job_id="periodica__exp_avanzar_todos"),
    }
    t = db.tarea
    with db.conectar() as con:
        con.execute(t.update().where(t.c.id == ids["viva_vieja"]).values(creada_en=hace(40)))
        con.execute(t.update().where(t.c.id == ids["hecha_vieja"]).values(estado="hecha", terminada_en=hace(10)))
        con.execute(t.update().where(t.c.id == ids["hecha_nueva"]).values(estado="hecha", terminada_en=hace(2)))
        con.execute(t.update().where(t.c.id == ids["error_vieja"]).values(estado="error", terminada_en=None, creada_en=hace(9)))
        con.execute(t.update().where(t.c.id == ids["periodica_ayer"]).values(estado="hecha", terminada_en=hace(2)))
        con.execute(t.update().where(t.c.id == ids["periodica_hoy"]).values(estado="hecha", terminada_en=hace(0)))
    assert cola.limpiar_terminadas() == 3
    with db.conectar() as con:
        quedan = {r[0] for r in con.execute(db.tarea.select().with_only_columns(t.c.job_id))}
    assert quedan == {"acme__v", "acme__n", "periodica__exp_avanzar_todos"}
    assert mantenimiento.ejecutar_cola_limpiar({"payload": {}}) == "0 tareas viejas borradas."


def test_db_respaldar_copia_consistente_y_conserva_las_ultimas(base_temporal, tmp_path):
    from tareas import mantenimiento
    carpeta = tmp_path / "respaldos"
    carpeta.mkdir()
    for i in range(9):
        (carpeta / f"creatv_2026090{i}_000000.db").write_bytes(b"viejo")
    (carpeta / "otro.txt").write_text("no se toca")
    destino = mantenimiento.respaldar_db(conservar=3, carpeta=str(carpeta))
    assert destino and os.path.exists(destino)
    con = sqlite3.connect(destino)
    assert con.execute("pragma integrity_check").fetchone()[0] == "ok"
    assert "tarea" in {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    con.close()
    quedan = sorted(os.listdir(carpeta))
    assert quedan == ["creatv_20260907_000000.db", "creatv_20260908_000000.db", os.path.basename(destino), "otro.txt"]


def test_db_respaldar_solo_sqlite(monkeypatch, tmp_path):
    import db
    from tareas import mantenimiento
    monkeypatch.setattr(db, "url", lambda: "postgresql://x")
    assert mantenimiento.respaldar_db(carpeta=str(tmp_path)) is None
    assert mantenimiento.ejecutar_db_respaldar({"payload": {}}).startswith("La base no es SQLite")


def test_periodicas_registradas():
    import worker
    from tareas import REGISTRO
    for tipo in ("salidas_limpiar", "cola_limpiar", "db_respaldar"):
        assert (tipo, 86400) in worker.PERIODICAS
        assert tipo in REGISTRO


def test_s3_mantenimiento_diario_poda_limites_por_marca_mas_nueva(base_temporal, monkeypatch):
    import json
    from tareas import mantenimiento
    db = base_temporal
    ahora = 10 * 86400
    monkeypatch.setattr(mantenimiento.time, 'time', lambda: ahora)
    monkeypatch.setattr(mantenimiento.cola, 'limpiar_terminadas', lambda: 0)
    filas = {'limite:viejo': json.dumps([ahora - 8 * 86400]),
             'limite:reciente': json.dumps([0, ahora - 3600]),
             'limite:frontera': json.dumps([ahora - 7 * 86400]),
             'limite:ilegible': 'no es JSON', 'limite:objeto': '{}',
             'limite:vacio': '[]', 'limite:infinito': '[NaN]',
             'limite:fuera_de_rango': json.dumps([10 ** 400]),
             'otro:viejo': json.dumps([0])}
    with db.conectar() as con:
        con.execute(db.kv.insert(), [{'clave': c, 'valor': v, 'actualizado_en': db.ahora()} for c, v in filas.items()])
    mantenimiento.ejecutar_cola_limpiar({'payload': {}})
    with db.conectar() as con:
        quedan = dict(con.execute(db.kv.select().with_only_columns(db.kv.c.clave, db.kv.c.valor)).all())
    assert quedan == {c: filas[c] for c in ['limite:reciente', 'limite:frontera', 'otro:viejo']}


def test_publicador_baja_el_video_si_ya_no_esta_en_disco(tmp_path, monkeypatch):
    import publicador
    monkeypatch.setenv("CREATV_SALIDAS", str(tmp_path / "salidas"))

    class _Resp:
        def raise_for_status(self):
            pass

        def iter_content(self, n):
            yield b"mp4-bytes"
    monkeypatch.setattr(publicador.requests, "get", lambda url, stream, timeout: _Resp())
    usados = []
    from uploaders import youtube_uploader
    monkeypatch.setattr(youtube_uploader, "upload_video", lambda ruta, **kw: usados.append(ruta) or "yt1")
    entry = {"video_local": str(tmp_path / "borrado.mp4"), "video_url": "https://r2/clientes/acme/videos/cf_1.mp4"}
    assert publicador._publicar_una("youtube", entry, "acme", {}) == "yt1"
    assert usados and usados[0].endswith(os.path.join("acme", "publicar", "cf_1.mp4"))
    assert open(usados[0], "rb").read() == b"mp4-bytes"
    # Con el archivo en disco no baja nada.
    (tmp_path / "local.mp4").write_bytes(b"ya")
    assert publicador.archivo_local({"video_local": str(tmp_path / "local.mp4"), "video_url": "https://r2/x.mp4"}, "acme") == str(tmp_path / "local.mp4")
    with pytest.raises(ValueError):
        publicador.archivo_local({"video_local": None, "video_url": ""}, "acme")
