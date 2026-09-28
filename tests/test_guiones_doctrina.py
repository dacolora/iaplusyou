"""Doctrina, bloque 4 (§7): los sitios de Flow Plus reciben su rebanada de la
doctrina como bloque con caché, delante de las instrucciones del sitio (que
siguen rodeadas por la orden de idioma). Lectura no lleva doctrina: copia
literal. Sin red: `fake`/`_llamar_fijo`."""
from types import SimpleNamespace

import doctrina
import idiomas
from tests.fixtures_guiones import CONFIG, PLAN, fake, video_nuevo
from tests.test_guiones_idioma import _armado, _proyecto_en_idioma
from tests.test_guiones_refinador import CLIP, _crear, _json, _llamar_fijo


def _sitio(system, combinacion):
    """Comprueba la forma y devuelve el texto del sitio."""
    assert isinstance(system, list) and len(system) == 2
    assert system[0]["text"] == doctrina.texto(*doctrina.COMBINACIONES[combinacion])
    assert system[0]["cache_control"] == {"type": "ephemeral"} and "cache_control" not in system[1]
    orden = idiomas.orden_idioma("es")
    assert system[1]["text"].startswith(orden) and system[1]["text"].endswith(orden)
    return system[1]["text"]


def test_recorte_lleva_la_rebanada_de_gancho(base_temporal, monkeypatch, tmp_path):
    from guiones import datos, recorte
    _proyecto_en_idioma(monkeypatch, tmp_path, "es")
    _, vid = video_nuevo(config=dict(CONFIG, duracion_objetivo=15))
    datos.empezar("acme", vid, "recortando", ("configurando",))
    registro = []
    recorte.proponer(vid, llamar=fake({"orden": [4, 3, 2, 5, 6, 1], "motivos": {"4": "detalle"}}, registro=registro))
    assert "Ordena TODAS las líneas" in _sitio(registro[0]["system"], "flowplus_recorte")
    assert doctrina.COMBINACIONES["flowplus_recorte"] == ("gancho",)


def test_clips_llevan_video_y_gancho(base_temporal, monkeypatch, tmp_path):
    from guiones import clips, datos
    _proyecto_en_idioma(monkeypatch, tmp_path, "es")
    _, vid = video_nuevo(config=CONFIG)
    datos.empezar("acme", vid, "armando", ("configurando",))
    registro = []
    clips.armar(vid, llamar=fake(PLAN, registro=registro))
    assert "Planeas los clips" in _sitio(registro[0]["system"], "flowplus_clips")
    assert doctrina.COMBINACIONES["flowplus_clips"] == ("video", "gancho")


def test_imagenes_solo_llevan_la_base(base_temporal, monkeypatch, tmp_path):
    from guiones import imagenes
    from tests.test_guiones_idioma import RESPUESTA_IMAGENES
    vid = _armado(monkeypatch, tmp_path, "es")
    registro = []
    imagenes.escribir(vid, llamar=fake(RESPUESTA_IMAGENES, registro=registro))
    assert "Escribes en inglés el cuerpo de los prompts" in _sitio(registro[0]["system"], "flowplus_imagenes")
    assert doctrina.COMBINACIONES["flowplus_imagenes"] == () and registro[0]["system"][0]["text"] == doctrina.texto()


def test_refinador_lleva_video_y_gancho(base_temporal, monkeypatch, tmp_path):
    from guiones import refinador
    _proyecto_en_idioma(monkeypatch, tmp_path, "es")
    p = _crear()
    mid = refinador.pedir_cambio("acme", p["id"], "Cambia el baño por una habitación cálida")
    registro = []
    refinador.responder(mid, llamar=_llamar_fijo(_json("Listo.", CLIP), registro=registro))
    assert "Ayudas a una persona a corregir un prompt" in _sitio(registro[0]["system"], "flowplus_refinador")
    assert doctrina.COMBINACIONES["flowplus_refinador"] == ("video", "gancho")


def test_lectura_no_lleva_doctrina():
    """Copia literal verificada: la doctrina no tiene nada que decir ahí."""
    from guiones import lectura
    assert isinstance(lectura.SISTEMA, str) and "doctrina" not in lectura.SISTEMA.lower()


def test_los_tokens_de_la_cache_cuentan_como_entrada():
    """La doctrina con cache_control no entra en input_tokens: escribirla
    cuesta 1,25× y leerla 0,1× (como sprints.analisis._llamar_contando)."""
    from guiones import claude
    uso = SimpleNamespace(input_tokens=1000, output_tokens=50, cache_creation_input_tokens=2000, cache_read_input_tokens=0)
    assert claude.tokens_entrada_equivalentes(uso) == 3500
    uso = SimpleNamespace(input_tokens=1000, output_tokens=50, cache_creation_input_tokens=0, cache_read_input_tokens=2000)
    assert claude.tokens_entrada_equivalentes(uso) == 1200
    assert claude.tokens_entrada_equivalentes(SimpleNamespace(input_tokens=7)) == 7
    assert claude.tokens_entrada_equivalentes(None) == 0
