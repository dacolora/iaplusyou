"""Flow Plus (guiones) en el idioma del proyecto (spec 2026-09-26 §B4): el
chat de corrección de prompts, «Proponer qué quitar» y «Escribir prompts de
imágenes» le piden a Claude la explicación / los motivos / el título para la
persona en el idioma DEL PROYECTO — el prompt del modelo (video o imagen)
sigue siempre en inglés, como hoy. `refinador.validar` es aparte: sus
mensajes van en el idioma de quien MIRA LA PANTALLA (gettext)."""
import idiomas

from tests.fixtures_guiones import CONFIG, PLAN, fake, video_nuevo
from tests.test_guiones_refinador import CLIP, _crear, _json, _llamar_fijo


def _proyecto_en_idioma(monkeypatch, tmp_path, idioma, cliente="acme"):
    """`idiomas.guardar_de_proyecto` escribe clientes/<cliente>/proyecto.json:
    apunta `proyectos._path` a un tmp_path para no tocar el repo real (mismo
    truco que tests/test_tareas_director.py)."""
    import proyectos
    monkeypatch.setattr(proyectos, "_path", lambda c: str(tmp_path / f"{c}.json"))
    idiomas.guardar_de_proyecto(cliente, idioma)


def _sin_frases_permitidas(system):
    """`system` del refinador sin las dos frases que SIEMPRE mencionan
    «inglés» (el prompt del modelo nunca cambia de idioma): lo que quede no
    debería volver a nombrar el inglés."""
    return (system.replace("El prompt sigue en inglés (los modelos rinden mejor así)", "")
                  .replace("revisado, en inglés", ""))


# --------------------------------------------------------- refinador.py ---

def test_refinador_responder_pide_la_explicacion_en_ingles(base_temporal, monkeypatch, tmp_path):
    from guiones import refinador
    _proyecto_en_idioma(monkeypatch, tmp_path, "en")
    p = _crear()
    mid = refinador.pedir_cambio("acme", p["id"], "Cambia el baño por una habitación cálida")
    registro = []
    refinador.responder(mid, llamar=_llamar_fijo(_json("Changed the room.", CLIP), registro=registro))
    system = registro[0]["system"]
    orden = idiomas.orden_idioma("en")
    assert orden in system and "inglés" in system
    # El prompt de salida (lo que va al modelo) se sigue pidiendo en inglés,
    # como hoy — cambia solo el idioma de la explicación para la persona.
    assert '"prompt": "<el prompt COMPLETO revisado, en inglés>"' in system
    assert refinador.obtener("acme", p["id"])["mensajes"][-1]["contenido"] == "Changed the room."


def test_refinador_responder_en_espanol_mantiene_el_texto_de_hoy(base_temporal, monkeypatch, tmp_path):
    """Con el proyecto en "es" (el idioma de hoy), el system queda exactamente
    igual que antes de este cambio, solo envuelto por la orden de idioma en
    español al inicio y al final."""
    from guiones import refinador
    _proyecto_en_idioma(monkeypatch, tmp_path, "es")
    p = _crear()
    mid = refinador.pedir_cambio("acme", p["id"], "Cambia el baño")
    registro = []
    refinador.responder(mid, llamar=_llamar_fijo(_json("Listo.", CLIP), registro=registro))
    system = registro[0]["system"]
    orden = idiomas.orden_idioma("es")
    assert system.startswith(orden) and system.endswith(orden)
    assert "español" in system
    assert '"respuesta": "<explicación para la persona, en español>"' in system
    # Ninguna otra mención a "inglés" salvo la regla de que el prompt del
    # modelo siempre queda en inglés.
    assert "inglés" not in _sin_frases_permitidas(system)


# ----------------------------------------------------------- recorte.py ---

def test_recorte_proponer_pide_los_motivos_en_ingles(base_temporal, monkeypatch, tmp_path):
    from guiones import datos, recorte
    _proyecto_en_idioma(monkeypatch, tmp_path, "en")
    _, vid = video_nuevo(config=dict(CONFIG, duracion_objetivo=15))
    datos.empezar("acme", vid, "recortando", ("configurando",))
    registro = []
    recorte.proponer(vid, llamar=fake({"orden": [4, 3, 2, 5, 6, 1], "motivos": {"4": "minor detail"}},
                                      registro=registro))
    system = registro[0]["system"]
    orden = idiomas.orden_idioma("en")
    assert system.startswith(orden) and system.endswith(orden)
    assert "por qué se puede quitar, en inglés, máximo 12 palabras" in system
    v = datos.video("acme", vid)
    assert v["recorte"]["motivos"]["4"] == "minor detail"


def test_recorte_proponer_en_espanol_mantiene_el_texto_de_hoy(base_temporal, monkeypatch, tmp_path):
    from guiones import datos, recorte
    _proyecto_en_idioma(monkeypatch, tmp_path, "es")
    _, vid = video_nuevo(config=dict(CONFIG, duracion_objetivo=15))
    datos.empezar("acme", vid, "recortando", ("configurando",))
    registro = []
    recorte.proponer(vid, llamar=fake({"orden": [4, 3, 2, 5, 6, 1], "motivos": {"4": "detalle"}},
                                      registro=registro))
    system = registro[0]["system"]
    orden = idiomas.orden_idioma("es")
    assert system.startswith(orden) and system.endswith(orden)
    assert "por qué se puede quitar, en español, máximo 12 palabras" in system
    assert "inglés" not in system


# ---------------------------------------------------------- imagenes.py ---

def _armado(monkeypatch, tmp_path, idioma, cliente="acme"):
    """Deja un video en `estado_imagenes = "escribiendo"`, con el proyecto en
    `idioma` (mismo camino que la fixture `armado` de
    tests/test_guiones_imagenes_escribir.py, más el idioma del proyecto)."""
    import proyectos
    from guiones import clips, datos
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / cliente).mkdir(parents=True)
    idiomas.guardar_de_proyecto(cliente, idioma)
    _, vid = video_nuevo(cliente=cliente, config=CONFIG)
    datos.empezar(cliente, vid, "armando", ("configurando",))
    clips.armar(vid, llamar=fake(PLAN))
    datos.empezar_imagenes(cliente, vid)
    return vid


RESPUESTA_IMAGENES = {"imagenes": [{"id": "img_1", "titulo": "Podiatrist", "prompt": "A calm British man."},
                                   {"id": "img_2", "titulo": "Clinic", "prompt": "A bright modern clinic."}]}


def test_imagenes_escribir_pide_el_titulo_en_ingles(base_temporal, monkeypatch, tmp_path):
    from guiones import imagenes
    vid = _armado(monkeypatch, tmp_path, "en")
    registro = []
    imagenes.escribir(vid, llamar=fake(RESPUESTA_IMAGENES, registro=registro))
    system = registro[0]["system"]
    orden = idiomas.orden_idioma("en")
    assert system.startswith(orden) and system.endswith(orden)
    assert '"titulo": "título corto en inglés"' in system
    # El cuerpo del prompt de imagen (lo que va al modelo) se sigue pidiendo
    # en inglés siempre, sin importar el idioma del proyecto.
    assert "Escribes en inglés el cuerpo de los prompts" in system


def test_imagenes_escribir_en_espanol_mantiene_el_texto_de_hoy(base_temporal, monkeypatch, tmp_path):
    from guiones import imagenes
    vid = _armado(monkeypatch, tmp_path, "es")
    registro = []
    imagenes.escribir(vid, llamar=fake(RESPUESTA_IMAGENES, registro=registro))
    system = registro[0]["system"]
    orden = idiomas.orden_idioma("es")
    assert system.startswith(orden) and system.endswith(orden)
    assert '"titulo": "título corto en español"' in system


# --------------------------------------------------------- refinador.validar ---

def test_validar_en_el_idioma_de_quien_mira_la_pantalla():
    """`validar` no depende del idioma del proyecto (no recibe `cliente`):
    depende del idioma de quien mira la pantalla — `gettext`, forzado por
    `idiomas.en_idioma` dentro de una petición, DEFECTO ("es") fuera de toda
    petición o app."""
    from guiones.refinador import validar
    with idiomas.en_idioma("en"):
        problemas_en = validar("")
    problemas_es = validar("")
    assert problemas_en == ["The prompt is empty."]
    assert problemas_es == ["El prompt está vacío."]
