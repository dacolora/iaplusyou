"""Selector de idioma (spec 2026-09-26 §B3): cfg_idioma (cuenta / proyecto),
/idioma/<codigo> con cookie, registro con el idioma de la cookie, y la bandera
ACTIVO_PARA_TODOS que esconde todo a los clientes durante las fases 2-5."""
import pytest

import idiomas
from tests.test_i18n_fugas import app_i18n  # noqa: F401  (fixture)

ORIGEN = {"Sec-Fetch-Site": "same-origin"}     # dashboard._mismo_origen mira Sec-Fetch-Site


def _sesion(dashboard, usuario, rol, cliente):
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = usuario
        s["rol"] = rol
        s["cliente"] = cliente
    return c


def test_admin_cambia_su_idioma_sin_tocar_el_proyecto(app_i18n):
    c = _sesion(app_i18n, "admin", "admin", None)
    r = c.post("/cliente/acme/cfg_idioma", data={"idioma": "en", "alcance": "cuenta"}, headers=ORIGEN)
    assert r.status_code == 302
    assert idiomas.de_usuario("admin") == "en"
    assert idiomas.de_proyecto("acme") == "es"


def test_admin_cambia_el_idioma_del_proyecto(app_i18n):
    c = _sesion(app_i18n, "admin", "admin", None)
    c.post("/cliente/acme/cfg_idioma", data={"idioma": "en", "alcance": "proyecto"}, headers=ORIGEN)
    assert idiomas.de_proyecto("acme") == "en"
    assert idiomas.de_usuario("admin") == "es"


def test_cliente_bloqueado_mientras_no_este_activo(app_i18n):
    c = _sesion(app_i18n, "user_acme", "cliente", "acme")
    r = c.post("/cliente/acme/cfg_idioma", data={"idioma": "en", "alcance": "cuenta"}, headers=ORIGEN)
    assert r.status_code == 403
    assert idiomas.de_usuario("user_acme") == "es"


def test_cliente_activo_cambia_su_idioma_y_el_de_su_proyecto(app_i18n, monkeypatch):
    monkeypatch.setattr(idiomas, "ACTIVO_PARA_TODOS", True)
    c = _sesion(app_i18n, "user_acme", "cliente", "acme")
    c.post("/cliente/acme/cfg_idioma", data={"idioma": "en", "alcance": "cuenta"}, headers=ORIGEN)
    assert idiomas.de_usuario("user_acme") == "en" and idiomas.de_proyecto("acme") == "en"
    r = c.post("/cliente/acme/cfg_idioma", data={"idioma": "es", "alcance": "proyecto"}, headers=ORIGEN)
    assert r.status_code == 400                     # un cliente no elige el alcance "proyecto"


def test_idioma_invalido_y_origen_ajeno(app_i18n):
    c = _sesion(app_i18n, "admin", "admin", None)
    assert c.post("/cliente/acme/cfg_idioma", data={"idioma": "pt", "alcance": "cuenta"}, headers=ORIGEN).status_code == 400
    assert c.post("/cliente/acme/cfg_idioma", data={"idioma": "en", "alcance": "cuenta"},
                  headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_selector_solo_admin_mientras_no_este_activo(app_i18n):
    html_admin = _sesion(app_i18n, "admin", "admin", None).get("/cliente/acme").get_data(as_text=True)
    assert 'id="config-idioma"' in html_admin and 'id="config-idioma-proyecto"' in html_admin
    html_cli = _sesion(app_i18n, "user_acme", "cliente", "acme").get("/cliente/acme").get_data(as_text=True)
    assert 'id="config-idioma"' not in html_cli and 'id="config-idioma-proyecto"' not in html_cli


def test_selector_del_cliente_cuando_esta_activo(app_i18n, monkeypatch):
    monkeypatch.setattr(idiomas, "ACTIVO_PARA_TODOS", True)
    html_cli = _sesion(app_i18n, "user_acme", "cliente", "acme").get("/cliente/acme").get_data(as_text=True)
    assert 'id="config-idioma"' in html_cli and 'id="config-idioma-proyecto"' not in html_cli


def test_html_lang_sigue_al_idioma(app_i18n):
    c = _sesion(app_i18n, "admin", "admin", None)
    assert '<html lang="es">' in c.get("/cliente/acme").get_data(as_text=True)
    idiomas.guardar_de_usuario("admin", "en")
    assert '<html lang="en">' in c.get("/cliente/acme").get_data(as_text=True)


def test_cookie_de_idioma_y_next_seguro(app_i18n):
    c = app_i18n.app.test_client()
    r = c.get("/idioma/en?next=/login")
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")
    assert "idioma=en" in r.headers["Set-Cookie"]
    for malo in ("https://malo.example/x", "//malo.example/x", "/\\malo.example"):
        r = c.get("/idioma/es", query_string={"next": malo})
        assert r.headers["Location"].endswith("/"), malo
    assert c.get("/idioma/pt").status_code == 404


def test_enlaces_publicos_solo_si_esta_activo(app_i18n, monkeypatch):
    c = app_i18n.app.test_client()
    assert 'class="idioma-enlaces"' not in c.get("/login").get_data(as_text=True)
    monkeypatch.setattr(idiomas, "ACTIVO_PARA_TODOS", True)
    assert 'class="idioma-enlaces"' in c.get("/login").get_data(as_text=True)


@pytest.mark.parametrize("activo, esperado", [(False, "es"), (True, "en")])
def test_registro_toma_la_cookie_solo_si_esta_activo(app_i18n, monkeypatch, activo, esperado):
    monkeypatch.setattr(idiomas, "ACTIVO_PARA_TODOS", activo)
    monkeypatch.setattr(app_i18n, "BASE_DIR", str(app_i18n.proyectos.BASE_DIR))
    c = app_i18n.app.test_client()
    c.set_cookie(idiomas.COOKIE, "en")
    r = c.post("/proyectos/nuevo", data={"nombre": "Nueva Marca", "usuario": "nueva", "correo": "nueva@prueba.local",
                                          "password": "una-clave-larga-123"})
    assert r.status_code == 302
    assert idiomas.de_usuario("nueva") == esperado
    assert idiomas.de_proyecto("nueva_marca") == esperado
