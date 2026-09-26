"""Pantallas en inglés sin español visible (spec 2026-09-26 §Pruebas). Render
real: atrapa también los textos que vienen de Python (flash, nombres de
constantes, tarjetas de llaves). Cada tarea que traduce una pantalla agrega su
test aquí."""
import pytest

import idiomas
from tests.i18n_util import espanol_visible

CLAVES = [
    "ANTHROPIC_API_KEY", "FAL_KEY", "HF_API_KEY_ID", "HF_API_KEY_SECRET", "R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME", "R2_PUBLIC_BASE_URL", "META_APP_ID", "META_APP_SECRET", "SMTP_HOST",
    "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "SMTP_FROM", "PLATAFORMA_URL", "MELI_APP_ID", "MELI_SECRET", "ATRIA_API_KEY",
]


@pytest.fixture()
def app_i18n(base_temporal, tmp_path, monkeypatch):
    import catalogo_productos
    import dashboard
    import proyectos
    monkeypatch.setenv("FLASK_SECRET_KEY", "clave-de-prueba-larga-1234567890")
    for v in CLAVES:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(dashboard, "_client_dir", lambda cliente: str(tmp_path / "clientes" / cliente))
    monkeypatch.setattr(catalogo_productos, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(dashboard.meta_conexion, "estado", lambda c: {"estado": "sin_conectar", "verificado": True, "detalle": {}})
    monkeypatch.setattr(dashboard.meta_conexion, "estado_pixel", lambda c, solo_cache=False: None)
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: False)
    monkeypatch.setattr(dashboard.estado_mod, "listar_clientes", lambda: ["acme"])
    dashboard.app.config["TESTING"] = True
    return dashboard


def _cliente(dashboard, usuario, rol, cliente):
    idiomas.guardar_de_usuario(usuario, "en")
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = usuario
        s["rol"] = rol
        s["cliente"] = cliente
    return c


@pytest.fixture()
def admin_en(app_i18n):
    return _cliente(app_i18n, "admin", "admin", None)


@pytest.fixture()
def cliente_en(app_i18n):
    return _cliente(app_i18n, "user_acme", "cliente", "acme")


@pytest.fixture()
def publico_en(app_i18n):
    c = app_i18n.app.test_client()
    c.set_cookie(idiomas.COOKIE, "en")
    return c


def html_de(c, url):
    r = c.get(url)
    assert r.status_code == 200, (url, r.status_code)
    return r.get_data(as_text=True)


def test_la_deteccion_funciona():
    html = '<div id="a"><p>Hello</p><input placeholder="Escribe aquí"></div><div id="b"><p>Guardar</p></div>'
    assert espanol_visible(html, ("a",)) == ["Escribe aquí"]
    assert espanol_visible(html) == ["Escribe aquí", "Guardar"]
