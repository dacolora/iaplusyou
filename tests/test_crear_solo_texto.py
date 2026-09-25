"""Crear sin referencias ni producto (2026-09-25): en el mismo formulario las
referencias y el catálogo son opcionales. Sin nada adjunto la pieza es de
«solo texto» (enfoque `libre`): sin logos, sin guía de marca, el texto de la
persona tal cual, y cada modelo va a su ruta text-to-video / text-to-image de
WaveSpeed (rutas y parámetros verificados en wavespeed.ai el 2026-09-25).
Sin red: se capturan los payloads."""
import pytest

import flowplus_prompt
from providers import flowplus_modelos as fm
from tests.test_rutas_experimentos import _cliente_admin


def _capturar_lanzar(monkeypatch):
    llamadas = []

    def _lanzar(path, payload, nombre, timeout_seconds=1200, on_progreso=None):
        llamadas.append((path, payload))
        return "https://prov/salida"

    monkeypatch.setattr(fm, "_lanzar", _lanzar)
    return llamadas


# ---------- proveedores ----------

def test_sin_imagenes_cada_modelo_de_video_va_a_su_ruta_de_texto(monkeypatch):
    llamadas = _capturar_lanzar(monkeypatch)
    monkeypatch.setattr(fm.wan3_client, "generar_video", lambda *a, **k: pytest.fail("reference-to-video sin imágenes"))
    for modelo in ("wan3", "kling_o3_pro", "seedance25"):
        assert fm.generar_video(modelo, "una mujer camina", [], 8, aspect_ratio="9:16") == "https://prov/salida"
    assert [p for p, _ in llamadas] == ["alibaba/wan-3.0/text-to-video",
                                        "kwaivgi/kling-video-o3-pro/text-to-video",
                                        "bytedance/seedance-2.5/text-to-video"]
    wan, kling, seedance = (pl for _, pl in llamadas)
    assert wan == {"prompt": "una mujer camina", "duration": 8, "resolution": "720p", "aspect_ratio": "9:16", "enable_audio": True}
    assert kling == {"prompt": "una mujer camina", "duration": 8, "aspect_ratio": "9:16", "sound": True}
    assert seedance == {"prompt": "una mujer camina", "duration": 8, "resolution": "720p", "aspect_ratio": "9:16",
                        "generate_audio": True}


def test_solo_texto_respeta_el_sonido_y_el_borrador(monkeypatch):
    llamadas = _capturar_lanzar(monkeypatch)
    fm.generar_video("wan3", "p", [], 5, calidad="borrador", con_sonido=False)
    fm.generar_video("kling_o3_pro", "p", [], 5, con_sonido=False)
    fm.generar_video("seedance25", "p", [], 5, aspect_ratio=None, con_sonido=False)
    assert llamadas[0][1]["resolution"] == "480p" and llamadas[0][1]["enable_audio"] is False
    assert llamadas[1][1]["sound"] is False
    assert llamadas[2][1]["generate_audio"] is False and "aspect_ratio" not in llamadas[2][1]


def test_imagen_sin_referencias_va_a_seedream_de_texto(monkeypatch):
    llamadas = _capturar_lanzar(monkeypatch)
    monkeypatch.setattr(fm.wavespeed_imagen, "editar_imagen_seedream", lambda *a, **k: pytest.fail("edit sin imagen"))
    assert fm.generar_imagen("seedream_v5_pro", "un gato astronauta", [], aspect_ratio="4:5") == "https://prov/salida"
    assert llamadas == [("bytedance/seedream-v5.0-pro",
                         {"prompt": "un gato astronauta", "resolution": "2k", "aspect_ratio": "4:5"})]
    assert fm.estimate_imagen("seedream_v5_pro", n_referencias=0)["usd"] == 0.09


def test_seedance_elige_formato_solo_cuando_no_hay_imagen():
    assert fm.ajustar_formato("seedance25", "9:16") is None            # sigue a la imagen de arranque
    assert fm.ajustar_formato("seedance25", "16:9", solo_texto=True) == "16:9"
    assert fm.ajustar_formato("seedance25", "", solo_texto=True) == "9:16"
    assert fm.ajustar_formato("kling_o3_pro", "4:3", solo_texto=True) == "9:16"   # Kling: sus tres formatos de siempre


# ---------- prompt ----------

def test_armar_libre_es_el_texto_tal_cual():
    p = flowplus_prompt.armar("  una mujer camina por la playa  ", [], guia_marca="Colores pastel",
                              negative_marca="gente triste", enfoque="libre")
    assert p == "una mujer camina por la playa"
    assert flowplus_prompt.ENFOQUES["libre"]["nombre"] == "Solo texto"


def test_armar_libre_con_sonido_agrega_solo_la_linea_de_sonido():
    p = flowplus_prompt.armar("una mujer camina", [], enfoque="libre", sonido="olas", con_sonido=True,
                              cierre_sonido="Sin voces.")
    assert p == "una mujer camina\n" + flowplus_prompt._linea_sonido("olas", True, cierre="Sin voces.")


def test_armar_libre_con_planos_del_director_no_agrega_marca():
    planos = [{"n": 1, "inicio_s": 0, "fin_s": 4, "camara": next(iter(flowplus_prompt.CAMARAS)),
               "plano": "Plano general", "accion": "una mujer camina", "sonido": "olas"}]
    p = flowplus_prompt.armar("idea", [], guia_marca="Colores pastel", enfoque="libre", planos=planos,
                              con_sonido=True, cierre_sonido="Sin voces.")
    assert p == "\n".join(flowplus_prompt._bloque_planos(planos, True) + ["Sin voces."])


def test_el_director_no_recibe_la_guia_de_marca_en_solo_texto(base_temporal, monkeypatch):
    import creative_flow as cf
    import director
    import marca
    monkeypatch.setattr(marca, "guia_efectiva", lambda c: "Colores pastel")
    monkeypatch.setattr(marca, "negative_prompt_efectivo", lambda c: "gente triste")
    s = cf.datos_para_director("acme", {"accion_central": "una mujer camina", "referencias": [], "enfoque": "libre"})
    assert s["guia_marca"] == "" and s["negative_marca"] is None
    assert "sin producto" in director._mensaje(s, "es")


# ---------- rutas ----------

@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import marca
    import proyectos
    import referencias_flowplus
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(dashboard.meta_conexion, "estado", lambda c: {"estado": "conectado", "verificado": True, "detalle": {}})
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: False)
    monkeypatch.setattr(referencias_flowplus, "listar", lambda c: [])      # bandeja vacía
    monkeypatch.setattr(referencias_flowplus, "vaciar", lambda c: None)
    # El proyecto tiene logo y guía de marca: en solo texto no entran.
    monkeypatch.setattr(dashboard, "_logos", lambda c: [{"url": "https://x/logo.png"}])
    monkeypatch.setattr(marca, "guia_efectiva", lambda c: "Colores pastel")
    lanzadas = []
    monkeypatch.setattr(dashboard, "_lanzar_video_cf", lambda c, cf_id, entry: lanzadas.append(cf_id) or True)
    encolados = []
    monkeypatch.setattr(dashboard.trabajos, "encolar",
                        lambda job_id, tipo, payload, **kw: (encolados.append(tipo), True)[1])
    return {"c": _cliente_admin(dashboard), "lanzadas": lanzadas, "encolados": encolados}


def _crear(app, **extra):
    data = {"accion_central": "una mujer camina por la playa", "duracion_objetivo": "8", "aspect_ratio": "9:16",
            "tipo": "video", "modelo": "wan3", "con_sonido": "si", "sonido": "olas", "musica_estilo": ""}
    data.update(extra)
    r = app["c"].post("/cliente/acme/creative_flow/crear", data=data)
    assert r.status_code == 302
    import creative_flow as cf
    return cf.cargar("acme")


def test_video_sin_referencias_ni_producto_se_genera_con_el_texto_tal_cual(app):
    (cf_id, e), = _crear(app).items()
    assert app["lanzadas"] == [cf_id]
    assert e["enfoque"] == "libre" and e["enfoque_nombre"] == "Solo texto"
    assert e["referencias"] == [] and e["referencias_urls"] == []          # sin logos
    assert e["prompt_relleno"] == flowplus_prompt.armar(
        "una mujer camina por la playa", [], enfoque="libre", sonido="olas", con_sonido=True,
        cierre_sonido=fm.cierre_sonido("wan3"))
    assert "Colores pastel" not in e["prompt_relleno"]


def test_imagen_sin_referencias_se_genera_con_el_texto_tal_cual(app):
    (cf_id, e), = _crear(app, tipo="imagen", modelo="seedream_v5_pro", aspect_ratio_imagen="4:5").items()
    assert app["lanzadas"] == [cf_id]
    assert e["enfoque"] == "libre" and e["prompt_relleno"] == "una mujer camina por la playa"
    assert e["aspect_ratio"] == "4:5" and e["referencias"] == []


def test_seedance_sin_referencias_guarda_el_formato_elegido(app):
    (_, e), = _crear(app, modelo="seedance25", aspect_ratio="16:9").items()
    assert e["aspect_ratio"] == "16:9"


def test_super_prompt_sin_referencias_encola_el_director(app):
    (_, e), = _crear(app, modo_prompt="director").items()
    assert e["estado"] == "prompt_pendiente" and e["enfoque"] == "libre"
    assert app["encolados"] == ["flowplus_director"] and app["lanzadas"] == []


def test_sin_texto_sigue_sin_crear_nada(app):
    assert _crear(app, accion_central="  ") == {}


def test_reintentar_una_pieza_de_solo_texto(app):
    import creative_flow as cf
    (cf_id, _), = _crear(app).items()
    cf.actualizar("acme", cf_id, estado="error", error="se cayó")
    r = app["c"].post(f"/cliente/acme/creative_flow/{cf_id}/generar_video")
    assert r.status_code == 302 and app["lanzadas"] == [cf_id, cf_id]


# ---------- worker y derivaciones ----------

def test_preparar_seedance_solo_texto_pide_el_formato(base_temporal):
    import creative_flow as cf
    import tareas.flowplus as fp
    cid = cf.crear("acme", [], [], [], "camina", 8, "", "A", referencias_urls=[])
    cf.actualizar("acme", cid, estado="video_generando", tipo="video", modelo="seedance25", prompt_relleno="camina",
                  aspect_ratio="9:16", enfoque="libre", referencias=[])
    _, referencias, videos, _, _, _, aspect_ratio, _, _ = fp._preparar("acme", cid)
    assert (referencias, videos, aspect_ratio) == ([], [], "9:16")


def test_regenerar_una_pieza_de_solo_texto_no_le_pone_producto(base_temporal):
    import creative_flow as cf
    import derivaciones
    cid = cf.crear("acme", [], [], [], "una mujer camina", 8, "", "A", referencias_urls=[])
    cf.actualizar("acme", cid, estado="video_listo", tipo="video", modelo="wan3", prompt_relleno="una mujer camina",
                  enfoque="libre", enfoque_nombre="Solo texto", referencias=[], con_sonido=False)
    item = derivaciones._item_regeneracion("acme", cid, 0, {})
    nueva = cf.cargar("acme")[item["cf_id"]]
    assert nueva["enfoque"] == "libre" and nueva["prompt_relleno"] == "una mujer camina"
    assert nueva["modelo"] != "wan3"
