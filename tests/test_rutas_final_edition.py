"""Rutas de Final Edition en dashboard (preparar guion, guardar guion,
producir finales, descartar) + `_creative_flow_items` y la plantilla de la
pestaña Final edition (`_tab_final.html`; hasta 2026-09-27 todo esto vivía en
el detalle de Crear). Las rutas solo validan y encolan: `trabajos.encolar` se
captura."""
import os
import re

import pytest

GUION_BASE = {
    "idioma": "es", "pais": "CO", "moneda": None, "precio_texto": None,
    "bloques": [
        {"rol": "hook", "texto_pantalla": "Hola", "texto_voz": "Hola a todos", "inicio_s": 0, "fin_s": 1.5},
        {"rol": "problema", "texto_pantalla": "Duele", "texto_voz": "Te duelen los pies", "inicio_s": 1.5, "fin_s": 3},
        {"rol": "producto", "texto_pantalla": "Chanclas", "texto_voz": "Estas chanclas", "inicio_s": 3, "fin_s": 5},
        {"rol": "prueba", "texto_pantalla": "Miles", "texto_voz": "Miles las usan", "inicio_s": 5, "fin_s": 6.5},
        {"rol": "cta", "texto_pantalla": "Pide hoy", "texto_voz": "Pide las tuyas", "inicio_s": 6.5, "fin_s": 8},
    ],
}


def _cliente_admin(dashboard):
    dashboard.app.config["TESTING"] = True
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "admin"
        s["rol"] = "admin"
        s["cliente"] = None
    return c


def _sesion_video_listo(cliente="acme"):
    import creative_flow as cf
    cf_id = cf.crear(cliente, [], ["Chancla Rose"], [], "la persona camina", 8, "", "A")
    cf.actualizar(cliente, cf_id, estado="video_listo", video_url="https://r2/clon.mp4", enfoque="producto")
    return cf_id


def _capturar_encolar(monkeypatch, dashboard):
    llamadas = []

    def _encolar(job_id, tipo, payload, **kw):
        llamadas.append(dict(job_id=job_id, tipo=tipo, payload=payload, **kw))
        return True
    monkeypatch.setattr(dashboard.trabajos, "encolar", _encolar)
    return llamadas


def _flashes(c):
    with c.session_transaction() as s:
        return [m for _cat, m in s.get("_flashes", [])]


def _no_encolar(monkeypatch, dashboard):
    def _no(*a, **k):
        raise AssertionError("no debía encolar")
    monkeypatch.setattr(dashboard.trabajos, "encolar", _no)


# ---------- preparar guion ----------

def test_preparar_encola_final_guion(base_temporal, monkeypatch):
    import dashboard
    cf_id = _sesion_video_listo()
    llamadas = _capturar_encolar(monkeypatch, dashboard)
    c = _cliente_admin(dashboard)
    r = c.post(f"/cliente/acme/creative_flow/{cf_id}/final/preparar",
               data={"precio": "89900", "idioma_base": "es"})
    assert r.status_code == 302 and r.headers["Location"].endswith("#final")
    assert len(llamadas) == 1
    t = llamadas[0]
    assert t["tipo"] == "final_guion"
    assert t["job_id"] == f"acme__{cf_id}__final_guion"
    assert t["max_intentos"] == 2 and t["duracion_estimada"] == 25 and t["cliente"] == "acme"
    assert t["payload"] == {"cliente": "acme", "cf_id": cf_id,
                            "opciones": {"precio": 89900.0, "idioma_base": "es"}}


def test_preparar_sin_video_no_encola(base_temporal, monkeypatch):
    import creative_flow as cf
    import dashboard
    cf_id = cf.crear("acme", [], ["Chancla Rose"], [], "la persona camina", 8, "", "A")
    _no_encolar(monkeypatch, dashboard)
    c = _cliente_admin(dashboard)
    r = c.post(f"/cliente/acme/creative_flow/{cf_id}/final/preparar", data={})
    assert r.status_code == 302
    assert any("video listo" in m for m in _flashes(c))


# ---------- producir ----------

def test_producir_sin_guion_no_encola(base_temporal, monkeypatch):
    import dashboard
    cf_id = _sesion_video_listo()
    _no_encolar(monkeypatch, dashboard)
    c = _cliente_admin(dashboard)
    r = c.post(f"/cliente/acme/creative_flow/{cf_id}/final/producir",
               data={"destinos": ["es_CO"], "voz": "Rachel", "estilo_musica": "energetico"})
    assert r.status_code == 302
    assert any("guion" in m.lower() for m in _flashes(c))


def test_producir_encola_una_tarea_por_destino(base_temporal, monkeypatch):
    import creative_flow as cf
    import dashboard
    from final_edition import ETAPAS_FINAL
    cf_id = _sesion_video_listo()
    cf.guardar_guion_base("acme", cf_id, GUION_BASE)
    llamadas = _capturar_encolar(monkeypatch, dashboard)
    c = _cliente_admin(dashboard)
    r = c.post(f"/cliente/acme/creative_flow/{cf_id}/final/producir", data={
        "destinos": ["es_CO", "en_US"], "voz": "Daniel", "estilo_musica": "lujo",
        "con_voz": "si", "precio": "89900", "con_sonido": "si", "mezcla": "ambiente_protagonista",
    })
    assert r.status_code == 302
    assert [t["tipo"] for t in llamadas] == ["final_producir", "final_producir"]
    assert [t["job_id"] for t in llamadas] == [f"acme__{cf_id}__es_CO__final", f"acme__{cf_id}__en_US__final"]
    for t in llamadas:
        assert t["max_intentos"] == 1 and t["duracion_estimada"] == 150 and t["cliente"] == "acme"
        assert list(t["etapas"]) == list(ETAPAS_FINAL)
    p0, p1 = llamadas[0]["payload"], llamadas[1]["payload"]
    assert (p0["cliente"], p0["cf_id"], p0["idioma"], p0["pais"]) == ("acme", cf_id, "es", "CO")
    assert (p1["idioma"], p1["pais"]) == ("en", "US")
    assert p0["opciones"] == {"voz": "Daniel", "estilo_musica": "lujo", "con_voz": True, "con_musica": False,
                              "precio": 89900.0, "precios": {}, "idioma_base": "es",
                              "con_sonido": True, "sonido": "nativo", "mezcla": "ambiente_protagonista"}
    assert any("2 finales" in m for m in _flashes(c))
    # Las filas finales existen en `generando` desde que se encola, no desde
    # que el worker arranca: la cuadrícula las muestra de una con su barra.
    filas = cf.finales("acme", cf_id)
    assert [(f["idioma"], f["pais"], f["estado"]) for f in filas] == [("es", "CO", "generando"), ("en", "US", "generando")]


def test_producir_precio_por_destino_no_se_convierte(base_temporal, monkeypatch):
    """I1: dos destinos con monedas distintas (CO/COP y US/USD) reciben cada
    uno el precio que se escribió en SU campo, no el precio del otro país
    formateado con su símbolo (el bug original)."""
    import creative_flow as cf
    import dashboard
    cf_id = _sesion_video_listo()
    cf.guardar_guion_base("acme", cf_id, GUION_BASE)  # base es_CO
    llamadas = _capturar_encolar(monkeypatch, dashboard)
    c = _cliente_admin(dashboard)
    r = c.post(f"/cliente/acme/creative_flow/{cf_id}/final/producir", data={
        "destinos": ["es_CO", "en_US"], "voz": "Rachel", "estilo_musica": "energetico",
        "precio_es_CO": "89900", "precio_en_US": "24.99",
    })
    assert r.status_code == 302
    p_co, p_us = llamadas[0]["payload"], llamadas[1]["payload"]
    assert p_co["opciones"]["precios"] == {"es_CO": 89900.0, "en_US": 24.99}
    assert p_us["opciones"]["precios"] == {"es_CO": 89900.0, "en_US": 24.99}


def test_producir_destino_sin_precio_propio_queda_none(base_temporal, monkeypatch):
    """Un destino sin su propio campo de precio no hereda el precio de otro
    país ni el 'Precio base' cuando su país no es el país base del guion."""
    import creative_flow as cf
    import dashboard
    cf_id = _sesion_video_listo()
    cf.guardar_guion_base("acme", cf_id, GUION_BASE)  # base es_CO
    llamadas = _capturar_encolar(monkeypatch, dashboard)
    c = _cliente_admin(dashboard)
    c.post(f"/cliente/acme/creative_flow/{cf_id}/final/producir", data={
        "destinos": ["es_CO", "en_US"], "voz": "Rachel", "estilo_musica": "energetico",
        "precio": "89900",  # solo el precio base; en_US no manda precio_en_US
    })
    p_co = llamadas[0]["payload"]
    assert p_co["opciones"]["precios"] == {}  # campos vacíos no se mandan
    assert p_co["opciones"]["precio"] == 89900.0


def test_producir_destino_en_curso_no_reinicia_la_fila(base_temporal, monkeypatch):
    import creative_flow as cf
    import dashboard
    cf_id = _sesion_video_listo()
    cf.guardar_guion_base("acme", cf_id, GUION_BASE)
    fid = cf.crear_final("acme", cf_id, "es", "CO")
    cf.actualizar_final("acme", fid, estado="listo", url_video="https://r2/f.mp4")
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda jid: jid == f"acme__{cf_id}__es_CO__final")
    llamadas = _capturar_encolar(monkeypatch, dashboard)
    c = _cliente_admin(dashboard)
    c.post(f"/cliente/acme/creative_flow/{cf_id}/final/producir",
           data={"destinos": ["es_CO", "en_US"], "voz": "Rachel", "estilo_musica": "energetico"})
    assert [t["job_id"] for t in llamadas] == [f"acme__{cf_id}__en_US__final"]
    assert cf.final_por_legado("acme", fid)["estado"] == "listo"  # la fila viva no se tocó
    assert cf.final_por_legado("acme", f"{cf_id}__en_US")["estado"] == "generando"
    assert any("1 finales" in m for m in _flashes(c))


def test_producir_rechaza_destinos_invalidos(base_temporal, monkeypatch):
    import creative_flow as cf
    import dashboard
    cf_id = _sesion_video_listo()
    cf.guardar_guion_base("acme", cf_id, GUION_BASE)
    _no_encolar(monkeypatch, dashboard)
    c = _cliente_admin(dashboard)
    r = c.post(f"/cliente/acme/creative_flow/{cf_id}/final/producir",
               data={"destinos": ["fr_FR"], "voz": "Rachel", "estilo_musica": "energetico"})
    assert r.status_code == 302
    assert any("destino" in m.lower() for m in _flashes(c))

    c2 = _cliente_admin(dashboard)
    r = c2.post(f"/cliente/acme/creative_flow/{cf_id}/final/producir",
                data={"voz": "Rachel", "estilo_musica": "energetico"})
    assert r.status_code == 302
    assert any("destino" in m.lower() for m in _flashes(c2))


def test_producir_ya_en_curso_avisa(base_temporal, monkeypatch):
    import creative_flow as cf
    import dashboard
    cf_id = _sesion_video_listo()
    cf.guardar_guion_base("acme", cf_id, GUION_BASE)
    monkeypatch.setattr(dashboard.trabajos, "encolar", lambda *a, **k: False)
    c = _cliente_admin(dashboard)
    c.post(f"/cliente/acme/creative_flow/{cf_id}/final/producir",
           data={"destinos": ["es_CO"], "voz": "Rachel", "estilo_musica": "energetico", "con_voz": "si", "con_musica": "si"})
    assert any("Ya se estaban produciendo" in m for m in _flashes(c))


def test_producir_voz_o_estilo_invalidos_usan_defecto(base_temporal, monkeypatch):
    import creative_flow as cf
    import dashboard
    cf_id = _sesion_video_listo()
    cf.guardar_guion_base("acme", cf_id, GUION_BASE)
    llamadas = _capturar_encolar(monkeypatch, dashboard)
    c = _cliente_admin(dashboard)
    c.post(f"/cliente/acme/creative_flow/{cf_id}/final/producir",
           data={"destinos": ["pt_BR"], "voz": "NoExiste", "estilo_musica": "rarísimo", "con_voz": "si", "con_musica": "si",
                 "mezcla": "x"})
    o = llamadas[0]["payload"]["opciones"]
    assert o["voz"] == "Rachel" and o["estilo_musica"] == "energetico" and o["precio"] is None
    # Sin `con_sonido` en el form el check está desmarcado; un preset inválido cae al de defecto.
    assert o["con_sonido"] is False and o["mezcla"] == "equilibrada" and o["sonido"] == "nativo"


# ---------- guardar guion ----------

def _form_guion(guion, **cambios):
    data = {}
    for i, b in enumerate(guion["bloques"]):
        data[f"bloque_{i}_pantalla"] = b["texto_pantalla"]
        data[f"bloque_{i}_voz"] = b["texto_voz"]
    data.update(cambios)
    return data


def test_guardar_guion_bloque_vacio_no_guarda(base_temporal, monkeypatch):
    import creative_flow as cf
    import dashboard
    cf_id = _sesion_video_listo()
    cf.guardar_guion_base("acme", cf_id, GUION_BASE)
    c = _cliente_admin(dashboard)
    r = c.post(f"/cliente/acme/creative_flow/{cf_id}/final/guion", data=_form_guion(GUION_BASE, bloque_2_pantalla="  "))
    assert r.status_code == 302
    assert cf.guion_base("acme", cf_id) == GUION_BASE
    assert any("bloque 3" in m.lower() and "texto_pantalla" in m for m in _flashes(c))


def test_guardar_guion_actualiza_textos_y_conserva_tiempos(base_temporal):
    import creative_flow as cf
    import dashboard
    cf_id = _sesion_video_listo()
    cf.guardar_guion_base("acme", cf_id, GUION_BASE)
    c = _cliente_admin(dashboard)
    c.post(f"/cliente/acme/creative_flow/{cf_id}/final/guion",
           data=_form_guion(GUION_BASE, bloque_0_pantalla="¡Hola!", bloque_4_voz="Pide las tuyas hoy"))
    g = cf.guion_base("acme", cf_id)
    assert g["bloques"][0]["texto_pantalla"] == "¡Hola!"
    assert g["bloques"][4]["texto_voz"] == "Pide las tuyas hoy"
    assert g["bloques"][4]["fin_s"] == 8 and g["bloques"][2]["inicio_s"] == 3
    assert g["idioma"] == "es" and g["pais"] == "CO"
    assert any("Guion guardado" in m for m in _flashes(c))


def test_guardar_guion_sin_base_avisa(base_temporal):
    import dashboard
    cf_id = _sesion_video_listo()
    c = _cliente_admin(dashboard)
    r = c.post(f"/cliente/acme/creative_flow/{cf_id}/final/guion", data=_form_guion(GUION_BASE))
    assert r.status_code == 302
    assert any("guion" in m.lower() for m in _flashes(c))


# ---------- descartar ----------

def test_descartar_final_la_elimina(base_temporal):
    import creative_flow as cf
    import dashboard
    cf_id = _sesion_video_listo()
    fid = cf.crear_final("acme", cf_id, "es", "CO")
    c = _cliente_admin(dashboard)
    r = c.post(f"/cliente/acme/creative_flow/{cf_id}/final/{fid}/descartar")
    assert r.status_code == 302
    assert cf.final_por_legado("acme", fid) is None
    assert cf.cargar("acme").get(cf_id)  # la clon sigue


def test_descartar_final_en_curso_no_la_borra(base_temporal, monkeypatch):
    import creative_flow as cf
    import dashboard
    cf_id = _sesion_video_listo()
    fid = cf.crear_final("acme", cf_id, "es", "CO")
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda jid: jid == f"acme__{cf_id}__es_CO__final")
    c = _cliente_admin(dashboard)
    r = c.post(f"/cliente/acme/creative_flow/{cf_id}/final/{fid}/descartar")
    assert r.status_code == 302
    assert cf.final_por_legado("acme", fid) is not None
    assert any("se está produciendo" in m for m in _flashes(c))


# ---------- items y plantilla ----------

def test_creative_flow_items_incluye_guion_finales_y_trabajos(base_temporal, monkeypatch):
    import creative_flow as cf
    import dashboard
    cf_id = _sesion_video_listo()
    cf.guardar_guion_base("acme", cf_id, GUION_BASE)
    fid = cf.crear_final("acme", cf_id, "es", "CO")
    en_curso = {f"acme__{cf_id}__es_CO__final", f"acme__{cf_id}__final_guion"}
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda jid: jid in en_curso)
    items = dashboard._creative_flow_items("acme")
    item = [i for i in items if i["id"] == cf_id][0]
    assert item["guion_base"] == GUION_BASE
    assert item["trabajo_guion"] == {"job_id": f"acme__{cf_id}__final_guion"}
    assert item["trabajo"] is None
    assert len(item["finales"]) == 1
    f = item["finales"][0]
    assert f["id"] == fid and f["estado"] == "generando"
    assert f["trabajo"] == {"job_id": f"acme__{cf_id}__es_CO__final"}


def test_ver_cliente_pasa_contexto_fe(base_temporal, monkeypatch):
    import dashboard
    from final_edition import tipos
    from providers import fal_audio
    capturado = {}

    def _render(nombre, **ctx):
        capturado.update(ctx)
        return "ok"
    monkeypatch.setattr(dashboard, "render_template", _render)
    c = _cliente_admin(dashboard)
    assert c.get("/cliente/acme").status_code == 200
    assert capturado["paises_fe"] is tipos.PAISES
    assert capturado["voces_fe"] is fal_audio.VOCES
    assert capturado["estilos_fe"] == list(tipos.ESTILOS_MUSICA)
    from final_edition import mezcla
    assert capturado["presets_mezcla"] == list(mezcla.PRESETS)


def _entorno_plantilla():
    import jinja2
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    import gastos
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(os.path.join(raiz, "templates")),
                             extensions=["jinja2.ext.i18n"])
    env.install_null_translations(newstyle=True)  # _()/gettext/ngettext de mentiras: devuelven el español tal cual
    env.globals["url_for"] = lambda *a, **k: "#"
    import doctrina
    env.globals.update(doctrina.globales_plantilla())   # editor del ángulo (doctrina, bloque 2)
    env.filters["usd"] = gastos.formatear   # mismo filtro que registra dashboard (costos «US$ 0,07»)
    env.filters["traducir"] = lambda x: x   # idiomas.traducir necesita un app de Flask-Babel; acá no hay ninguno
    return env


def _contexto_minimo(items):
    from final_edition import tipos
    from providers import fal_audio
    return dict(
        creative_flow_items=items, cliente="acme", logos=[],
        modelos_flowplus_video={}, modelos_flowplus_imagen={}, preferencias_flowplus={},
        preferencias_sonido={"con_sonido": True, "musica_al_crear": ""},
        fp_prefill=None, activos_por_categoria={}, categorias={}, productos=[],
        referencias_bandeja=[], trabajo_link=None, capacidades_meta={},
        paises_fe=tipos.PAISES, voces_fe=fal_audio.VOCES, estilos_fe=list(tipos.ESTILOS_MUSICA),
        nombres_estilo_musica=tipos.NOMBRES_ESTILO_MUSICA,
        presets_mezcla=["equilibrada", "voz_protagonista", "ambiente_protagonista"],
        duraciones_crear=(5, 8, 10, 12, 15, 20, 25, 30), formatos_nombres={"9:16": "Vertical 9:16"},
        ediciones_por_cf={},
    )


def _item_video_listo(**extra):
    item = {
        "id": "cf_1", "estado": "video_listo", "tipo": "video", "video_url": "https://r2/clon.mp4",
        "duracion_objetivo": 8, "aspect_ratio": "9:16", "modelo_nombre": "Wan 3.0", "accion_central": "camina",
        "referencias": [], "referencias_urls": [], "trabajo": None, "usd": 0.8, "enfoque_nombre": "Producto",
        "guion_base": None, "finales": [], "trabajo_guion": None, "capas": {},
    }
    item.update(extra)
    return item


# Tarjetas ligeras (spec 2026-09-28): la pestaña pinta las tarjetas (sin el
# <template> del detalle) y el detalle lo responde su ruta al abrir la
# tarjeta. Acá se renderizan las dos piezas por separado, con el mismo
# contexto que reciben en dashboard.
def _listas(items):
    """Lo que dashboard._listas_crear_final le da a las pestañas."""
    videos = [i for i in items if i.get("estado") == "video_listo" and (i.get("tipo") or "video") != "imagen"]
    finales = [(i, f) for i in items for f in (i.get("finales") or [])]
    return dict(crear=items, crear_total=len(items), final_videos=videos, final_videos_total=len(videos),
                finales=finales, finales_total=len(finales))


def _tab_final(env, items):
    """La pestaña Final edition: tarjetas + JS del modal."""
    return env.get_template("_tab_final.html").render(**_contexto_minimo(items), **_listas(items))


def _detalle_video_fe(env, item):
    """Lo que responde fe_detalle_video para esa pieza (guion, «Producir finales», editor)."""
    return env.get_template("_final_detalle_respuesta.html").render(**_contexto_minimo([item]), item=item, f=None)


def _tab_crear(env, items):
    """La pestaña Crear: formulario + tarjetas + JS del modal."""
    return env.get_template("_tab_creativeflowplus.html").render(**_contexto_minimo(items), **_listas(items))


def _detalle_crear(env, item):
    """Lo que responde cf_detalle para esa pieza."""
    return env.get_template("_crear_detalle_respuesta.html").render(**_contexto_minimo([item]), item=item)


def test_plantilla_sin_guion_ofrece_preparar():
    env = _entorno_plantilla()
    item = _item_video_listo()
    html = _detalle_video_fe(env, item)
    assert "Final edition" in _tab_final(env, [item]) and "Final edition" in html
    assert "Preparar guion con IA" in html and 'name="precio"' in html
    assert "Guardar guion" not in html and "trabajo-acme__cf_1__final_guion" not in html
    assert "trabajo-acme__cf_1__final_guion" not in _tab_final(env, [item])

    # Con el guion en curso: barra de progreso en la TARJETA (el detalle llega
    # por fetch, así que el sondeo arranca desde data-poll-job en la página,
    # sin <script> embebido), y sin el botón (no se puede encolar dos veces).
    item = _item_video_listo(trabajo_guion={"job_id": "acme__cf_1__final_guion"})
    tarjeta = _tab_final(env, [item])
    assert 'data-poll-job="acme__cf_1__final_guion"' in tarjeta and "<script>iniciarPolling" not in tarjeta
    assert 'id="trabajo-acme__cf_1__final_guion"' in tarjeta and "Escribiendo el guion…" in tarjeta
    detalle = _detalle_video_fe(env, item)
    assert "Se está escribiendo el guion…" in detalle and "barra-progreso" not in detalle
    assert "Preparar guion con IA" not in detalle
    assert "Volver a escribir con IA" not in detalle


def test_plantilla_con_guion_ofrece_reescribir():
    env = _entorno_plantilla()
    html = _detalle_video_fe(env, _item_video_listo(guion_base=GUION_BASE))
    assert "Volver a escribir con IA" in html and "Volver a escribir el guion con IA" in html  # botón + confirm
    assert 'name="idioma_base" value="es"' in html
    assert "reescribiendo" not in html
    # Mientras se reescribe no se ofrece el botón; la barra va en la tarjeta (data-poll-job).
    item = _item_video_listo(guion_base=GUION_BASE, trabajo_guion={"job_id": "acme__cf_1__final_guion"})
    assert "Volver a escribir con IA" not in _detalle_video_fe(env, item)
    assert 'data-poll-job="acme__cf_1__final_guion"' in _tab_final(env, [item])


def test_plantilla_con_guion_y_finales_renderiza():
    env = _entorno_plantilla()
    finales = [
        {"id": "cf_1__es_CO", "idioma": "es", "pais": "CO", "estado": "listo", "video_url": "https://r2/f.mp4",
         "url_miniatura": "https://r2/f.png", "duracion_s": 8.0, "costo_usd": 0.12,
         "capas": {"voz": {"estado": "ok", "proveedor": "fal/elevenlabs", "costo_usd": 0.05},
                   "musica": {"estado": "error", "error": "timeout"}}, "guion": None, "error": None, "trabajo": None},
        {"id": "cf_1__en_US", "idioma": "en", "pais": "US", "estado": "generando", "video_url": None,
         "url_miniatura": None, "duracion_s": None, "costo_usd": None, "capas": {}, "guion": None, "error": None,
         "trabajo": {"job_id": "acme__cf_1__en_US__final"}},
        {"id": "cf_1__pt_BR", "idioma": "pt", "pais": "BR", "estado": "error", "video_url": None,
         "url_miniatura": None, "duracion_s": None, "costo_usd": None, "capas": {}, "guion": None,
         "error": "ffmpeg murió", "trabajo": None},
    ]
    item = _item_video_listo(guion_base=GUION_BASE, finales=finales)
    html = _detalle_video_fe(env, item)        # el guion y «Producir finales» llegan por fetch
    tarjetas = _tab_final(env, [item])         # la clon y sus finales, en las cuadrículas
    assert "Guardar guion" in html and 'name="bloque_4_voz"' in html
    assert "Pide las tuyas" in html
    assert 'name="destinos" value="es_CO"' in html and 'name="destinos" value="en_US"' in html
    assert "Producir" in html
    assert "🇨🇴" in tarjetas and "🇺🇸" in tarjetas and "🇧🇷" in tarjetas
    assert "trabajo-acme__cf_1__en_US__final" in tarjetas
    assert "generado-badge" in tarjetas
    assert "ffmpeg murió" in html
    # la clon + 3 finales en las cuadrículas (el selector del JS no cuenta)
    assert len(re.findall(r'data-cf="[\w-]+"', tarjetas)) == 4
    assert "Final de Producto" in tarjetas
    # I4: es_CO ya tiene una final -> hint + checkbox marcado para confirm(); en_US y pt_BR no.
    assert "ya producida — se reemplaza" in html
    assert 'value="es_CO" data-ya-producida="1"' in html
    assert 'value="en_US"' in html and 'value="en_US" data-ya-producida="1"' not in html
    assert "feConfirmarReemplazo" in html
    # precio por destino (I1): un input propio por país, con su moneda.
    assert 'name="precio_es_CO"' in html and 'data-moneda="COP"' in html
    assert 'name="precio_en_US"' in html and 'data-moneda="USD"' in html
    # S2: capa sonido — check marcado (el clon no dice que sea mudo) y presets de mezcla.
    assert 'name="con_sonido" value="si" checked' in html and "con sonido de la escena" in html
    assert 'name="mezcla"' in html and 'value="voz_protagonista"' in html and "voz protagonista" in html
    assert "este clon no trae sonido" not in html


def test_plantilla_clon_mudo_desmarca_el_sonido():
    """Si Crear anotó que el clon vino sin pista, el check «con sonido» sale
    desmarcado y se avisa; no se ofrece pedir lo que no existe."""
    env = _entorno_plantilla()
    html = _detalle_video_fe(env, _item_video_listo(guion_base=GUION_BASE,
                                                    capas={"sonido": {"proveedor": "wan3", "estado": "ausente"}}))
    assert 'name="con_sonido" value="si" checked' not in html and 'name="con_sonido" value="si"' in html
    assert "este clon no trae sonido" in html


def test_plantilla_imagen_no_muestra_final_edition():
    """Una imagen no entra a Final edition: la pestaña no la lista y Crear no
    ofrece «Llevar a final edition» (un video listo sí)."""
    env = _entorno_plantilla()
    imagen = _item_video_listo(tipo="imagen")
    html = _tab_final(env, [imagen])
    assert 'data-cf="cf_1"' not in html and "Preparar guion con IA" not in html
    assert "Videos listos (0)" in html
    crear = _tab_crear(env, [imagen]) + _detalle_crear(env, imagen)    # la tarjeta y su detalle (por fetch)
    marcado = re.sub(r"<script>.*?</script>", "", crear, flags=re.S)   # lo que se ve, sin los comentarios del JS
    assert "Llevar a final edition" not in marcado and "Final edition" not in marcado
    video = _item_video_listo()
    crear = _detalle_crear(env, video)
    assert 'href="#final?cf=cf_1"' in crear and "Llevar a final edition" in crear
    assert "Preparar guion con IA" not in crear and "Preparar guion con IA" not in _tab_crear(env, [video])


def test_plantilla_muestra_el_editor_del_angulo_de_la_pieza():
    """Doctrina, bloque 2 (§3.1): el ángulo de la pieza se ve y se edita antes del guion."""
    env = _entorno_plantilla()
    angulo = {"consciencia": "consciente_del_problema", "lead": "problema_solucion", "gancho": "¿Pies fríos en casa?",
              "promesa": "pies calientes", "faltantes": ["error: campo_faltante:audiencia", "falta el precio"]}
    html = _detalle_video_fe(env, _item_video_listo(angulo=angulo))
    assert 'class="angulo-editor"' in html and "Consciente del problema · problema-solución · “¿Pies fríos en casa?”" in html
    assert "falta el precio" in html and "campo_faltante" not in html
    vacio = _detalle_video_fe(env, _item_video_listo())
    assert "Todavía no tiene ángulo: se decide al preparar el guion" in vacio
    # Se mudó con la sección Final edition: Crear ya no lo muestra (ni lo
    # inicializa), ni en la pestaña ni en el detalle de la pieza.
    item = _item_video_listo(angulo=angulo)
    crear = _tab_crear(env, [item]) + _detalle_crear(env, item)
    assert 'class="angulo-editor"' not in crear and "iniciarEditoresAngulo" not in crear


def test_plantilla_muestra_la_cifra_no_verificada_antes_de_guardar():
    """Doctrina, bloque 2 (revisión final #2): §11 dice «la interfaz lo dice»
    — un `error: cifra_no_verificada:47` guardado se ve como aviso apenas se
    abre el editor, no solo después de un guardado."""
    env = _entorno_plantilla()
    angulo = {"consciencia": "consciente_del_problema", "lead": "problema_solucion", "gancho": "¿Pies fríos en casa?",
              "promesa": "pies calientes", "faltantes": ["error: cifra_no_verificada:47", "falta el precio"]}
    html = _detalle_video_fe(env, _item_video_listo(angulo=angulo))
    assert "La cifra «47» no está en los datos del producto." in html
    assert "cifra_no_verificada" not in html      # se muestra el mensaje, nunca el código


def test_editor_del_angulo_se_inicializa_al_abrir_la_pieza():
    """Doctrina, bloque 2 (revisión final, bug crítico #1): el editor llega
    dentro del detalle que el modal pide por fetch, e `iniciarEditoresAngulo()`
    solo corre sobre `document` al cargar la página — nunca vería ese
    contenido, así que la pestaña lo llama sobre lo recién insertado
    (`alInsertar` de abrirDetalleRemoto); sin esto no guarda nada."""
    env = _entorno_plantilla()
    env.globals["url_for"] = lambda ruta, **k: "/static/" + k["filename"] if ruta == "static" else "#"
    html = _tab_final(env, [_item_video_listo()])
    assert "window.iniciarEditoresAngulo(c)" in html
    assert "abrirDetalleRemoto(modal, cuerpo, card.dataset.detalle, alInsertar)" in html
    assert 'src="/static/angulo.js"' in html      # la pestaña carga su propio script
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(raiz, "static", "angulo.js")) as f:
        js = f.read()
    assert ".angulo-editor" in js
    # Tras guardar, el editor fija en el DOM el valor elegido (atributos
    # `selected`/`value` y el texto): un segundo guardado parte del valor
    # real, no del que vino del servidor. (El detalle se vuelve a pedir al
    # abrir, así que la próxima apertura ya trae lo guardado.)
    assert "setAttribute('selected'" in js and "removeAttribute('selected')" in js
    assert "setAttribute('value'" in js and "textContent = valor" in js


def test_guardar_el_angulo_de_una_pieza(base_temporal, monkeypatch):
    import creative_flow
    import dashboard
    c = _cliente_admin(dashboard)
    cf_id = creative_flow.crear("acme", [], ["Chancla Rose"], [], "camina", 8, "", "A")
    r = c.post(f"/cliente/acme/creative_flow/{cf_id}/angulo",
               json={"angulo": {"audiencia": "quien tiene pies fríos", "consciencia": "consciente_del_problema",
                                "sofisticacion": "2", "deseo": "pies calientes", "promesa": "pies calientes en casa",
                                "lead": "problema_solucion", "gancho": "¿Pies fríos?", "pruebas": []}})
    assert r.status_code == 200 and r.get_json()["ok"] and r.get_json()["avisos"] == []
    ang = creative_flow.cargar("acme")[cf_id]["angulo"]
    assert ang["gancho"] == "¿Pies fríos?" and ang["editado_en"]
    assert c.post("/cliente/acme/creative_flow/nada/angulo", json={"angulo": {}}).status_code == 404


# ------------------------------------------ doctrina, bloque 3: revisión ---

REV_MEJORAR = {"video_url": "https://r2/clon.mp4", "resumen": "Muestra el producto antes.",
               "puntos": [{"n": n, "estado": "pasa", "detalle": "", "donde": ""} for n in range(1, 13)],
               "reglas": [{"n": 5, "codigo": "sin_mecanismo", "texto": "Falta el mecanismo.", "donde": "angulo"}]}
REV_MEJORAR["puntos"][5] = {"n": 6, "estado": "mejorar", "detalle": "El producto aparece hasta el segundo 5.",
                            "donde": "segundo 5"}
REV_MEJORAR["puntos"][9] = {"n": 10, "estado": "no_aplica", "detalle": "Sin guía de marca.", "donde": ""}


def _item_revisable(**extra):
    base = dict(revision=None, revision_estado="sin_revisar", revision_n=0, reglas=[], trabajo_revision=None,
                precio_revision="US$ 0,05 aprox.")
    base.update(extra)
    return _item_video_listo(**base)


def test_plantilla_revision_sin_revisar_muestra_las_reglas_y_el_boton():
    env = _entorno_plantilla()
    reglas = [{"n": 4, "codigo": "cifra_no_verificada", "texto": "La cifra «1200» del caption no está.", "donde": "caption"}]
    item = _item_revisable(reglas=reglas)
    html = _detalle_crear(env, item)          # la revisión va en el detalle (por fetch)
    assert "Revisión de la doctrina" in html and "Revisión rápida (gratis)" in html
    assert "La cifra «1200» del caption no está." in html and "#base" in html
    assert "Revisar con la doctrina (US$ 0,05 aprox.)" in html and "Doctrina:" not in html
    assert "Doctrina:" not in _tab_crear(env, [item])      # sin revisión, la tarjeta no lleva etiqueta
    sin = _detalle_crear(env, _item_revisable())
    assert "Las reglas no encontraron nada." in sin


def test_plantilla_revision_con_claude_agrupa_y_pone_la_etiqueta():
    env = _entorno_plantilla()
    item = _item_revisable(revision=REV_MEJORAR, revision_estado="mejorar", revision_n=2)
    html = _detalle_crear(env, item)
    assert "Muestra el producto antes." in html
    assert "<strong>Visuales</strong>: El producto aparece hasta el segundo 5." in html and "#video" in html
    assert "Pasa (10)" in html and "No aplica (1)" in html
    assert "Revisar de nuevo (US$ 0,05 aprox.)" in html
    assert "Doctrina: 2 por mejorar" in _tab_crear(env, [item])     # la etiqueta va en la tarjeta
    bien = _item_revisable(revision=dict(REV_MEJORAR, reglas=[], puntos=[dict(p, estado="pasa") for p in REV_MEJORAR["puntos"]]),
                           revision_estado="bien")
    assert "Doctrina: bien" in _tab_crear(env, [bien])
    assert "Claude no encontró nada para mejorar." in _detalle_crear(env, bien)


def test_plantilla_revision_vieja_error_y_en_curso():
    env = _entorno_plantilla()
    item = _item_revisable(revision=REV_MEJORAR, revision_estado="vieja")
    vieja = _detalle_crear(env, item)
    assert "es de una versión anterior" in vieja and "Revisar de nuevo" in vieja
    assert "Doctrina:" not in vieja and "Doctrina:" not in _tab_crear(env, [item])
    error = _detalle_crear(env, _item_revisable(revision={"error": "Claude no devolvió JSON."}, revision_estado="error"))
    assert "no se pudo terminar: Claude no devolvió JSON." in error
    item = _item_revisable(trabajo_revision={"job_id": "acme__cf_1__revisar"})
    tarjeta = _tab_crear(env, [item])          # la barra va en la tarjeta, con data-poll-job
    assert 'id="trabajo-acme__cf_1__revisar"' in tarjeta and "Revisando con la doctrina…" in tarjeta
    assert 'data-poll-job="acme__cf_1__revisar"' in tarjeta and "<script>iniciarPolling" not in tarjeta
    curso = _detalle_crear(env, item)
    assert "Revisando la pieza…" in curso and "Revisar con la doctrina (" not in curso


def test_plantilla_muestra_el_error_junto_a_la_revision_buena():
    """Bloque 3, revisión final (I2): un fallo posterior no reemplaza la
    buena revisión guardada — las dos se muestran."""
    env = _entorno_plantilla()
    item = _item_revisable(revision=REV_MEJORAR, revision_estado="mejorar", revision_n=2,
                           revision_error={"error": "Claude no devolvió JSON.", "video_url": "https://r2/clon.mp4"})
    html = _detalle_crear(env, item)
    assert "Muestra el producto antes." in html                          # la buena sigue mostrándose
    assert "El último intento de revisión no se pudo terminar: Claude no devolvió JSON." in html
    # el error es de otro video (uno anterior a la última generación): no se muestra
    otro = _item_revisable(revision=REV_MEJORAR, revision_estado="mejorar", revision_n=2,
                           revision_error={"error": "x", "video_url": "https://r2/otro.mp4"})
    html2 = _detalle_crear(env, otro)
    assert "no se pudo terminar" not in html2


def test_items_de_crear_traen_la_revision_y_las_reglas(base_temporal, monkeypatch):
    import creative_flow
    import dashboard
    import final_edition
    monkeypatch.setattr(final_edition, "_producto", lambda cliente, entry, precio: {"nombre": "Chancla", "sofisticacion": 3})
    cf_id = _sesion_video_listo()
    creative_flow.actualizar("acme", cf_id, angulo={"promesa": "pies frescos", "gancho": "¿Calor?", "sofisticacion": 2},
                             revision_doctrina=dict(REV_MEJORAR, video_url="https://r2/clon.mp4"))
    item = next(i for i in dashboard._creative_flow_items("acme") if i["id"] == cf_id)
    assert item["revision_estado"] == "mejorar" and item["revision_n"] == 2
    assert [a["codigo"] for a in item["reglas"]] == ["sin_mecanismo"] and item["trabajo_revision"] is None
    assert item["precio_revision"].startswith("US$")
    otra = creative_flow.crear("acme", [], ["Chancla Rose"], [], "camina", 8, "", "A")
    sin = next(i for i in dashboard._creative_flow_items("acme") if i["id"] == otra)
    assert sin["revision_estado"] is None and sin["reglas"] == []


def test_creative_flow_items_trae_el_error_de_revision_aparte(base_temporal, monkeypatch):
    """Bloque 3, revisión final (I2): `revision_error` viaja aparte de
    `revision` (la buena, guardada, sigue disponible)."""
    import creative_flow
    import dashboard
    import final_edition
    monkeypatch.setattr(final_edition, "_producto", lambda cliente, entry, precio: {"nombre": "Chancla"})
    cf_id = _sesion_video_listo()
    error = {"error": "Claude no devolvió JSON.", "video_url": "https://r2/clon.mp4"}
    creative_flow.actualizar("acme", cf_id, revision_doctrina=dict(REV_MEJORAR, video_url="https://r2/clon.mp4"),
                             revision_doctrina_error=error)
    item = next(i for i in dashboard._creative_flow_items("acme") if i["id"] == cf_id)
    assert item["revision_error"] == error and item["revision"]["resumen"] == REV_MEJORAR["resumen"]
    otra = creative_flow.crear("acme", [], ["Chancla Rose"], [], "camina", 8, "", "A")
    sin = next(i for i in dashboard._creative_flow_items("acme") if i["id"] == otra)
    assert sin["revision_error"] is None


def test_creative_flow_items_resuelve_el_producto_una_sola_vez_por_productos_ids(base_temporal, monkeypatch):
    """Bloque 3, revisión final (I1): dos piezas terminadas con los mismos
    `productos_ids` no deben escanear el catálogo dos veces — `_producto` se
    memoiza por tupla de `productos_ids` para toda la lista de Crear."""
    import creative_flow
    import dashboard
    import final_edition
    llamadas = []

    def fake(cliente, entry, precio):
        llamadas.append(tuple(entry.get("productos_ids") or ()))
        return {"nombre": "Chancla", "sofisticacion": 3, "pruebas": []}   # resuelto en el catálogo
    monkeypatch.setattr(final_edition, "_producto", fake)
    cf1 = _sesion_video_listo("acme")
    cf2 = creative_flow.crear("acme", [], ["Chancla Rose"], [], "otra acción", 8, "", "A")
    creative_flow.actualizar("acme", cf2, estado="video_listo", video_url="https://r2/otra.mp4")
    dashboard._creative_flow_items("acme")
    assert llamadas == [("Chancla Rose",)]           # una sola llamada para las dos piezas


def test_creative_flow_items_no_comparte_el_producto_de_respaldo(base_temporal, monkeypatch):
    """Re-revisión del bloque 3: si el nombre no está en el catálogo, `_producto`
    arma uno de respaldo con los datos de ESA pieza; recordarlo por
    `productos_ids` le daba a otra pieza el texto de la primera."""
    import creative_flow
    import dashboard
    from doctrina import revisor
    vistos = {}
    monkeypatch.setattr(revisor, "reglas", lambda d: vistos.update({d["cf_id"]: d["producto"].get("nombre")}) or [])
    cf1 = creative_flow.crear("acme", [], ["Zapato Fantasma"], [], "primera acción", 8, "", "A")
    cf2 = creative_flow.crear("acme", [], ["Zapato Fantasma"], [], "segunda acción", 8, "", "A")
    for cf in (cf1, cf2):
        creative_flow.actualizar("acme", cf, estado="video_listo", video_url=f"https://r2/{cf}.mp4")
    dashboard._creative_flow_items("acme")
    assert vistos[cf1] != vistos[cf2]


def test_creative_flow_items_reglas_vacias_si_reunir_falla(base_temporal, monkeypatch):
    """Bloque 3, revisión final (I9): un fallo de `reunir` (informativo) no
    debe tumbar la lista de Crear — la pieza sigue apareciendo, sin reglas."""
    import dashboard
    from doctrina import revisor
    cf_id = _sesion_video_listo()

    def rompe(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(revisor, "reunir", rompe)
    item = next(i for i in dashboard._creative_flow_items("acme") if i["id"] == cf_id)
    assert item["reglas"] == []


def test_ruta_revisar_encola_solo_piezas_terminadas(base_temporal, monkeypatch):
    import creative_flow
    import dashboard
    from tareas import doctrina as td
    encoladas = []
    monkeypatch.setattr(td, "encolar_revisar", lambda cliente, cf_id: encoladas.append((cliente, cf_id)))
    c = _cliente_admin(dashboard)
    cf_id = _sesion_video_listo()
    assert c.post(f"/cliente/acme/creative_flow/{cf_id}/revisar").status_code == 302
    assert encoladas == [("acme", cf_id)]
    creative_flow.actualizar("acme", cf_id, estado="video_generando")
    c.post(f"/cliente/acme/creative_flow/{cf_id}/revisar")
    c.post("/cliente/acme/creative_flow/cf_no_existe/revisar")
    assert encoladas == [("acme", cf_id)]



def test_selector_de_idioma_base_marca_el_idioma_del_proyecto():
    """Decisión B (2026-09-28): el selector se queda; de entrada marca el
    idioma del proyecto (`idioma_proyecto`, del context processor) y, sin él,
    «es» como hasta hoy."""
    env = _entorno_plantilla()
    item = _item_video_listo()
    en_ingles = env.get_template("_final_detalle_respuesta.html").render(
        **_contexto_minimo([item]), item=item, f=None, idioma_proyecto="en")
    assert 'name="idioma_base"' in en_ingles
    assert '<option value="en" selected>' in en_ingles and '<option value="es" selected>' not in en_ingles
    sin_proyecto = _detalle_video_fe(env, item)
    assert '<option value="es" selected>' in sin_proyecto and '<option value="en" selected>' not in sin_proyecto


def test_boton_producir_con_sin_n():
    env = _entorno_plantilla()
    html = _detalle_video_fe(env, _item_video_listo(guion_base=GUION_BASE))
    assert 'data-plantilla="Producir {n} finales' in html and 'data-sin-n="Producir finales' in html
    # Un solo destino: «Producir 1 final», no «Producir 1 finales» (fix round 1).
    assert 'data-plantilla-uno="Producir 1 final' in html and "Producir 1 finales" not in html
    tab = _tab_final(env, [_item_video_listo(guion_base=GUION_BASE)])
    assert "btn.dataset.sinN" in tab and "replace('Producir {n} finales'" not in tab
    assert "n === 1 ? btn.dataset.plantillaUno" in tab


@pytest.mark.parametrize("enviado, esperado", [(None, "en"), ("pt", "pt"), ("es", "es"), ("fr", "en")])
def test_preparar_idioma_base_elegido_o_el_del_proyecto(base_temporal, monkeypatch, enviado, esperado):
    """Decisión B (2026-09-28): el guion base no es por destino. Sin elección
    (o con una que no vale) sale en el idioma del proyecto; la elección
    explícita del selector gana."""
    import dashboard
    import idiomas
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    cf_id = _sesion_video_listo()
    llamadas = _capturar_encolar(monkeypatch, dashboard)
    datos = {"precio": "24.99", **({"idioma_base": enviado} if enviado else {})}
    _cliente_admin(dashboard).post(f"/cliente/acme/creative_flow/{cf_id}/final/preparar", data=datos)
    assert llamadas[0]["payload"]["opciones"] == {"precio": 24.99, "idioma_base": esperado}


def test_decision_b_un_proyecto_en_ingles_produce_co_en_espanol(base_temporal, monkeypatch):
    """Decisión B (Daniel, 2026-09-28; reemplaza §B5 y el «Final edition» de
    §Pruebas del spec): en un proyecto en inglés el destino CO sigue siendo
    `es_CO` — la final se localiza en español con precio en COP — y la clave
    queda `<cf_id>__es_CO`."""
    import creative_flow as cf
    import dashboard
    import idiomas
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    base_en = dict(GUION_BASE, idioma="en", pais="US")
    item = _item_video_listo(guion_base=base_en)
    html = _entorno_plantilla().get_template("_final_detalle_respuesta.html").render(
        **_contexto_minimo([item]), item=item, f=None, idioma_proyecto="en")
    assert 'name="destinos" value="es_CO"' in html
    cf_id = _sesion_video_listo()
    cf.guardar_guion_base("acme", cf_id, base_en)
    llamadas = _capturar_encolar(monkeypatch, dashboard)
    _cliente_admin(dashboard).post(f"/cliente/acme/creative_flow/{cf_id}/final/producir", data={
        "destinos": ["es_CO"], "voz": "Rachel", "estilo_musica": "energetico", "precio_es_CO": "89900"})
    (t,) = llamadas
    assert t["job_id"] == f"acme__{cf_id}__es_CO__final"
    assert (t["payload"]["idioma"], t["payload"]["pais"]) == ("es", "CO")
    assert t["payload"]["opciones"]["precios"] == {"es_CO": 89900.0}
    assert cf.final_por_legado("acme", f"{cf_id}__es_CO")["estado"] == "generando"
