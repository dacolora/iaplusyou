"""tareas.cadena.lanzar_escena: qué sesión de Crear arma cada modelo (sin red ni cola)."""
import pytest

from guiones import cadena, escenas
from tests.test_guiones_cadena import TEXTO, _completo


@pytest.fixture()
def lanzar(monkeypatch):
    from tareas import cadena as tareas_cadena
    sesiones = {}

    def crear(cliente, *a, **k):
        sesiones["cf_1"] = {"referencias_urls": k.get("referencias_urls")}
        return "cf_1"

    monkeypatch.setattr(tareas_cadena, "_prompt_vigente", lambda vid, k: TEXTO)
    monkeypatch.setattr(tareas_cadena.medios, "url_publica", lambda c, img: f"https://pub/{img.get('activo_id') or img.get('url')}")
    monkeypatch.setattr(tareas_cadena.creative_flow, "crear", crear)
    monkeypatch.setattr(tareas_cadena.creative_flow, "actualizar", lambda c, cf, **k: sesiones["cf_1"].update(k))
    monkeypatch.setattr(tareas_cadena.creative_flow, "cargar", lambda c: sesiones)
    monkeypatch.setattr(tareas_cadena.datos, "modificar_cadena", lambda *a, **k: None)
    monkeypatch.setattr(tareas_cadena.flowplus_lanzar, "lanzar", lambda *a, **k: True)

    def correr(modelo, k, frame="https://r2/cuadro1.jpg"):
        v = _completo()
        est = cadena.aprobar(v, 1, 1.0, "admin", "t", modelo=modelo)
        est = cadena.lista(cadena.lanzada(est, 1, "cf_0"), 1, frame)
        v = dict(v, id=9, guion={"titulo": "Podcast"}, extra=dict(v["extra"], cadena=est))
        monkeypatch.setattr(tareas_cadena.datos, "video", lambda c, vid: v)
        tareas_cadena.lanzar_escena("acme", 9, k)
        return v, sesiones["cf_1"]
    return correr


def test_wan_escena_siguiente_lleva_el_cuadro_y_sus_imagenes_como_referencias(lanzar):
    v, s = lanzar(cadena.WAN, 2)
    imgs = escenas.imagenes_para_crear(v, 2)
    assert s["modelo"] == "wan3" and "imagen_inicial" not in s and "elementos" not in s
    assert s["referencias_urls"][0] == "https://r2/cuadro1.jpg" and len(s["referencias_urls"]) == len(imgs) + 1
    assert [r["token"] for r in s["referencias"]] == [f"Image {i}" for i in range(1, len(imgs) + 2)]
    assert "@Imagen" not in s["prompt_relleno"]                      # tokens de Wan, no menciones de Crear
    assert s["prompt_relleno"].startswith("The video starts exactly on Image 1.")


def test_wan_primera_escena_sin_cuadro(lanzar):
    v, s = lanzar(cadena.WAN, 1)
    assert s["referencias_urls"] == [f"https://pub/{x['imagen'].get('activo_id') or x['imagen'].get('url')}"
                                     for x in escenas.imagenes_para_crear(v, 1)]
    assert "@Imagen" not in s["prompt_relleno"] and "Image 1 =" in s["prompt_relleno"]


def test_kling_primera_escena_ya_no_manda_menciones_de_crear(lanzar):
    _v, s = lanzar(cadena.MODELO, 1)
    assert s["modelo"] == "kling_o3_pro" and "@Imagen" not in s["prompt_relleno"] and "Image 1 =" in s["prompt_relleno"]
