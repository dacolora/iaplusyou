"""Lo que se GUARDA (un error de una publicación o de un experimento, el
detalle de un gasto, un evento, el mensaje de una tarea) va en el idioma del
proyecto aunque lo arme una ruta mirada por alguien en otro idioma (spec
2026-09-26 §B8; fase 6). Lo que se RESPONDE sigue a quien mira."""
import idiomas
from tests.test_rutas_referentes import app  # noqa: F401 (fixture: proyecto y catálogo de prueba)


def test_error_guardado_de_una_publicacion_va_en_el_idioma_del_proyecto(base_temporal, monkeypatch):
    import dashboard
    import organico
    guardados = []
    monkeypatch.setattr(dashboard.trabajos, "encolar", lambda *a, **k: None)
    monkeypatch.setattr(organico, "actualizar", lambda c, pub_id, **kw: guardados.append(kw["error"]))
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    with idiomas.en_idioma("es"):                     # quien mira, en español
        assert not dashboard._encolar_organico("acme", 1, [7])
    assert guardados == ["There was already a post of this piece in progress; retry once it finishes."]




def _huerfanos_en_carpeta_temporal(dashboard, monkeypatch, tmp_path, clientes=()):
    """_reconciliar_huerfanos recorre BASE_DIR/clientes: una carpeta temporal
    para no tocar nunca los proyectos reales del repo."""
    for cliente in clientes:
        (tmp_path / "clientes" / cliente).mkdir(parents=True)
    (tmp_path / "clientes").mkdir(exist_ok=True)
    monkeypatch.setattr(dashboard, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: False)


def test_generacion_interrumpida_se_guarda_en_el_idioma_de_cada_proyecto(base_temporal, monkeypatch, tmp_path):
    import dashboard
    _huerfanos_en_carpeta_temporal(dashboard, monkeypatch, tmp_path, clientes=("acme", "otro"))
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: {"acme": "en", "otro": "es"}[c])
    monkeypatch.setattr(dashboard.swaps_mod, "cargar", lambda c: {"s1": {"estado": "generando"}})
    guardados = {}
    monkeypatch.setattr(dashboard.swaps_mod, "guardar", lambda c, data: guardados.__setitem__(c, data["s1"]["error"]))
    monkeypatch.setattr(dashboard.creative_flow, "cargar", lambda c: {})
    monkeypatch.setattr(dashboard.conceptos_imagen, "cargar", lambda c: {})
    dashboard._reconciliar_huerfanos()
    assert guardados == {
        "acme": "The generation was interrupted because the server restarted — try again.",
        "otro": "La generación se interrumpió porque el servidor se reinició — vuelve a intentarlo.",
    }


def test_detalle_del_gasto_de_adaptar_invalido_va_en_el_idioma_del_proyecto(app, monkeypatch):
    """La respuesta (el JSON de error) sigue a quien mira; el `detalle` del
    gasto que queda en Configuración › Gasto, al proyecto."""
    import gastos
    import proyectos
    from referentes import recrear
    from tests.test_rutas_referentes import _sembrar
    monkeypatch.setattr(proyectos, "referentes_copycoders", lambda cliente: True)
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    monkeypatch.setattr(recrear, "_llamar", lambda texto, max_tokens: ("no es json", 80, 20))
    ids = _sembrar()
    r = app["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/adaptar", json={"producto_id": "espejo_led"})
    assert r.status_code == 502
    assert gastos.historial("acme", limite=1)[0]["detalle"] == "Espejo LED · Price Slash Hero · invalid response"


def test_lanzamiento_interrumpido_se_guarda_en_el_idioma_del_proyecto(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import experimentos as ex
    from tests.test_experimentos_db import PAISES
    _huerfanos_en_carpeta_temporal(dashboard, monkeypatch, tmp_path)
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ex.actualizar("acme", eid, estado="lanzando")
    dashboard._reconciliar_huerfanos()
    exp = ex.obtener("acme", eid)
    assert exp["estado"] == "error"
    assert exp["error"] == "The launch was interrupted; check Ads Manager and try again."


# --- Fase 6, Task 7: el worker y lo que se guarda ---------------------------

def test_hook_de_tarea_interrumpida_en_el_idioma_del_proyecto(tmp_path, monkeypatch):
    import cola
    import proyectos
    import tareas
    import worker
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    idiomas.guardar_de_proyecto("acme", "en")
    vistos = []
    monkeypatch.setitem(tareas.AL_INTERRUMPIR, "prueba_idioma", lambda t, mensaje: vistos.append(mensaje))
    # `excluir` llegó con el carril de Crear (main): recuperar_interrumpidas le pasa lo que está en vuelo.
    monkeypatch.setattr(cola, "recuperar_colgadas",
                        lambda minutos, excluir=(): (1, [{"id": 1, "tipo": "prueba_idioma", "cliente": "acme",
                                                          "payload": {}}]))
    worker.recuperar_interrumpidas(30)
    assert vistos == ["Interrupted by a server restart. Try again."]


def test_colgada_sin_reintentos_queda_en_el_idioma_del_proyecto(base_temporal, monkeypatch):
    from datetime import datetime, timedelta

    import cola
    import db
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    tid = cola.encolar("prueba", {"cliente": "acme"}, cliente="acme", max_intentos=1)
    cola.reclamar()
    vieja = (datetime.now() - timedelta(minutes=45)).isoformat(timespec="seconds")
    with db.conectar() as con:
        con.execute(db.tarea.update().where(db.tarea.c.id == tid).values(iniciada_en=vieja))
    cola.recuperar_colgadas(30)
    assert cola.consultar_por_id(tid)["error"] == (
        "Interrupted (it had been running for more than 30 min). Check the result and try again.")


def test_colgada_con_reintentos_y_proyecto_en_espanol_no_cambia(base_temporal, monkeypatch):
    from datetime import datetime, timedelta

    import cola
    import db
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "es")
    tid = cola.encolar("prueba", {"cliente": "acme"}, cliente="acme", max_intentos=2)
    cola.reclamar()
    vieja = (datetime.now() - timedelta(minutes=45)).isoformat(timespec="seconds")
    with db.conectar() as con:
        con.execute(db.tarea.update().where(db.tarea.c.id == tid).values(iniciada_en=vieja))
    with idiomas.en_idioma("en"):                     # el idioma ambiente no manda: manda el proyecto
        cola.recuperar_colgadas(30)
    assert cola.consultar_por_id(tid)["error"] == "recuperada: llevaba más de 30 min en curso"


def test_continuacion_perdida_se_guarda_en_el_idioma_del_proyecto(monkeypatch):
    """worker._terminar_y_encolar (carril de Crear): si no logra encolar la
    continuación, el error de la tarea y el gancho de interrupción van en el
    idioma del proyecto, no en el del hilo (que no tiene ninguno)."""
    import pytest

    import cola
    import tareas
    import worker
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    monkeypatch.setattr(worker.time, "sleep", lambda s: None)

    def _falla(*a, **k):
        raise RuntimeError("database is locked")
    monkeypatch.setattr(cola, "terminar_y_encolar", _falla)
    errores, vistos = [], []
    monkeypatch.setattr(cola, "fallar", lambda tid, error: errores.append(error))
    monkeypatch.setitem(tareas.AL_INTERRUMPIR, "prueba_idioma", lambda t, mensaje: vistos.append(mensaje))
    tarea = {"id": 7, "tipo": "prueba_idioma", "cliente": "acme", "payload": {}}
    with pytest.raises(worker.ContinuacionPerdida):
        worker._terminar_y_encolar(tarea, tareas.Continuar("prueba_idioma", {}))
    assert errores == ["Couldn't queue the follow-up task (RuntimeError: database is locked)"]
    assert vistos == ["Interrupted by a server restart. Try again."]


def test_evento_de_creacion_desde_la_galeria_en_el_idioma_del_proyecto(base_temporal, monkeypatch):
    import experimentos as ex
    from tests.test_experimentos_db import PAISES, _pieza
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    f_co = _pieza(base_temporal)
    # Solo CO: con MX sin pieza, crear_con_piezas rechaza («Sin piezas para: MX») antes de crear nada.
    datos = dict(nombre="Test", paises=[PAISES[0]], objetivo_meta="OUTCOME_TRAFFIC", dias=7, tope_total=100.0,
                 destino_url="https://t", moneda="COP", edad_min=18, edad_max=65, modo="manual", atribucion="ninguna")
    eid = ex.crear_con_piezas("acme", datos, [(f_co, "CO")])
    creado = next(e for e in ex.obtener("acme", eid)["eventos"] if e["tipo"] == "creado")
    assert creado["mensaje"].startswith("Experiment created from the gallery with 1 ad(s) in ")


def test_detalle_del_pixel_en_el_error_de_lanzamiento_va_traducido(monkeypatch):
    """Desde la Task 5 el `detalle` del Pixel es un msgid (N_); el error de
    lanzamiento que lo incluye (worker → idioma del proyecto) lo traduce."""
    import pytest

    import lanzador
    monkeypatch.setattr(lanzador.meta_conexion, "estado_pixel", lambda c, solo_cache=False: {
        "estado": "sin_pixel", "pixel_id": None, "detalle": "La cuenta publicitaria no tiene ningún Pixel."})
    with idiomas.en_idioma("en"), pytest.raises(ValueError) as e:
        lanzador._promoted_object_para("acme", {"objetivo_meta": "OUTCOME_SALES"})
    assert "(The ad account has no Pixel)" in str(e.value)


def test_nombre_por_defecto_de_una_cancion_en_el_idioma_del_proyecto(base_temporal, monkeypatch, tmp_path):
    """Mi música: el nombre que se GUARDA cuando el archivo no trae nombre (o
    ElevenLabs no recibió texto) sigue al proyecto, no a quien sube."""
    import materiales
    import mi_musica
    from tests.test_mi_musica import _Archivo, _wav_bytes
    monkeypatch.setattr(materiales.r2_uploader, "upload_file", lambda local, key, ct: f"https://r2/{key}")
    proyecto = {"idioma": "en"}
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: proyecto["idioma"])
    with idiomas.en_idioma("es"):                     # quien sube mira en español
        subida = mi_musica.subir("acme", _Archivo(" .wav", _wav_bytes(2.0)), str(tmp_path / "subidas"))
        p = tmp_path / "generada.wav"
        p.write_bytes(_wav_bytes(3.0))
        generada = mi_musica.registrar_generada("acme", str(p), "   ", True, 0.6)
    assert (subida["nombre"], generada["nombre"]) == ("Song", "ElevenLabs song")
    proyecto["idioma"] = "es"
    with idiomas.en_idioma("en"):
        q = tmp_path / "otra.wav"
        q.write_bytes(_wav_bytes(4.0))
        assert mi_musica.registrar_generada("acme", str(q), "", False, 0.6)["nombre"] == "Canción ElevenLabs"


def _error_del_hilo_de_pegar_link(app, monkeypatch, idioma_proyecto):
    """Corre el trabajo de «Pegar link» (dashboard.fp_agregar_link) en un hilo
    aparte, sin petición ni app, como lo corre trabajos.iniciar."""
    import threading
    dashboard = app["dashboard"]
    capturado = {}

    def _iniciar(job_id, fn, duracion_estimada=None, **k):
        capturado["fn"] = fn
        return True
    monkeypatch.setattr(dashboard.trabajos, "iniciar", _iniciar)
    monkeypatch.setattr(dashboard.bitacora, "registrar", lambda *a, **k: None)
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: idioma_proyecto)
    r = app["c"].post("/cliente/acme/flowplus/referencias/link", data={"link": "esto-no-es-un-link"})
    assert r.status_code in (200, 302)
    resultado = {}

    def _correr():
        try:
            capturado["fn"]()
        except Exception as e:  # noqa: BLE001
            resultado["error"] = str(e)
    hilo = threading.Thread(target=_correr)
    hilo.start()
    hilo.join(10)
    return resultado.get("error")


def test_error_del_hilo_de_pegar_link_en_el_idioma_del_proyecto(app, monkeypatch):
    assert _error_del_hilo_de_pegar_link(app, monkeypatch, "en") == (
        "That doesn't look like a link (it must start with http:// or https://).")


def test_error_del_hilo_de_pegar_link_en_espanol(app, monkeypatch):
    assert _error_del_hilo_de_pegar_link(app, monkeypatch, "es") == (
        "Eso no parece un link (tiene que empezar por http:// o https://).")


# --- Fase 6, Task 7, fix round 1 --------------------------------------------

def test_interrumpidas_de_dos_proyectos_cada_una_en_su_idioma(base_temporal, monkeypatch):
    """Una misma pasada de recuperar_interrumpidas con una tarea de un proyecto
    en inglés y otra de uno en español: el error de cada tarea y lo que guarda
    su gancho van cada uno en el idioma de SU proyecto."""
    from datetime import datetime, timedelta

    import cola
    import db
    import tareas
    import worker
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: {"acme": "en", "otro": "es"}[c])
    vistos = {}
    monkeypatch.setitem(tareas.AL_INTERRUMPIR, "prueba_idioma",
                        lambda t, mensaje: vistos.__setitem__(t["cliente"], mensaje))
    ids = {c: cola.encolar("prueba_idioma", {"cliente": c}, cliente=c, max_intentos=1) for c in ("acme", "otro")}
    cola.reclamar()
    cola.reclamar()
    vieja = (datetime.now() - timedelta(minutes=45)).isoformat(timespec="seconds")
    with db.conectar() as con:
        con.execute(db.tarea.update().where(db.tarea.c.id.in_(list(ids.values()))).values(iniciada_en=vieja))
    worker.recuperar_interrumpidas(30)
    assert vistos == {"acme": "Interrupted by a server restart. Try again.",
                      "otro": "Se interrumpió por un reinicio del servidor. Vuelve a intentar."}
    assert cola.consultar_por_id(ids["acme"])["error"] == (
        "Interrupted (it had been running for more than 30 min). Check the result and try again.")
    assert cola.consultar_por_id(ids["otro"])["error"] == (
        "Se interrumpió (llevaba más de 30 min en curso). Revisa el resultado y vuelve a intentar.")


def _gasto_de_crear_video(base_temporal, monkeypatch, tmp_path, idioma_proyecto):
    """Crear (video) por worker.ejecutar, como en producción: sin sonido y con
    una música cuya mezcla falla, para que el `detalle` lleve todas sus partes."""
    import creative_flow as cf
    import gastos
    import tareas.flowplus as fp
    import worker
    from tests.test_tareas_flowplus import _sesion_lista_para_generar
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: idioma_proyecto)
    cid = _sesion_lista_para_generar(cf, monkeypatch, fp, tmp_path, con_sonido=False, musica_estilo="lujo")
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", lambda *a, **k: "https://prov/v.mp4")
    monkeypatch.setattr(fp.musica, "obtener_pista",
                        lambda estilo, segundos, carpeta_cache=None, on_progreso=None:
                            ({"archivo": "/tmp/p.wav", "url": "https://r2/musica/lujo_15.wav", "estilo": estilo,
                              "generada": True}, 0.02))
    monkeypatch.setattr(fp.cortes, "duracion", lambda p: 5.0)

    def _mezclar_roto(video_in, pista, salida, duracion_s, volumenes=None):
        raise RuntimeError("ffmpeg murió")
    monkeypatch.setattr(fp.mezcla, "mezclar_musica", _mezclar_roto)
    monkeypatch.setattr(fp.r2_uploader, "upload_video", lambda local, key: "https://r2/" + key)
    worker.ejecutar({"id": 5, "tipo": "flowplus_video", "cliente": "acme", "job_id": "j1",
                     "payload": {"cliente": "acme", "cf_id": cid}})
    return gastos.historial("acme")[0]["detalle"]


def test_gasto_de_un_video_de_crear_en_el_idioma_del_proyecto(base_temporal, monkeypatch, tmp_path):
    assert _gasto_de_crear_video(base_temporal, monkeypatch, tmp_path, "en") == (
        "kling_o3_pro · 5 s · no sound + music lujo (mix failed; the track was already charged)")


def test_gasto_de_un_video_de_crear_en_espanol_no_cambia(base_temporal, monkeypatch, tmp_path):
    assert _gasto_de_crear_video(base_temporal, monkeypatch, tmp_path, "es") == (
        "kling_o3_pro · 5 s · sin sonido + música lujo (falló la mezcla; la pista ya se cobró)")


def _gasto_de_crear_imagen(base_temporal, monkeypatch, tmp_path, idioma_proyecto):
    import creative_flow as cf
    import gastos
    import tareas.flowplus as fp
    import worker
    from tests.test_tareas_flowplus import _Resp
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: idioma_proyecto)
    monkeypatch.setattr(fp, "BASE_DIR", str(tmp_path))
    cid = cf.crear("acme", [], [], [], "posa", 5, "", "A", referencias_urls=["https://x/1.png", "https://x/2.png"])
    cf.actualizar("acme", cid, estado="video_generando", tipo="imagen", modelo="seedream_v5_pro", prompt_relleno="P")
    monkeypatch.setattr(fp.flowplus_modelos, "generar_imagen", lambda *a, **k: "https://prov/i.png")
    monkeypatch.setattr(fp.flowplus_modelos, "estimate_imagen", lambda m, n_referencias=1: {"credits": 2, "usd": 0.093})
    monkeypatch.setattr(fp.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(fp.r2_uploader, "upload_image", lambda local, key: "https://r2/" + key)
    monkeypatch.setattr(fp.bitacora, "registrar", lambda *a, **k: None)
    worker.ejecutar({"id": 3, "tipo": "flowplus_imagen", "cliente": "acme", "job_id": "j",
                     "payload": {"cliente": "acme", "cf_id": cid}})
    return gastos.historial("acme")[0]["detalle"]


def test_gasto_de_una_imagen_de_crear_en_el_idioma_del_proyecto(base_temporal, monkeypatch, tmp_path):
    assert _gasto_de_crear_imagen(base_temporal, monkeypatch, tmp_path, "en") == "seedream_v5_pro · 2 reference(s)"
    assert _gasto_de_crear_imagen(base_temporal, monkeypatch, tmp_path, "es") == "seedream_v5_pro · 2 referencia(s)"


def test_error_del_proveedor_en_el_idioma_ambiente():
    """wavespeed_common: el texto de la excepción se guarda (tarjeta de Crear,
    mensaje de la tarea); en el worker sale en el idioma del proyecto y, fuera
    de toda app, idéntico al español de siempre."""
    from providers import wavespeed_common as ws
    error = ws.ErrorProveedor("Kling O3 Pro", "failed", detalle="boom", codigo=500, prediction_id="p1")
    assert str(error) == "Kling O3 Pro no pudo generar: boom (código 500) · predicción p1"
    assert str(ws.EsperaAgotada("Wan 3.0", "p2", 1200)) == (
        "Se agotó el tiempo esperando el resultado de Wan 3.0 (20 min; predicción p2).")
    with idiomas.en_idioma("en"):
        assert str(ws.ErrorProveedor("Kling O3 Pro", "failed", detalle="boom", codigo=500, prediction_id="p1")) == (
            "Kling O3 Pro couldn't generate: boom (code 500) · prediction p1")
        assert str(ws.EsperaInterrumpida("Wan 3.0", "p3", 60)) == (
            "Stopped waiting for Wan 3.0 because the worker is restarting (prediction p3); it resumes on its own.")
