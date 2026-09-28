"""Sprints: Claude escribe en el idioma del proyecto (spec 2026-09-26 §B4);
el gancho de las ideas sigue en el idioma del MERCADO del sprint. Sin red:
se reemplazan las costuras de siempre (`analisis._llamar`, `_llamar_contando`)."""
import json

import idiomas
from sprints import analisis
from tests.test_sprints_analisis import JSON_OK

ORDEN_EN = idiomas.orden_idioma("en")


def _extra(system):
    """El bloque sin caché de `doctrina.bloque_system`: las instrucciones del sitio."""
    return system[1]["text"]


def test_analizar_referencia_en_ingles(monkeypatch):
    visto = {}
    monkeypatch.setattr(analisis, "_llamar",
                        lambda content, max_tokens=700, system=None: visto.update(c=content, s=system) or json.dumps(JSON_OK))
    analisis.analizar({"tipo": "imagen", "url": "https://r2/a.jpg", "intencion": ["paleta"], "descripcion": "warm light"},
                      marca="Glow", idioma="en")
    s = _extra(visto["s"])
    assert s.startswith(ORDEN_EN) and s.endswith(ORDEN_EN)
    assert "Todo en inglés." in visto["c"][0]["text"] and "Todo en español." not in visto["c"][0]["text"]


def test_analizar_en_espanol_por_defecto(monkeypatch):
    visto = {}
    monkeypatch.setattr(analisis, "_llamar",
                        lambda content, max_tokens=700, system=None: visto.update(c=content) or json.dumps(JSON_OK))
    analisis.analizar({"tipo": "imagen", "url": "https://r2/a.jpg", "intencion": [], "descripcion": ""})
    assert "Todo en español." in visto["c"][0]["text"]


def test_la_tarea_de_analisis_usa_el_idioma_del_proyecto(base_temporal, monkeypatch):
    import tareas
    from sprints import datos
    from tests.test_tareas_sprints import _referencia
    sid, cid, rid = _referencia(datos)
    visto = {}
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    monkeypatch.setattr(analisis, "analizar", lambda ref, marca="", idioma="es": visto.update(idioma=idioma) or
                        {"resumen": "ok", "paleta": []})
    tareas.cargar_todas()
    tareas.REGISTRO["sprint_analizar_referencia"]({"payload": {"cliente": "acme", "referencia_id": rid}})
    assert visto["idioma"] == "en"


def test_ideas_en_el_idioma_del_proyecto_con_el_gancho_del_mercado(base_temporal, monkeypatch):
    from sprints import datos, ideas
    from tests.test_sprints_ideas import IDEA_I, IDEA_V, _contando, _ctx
    sid, cid, rid = _ctx(monkeypatch, datos)            # sprint nuevo: mercado en inglés (datos.IDIOMA_BASE)
    vistos = []

    def falso(content, max_tokens=700, system=None):
        vistos.append(_extra(system))
        return json.dumps({"ideas": [dict(IDEA_V, referencias_ids=[rid]), IDEA_I]})
    monkeypatch.setattr(analisis, "_llamar_contando", _contando(falso))
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    ideas.proponer("acme", cid, n_videos=1, n_imagenes=1)
    en = vistos[-1]
    assert en.startswith(ORDEN_EN) and en.endswith(ORDEN_EN)
    assert "Todo en inglés." in en and "salvo el gancho" not in en and "Única excepción" not in en
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "es")
    ideas.proponer("acme", cid, n_videos=1, n_imagenes=1)
    es, orden_es = vistos[-1], ideas.orden_ideas("es", "en")
    assert orden_es.startswith(idiomas.orden_idioma("es")) and "Única excepción: el gancho" in orden_es
    assert es.startswith(orden_es) and es.endswith(orden_es)
    assert "Todo en español salvo el gancho (el texto en pantalla), que va en inglés, el idioma del MERCADO." in es


def test_reescribir_en_el_idioma_del_proyecto(base_temporal, monkeypatch):
    from sprints import datos, ideas
    from tests.test_sprints_ideas import ANGULO, _ctx
    sid, cid, rid = _ctx(monkeypatch, datos)
    cp = datos.crear_idea("acme", cid, "video", "Old", "old scene", gancho=ANGULO["gancho"], extra={"angulo": dict(ANGULO)})
    vistos = []

    def falso(content, max_tokens=700, system=None):
        vistos.append(_extra(system))
        return json.dumps({"titulo": "New", "escena": "The mirror light reveals the bathroom."}), 900, 300
    monkeypatch.setattr(analisis, "_llamar_contando", falso)
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    ideas.reescribir("acme", cp)
    assert vistos[0].startswith(ORDEN_EN) and vistos[0].endswith(ORDEN_EN) and "Reescribe UNA idea" in vistos[0]


def test_qa_en_ingles(base_temporal, monkeypatch, tmp_path):
    import marca
    from doctrina import revisor
    from final_edition import cortes
    from sprints import datos, qa
    from tests.test_sprints_qa import CHECKS_OK
    monkeypatch.setattr(marca, "guia_efectiva", lambda c: "Natural light.")
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    monkeypatch.setattr(revisor, "duracion", lambda ruta: 8.0)
    monkeypatch.setattr(revisor, "fotogramas", lambda ruta, ts: [(t, b"f") for t in ts])
    monkeypatch.setattr(cortes, "ffprobe_json", lambda p: {"format": {"duration": "8.0"},
                                                             "streams": [{"codec_type": "video", "width": 720, "height": 1280}]})
    pid = datos.crear_persona("acme", "Premium", resumen="Wants quality")
    tid = datos.crear_temporada("acme", "Christmas", "2026-11-15", "2026-12-31", contexto="gifts")
    sid = datos.crear_sprint("acme", "S", "2026-10-01", "2026-10-31")
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 1, 0)
    cp = datos.crear_idea("acme", cid, "video", "Sunrise", "circles", estado_idea="aprobada", duracion_s=8)
    v = tmp_path / "v.mp4"
    v.write_bytes(b"x")
    capturado = {}
    monkeypatch.setattr(analisis, "_llamar_contando", lambda content, max_tokens=700, system=None: capturado.update(
        c=content, s=system) or (json.dumps({"score": 88, "checks": CHECKS_OK}), 1000, 200))
    entry = {"tipo": "video", "video_local": str(v), "video_url": "https://r2/v.mp4", "aspect_ratio": "9:16",
             "duracion_objetivo": 8, "modelo": "wan3"}
    qa.evaluar("acme", datos.idea("acme", cp), entry, datos.campana("acme", cid), umbral=70)
    s = _extra(capturado["s"])
    assert s.startswith(ORDEN_EN) and s.endswith(ORDEN_EN)
    assert "Notas de máximo 20 palabras, en inglés," in capturado["c"][0]["text"]


def test_personas_sugeridas_en_ingles(monkeypatch):
    import catalogo_productos
    import marca
    import proyectos
    from sprints import sugerencias
    monkeypatch.setattr(marca, "guia_efectiva", lambda c: "Natural light.")
    monkeypatch.setattr(catalogo_productos, "listar", lambda c, cat="producto": [{"nombre": "LED mirror", "descripcion": "round"}])
    monkeypatch.setattr(proyectos, "nombre_visible", lambda c: "Glow")
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    visto = {}
    salida = {"personas": [{"nombre": "Premium buyer", "resumen": "r", "descripcion": "d", "edad_rango": "35-50",
                            "tono": "t", "senales_visuales": ["kitchen"], "palabras_clave": ["luxury"]}]}
    monkeypatch.setattr(analisis, "_llamar", lambda content, max_tokens=700, system=None: visto.update(
        c=content, s=system) or json.dumps(salida))
    sugerencias.sugerir_personas("acme", cuantas=1)
    s = _extra(visto["s"])
    assert s.startswith(ORDEN_EN) and s.endswith(ORDEN_EN)
    assert "Todo en inglés, sin texto fuera del JSON." in visto["c"][0]["text"]
