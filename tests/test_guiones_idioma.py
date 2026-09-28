"""Flow Plus (guiones) en el idioma del proyecto (spec 2026-09-26 §B4): el
chat de corrección de prompts, «Proponer qué quitar» y «Escribir prompts de
imágenes» le piden a Claude la explicación / los motivos / el título para la
persona en el idioma DEL PROYECTO — el prompt del modelo (video o imagen)
sigue siempre en inglés, como hoy. `refinador.validar` es aparte: sus
mensajes van en el idioma de quien MIRA LA PANTALLA (gettext)."""
from flask import Flask
from flask_babel import Babel

import idiomas
from tests.fixtures_guiones import CONFIG, PLAN, fake, video_nuevo
from tests.test_guiones_refinador import CLIP, _crear, _envejecer, _json, _llamar_fijo


def _proyecto_en_idioma(monkeypatch, tmp_path, idioma, cliente="acme"):
    """`idiomas.guardar_de_proyecto` escribe clientes/<cliente>/proyecto.json:
    apunta `proyectos._path` a un tmp_path para no tocar el repo real (mismo
    truco que tests/test_tareas_director.py)."""
    import proyectos
    monkeypatch.setattr(proyectos, "_path", lambda c: str(tmp_path / f"{c}.json"))
    idiomas.guardar_de_proyecto(cliente, idioma)


def _app_con_catalogo_real():
    """App Flask + Babel mínima, con el catálogo REAL del repo (mismo patrón
    que `app_prueba` de tests/test_idiomas.py, pero sin fabricar un catálogo
    de prueba: acá lo que importa es la traducción real que este task agregó).
    `locale_selector=idiomas.de_peticion` es el mismo que usa `dashboard.py`."""
    app = Flask(__name__)
    app.secret_key = "prueba"
    app.config["BABEL_DEFAULT_LOCALE"] = "es"
    app.config["BABEL_TRANSLATION_DIRECTORIES"] = idiomas.DIR_TRADUCCIONES
    Babel(app, locale_selector=idiomas.de_peticion)
    return app


def _sin_frases_permitidas(system):
    """`system` del refinador sin las frases que SIEMPRE mencionan «inglés»: las
    dos del cuerpo (el prompt del modelo nunca cambia de idioma) y, desde la
    revisión final fase 3 (finding 1), la propia orden de idioma en español —
    que ahora nombra «inglés» al describir su excepción (tokens Image N/Video N
    y prompts de modelo). Lo que quede no debería volver a nombrar el inglés."""
    return (system.replace("El prompt sigue en inglés (los modelos rinden mejor así)", "")
                  .replace("revisado, en inglés", "")
                  .replace(idiomas.orden_idioma("es"), ""))


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
    # La propia orden de idioma en español nombra «inglés» al describir su
    # excepción (finding 1, revisión final fase 3): se descuenta antes de
    # comprobar que no queda ninguna OTRA mención.
    assert "inglés" not in system.replace(orden, "")


def test_recorte_proponer_aviso_de_error_en_el_idioma_del_proyecto(base_temporal, monkeypatch, tmp_path):
    """Fix round 1: `proponer()` corre en un hilo de trabajos.iniciar (sin
    contexto de petición) igual que clips.armar/imagenes.escribir, pero no
    estaba envuelto en idiomas.en_idioma(idiomas.de_proyecto(cliente)) — el
    aviso del catch-all («No se pudo proponer qué quitar...») se guardaba
    siempre en español sin importar el idioma del proyecto. Se fuerza una
    excepción DESPUÉS de la llamada a Claude (datos.terminar_recorte revienta)
    para llegar al catch-all real, no al camino de `error` de pedir_json."""
    from guiones import datos, recorte

    def _revienta(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(datos, "terminar_recorte", _revienta)

    _proyecto_en_idioma(monkeypatch, tmp_path, "en")
    _, vid = video_nuevo(config=dict(CONFIG, duracion_objetivo=15))
    datos.empezar("acme", vid, "recortando", ("configurando",))
    recorte.proponer(vid, llamar=fake({"orden": [4, 3, 2, 5, 6, 1], "motivos": {"4": "minor detail"}}))
    v = datos.video("acme", vid)
    assert v["estado"] == "configurando"
    assert v["aviso"] == "Couldn't propose what to cut. Try again."

    _proyecto_en_idioma(monkeypatch, tmp_path, "es")
    _, vid2 = video_nuevo(config=dict(CONFIG, duracion_objetivo=15))
    datos.empezar("acme", vid2, "recortando", ("configurando",))
    recorte.proponer(vid2, llamar=fake({"orden": [4, 3, 2, 5, 6, 1], "motivos": {"4": "detalle"}}))
    v2 = datos.video("acme", vid2)
    assert v2["estado"] == "configurando"
    assert v2["aviso"] == "No se pudo proponer qué quitar. Vuelve a intentarlo."


# -------------------------------------------------------------- clips.py ---

def test_clips_armar_pide_el_titulo_en_ingles(base_temporal, monkeypatch, tmp_path):
    """Fix ronda revisión final (finding 3b): el plan de clips (momentos,
    bloque_video, estados) sigue en inglés siempre — es lo único que Claude no
    tenía instrucción de idioma para "titulo", que sí llega a la persona
    (vía _crear_prompts). Ahora se pide en el idioma del proyecto, con la
    misma orden al inicio y al final que recorte._sistema/imagenes._sistema."""
    from guiones import clips, datos
    _proyecto_en_idioma(monkeypatch, tmp_path, "en")
    _, vid = video_nuevo(config=CONFIG)
    datos.empezar("acme", vid, "armando", ("configurando",))
    registro = []
    clips.armar(vid, llamar=fake(PLAN, registro=registro))
    system = registro[0]["system"]
    orden = idiomas.orden_idioma("en")
    assert system.startswith(orden) and system.endswith(orden)
    assert '"titulo": "título corto en inglés"' in system
    # El plan en sí (lo que termina en el prompt del modelo de video) se sigue
    # pidiendo en inglés siempre, sin importar el idioma del proyecto.
    assert '"bloque_video" (en inglés)' in system


def test_clips_armar_en_espanol_mantiene_el_texto_de_hoy(base_temporal, monkeypatch, tmp_path):
    from guiones import clips, datos
    _proyecto_en_idioma(monkeypatch, tmp_path, "es")
    _, vid = video_nuevo(config=CONFIG)
    datos.empezar("acme", vid, "armando", ("configurando",))
    registro = []
    clips.armar(vid, llamar=fake(PLAN, registro=registro))
    system = registro[0]["system"]
    orden = idiomas.orden_idioma("es")
    assert system.startswith(orden) and system.endswith(orden)
    assert '"titulo": "título corto en español"' in system


def _capturar_prompts_de_chat(monkeypatch):
    """Reemplaza `refinador.crear` por uno que solo guarda título/contexto
    (sin tocar la base): lo que arma `clips._crear_prompts`, no lo que hace
    `refinador.crear` con eso."""
    from guiones import clips
    llamadas = []

    def _falso_crear(cliente, texto, titulo="", tipo="libre", contexto="", texto_fijo=(), origen="manual", extra=None):
        llamadas.append({"titulo": titulo, "contexto": contexto, "extra": extra or {}})
        return {"id": len(llamadas)}

    monkeypatch.setattr(clips.refinador, "crear", _falso_crear)
    return llamadas


def test_clips_prompts_de_chat_en_ingles_sin_marcas_de_espanol(base_temporal, monkeypatch, tmp_path):
    """Fix ronda revisión final (finding 2): título y contexto del prompt de
    chat de cada clip (antes f-strings fijos en español, incluso en un
    proyecto en inglés) se arman con gettext dentro del mismo en_idioma que ya
    envuelve clips.armar."""
    from guiones import clips, datos
    from tests.i18n_util import _con_marca
    _proyecto_en_idioma(monkeypatch, tmp_path, "en")
    _, vid = video_nuevo(config=CONFIG)
    datos.empezar("acme", vid, "armando", ("configurando",))
    llamadas = _capturar_prompts_de_chat(monkeypatch)
    clips.armar(vid, llamar=fake(PLAN))
    assert llamadas
    for l in llamadas:
        assert not _con_marca(l["titulo"]), l["titulo"]
        assert not _con_marca(l["contexto"]), l["contexto"]


def test_clips_prompts_de_chat_en_espanol_mantiene_el_texto_de_hoy(base_temporal, monkeypatch, tmp_path):
    """En español (DEFECTO, sin catálogo propio) el texto sale idéntico al de
    antes de este cambio: `etiqueta_version` traduce igual que `nombre_version`
    cuando no hay traducción que aplicar."""
    from guiones import clips, datos
    _proyecto_en_idioma(monkeypatch, tmp_path, "es")
    _, vid = video_nuevo(config=CONFIG)
    datos.empezar("acme", vid, "armando", ("configurando",))
    llamadas = _capturar_prompts_de_chat(monkeypatch)
    clips.armar(vid, llamar=fake(PLAN))
    principal_1 = next(l for l in llamadas
                       if l["extra"].get("variante") == "principal" and l["extra"].get("clip_index") == 1)
    assert principal_1["titulo"] == "AI podiatrist · v1 · Clip 1 de 2 · The hook"
    assert principal_1["contexto"].startswith(
        "Guion «AI podiatrist», Completo · diálogo · v1. Líneas del video, en orden:\n1. ")
    assert "El clip siguiente empieza así: Hands empty." in principal_1["contexto"]


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


def _capturar_prompts_de_chat_imagenes(monkeypatch):
    """Igual que `_capturar_prompts_de_chat` (clips.py) pero para
    `imagenes.refinador.crear`."""
    from guiones import imagenes
    llamadas = []

    def _falso_crear(cliente, texto, titulo="", tipo="libre", contexto="", texto_fijo=(), origen="manual", extra=None):
        llamadas.append({"titulo": titulo, "contexto": contexto})
        return {"id": len(llamadas)}

    monkeypatch.setattr(imagenes.refinador, "crear", _falso_crear)
    return llamadas


def test_imagenes_prompts_de_chat_en_ingles_sin_marcas_de_espanol(base_temporal, monkeypatch, tmp_path):
    """Fix ronda revisión final (finding 2): el contexto del prompt de chat de
    cada imagen (antes un f-string fijo en español, con `v['nombre']` que
    nunca se traduce porque se persiste) se arma con gettext y
    `datos.etiqueta_version` dentro del mismo en_idioma que ya envuelve
    imagenes.escribir."""
    from guiones import imagenes
    from tests.i18n_util import _con_marca
    vid = _armado(monkeypatch, tmp_path, "en")
    llamadas = _capturar_prompts_de_chat_imagenes(monkeypatch)
    imagenes.escribir(vid, llamar=fake(RESPUESTA_IMAGENES))
    assert llamadas
    for l in llamadas:
        assert not _con_marca(l["titulo"]), l["titulo"]
        assert not _con_marca(l["contexto"]), l["contexto"]


def test_imagenes_prompts_de_chat_en_espanol_mantiene_el_texto_de_hoy(base_temporal, monkeypatch, tmp_path):
    from guiones import imagenes
    vid = _armado(monkeypatch, tmp_path, "es")
    llamadas = _capturar_prompts_de_chat_imagenes(monkeypatch)
    imagenes.escribir(vid, llamar=fake(RESPUESTA_IMAGENES))
    assert llamadas[0]["titulo"] == "AI podiatrist · v1 · img_1 · Podiatrist"
    assert llamadas[0]["contexto"] == "Imagen de referencia para Completo · diálogo · v1 del guion «AI podiatrist»."


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


def test_mensaje_interrumpido_sigue_el_idioma_de_quien_mira_la_pantalla(base_temporal):
    """`MENSAJE_INTERRUMPIDO` (fix round 1): `_vencer_pendientes` corre siempre
    dentro de una petición real (vía `obtener`/`pedir_cambio`/`aprobar`), así
    que el aviso de chat interrumpido sigue el idioma de quien mira la
    pantalla, igual que `validar` — DEFECTO ("es") fuera de toda petición."""
    from guiones import refinador
    p = _crear()
    mid = refinador.pedir_cambio("acme", p["id"], "uno")
    _envejecer(mid)
    with idiomas.en_idioma("en"):
        d = refinador.obtener("acme", p["id"])
    claude = d["mensajes"][-1]
    assert claude["estado"] == "error" and claude["contenido"] == "The answer was interrupted. Send your message again."

    p2 = _crear(titulo="Otro")
    mid2 = refinador.pedir_cambio("acme", p2["id"], "uno")
    _envejecer(mid2)
    d2 = refinador.obtener("acme", p2["id"])  # sin petición ni idiomas.en_idioma: DEFECTO
    assert d2["mensajes"][-1]["contenido"] == "Se interrumpió la respuesta. Vuelve a enviar tu mensaje."


# ------------------------------------------------------- guiones/claude.py ---

def test_pedir_json_dentro_de_una_peticion_sigue_el_idioma_de_la_pantalla(base_temporal, monkeypatch, tmp_path):
    """Fix round 1 (finding 2): dentro de una petición, `pedir_json` NO fuerza
    el idioma del proyecto — los mensajes que llegan a la persona siguen el
    idioma de la pantalla (spec §B4, «pantallas = la persona»), aunque el
    proyecto esté en otro idioma."""
    from guiones import claude
    _proyecto_en_idioma(monkeypatch, tmp_path, "en")

    def revienta(*_):
        raise TimeoutError("lento")

    app = _app_con_catalogo_real()
    with app.test_request_context("/", headers={"Cookie": "idioma=es"}):
        data, usd, error = claude.pedir_json("acme", "leer", 1, "sis", [], "Leer", llamar_fn=revienta)
    assert data is None and "No se pudo consultar a Claude" in error and "TimeoutError" in error


def test_pedir_json_sin_peticion_fuerza_el_idioma_del_proyecto(base_temporal, monkeypatch, tmp_path):
    """Sin petición (el camino real: `recorte.proponer`/`imagenes.escribir`
    corren en el hilo del worker, sin ningún contexto de Flask), `pedir_json`
    sigue forzando el idioma del proyecto — es la mejor señal disponible."""
    from guiones import claude
    _proyecto_en_idioma(monkeypatch, tmp_path, "en")

    def revienta(*_):
        raise TimeoutError("lento")

    data, usd, error = claude.pedir_json("acme", "leer", 1, "sis", [], "Leer", llamar_fn=revienta)
    assert data is None and "Couldn't reach Claude" in error and "TimeoutError" in error
