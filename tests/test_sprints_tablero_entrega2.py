"""Entrega 2 del tablero de Sprints (spec 2026-09-27): pestañas del panel,
ideas, generar y piezas dentro del panel. Fixtures de test_rutas_sprints:
`app` (sesión admin, catálogo falso con espejo_led «Espejo LED»),
`con_ideas` (campaña 2 videos + 1 imagen con una idea de video aprobada y
una de imagen propuesta) y `_con_piezas` (les da sesión de Crear)."""
import json

import pytest

from tests.test_rutas_sprints import _con_piezas, app, con_ideas  # noqa: F401


def _sprint(datos):
    return datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31")


def _campana(datos, sid, n_refs=0):
    pid = datos.crear_persona("acme", "Premium")
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", None, 2, 1)
    for n in range(n_refs):
        datos.agregar_referencia("acme", cid, "imagen", f"https://r2/r{n}.jpg", descripcion="luz lateral")
    return cid


def _panel(c, sid, cid, paso=None):
    url = f"/cliente/acme/sprints/{sid}/campanas/{cid}/panel" + (f"?paso={paso}" if paso else "")
    return c.get(url).data.decode()


# ------------------------------------------------------------- pestañas ---

def test_panel_abre_en_la_pestana_que_toca(app):
    from sprints import datos
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    html = _panel(app["c"], sid, cid)
    assert 'data-paso="armar"' in html and '<div data-pestana="ideas" role="tabpanel" hidden>' in html
    for n in range(5):
        datos.agregar_referencia("acme", cid, "imagen", f"https://r2/r{n}.jpg", descripcion="luz")
    html = _panel(app["c"], sid, cid)
    assert 'data-paso="ideas"' in html and "Armar <span>✓</span>" in html and "Ideas <span>0/3</span>" in html
    assert 'data-paso="piezas"' in _panel(app["c"], sid, cid, "piezas")
    assert 'data-paso="ideas"' in _panel(app["c"], sid, cid, "cualquiera")


def test_tablero_pasa_la_pestana_pedida(app):
    from sprints import datos
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    html = app["c"].get(f"/cliente/acme/sprints/{sid}?panel={cid}&paso=piezas").data.decode()
    assert f'data-panel-inicial="{cid}"' in html and 'data-paso-inicial="piezas"' in html
    assert "irAPaso" in html and "tablero:paso" in html and "tablero:cerrado" in html
    html = app["c"].get(f"/cliente/acme/sprints/{sid}?panel={cid}&paso=raro").data.decode()
    assert 'data-paso-inicial=""' in html


def test_armar_muestra_la_sofisticacion_y_describe_referencias(app):
    from sprints import datos
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    rid = datos.agregar_referencia("acme", cid, "imagen", "https://r2/sin.jpg")      # borrador: sin descripción
    html = _panel(app["c"], sid, cid, "armar")
    assert "Promesas parecidas que ya vio el cliente de Espejo LED: Claude lo decide" in html
    assert f'data-describir="{rid}"' in html and f"/cliente/acme/sprints/referencias/{rid}" in html
    assert f'data-abrir-describir="{rid}"' in html and "Más opciones de referencias" in html
    assert "descríbelos aquí" not in html and 'id="persona-conciencia"' not in html and "Qué tanto sabe Premium" not in html
    r = app["c"].post(f"/cliente/acme/sprints/referencias/{rid}", json={"descripcion": "luz lateral", "intencion": ["iluminacion"]})
    assert r.get_json()["ok"] and r.get_json()["estado"] == "lista"
    assert "<script" not in html


# ---------------------------------------------------------------- ideas ---

def test_la_pagina_de_ideas_redirige_al_panel(con_ideas):
    c, sid, cid = con_ideas["c"], con_ideas["sid"], con_ideas["cid"]
    r = c.get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/ideas")
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/sprints/{sid}?panel={cid}&paso=ideas")
    assert c.get(f"/cliente/acme/sprints/{sid}/campanas/999/ideas").status_code == 404


def test_pestana_ideas_muestra_conteo_ideas_y_generar(con_ideas):
    c, sid, cid, iv, ii = con_ideas["c"], con_ideas["sid"], con_ideas["cid"], con_ideas["iv"], con_ideas["ii"]
    html = _panel(c, sid, cid, "ideas")
    assert "1 de 3 aprobadas · videos 1/2 · imágenes 0/1" in html
    assert "Proponer las que faltan (1 video, 0 imágenes) (" in html and "aprox." in html
    assert "Aprobar todas las propuestas (1)" in html
    assert f'data-url="/cliente/acme/sprints/ideas/{ii}"' in html and 'class="sprint-idea panel-idea' in html
    assert "Otra idea (" in html and "Amanecer" in html and "Marco" in html
    assert "data-generar-lote" in html and "1 aprobada(s) sin generar (1 video, 0 imágenes)" in html
    assert 'data-lote-modelo="video"' in html and "<script" not in html


def test_el_tablero_carga_el_editor_del_angulo(con_ideas):
    html = con_ideas["c"].get(f"/cliente/acme/sprints/{con_ideas['sid']}").data.decode()
    assert "/static/angulo.js" in html and "iniciarEditoresAngulo(cuerpo)" in html
    assert '[data-angulo-campo="gancho"]' in html


def test_proponer_ideas_por_fetch(con_ideas, monkeypatch):
    from sprints import rutas
    c, sid, cid = con_ideas["c"], con_ideas["sid"], con_ideas["cid"]
    url = f"/cliente/acme/sprints/{sid}/campanas/{cid}/ideas/proponer"
    j = c.post(url, data={"mas": "3", "tipo": "imagen"}, headers={"X-Requested-With": "fetch"}).get_json()
    assert j["ok"] and j["job_id"] == f"acme__campana{cid}__ideas"
    assert con_ideas["encolados"][-1]["payload"]["n_imagenes"] == 3
    monkeypatch.setattr(rutas.tareas_sprints, "encolar_ideas", lambda *a, **k: False)
    r = c.post(url, data={}, headers={"X-Requested-With": "fetch"})
    assert r.status_code == 409 and "en curso" in r.get_json()["error"]
    r = c.post(url, data={})
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/sprints/{sid}?panel={cid}&paso=ideas")


def test_acciones_de_idea_por_fetch(con_ideas):
    from sprints import datos
    c, sid, cid, iv, ii = con_ideas["c"], con_ideas["sid"], con_ideas["cid"], con_ideas["iv"], con_ideas["ii"]
    H = {"X-Requested-With": "fetch"}
    assert c.post(f"/cliente/acme/sprints/{sid}/campanas/{cid}/ideas/aprobar_todas", headers=H).get_json() == \
        {"ok": True, "aprobadas": 1}
    j = c.post(f"/cliente/acme/sprints/ideas/{ii}/otra", headers=H).get_json()
    assert j["ok"] and con_ideas["encolados"][-1]["payload"]["reemplaza"] == ii
    r = c.post(f"/cliente/acme/sprints/ideas/{ii}/reescribir", headers=H)
    assert r.status_code == 400 and "promesa" in r.get_json()["error"]
    assert c.post(f"/cliente/acme/sprints/ideas/{ii}/descartar", headers=H).get_json()["ok"]
    assert datos.idea("acme", ii)["estado_idea"] == "descartada"
    r = c.post(f"/cliente/acme/sprints/ideas/{iv}/aprobar")
    assert r.headers["Location"].endswith(f"/sprints/{sid}?panel={cid}&paso=ideas")


def test_generar_por_fetch(con_ideas, monkeypatch):
    from sprints import rutas
    c, sid, cid = con_ideas["c"], con_ideas["sid"], con_ideas["cid"]
    H = {"X-Requested-With": "fetch"}
    monkeypatch.setattr(rutas.produccion, "lanzar_lote",
                        lambda cliente, sid_, campana_id=None, modelo_video=None, modelo_imagen=None:
                        {"encoladas": 1, "omitidas": 0, "cf_ids": ["x"], "usd": 0.8})
    j = c.post(f"/cliente/acme/sprints/{sid}/lote", data={"campana_id": cid}, headers=H).get_json()
    assert j["ok"] and j["encoladas"] == 1 and "Lote encolado" in j["mensaje"]
    monkeypatch.setattr(rutas.produccion, "lanzar_lote",
                        lambda cliente, sid_, campana_id=None, modelo_video=None, modelo_imagen=None:
                        {"encoladas": 0, "omitidas": 0, "cf_ids": [], "usd": 0.0})
    r = c.post(f"/cliente/acme/sprints/{sid}/lote", data={"campana_id": cid}, headers=H)
    assert r.status_code == 409 and r.get_json()["error"] == "No había ideas aprobadas sin generar."


# --------------------------------------------------------------- piezas ---

def test_pestana_piezas_muestra_estados_qa_y_acciones(con_ideas, monkeypatch, tmp_path):
    sid, cid, iv, ii, cfs = _con_piezas(con_ideas, monkeypatch, tmp_path)
    html = _panel(con_ideas["c"], sid, cid, "piezas")
    for frag in ("Amanecer", "Marco", 'data-piezas-vivas="0"', 'data-pieza-accion="aprobar"',
                 'data-pieza-accion="rechazar"', "data-motivo", "Regenerar (US$", "Abrir en Crear",
                 "Aprobar las que pasaron QA (1)", ">90<"):
        assert frag in html, frag
    assert "prompt(" not in html


def test_piezas_se_piden_solas(con_ideas, monkeypatch, tmp_path):
    sid, cid, iv, ii, cfs = _con_piezas(con_ideas, monkeypatch, tmp_path)
    r = con_ideas["c"].get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/piezas")
    assert r.status_code == 200 and r.data.decode().lstrip().startswith('<div class="panel-piezas"')
    otro = con_ideas["c"].get(f"/cliente/acme/sprints/{sid}/campanas/999/piezas")
    assert otro.status_code == 404


def test_piezas_vivas_se_marcan(con_ideas):
    from sprints import datos
    c, sid, cid, iv = con_ideas["c"], con_ideas["sid"], con_ideas["cid"], con_ideas["iv"]
    datos.actualizar_idea("acme", iv, cf_id=datos.reserva_placeholder(iv))      # reserva viva = en marcha
    assert 'data-piezas-vivas="1"' in _panel(c, sid, cid, "piezas")


def test_aprobar_qa_solo_de_esta_campana(con_ideas, monkeypatch, tmp_path):
    from sprints import datos
    sid, cid, iv, ii, cfs = _con_piezas(con_ideas, monkeypatch, tmp_path)
    c = con_ideas["c"]
    url = f"/cliente/acme/sprints/{sid}/revision/aprobar_qa"
    j = c.post(url, data={"campana_id": cid + 1000}, headers={"X-Requested-With": "fetch"}).get_json()
    assert j == {"ok": True, "aprobadas": 0} and datos.idea("acme", iv)["revision"] == "pendiente"
    j = c.post(url, data={"campana_id": cid}, headers={"X-Requested-With": "fetch"}).get_json()
    assert j == {"ok": True, "aprobadas": 1} and datos.idea("acme", iv)["revision"] == "aprobada"


def test_reintentar_regenerar_y_qa_por_fetch(con_ideas, monkeypatch, tmp_path):
    from sprints import datos, rutas
    sid, cid, iv, ii, cfs = _con_piezas(con_ideas, monkeypatch, tmp_path)
    c = con_ideas["c"]
    H = {"X-Requested-With": "fetch"}
    monkeypatch.setattr(rutas.produccion, "reintentar", lambda cliente, cp: False)
    r = c.post(f"/cliente/acme/sprints/ideas/{iv}/reintentar", headers=H)
    assert r.status_code == 409 and not r.get_json()["ok"]
    monkeypatch.setattr(rutas.produccion, "regenerar", lambda cliente, cp: "cf-nuevo")
    assert c.post(f"/cliente/acme/sprints/ideas/{iv}/regenerar", headers=H).get_json() == {"ok": True, "error": None}
    monkeypatch.setattr(rutas.produccion, "regenerar",
                        lambda cliente, cp: (_ for _ in ()).throw(datos.ErrorDatos("No se puede.")))
    r = c.post(f"/cliente/acme/sprints/ideas/{iv}/regenerar", headers=H)
    assert r.status_code == 400 and r.get_json()["error"] == "No se puede."
    monkeypatch.setattr(rutas.tareas_sprints, "encolar_qa", lambda cliente, cp: True)
    # PND-088: repetir por fetch corresponde a una pieza que no pasó el QA.
    datos.actualizar_idea("acme", iv, qa={"veredicto": "no_pasa"})
    assert c.post(f"/cliente/acme/sprints/ideas/{iv}/qa", headers=H).get_json()["ok"]
    r = c.post(f"/cliente/acme/sprints/ideas/{iv}/regenerar", data={"volver": "panel"})
    assert r.headers["Location"].endswith(f"/sprints/{sid}")    # error: vuelve al tablero como antes
    monkeypatch.setattr(rutas.produccion, "regenerar", lambda cliente, cp: "cf-nuevo")
    r = c.post(f"/cliente/acme/sprints/ideas/{iv}/regenerar", data={"volver": "panel"})
    assert r.headers["Location"].endswith(f"/sprints/{sid}?panel={cid}&paso=piezas")


# -------------------------------------------------------- revisión sprint ---

def test_revision_del_sprint_renovada(con_ideas, monkeypatch, tmp_path):
    sid, cid, iv, ii, cfs = _con_piezas(con_ideas, monkeypatch, tmp_path)
    html = con_ideas["c"].get(f"/cliente/acme/sprints/{sid}/revision").data.decode()
    assert f'<option value="{cid}">1 · TOF · Premium · Espejo LED</option>' in html
    assert f"/cliente/acme/sprints/{sid}?panel={cid}&amp;paso=piezas" in html and "Abrir en el panel" in html
    assert "data-motivo" in html and "data-rechazo" in html and "prompt(" not in html
    assert "if (e.metaKey || e.ctrlKey || e.altKey) return;" in html       # los atajos siguen


# ------------------------------------------- ronda final (revisión + pantalla) ---

def _tablero(c, sid):
    return c.get(f"/cliente/acme/sprints/{sid}").data.decode()


def _js_panel(html):
    """El segundo <script> del tablero: los listeners del panel."""
    return html[html.index("// Panel de la campaña: autoguardado"):]


def test_la_guardia_de_base_solo_marca_selects_en_change(app):
    """F1: en un campo de texto `change` llega al salir (blur), DESPUÉS del
    autoguardado con espera que ya borró la marca: volver a marcarlo lo dejaba
    sucio para siempre y la página nunca se recargaba sola."""
    from sprints import datos
    html = _tablero(app["c"], _sprint(datos))
    assert "['input', 'change'].forEach" not in html
    assert "document.addEventListener('input', marcarSucio);" in html
    assert "document.addEventListener('change', function (e) { if (e.target && e.target.tagName === 'SELECT') marcarSucio(e); });" in html


def test_los_selects_del_tablero_borran_su_marca(app):
    """F1: los selects que no pasan por `guardar` (modelos de la caja Generar y
    del modal del lote) borran su `data-sucio` cuando el estimado respondió; el
    texto de «Momento del mes» se limpia al guardarse el momento."""
    from sprints import datos
    html = _tablero(app["c"], _sprint(datos))
    campana = html[html.index("function estimarLoteCampana"):html.index("// ---- Pestaña Piezas")]
    exito = campana[campana.index(".then(function (j) {"):]
    assert "[data-lote-modelo]" in exito and "delete s.dataset.sucio" in exito
    modal = html[html.index("function estimarLote()"):html.index("document.getElementById('lote-modelo-video').addEventListener")]
    assert "delete s.dataset.sucio" in modal[modal.index(".then(function (j) {"):]
    cabecera = html[html.index("function guardarSprint"):html.index("campos.addEventListener")]
    assert "delete campos.querySelector('[data-momento-texto]').dataset.sucio" in cabecera


def test_precio_de_reintentar_y_regenerar_es_el_del_modelo_de_la_pieza(con_ideas, monkeypatch, tmp_path):
    """F2 + F6: la pieza se hizo con Kling O3 Pro (no el modelo del proyecto,
    Wan 3.0): el precio es el de Kling, con la duración recortada a su rango
    (20 s → 15 s: US$ 0.14 × 15 = 2.10), con dos decimales, en el panel y en la
    revisión del sprint. Sin estimado: «precio no disponible», nunca «US$ 0»."""
    import creative_flow
    from providers import flowplus_modelos
    from sprints import datos
    sid, cid, iv, ii, cfs = _con_piezas(con_ideas, monkeypatch, tmp_path)
    c = con_ideas["c"]
    creative_flow.actualizar("acme", cfs[iv], modelo="kling_o3_pro")
    datos.actualizar_idea("acme", iv, duracion_s=20)
    piezas = c.get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/piezas").data.decode()
    assert "Regenerar (US$ 2.10)" in piezas and "(US$ 2.10). ¿Seguir?" in piezas
    assert "Regenerar (US$ 0.09)" in piezas              # la imagen: dos decimales, no «0.093»
    revision = c.get(f"/cliente/acme/sprints/{sid}/revision").data.decode()
    # Idioma (Task 4): el onsubmit de revisión va con `_(...)|tojson` (comillas simples
    # en el atributo, como toda la app); tojson escapa el «¿» a ¿, JSON válido que
    # el navegador decodifica igual — el botón en sí (fuera del tojson) no cambia.
    assert "Regenerar (USD 2.10)" in revision and "(USD 2.10). \\u00bfSeguir?" in revision
    creative_flow.actualizar("acme", cfs[iv], modelo="modelo_que_ya_no_existe")      # cae al del proyecto
    assert "Regenerar (US$ 2.00)" in c.get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/piezas").data.decode()
    monkeypatch.setattr(flowplus_modelos, "estimate_imagen", lambda *a, **k: {})
    piezas = c.get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/piezas").data.decode()
    assert "Regenerar (precio no disponible)" in piezas and "(precio no disponible). ¿Seguir?" in piezas
    assert "US$ 0)" not in piezas and "US$ 0.00)" not in piezas
    revision = c.get(f"/cliente/acme/sprints/{sid}/revision").data.decode()
    assert "Regenerar (precio no disponible)" in revision


def test_describir_un_referente_no_recarga_el_panel(app):
    """F3: guardar la descripción no vuelve a pintar el panel (se cerraba la
    caja y se perdía el segundo chip): avisa «Guardado ✓», refresca la tarjeta
    y actualiza en el sitio el contador de Armar y el de Referentes."""
    from sprints import datos
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    rid = datos.agregar_referencia("acme", cid, "imagen", "https://r2/sin.jpg")
    html = _panel(app["c"], sid, cid, "armar")
    assert "data-ref-listas>0</span>" in html and "data-ref-objetivo>5</span>" in html
    caja = html[html.index(f'data-describir="{rid}"'):]
    assert "Guardado ✓" in caja[:caja.index("Más opciones de referencias")]
    js = _js_panel(_tablero(app["c"], sid))
    fn = js[js.index("function pintarConteoReferentes"):js.index("// ---- Pestaña Ideas")]
    assert "T.abrir(" not in fn and "T.refrescarTarjeta(cid)" in fn
    # Idioma (Task 4): «Falta describir ✎» / «Descrito ✓» ahora viven en TEXTO_PANEL
    # (traducibles con _()|tojson), no como literal suelto en el JS.
    assert "j.referencias_listas" in fn and "j.referencias_objetivo" in fn and "TEXTO_PANEL.faltaDescribir" in fn
    assert "sigue(cid)" in fn


def test_piezas_y_pestanas_con_buen_tamano():
    """F5 + F15: los botones de una pieza no se estiran a la altura de la
    tarjeta vecina y las pestañas del panel conservan una altura cómoda al dedo
    (F4, la cabecera en el celular, está en tests/test_movil.py)."""
    import re
    css = open("static/style.css", encoding="utf-8").read()
    pieza = re.search(r"\.panel-pieza \{[^}]*\}", css).group(0)
    assert "align-content: start" in pieza
    pestana = re.search(r"\.panel-pestana \{[^}]*\}", css).group(0)
    assert "min-height: 0" not in pestana and "min-height: 2.25rem" in pestana


def test_respuestas_tardias_no_tocan_otra_campana(con_ideas):
    """F7 + F8 + F9 + F13: el cid se toma al hacer clic; al volver, solo se
    reabre si el panel sigue en esa campaña. Antes de recargar se guardan las
    ideas con autoguardado pendiente. El estimado del lote ignora respuestas
    viejas y la pestaña Piezas deja de preguntar si la campaña ya no existe."""
    js = _js_panel(_tablero(con_ideas["c"], con_ideas["sid"]))
    assert "T.abrir(raiz().dataset.cid" not in js
    assert "function sigue(cid)" in js
    for bloque in ("var proponer = ", "var accionIdea = ", "var generar = "):
        trozo = js[js.index(bloque):js.index(bloque) + 900]
        assert "guardarIdeasPendientes()" in trozo, bloque
    est = js[js.index("function estimarLoteCampana"):js.index("// ---- Pestaña Piezas")]
    assert "pedidoEstimar" in est and "miPedido !== pedidoEstimar" in est
    ref = js[js.index("function refrescarPiezas"):js.index("function trasAccionPieza")]
    assert "x.status === 404" in ref


def test_recarga_del_sprint_generando_respeta_lo_escrito(con_ideas):
    """F10: al terminar de generar, el tablero recarga solo si no hay nada sin
    guardar ni un motivo de rechazo a medio escribir."""
    html = _tablero(con_ideas["c"], con_ideas["sid"])
    bloque = html[html.index("Mientras el sprint genera"):html.index("if (panel.dataset.panelInicial)")]
    assert "if (j.estado !== 'generando' && puedeRecargar()) location.reload();" in bloque
    assert "haySinGuardar()" in html and "[data-motivo]" in html[html.index("function puedeRecargar"):]


def test_atajos_de_la_revision_no_escriben_la_letra(con_ideas, monkeypatch, tmp_path):
    """F11: la R abre el motivo y le da el foco; sin preventDefault la misma R
    quedaba escrita en la caja."""
    sid, cid, iv, ii, cfs = _con_piezas(con_ideas, monkeypatch, tmp_path)
    html = con_ideas["c"].get(f"/cliente/acme/sprints/{sid}/revision").data.decode()
    assert "{ e.preventDefault(); accionSeleccionada('aprobar'); }" in html
    assert "{ e.preventDefault(); accionSeleccionada('rechazar'); }" in html


def test_la_pieza_de_crear_lleva_a_su_panel(con_ideas, monkeypatch, tmp_path):
    """F14: el distintivo «Sprint · Campaña n» de una pieza de Crear abre el
    panel de su campaña en la pestaña Piezas (es una pieza, no una idea)."""
    sid, cid, iv, ii, cfs = _con_piezas(con_ideas, monkeypatch, tmp_path)
    import creative_flow
    creative_flow.actualizar("acme", cfs[iv], sprint={"sprint_id": sid, "sprint_nombre": "Octubre", "campana_id": cid,
                                                      "campana_n": 1, "cp_id": iv})
    html = con_ideas["c"].get("/cliente/acme").data.decode()
    assert f"/cliente/acme/sprints/{sid}?panel={cid}&amp;paso=piezas" in html and "Sprint · Campaña 1" in html
    assert f"/sprints/{sid}/campanas/{cid}/ideas" not in html


def test_ideas_en_singular(con_ideas):
    """F15: «1 video», nunca «1 videos»."""
    html = _panel(con_ideas["c"], con_ideas["sid"], con_ideas["cid"], "ideas")
    assert "Proponer las que faltan (1 video, 0 imágenes)" in html
    assert "1 aprobada(s) sin generar (1 video, 0 imágenes)" in html
    assert "1 videos" not in html and "1 imágenes" not in html


def test_precio_de_regenerar_respeta_el_sonido_de_la_sesion(con_ideas, monkeypatch, tmp_path):
    """Kling cobra aparte el sonido nativo: una pieza hecha SIN «Sonido de la escena»
    se regenera sin él, así que su precio no lleva ese recargo."""
    import creative_flow
    from providers import flowplus_modelos
    from sprints import datos
    sid, cid, iv, ii, cfs = _con_piezas(con_ideas, monkeypatch, tmp_path)
    c = con_ideas["c"]
    creative_flow.actualizar("acme", cfs[iv], modelo="kling_o3_pro", con_sonido=False)
    datos.actualizar_idea("acme", iv, duracion_s=15)
    sin = flowplus_modelos.estimate_video("kling_o3_pro", 15, con_sonido=False)["usd"]
    con = flowplus_modelos.estimate_video("kling_o3_pro", 15, con_sonido=True)["usd"]
    assert sin < con
    piezas = c.get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/piezas").data.decode()
    assert "Regenerar (US$ %.2f)" % sin in piezas and "Regenerar (US$ %.2f)" % con not in piezas


def test_pnd127_precio_de_regenerar_suma_musica_generada(con_ideas, monkeypatch, tmp_path):
    import creative_flow
    from providers import flowplus_modelos
    from sprints import datos
    sid, cid, iv, ii, cfs = _con_piezas(con_ideas, monkeypatch, tmp_path)
    creative_flow.actualizar('acme', cfs[iv], modelo='kling_o3_pro', musica_estilo='calmado')
    datos.actualizar_idea('acme', iv, duracion_s=15)
    base = flowplus_modelos.estimate_video('kling_o3_pro', 15, con_sonido=True)['usd']
    html = con_ideas['c'].get(f'/cliente/acme/sprints/{sid}/campanas/{cid}/piezas').data.decode()
    assert 'Regenerar (US$ %.2f)' % (base + .02) in html


def test_contadores_de_piezas_en_singular_y_plural(con_ideas, monkeypatch, tmp_path):
    """«1 aprobadas» / «1 listas»: con uno va en singular (panel, revisión y entrega)."""
    from sprints import datos
    sid, cid, iv, ii, cfs = _con_piezas(con_ideas, monkeypatch, tmp_path)
    c = con_ideas["c"]
    datos.actualizar_idea("acme", iv, revision="aprobada")
    piezas = c.get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/piezas").data.decode()
    assert "2 listas" in piezas and "1 aprobada</strong>" in piezas and "1 aprobadas" not in piezas
    for url in (f"/cliente/acme/sprints/{sid}/revision", f"/cliente/acme/sprints/{sid}/entrega"):
        html = c.get(url).data.decode()
        assert "1 aprobada ·" in html and "1 aprobadas" not in html, url


def test_marcas_repetidas_con_tildes_distintas_cuentan_una_vez():
    from sprints import datos
    assert datos.normalizar_marcas("Élite\nelite\nCröcs, CROCS") == [{"nombre": "Élite"}, {"nombre": "Cröcs"}]


@pytest.mark.parametrize("sitio, pasa", [(None, True), ("same-origin", True), ("none", True),
                                         ("cross-site", False), ("same-site", False)])
def test_los_post_de_sprints_rechazan_pedidos_de_otro_sitio(app, sitio, pasa):
    """Barrera CSRF como la de Flow Plus y el editor: un POST que el navegador
    declara de otro sitio no toca nada (y la lectura sigue abierta)."""
    from sprints import datos
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    headers = {"X-Requested-With": "fetch"} | ({} if sitio is None else {"Sec-Fetch-Site": sitio})
    r = app["c"].post(f"/cliente/acme/sprints/{sid}/campanas/{cid}/campo", json={"campo": "dolor", "valor": "pies"},
                      headers=headers)
    assert (r.status_code == 403) is (not pasa)
    assert (datos.campana("acme", cid)["dolor"] == "pies") is pasa
    if not pasa:
        assert r.get_json()["ok"] is False
        r = app["c"].post(f"/cliente/acme/sprints/{sid}/campo", data={"campo": "nombre", "valor": "X"},
                          headers={"Sec-Fetch-Site": sitio})
        assert r.status_code == 403
        assert app["c"].get(f"/cliente/acme/sprints/{sid}", headers={"Sec-Fetch-Site": sitio}).status_code == 200


def test_estado_del_sprint_con_tilde(app):
    d = app["dashboard"]
    with d.app.test_request_context():
        html = d.app.jinja_env.from_string('{% from "_sprint_macros.html" import chip_estado %}'
                                           '{{ chip_estado("revision") }} {{ chip_estado("listo_para_generar") }}').render()
    assert 'estado-sprint-revision">revisión</span>' in html
    assert 'estado-sprint-listo_para_generar">listo para generar</span>' in html


def test_estado_del_sprint_con_mayuscula_solo_al_principio():
    """La etiqueta del sprint salía «Ready To Generate» (2026-10-01): el CSS
    ponía `text-transform: capitalize` (mayúscula en cada palabra). Ahora solo
    la primera letra (`::first-letter`, que funciona porque .tag-estado es
    inline-block): «Ready to generate», «Listo para generar»."""
    import os
    import re
    css = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "style.css"),
               encoding="utf-8").read()
    reglas = re.findall(r"\.estado-sprint(?![-\w])([^{]*)\{([^}]*)\}", css)
    assert reglas, "no encontré las reglas de .estado-sprint"
    assert not any("capitalize" in cuerpo for _, cuerpo in reglas)
    assert any("::first-letter" in selector and "uppercase" in cuerpo for selector, cuerpo in reglas)
    assert re.search(r"\.tag-estado\s*\{[^}]*display:\s*inline-block", css)


def test_js_del_panel_espera_el_angulo_y_conserva_lo_escrito():
    """Verificado en Chrome sin ventana (2026-09-28): lo escrito, la tarjeta abierta y el
    cursor sobreviven a una recarga del panel; «Reescribir» sale después del guardado del
    ángulo; un formulario con confirm() pregunta una sola vez. Aquí se vigilan los ganchos."""
    js = open("static/angulo.js", encoding="utf-8").read()
    assert "window.guardarAngulosPendientes = function" in js
    assert "ev.stopImmediatePropagation();" in js and "form.requestSubmit" in js
    panel = open("templates/sprint_detalle.html", encoding="utf-8").read()
    assert "window.guardarAngulosPendientes(cuerpo)" in panel
    assert "var escrito = mismo ? tomarEscrito() : null;" in panel and "devolverEscrito(escrito);" in panel
    assert "d.open = guardado.abiertos[k];" in panel
    assert "if (!sigue(cid)) return;" in panel
