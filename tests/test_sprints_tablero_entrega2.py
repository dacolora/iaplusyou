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
