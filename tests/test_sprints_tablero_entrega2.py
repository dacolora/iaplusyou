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
    assert "Proponer las que faltan (1 videos, 0 imágenes) (" in html and "aprox." in html
    assert "Aprobar todas las propuestas (1)" in html
    assert f'data-url="/cliente/acme/sprints/ideas/{ii}"' in html and 'class="sprint-idea panel-idea' in html
    assert "Otra idea (" in html and "Amanecer" in html and "Marco" in html
    assert "data-generar-lote" in html and "1 aprobada(s) sin generar (1 videos, 0 imágenes)" in html
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
    assert "Regenerar (USD 2.10)" in revision and "(USD 2.10). ¿Seguir?" in revision
    creative_flow.actualizar("acme", cfs[iv], modelo="modelo_que_ya_no_existe")      # cae al del proyecto
    assert "Regenerar (US$ 2.00)" in c.get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/piezas").data.decode()
    monkeypatch.setattr(flowplus_modelos, "estimate_imagen", lambda *a, **k: {})
    piezas = c.get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/piezas").data.decode()
    assert "Regenerar (precio no disponible)" in piezas and "(precio no disponible). ¿Seguir?" in piezas
    assert "US$ 0)" not in piezas and "US$ 0.00)" not in piezas
    revision = c.get(f"/cliente/acme/sprints/{sid}/revision").data.decode()
    assert "Regenerar (precio no disponible)" in revision


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
