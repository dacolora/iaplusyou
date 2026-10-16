"""Restos cuando una tarea nunca corre (decisión de quien orquesta, 2026-10-15): la grabación de un clon de voz que no
llegó a ser voz no se queda en R2, y el archivo subido para una importación de catálogo no se queda en disco. Los dos
los borraba solo la tarea al correr; si se cortaba antes (reinicio, colgada, el respaldo sin saldo), quedaban."""
import os

import pytest

import gastos
import materiales
from tests.test_voces_propias import r2  # noqa: F401 — R2 falso (sube y borra en listas)


@pytest.fixture()
def ganchos(base_temporal):
    import tareas
    tareas.cargar_todas()
    return tareas.AL_INTERRUMPIR


def _grabacion(cliente="acme", h="h_grab"):
    return materiales.registrar(cliente, tipo="audio", origen="grabacion",
                                url=f"https://r2/clientes/{cliente}/materiales/{h}.wav", hash=h, bytes=10,
                                duracion_ms=15000, extra={"nombre": "Mi voz"})


def _tarea_clon(g, tid=41, forma="clonar"):
    return {"id": tid, "tipo": "voz_propia_crear", "job_id": "acme__voz_propia", "cliente": "acme",
            "payload": {"cliente": "acme", "forma": forma, "nombre": "Mi voz", "idioma": "es",
                        "grabacion_id": g["id"], "consentimiento": {}}}


# ---------------------------------------------------------------- la voz propia ---

def test_un_clon_que_no_corrio_borra_su_grabacion(ganchos, r2):  # noqa: F811
    g = _grabacion()
    ganchos["voz_propia_crear"](_tarea_clon(g), "Sin saldo: recarga para seguir. No se cobró nada.")
    assert materiales.obtener("acme", g["id"]) is None
    assert r2["borrados"] == ["clientes/acme/materiales/h_grab.wav"]


def test_si_fal_ya_devolvio_la_voz_la_grabacion_se_queda_para_recuperarla(ganchos, r2):  # noqa: F811
    """La ficha con `voice_id` la recupera Mis voces sin volver a cobrar, y esa voz usa su grabación."""
    g = _grabacion()
    ficha = {"tipo": "audio", "origen": "voz_propia", "extra": {"voice_id": "mmx_clon", "grabacion_id": g["id"]}}
    gastos.registrar("acme", "voz_propia", 1.5, "voz_propia:clonar:t41", proveedor="fal",
                     extra={"ficha": ficha, "ficha_guardada": False})
    ganchos["voz_propia_crear"](_tarea_clon(g), "Se interrumpió por un reinicio del servidor. Vuelve a intentar.")
    assert materiales.obtener("acme", g["id"]) is not None and r2["borrados"] == []


def test_una_voz_disenada_o_una_grabacion_en_uso_no_se_tocan(ganchos, r2):  # noqa: F811
    g = _grabacion()
    ganchos["voz_propia_crear"](_tarea_clon(g, forma="disenar"), "x")
    assert materiales.obtener("acme", g["id"]) is not None
    otra = materiales.registrar("acme", tipo="audio", origen="voz_propia", url="https://r2/v.mp3", hash="h_voz",
                                bytes=10, extra={"voice_id": "mmx_otra", "grabacion_id": g["id"]})
    assert otra
    ganchos["voz_propia_crear"](_tarea_clon(g), "x")                    # otra voz propia la usa
    assert materiales.obtener("acme", g["id"]) is not None and r2["borrados"] == []


# ---------------------------------------------------- la importación de catálogo ---

def _importacion(tmp_path, cliente="acme", nombre="productos.csv"):
    carpeta = tmp_path / "clientes" / cliente / "importaciones"
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / nombre
    ruta.write_text("titulo,precio\nChancla,10\n")
    return str(ruta)


def _tarea_importar(ruta, cliente="acme", job_id="acme__importar_archivo", borrar=True):
    return {"id": 9, "tipo": "catalogo_importar", "job_id": job_id, "cliente": cliente,
            "payload": {"cliente": cliente, "ruta": ruta, "nombre_archivo": "productos.csv",
                        "borrar_al_terminar": borrar}}


def test_una_importacion_que_no_corrio_borra_su_archivo(ganchos, tmp_path):
    ruta = _importacion(tmp_path)
    ganchos["catalogo_importar"](_tarea_importar(ruta), "Se interrumpió por un reinicio del servidor.")
    assert not os.path.exists(ruta)


def test_no_borra_si_la_continuacion_sigue_viva_ni_fuera_de_su_carpeta(ganchos, tmp_path):
    import cola
    from tareas import tiendas
    ruta = _importacion(tmp_path)
    viva = tiendas.job_id_continuacion("acme__importar_archivo")
    cola.encolar("catalogo_importar", {"cliente": "acme"}, cliente="acme", job_id=viva, max_intentos=1)
    ganchos["catalogo_importar"](_tarea_importar(ruta), "x")
    assert os.path.exists(ruta)                                          # la continuación lo necesita
    ajena = _importacion(tmp_path, cliente="otro")
    ganchos["catalogo_importar"](_tarea_importar(ajena, job_id="acme__otro_job"), "x")
    assert os.path.exists(ajena)                                         # no es de la carpeta de «acme»
    suelto = tmp_path / "suelto.csv"
    suelto.write_text("x")
    ganchos["catalogo_importar"](_tarea_importar(str(suelto), job_id="acme__otro_job"), "x")
    assert suelto.exists()
    sin_bandera = _importacion(tmp_path, nombre="fixture.csv")
    ganchos["catalogo_importar"](_tarea_importar(sin_bandera, job_id="acme__otro_job", borrar=False), "x")
    assert os.path.exists(sin_bandera)


def test_el_respaldo_sin_saldo_tambien_limpia(base_temporal, tmp_path, monkeypatch):
    """De punta a punta: el worker no arranca la importación en un proyecto que cobra sin saldo y el archivo se
    borra igual."""
    import cola
    import idiomas
    import tareas
    import worker
    from cobros import libro
    tareas.cargar_todas()
    monkeypatch.setattr(worker, "PERIODICAS", [])
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "es")
    libro.configurar("acme", usuario="admin", cobrar=True)               # saldo 0
    ruta = _importacion(tmp_path)
    cola.encolar("catalogo_importar", _tarea_importar(ruta)["payload"], cliente="acme",
                 job_id="acme__importar_archivo", max_intentos=1)
    worker._correr(cola.reclamar())
    assert not os.path.exists(ruta)
