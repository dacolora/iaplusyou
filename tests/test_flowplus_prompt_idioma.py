"""flowplus_prompt en inglés (spec 2026-09-26 §B5): un proyecto en inglés
manda a los modelos de video un prompt entero en inglés; en español, idéntico
al de siempre. El texto de la persona nunca se toca."""
import re

import flowplus_prompt as fp

REFS = [{"tipo": "imagen", "etiqueta": "foto", "token": "Image 1", "activo": "Sandalia Sol", "categoria": "producto",
         "producto": True, "regla": "Rule text."}]
# «cámara», «plano», «despacio», «hacia»: palabras del vocabulario de cámara
# en español (flowplus_prompt.CAMARAS) que se colaban en un prompt en inglés
# armado a partir de planos del director (ronda de revisión de la fase 3).
ESPANOL = re.compile(
    r"[áéíóúñ¿¡]|\b(?:ESCENA|EVITAR|SONIDO|Sin diálogo|Recordatorio|PRODUCTO EXACTO|FIDELIDAD"
    r"|cámara|plano|despacio|hacia)\b")


def test_tal_cual_solo_cambia_la_etiqueta_del_sonido():
    assert fp.tal_cual("Una ola rompe", [], sonido="olas", idioma="en") == "Una ola rompe\nSOUND: olas."
    assert fp.tal_cual("Una ola rompe", [], sonido="olas") == "Una ola rompe\nSONIDO: olas."
    assert fp.tal_cual("Una ola rompe", [], idioma="en") == "Una ola rompe"


def test_armar_en_ingles_no_deja_espanol_fijo():
    p = fp.armar("the sandal on the sand", REFS, con_sonido=True, idioma="en",
                 contexto={"persona": {"resumen": "moms", "senales_visuales": ["sun"], "tono": "warm"},
                           "temporada": {"nombre": "summer", "mood_visual": {"paleta": ["blue"], "luz": "soft"}}})
    assert "the sandal on the sand" in p
    assert not ESPANOL.search(p), p


def test_armar_en_espanol_identico_al_de_siempre():
    assert fp.armar("la sandalia en la arena", REFS, con_sonido=True) == \
        fp.armar("la sandalia en la arena", REFS, con_sonido=True, idioma="es")


def test_planos_en_ingles():
    """Cada plano trae un id de cámara distinto (spec §B5, ronda de revisión):
    `flowplus_prompt.CAMARAS` es el vocabulario en español que `director.py`
    valida contra Claude — su texto NO debe colarse en un prompt en inglés."""
    planos = [
        {"n": 1, "inicio_s": 0, "fin_s": 3, "plano": "close-up", "camara": "dolly_in", "accion": "turns", "sonido": "waves"},
        {"n": 2, "inicio_s": 3, "fin_s": 6, "plano": "wide shot", "camara": "orbita_360", "accion": "reveals"},
        {"n": 3, "inicio_s": 6, "fin_s": 8, "plano": "medium shot", "camara": "tilt_arriba", "accion": "settles"},
    ]
    p = fp.armar("x", REFS, con_sonido=True, planos=planos, idioma="en")
    assert "Sound: waves." in p and "Sonido:" not in p
    assert not ESPANOL.search(p), p


def test_unboxing_en_ingles():
    p = fp.armar("x", REFS, enfoque="unboxing", idioma="en")
    assert "UNBOXING" in p and not ESPANOL.search(p), p
