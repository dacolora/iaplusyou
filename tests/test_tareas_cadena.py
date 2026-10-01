"""Worker de la cadena de escenas de Flow Plus, con el proveedor, ffmpeg y R2 simulados."""
import pytest
import sqlalchemy as sa

from tests.fixtures_guiones import video_nuevo


@pytest.fixture()
def cadena_lista(base_temporal, monkeypatch, tmp_path):
    """Versión armada (2 escenas) con las imágenes «por crear» subidas y la cadena aprobada."""
    import creative_flow
    from final_edition import cortes
    from guiones import cadena, clips, datos, escenas
    from providers import flowplus_modelos
    from storage import r2_uploader
    from tareas import cadena as t
    from tests.fixtures_guiones import PLAN, fake
    monkeypatch.setattr(t, "BASE_DIR", str(tmp_path))
    creados = []
    monkeypatch.setattr(flowplus_modelos, "crear_elemento",
                        lambda nombre, desc, url: creados.append((nombre, url)) or f"E{len(creados)}")
    monkeypatch.setattr(r2_uploader, "upload_image", lambda ruta, key: f"https://r2.test/{key}")

    def ultimo(video, destino):
        open(destino, "wb").write(b"jpg")
        return destino
    monkeypatch.setattr(cortes, "ultimo_fotograma", ultimo)
    _, vid = video_nuevo()
    datos.empezar("acme", vid, "armando", ("configurando",))
    clips.armar(vid, llamar=fake(PLAN))
    for n in (1, 2):
        datos.modificar_imagenes_escenas("acme", vid, lambda est, v, n=n: escenas.poner_ref(
            est, v, n, {"url": f"https://r2.test/ref{n}.jpg", "material_id": n, "nombre": f"ref{n}"}))
    v = datos.video("acme", vid)
    datos.modificar_cadena("acme", vid, lambda e, _v: cadena.aprobar(v, 1, cadena.precio(v), "admin", "t"))
    return {"vid": vid, "creados": creados, "tmp": tmp_path, "cf": creative_flow}


def _tarea(vid, tipo="cadena_elementos"):
    return {"id": 1, "tipo": tipo, "payload": {"cliente": "acme", "video_id": vid}}


def _cola(base, tipo):
    with base.conectar() as con:
        return [dict(f._mapping) for f in con.execute(sa.select(base.tarea).where(base.tarea.c.tipo == tipo))]


def _listo(cf, cf_id, tmp):
    video = tmp / f"{cf_id}.mp4"
    video.write_bytes(b"mp4")
    cf.actualizar("acme", cf_id, estado="video_listo", video_url="https://r2.test/v.mp4", video_local_crudo=str(video))


def test_cadena_completa(cadena_lista, base_temporal, monkeypatch):
    from final_edition import edicion_clon
    from guiones import cadena, datos
    from tareas import cadena as t
    vid, cf = cadena_lista["vid"], cadena_lista["cf"]
    t.ejecutar_elementos(_tarea(vid))
    # el personaje (Image 1) es elemento; el entorno (Image 2) no
    assert cadena_lista["creados"] == [("the AI podiatrist,", "https://r2.test/ref1.jpg")]
    est = cadena.estado(datos.video("acme", vid))
    assert not est["preparando"] and est["escenas"]["1"]["estado"] == "generando"
    cf1 = est["escenas"]["1"]["cf_id"]
    e1 = cf.cargar("acme")[cf1]
    assert e1["modelo"] == "kling_o3_pro" and e1["estado"] == "video_generando" and not e1.get("imagen_inicial")
    assert e1["referencias_urls"] == ["https://r2.test/ref1.jpg", "https://r2.test/ref2.jpg"]
    assert [x["prioridad"] for x in _cola(base_temporal, "flowplus_video")] == [3]
    # gasto del elemento
    with base_temporal.conectar() as con:
        gastos = [f.referencia for f in con.execute(sa.select(base_temporal.gasto).where(base_temporal.gasto.c.tipo == "video"))]
    assert len(gastos) == 1 and gastos[0].startswith("kling_elemento:")

    t.ejecutar_vigilar({})  # la escena 1 sigue generando: nada cambia
    assert cadena.estado(datos.video("acme", vid))["escenas"].keys() == {"1"}

    _listo(cf, cf1, cadena_lista["tmp"])
    t.ejecutar_vigilar({})
    est = cadena.estado(datos.video("acme", vid))
    assert est["escenas"]["1"]["estado"] == "lista"
    assert est["escenas"]["1"]["frame_url"] == f"https://r2.test/clientes/acme/flowplus/cadena/{vid}_1.jpg"
    cf2 = est["escenas"]["2"]["cf_id"]
    e2 = cf.cargar("acme")[cf2]
    assert e2["imagen_inicial"] == est["escenas"]["1"]["frame_url"] and e2["elementos"] == ["E1"]
    assert e2["referencias_urls"] == [] and e2["prompt_relleno"].startswith(cadena.ARRANQUE)

    _listo(cf, cf2, cadena_lista["tmp"])
    t.ejecutar_vigilar({})
    assert cadena.estado(datos.video("acme", vid))["estado"] == "terminada"
    assert len(_cola(base_temporal, "cadena_unir")) == 1
    monkeypatch.setattr(edicion_clon, "crear_de_piezas", lambda c, ids, carpeta, nombre: 42 if ids == [cf1, cf2] else 0)
    t.ejecutar_unir(_tarea(vid, "cadena_unir"))
    assert cadena.estado(datos.video("acme", vid))["edicion_id"] == 42


def test_fallo_detiene_sin_lanzar_la_siguiente(cadena_lista):
    from guiones import cadena, datos
    from tareas import cadena as t
    vid, cf = cadena_lista["vid"], cadena_lista["cf"]
    t.ejecutar_elementos(_tarea(vid))
    cf1 = cadena.estado(datos.video("acme", vid))["escenas"]["1"]["cf_id"]
    cf.actualizar("acme", cf1, estado="error", error="Kling: contenido sensible")
    t.ejecutar_vigilar({})
    est = cadena.estado(datos.video("acme", vid))
    assert est["estado"] == "detenida" and est["escenas"]["1"]["error"] == "Kling: contenido sensible"
    assert "2" not in est["escenas"] and datos.cadenas_vivas() == []


def test_detener_espera_la_escena_en_curso(cadena_lista):
    from guiones import cadena, datos
    from tareas import cadena as t
    vid, cf = cadena_lista["vid"], cadena_lista["cf"]
    t.ejecutar_elementos(_tarea(vid))
    datos.modificar_cadena("acme", vid, lambda e, _v: cadena.pedir_detener(e))
    t.ejecutar_vigilar({})
    assert cadena.estado(datos.video("acme", vid))["estado"] == "corriendo"  # la 1 sigue generando
    _listo(cf, cadena.estado(datos.video("acme", vid))["escenas"]["1"]["cf_id"], cadena_lista["tmp"])
    t.ejecutar_vigilar({})
    est = cadena.estado(datos.video("acme", vid))
    assert est["estado"] == "detenida" and est["escenas"]["1"]["estado"] == "lista" and "2" not in est["escenas"]


def test_rehacer_no_vuelve_a_crear_ni_cobrar_elementos(cadena_lista, base_temporal):
    from guiones import cadena, datos
    from tareas import cadena as t
    vid, cf = cadena_lista["vid"], cadena_lista["cf"]
    t.ejecutar_elementos(_tarea(vid))
    _listo(cf, cadena.estado(datos.video("acme", vid))["escenas"]["1"]["cf_id"], cadena_lista["tmp"])
    t.ejecutar_vigilar({})
    cf2 = cadena.estado(datos.video("acme", vid))["escenas"]["2"]["cf_id"]
    cf.actualizar("acme", cf2, estado="error", error="falló")
    t.ejecutar_vigilar({})
    v = datos.video("acme", vid)
    est = cadena.estado(v)
    assert cadena.puede_rehacer(est, 2)
    # «Rehacer desde la escena 2»: la cadena nueva olvida los elementos (como si se perdieran) y el kv los trae
    datos.modificar_cadena("acme", vid, lambda e, _v: dict(cadena.aprobar(v, 2, 1.0, "admin", "t2", previo=e),
                                                         elementos={}))
    t.ejecutar_elementos(_tarea(vid))
    assert len(cadena_lista["creados"]) == 1  # no se creó otro
    with base_temporal.conectar() as con:
        assert len(list(con.execute(sa.select(base_temporal.gasto).where(base_temporal.gasto.c.tipo == "video")))) == 1
    est = cadena.estado(datos.video("acme", vid))
    assert est["escenas"]["2"]["cf_id"] != cf2 and est["escenas"]["2"]["estado"] == "generando"


def test_vigilante_tolera_una_cadena_rota(cadena_lista, monkeypatch):
    from guiones import datos
    from tareas import cadena as t
    monkeypatch.setattr(datos, "cadenas_vivas", lambda: [("acme", 999999), ("acme", cadena_lista["vid"])])
    t.ejecutar_vigilar({})  # no lanza aunque el primer video no exista
