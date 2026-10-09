"""fal sin saldo (2026-10-09, PND-213). Seedance 2.5 con varias referencias va
por fal: si fal se queda sin saldo, la tarjeta de la pieza ya lo decía, pero el
aviso de Crear y Alertas solo miraban a WaveSpeed. Ahora lo dicen, y sin
exagerar: solo se pausan los modelos de fal; los demás siguen."""
import json
import time

from tests.test_alertas_fuentes import AHORA, _claves, _kv
from tests.test_rutas_crear_videos_ref import app  # noqa: F401  (fixture de la página del proyecto)
from tests.test_saldo import avisos  # noqa: F401  (fixture del correo al admin)


def _sin_saldo_fal(base, desde="2026-10-09T17:20:00"):
    ahora = time.time()
    _kv(base, "sin_saldo:fal", json.dumps({"desde": desde, "desde_ts": ahora - 600, "ultimo_ts": ahora - 60,
                                           "fallos": 1, "detalle": "Exhausted balance"}))


def _cliente(app):  # noqa: F811
    c = app["dashboard"].app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "alguien"; s["rol"] = "cliente"; s["cliente"] = "acme"
    return c


def test_crear_avisa_que_solo_se_pausan_los_modelos_de_fal(app, base_temporal):  # noqa: F811
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert "data-aviso-saldo-fal" not in html
    _sin_saldo_fal(base_temporal)
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    # Una sola vez: en Crear, no en Cambiar producto (que no usa fal).
    assert html.count("data-aviso-saldo-fal") == 1
    assert "data-aviso-saldo " not in html and 'data-aviso-saldo role' not in html     # el de WaveSpeed no sale
    bloque = html[html.index("data-aviso-saldo-fal"):html.index("data-aviso-saldo-fal") + 1500]
    assert "fal.ai se quedó sin saldo" in bloque and "https://fal.ai/dashboard/billing" in bloque
    assert "Seedance 2.5 · varias referencias" in bloque and "Los demás modelos de Crear siguen funcionando" in bloque
    # El cliente: neutro, sin proveedor ni enlace de recarga.
    html = _cliente(app).get("/cliente/acme").get_data(as_text=True)
    bloque = html[html.index("data-aviso-saldo-fal"):html.index("data-aviso-saldo-fal") + 1000]
    assert "Seedance 2.5 · varias referencias está en pausa" in bloque and "elige otro modelo" in bloque
    assert "fal.ai" not in bloque and "billing" not in bloque


def test_alertas_de_fal_una_neutra_y_otra_solo_para_el_admin(base_temporal):
    import alertas
    assert alertas._fuente_saldo("acme", AHORA) == []
    _sin_saldo_fal(base_temporal)
    neutra, recarga = alertas._fuente_saldo("acme", AHORA)
    assert [neutra["clave"], recarga["clave"]] == ["saldo:fal", "saldo:fal_recarga"]
    # `atencion`, no `bloquea`: los demás modelos siguen generando.
    assert {neutra["nivel"], recarga["nivel"]} == {"atencion"} and neutra["huella"] == recarga["huella"]
    assert neutra["solo_admin"] is False and recarga["solo_admin"] is True
    assert neutra["titulo"] == "Seedance 2.5 · varias referencias está en pausa"
    assert "fal.ai" not in (neutra["titulo"] + neutra["detalle"]).lower() and "http" not in neutra["detalle"]
    assert recarga["titulo"] == "fal.ai se quedó sin saldo"
    assert "2026-10-09 17:20" in recarga["detalle"] and "https://fal.ai/dashboard/billing" in recarga["detalle"]
    # Un cliente nunca puede descartar la del admin.
    assert alertas.es_solo_admin("saldo:fal_recarga", []) and not alertas.es_solo_admin("saldo:fal", [])


def test_wavespeed_y_fal_a_la_vez_salen_las_cuatro(base_temporal):
    import alertas
    _sin_saldo_fal(base_temporal)
    ahora = time.time()
    _kv(base_temporal, "sin_saldo:wavespeed", json.dumps({"desde": "2026-10-09T17:00:00", "desde_ts": ahora - 600,
                                                          "ultimo_ts": ahora - 60, "fallos": 1, "detalle": "x"}))
    assert _claves(alertas._fuente_saldo("acme", AHORA)) == [
        "saldo:wavespeed", "saldo:wavespeed_recarga", "saldo:fal", "saldo:fal_recarga"]


def test_el_correo_al_admin_de_fal_no_dice_que_todo_crear_esta_parado(avisos):  # noqa: F811
    import saldo
    assert saldo.marcar("fal", "Exhausted balance", cliente="acme") is True
    (tipo, asunto, cuerpo, cliente), = avisos
    assert tipo == "sin_saldo" and asunto == "fal.ai se quedó sin saldo" and cliente == "acme"
    assert "Seedance 2.5 · varias referencias" in cuerpo and "los demás modelos de Crear siguen funcionando" in cuerpo
    assert "Cambiar producto no pueden" not in cuerpo and "https://fal.ai/dashboard/billing" in cuerpo
    # WaveSpeed sigue diciendo lo de siempre
    assert saldo.marcar("wavespeed", "Insufficient credits", cliente="acme") is True
    assert "Crear y Cambiar producto no pueden generar" in avisos[-1][2]
