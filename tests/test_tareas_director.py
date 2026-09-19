"""Tarea flowplus_director (spec §4): compila con Claude, guarda A/B en la
sesión, cae al prompt determinista si el director falla y lanza la
generación solo cuando el payload lo pide (lotes de sprints)."""
import pytest


def _sesion(cf, cliente="acme"):
    cid = cf.crear(cliente, [], ["Espejo"], [], "@Imagen 1 gira despacio", 8, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar(cliente, cid, estado="prompt_pendiente", tipo="video", modelo="wan3", aspect_ratio="9:16",
                  con_sonido=True, sonido_texto="", musica_estilo="", enfoque="producto",
                  referencias=[{"tipo": "imagen", "etiqueta": "@Imagen 1", "token": "Image 1", "url": "https://x/1.png", "frame_url": "https://x/1.png"}])
    return cid


def _resultado():
    planos = [{"n": 1, "inicio_s": 0, "fin_s": 4, "plano": "primer plano", "camara": "dolly_in", "accion": "Image 1 gira", "sonido": "brisa"},
              {"n": 2, "inicio_s": 4, "fin_s": 8, "plano": "plano medio", "camara": "orbita_corta", "accion": "la cámara rodea Image 1", "sonido": "olas"}]
    return {"planos": planos, "planos_b": planos, "prompt_a": "PROMPT A", "prompt_b": "PROMPT B", "diferencia_b": "otro arranque",
            "modelo_claude": "claude-sonnet-5", "version": 1, "usd": 0.01}


def test_registra_el_tipo_y_el_job_id(base_temporal):
    import tareas
    import tareas.director as td
    assert tareas.REGISTRO["flowplus_director"] is td.ejecutar
    assert td.job_id("acme", "cf_1") == "acme__cf_1__director"
    assert sum(p for _, p in td.ETAPAS_DIRECTOR) == 100


def test_ok_guarda_prompt_a_y_director_en_la_sesion(base_temporal, monkeypatch):
    import creative_flow as cf
    import tareas.director as td
    cid = _sesion(cf)
    monkeypatch.setattr(td.director, "compilar", lambda cliente, sesion, idioma="es": _resultado())
    lanzados = []
    monkeypatch.setattr(td.flowplus_lanzar, "lanzar", lambda c, cf_id, entry, prioridad=5: lanzados.append((cf_id, prioridad)) or True)
    msg = td.ejecutar({"payload": {"cliente": "acme", "cf_id": cid, "auto_lanzar": False}, "job_id": td.job_id("acme", cid)})
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "prompt_listo" and e["prompt_relleno"] == "PROMPT A"
    assert e["director"]["estado"] == "ok" and e["director"]["prompt_b"] == "PROMPT B" and e["director"]["usd"] == 0.01
    assert lanzados == [] and "revísalo" in msg


def test_fallback_al_prompt_determinista_cuando_el_director_falla(base_temporal, monkeypatch):
    import creative_flow as cf
    import director
    import tareas.director as td
    cid = _sesion(cf)

    def _boom(cliente, sesion, idioma="es"):
        raise director.DirectorError("Anthropic caído")
    monkeypatch.setattr(td.director, "compilar", _boom)
    msg = td.ejecutar({"payload": {"cliente": "acme", "cf_id": cid, "auto_lanzar": False}, "job_id": "j"})
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "prompt_listo"
    assert "ESCENA: Image 1 gira despacio" in e["prompt_relleno"] and "No dialogue. No background music." in e["prompt_relleno"]
    assert e["director"]["estado"] == "fallback" and "Anthropic caído" in e["director"]["aviso"]
    assert "básico" in msg


def test_cualquier_excepcion_tambien_cae_al_fallback(base_temporal, monkeypatch):
    import creative_flow as cf
    import tareas.director as td
    cid = _sesion(cf)

    def _boom(cliente, sesion, idioma="es"):
        raise RuntimeError("red")
    monkeypatch.setattr(td.director, "compilar", _boom)
    td.ejecutar({"payload": {"cliente": "acme", "cf_id": cid, "auto_lanzar": False}, "job_id": "j"})
    assert cf.cargar("acme")[cid]["director"]["estado"] == "fallback"


def test_auto_lanzar_encola_la_generacion_con_la_prioridad_del_payload(base_temporal, monkeypatch):
    import creative_flow as cf
    import tareas.director as td
    cid = _sesion(cf)
    monkeypatch.setattr(td.director, "compilar", lambda cliente, sesion, idioma="es": _resultado())
    lanzados = []
    monkeypatch.setattr(td.flowplus_lanzar, "lanzar", lambda c, cf_id, entry, prioridad=5: lanzados.append((cf_id, prioridad, entry["prompt_relleno"])) or True)
    td.ejecutar({"payload": {"cliente": "acme", "cf_id": cid, "auto_lanzar": True, "prioridad": 3}, "job_id": "j"})
    assert lanzados == [(cid, 3, "PROMPT A")]


def test_interrumpida_deja_el_prompt_basico_con_aviso(base_temporal, monkeypatch):
    import creative_flow as cf
    import tareas
    import tareas.director as td
    assert tareas.AL_INTERRUMPIR["flowplus_director"] is td.interrumpida
    cid = _sesion(cf)
    lanzados = []
    monkeypatch.setattr(td.flowplus_lanzar, "lanzar", lambda c, cf_id, entry, prioridad=5: lanzados.append((cf_id, prioridad)) or True)
    td.interrumpida({"payload": {"cliente": "acme", "cf_id": cid, "auto_lanzar": True}},
                     "Se interrumpió por un reinicio del servidor.")
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "prompt_listo"
    assert "ESCENA: Image 1 gira despacio" in e["prompt_relleno"]
    assert e["director"]["estado"] == "fallback"
    assert "reinicio" in e["director"]["aviso"]
    assert lanzados == []


def test_interrumpida_no_pisa_una_sesion_que_ya_avanzo(base_temporal, monkeypatch):
    import creative_flow as cf
    import tareas.director as td
    cid = _sesion(cf)
    cf.actualizar("acme", cid, estado="prompt_listo", prompt_relleno="A")
    td.interrumpida({"payload": {"cliente": "acme", "cf_id": cid, "auto_lanzar": False}}, "motivo")
    e = cf.cargar("acme")[cid]
    assert e["prompt_relleno"] == "A"
    assert not e.get("director")


@pytest.mark.skip(reason="Task 6")
def test_idioma_viene_de_la_preferencia_del_proyecto(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import proyectos
    import tareas.director as td
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    proyectos.guardar_preferencias_flowplus("acme", "wan3", "seedream_v5_pro", idioma_prompt="en", duracion_defecto=8)
    cid = _sesion(cf)
    visto = {}
    monkeypatch.setattr(td.director, "compilar", lambda cliente, sesion, idioma="es": visto.update(idioma=idioma) or _resultado())
    td.ejecutar({"payload": {"cliente": "acme", "cf_id": cid, "auto_lanzar": False}, "job_id": "j"})
    assert visto["idioma"] == "en"
