"""El flujo viejo «Nueva idea» (9 plantillas sin pantalla viva) en inglés y en
español (pedido de Daniel, 2026-10-01): se pintan con datos que recorren sus
ramas — ideas con prompts e imágenes, ideas visuales con cada estado de imagen,
videos pendientes/publicados/rechazados y la bitácora — y en inglés no queda
español visible, mientras el español sigue diciendo lo mismo de antes."""
import pytest
from flask import render_template

import dashboard
import idiomas
from tests.i18n_util import espanol_visible

PERSONAJES = [{"url": "https://r2.test/hero.jpg", "nombre": "Hero", "tipo": "video"}]

IMG = "https://r2.test/img.jpg"
IDEAS_VISUALES = [{"id": "iv1", "idea": "A warrior finds a map", "conceptos": [
    {"id": "c1", "texto": "Scene one", "imagenes": {
        "nano_banana": {"estado": "error", "error": "Provider said no"},
        "higgsfield": {"estado": "descartado", "url": IMG}}},
    {"id": "c2", "texto": "Scene two", "imagenes": {
        "nano_banana": {"estado": "listo", "url": IMG, "credits": 1.5, "usd": 0.3},
        "higgsfield": {"estado": "aprobado", "url": IMG, "usd": 0.012, "animaciones_pendientes": [
            {"id": "a1", "prompt": "Slow push in", "trabajo": None},
            {"id": "a2", "prompt": "Pan left", "trabajo": {"job_id": "job-anim"}}]}}},
    {"id": "c3", "texto": "Scene three", "imagenes": {
        "nano_banana": {"estado": "listo", "url": None, "local": "/tmp/x.png", "error_storage": "R2 timeout"},
        "higgsfield": {"estado": "generando", "url": None}}},
    {"id": "c4", "texto": "Scene four", "imagenes": {
        "nano_banana": {"estado": "generando", "url": None, "trabajo": {"job_id": "job-img"}}}},
]}]

PROMPT = {"id": "p1", "numero": 1, "prompt": "A sneaker on a rock", "image_url": IMG, "aspect_ratio": "9:16",
          "credits": 1.5, "usd": 0.3, "platforms": [], "duration": 5, "cfg_scale": 0.5, "imagen_url": IMG}
IDEAS = [{"id": "i1", "idea": "Sneaker on the beach", "prompts": [
    {**PROMPT, "estado": "pendiente", "trabajo": None},
    {**PROMPT, "id": "p2", "numero": 2, "estado": "imagen_pendiente", "trabajo": None, "credits": None,
     "platforms": ["youtube"]},
    {**PROMPT, "id": "p3", "numero": 3, "estado": "pendiente", "trabajo": {"job_id": "job-p3"}},
]}]

VIDEO = {"id": "b1", "title": "Wave run", "prompt": "Sneaker vs wave", "video_url": "https://r2.test/v.mp4",
         "platforms": ["youtube", "tiktok"], "plataformas_estado": {}, "trabajo": None}
VIDEOS = [{**VIDEO, "estado": "pendiente"},
          {**VIDEO, "id": "b2", "estado": "pendiente", "trabajo": {"job_id": "job-pub"}},
          {**VIDEO, "id": "b3", "estado": "publicado"},
          {**VIDEO, "id": "b4", "estado": "rechazado", "platforms": []}]
LOG = [{"fecha": "2026-10-01T00:00:00.123", "id": "b1", "etapa": "publish", "estado": "ok", "detalle": "done"}]


def _pintar(idioma):
    with dashboard.app.test_request_context(), idiomas.en_idioma(idioma):
        comun = {"cliente": "acme", "personajes": PERSONAJES, "ideas": IDEAS, "ideas_visuales": IDEAS_VISUALES}
        return {
            "visual": render_template("_seccion_ideas.html", marca={"root": True}, **comun),
            "prompts": render_template("_seccion_ideas.html", marca={"root": False}, **comun),
            "sin_personajes": render_template("_seccion_ideas.html", marca={"root": False}, cliente="acme",
                                              personajes=[], ideas=[], ideas_visuales=[]),
            "videos": render_template("_seccion_videos.html", cliente="acme", videos=VIDEOS),
            "bitacora": render_template("_seccion_bitacora.html", log=LOG)
                        + render_template("_seccion_bitacora.html", log=[]),
        }


@pytest.mark.parametrize("parte", ["visual", "prompts", "sin_personajes", "videos", "bitacora"])
def test_nueva_idea_sin_espanol_en_ingles(parte):
    html = _pintar("en")[parte]
    assert espanol_visible(html) == [], parte


def test_nueva_idea_en_ingles_dice_lo_que_debe():
    html = "".join(_pintar("en").values())
    for texto in ("New idea", "Generate 5 prompts", "Generate images (5 scenes × 2 engines)",
                  "Upload at least one character", "Delete this whole idea and its 3 prompts?",
                  "Generating video… 0% · 0s", "~1.50 cr image ($0.30)", "unknown cost",
                  "Approve image and generate video", "Videos waiting for review (2)", "Rejected (1)",
                  "no platforms assigned", "Recent activity", "No activity recorded yet.", "Discarded.",
                  "It was generated, but it couldn't be uploaded to storage (R2 timeout).", "It's on disk:"):
        assert texto in html, texto
    # La confirmación de publicar lleva los datos por .replace en JS, no dentro del _().
    assert '"Publish __I__ on: __P__?".replace("__I__", "b1").replace("__P__", "youtube, tiktok")' in html


def test_nueva_idea_en_espanol_no_cambia():
    html = "".join(_pintar("es").values())
    for texto in ("Nueva idea", "Generar 5 prompts", "Describe la idea del video", "(fotograma del video)",
                  "Generando… 0% · 0s", "~1.50 cr imagen ($0.30)", "costo desconocido",
                  "Se generó, pero no se pudo subir al almacenamiento (R2 timeout).",
                  "La generación se interrumpió (el servidor se reinició). Vuelve a intentarlo.",
                  "Videos pendientes de revisión (2)", "Publicados (1)", "sin plataformas asignadas",
                  "Bitácora reciente", "Sin actividad registrada todavía."):
        assert texto in html, texto
