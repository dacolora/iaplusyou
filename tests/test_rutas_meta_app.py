"""Rutas de la app de Meta por proyecto: el cliente registra su app (id,
secret, config de login) desde FlowMarketing y desde ahí "Conectar con
Meta" usa esa app. Sin app registrada no hay botón de conectar."""
import pytest

from tests.test_rutas_experimentos import _cliente_admin


@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import meta_conexion as mc
    import proyectos
    monkeypatch.setattr(mc, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    monkeypatch.setenv("META_REDIRECT_URI", "https://app.example/meta/callback")
    monkeypatch.setattr(dashboard.meta_conexion, "estado", lambda c: {"estado": "sin_conectar", "verificado": True, "detalle": {}})
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard), "mc": mc}


def _flashes(c):
    with c.session_transaction() as s:
        return [m for _cat, m in s.get("_flashes", [])]


DATOS = {"app_id": "111", "app_secret": "s3cr3t", "login_config_id": "222"}


def test_guardar_app_del_proyecto(app):
    r = app["c"].post("/cliente/acme/meta/app", data=DATOS)
    assert r.status_code == 302
    assert app["mc"].cargar_app("acme") == DATOS


def test_guardar_app_incompleta_no_guarda(app):
    r = app["c"].post("/cliente/acme/meta/app", data={"app_id": "111", "app_secret": "", "login_config_id": "222"})
    assert r.status_code == 302
    assert app["mc"].cargar_app("acme") is None
    assert any("app_secret" in m for m in _flashes(app["c"]))


def test_conectar_usa_la_app_del_proyecto(app):
    app["mc"].guardar_app("acme", DATOS)
    r = app["c"].get("/cliente/acme/meta/conectar")
    assert r.status_code == 302
    assert "client_id=111" in r.headers["Location"]
    assert "config_id=222" in r.headers["Location"]


def test_conectar_sin_app_avisa_y_no_redirige_a_meta(app):
    r = app["c"].get("/cliente/acme/meta/conectar")
    assert r.status_code == 302
    assert "facebook.com" not in r.headers["Location"]
    assert any("app de Meta" in m for m in _flashes(app["c"]))


def test_flowmarketing_sin_app_pide_registrarla_y_no_muestra_conectar(app):
    """Con la forma «propia» elegida (spec 2026-09-20 §3) y sin app registrada
    se ve el formulario de la app y todavía no el enlace de conectar."""
    import proyectos
    proyectos.guardar_meta_forma("acme", "propia")
    r = app["c"].get("/cliente/acme#ads")
    html = r.get_data(as_text=True)
    assert 'action="/cliente/acme/meta/app"' in html
    assert "/cliente/acme/meta/conectar" not in html


def test_flowmarketing_con_app_muestra_conectar_y_nunca_el_secret(app):
    app["mc"].guardar_app("acme", DATOS)
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert "/cliente/acme/meta/conectar" in html
    assert "111" in html
    assert "s3cr3t" not in html


def test_callback_cambia_el_code_con_la_app_del_proyecto(app, monkeypatch):
    app["mc"].guardar_app("acme", DATOS)
    visto = {}
    monkeypatch.setattr(app["mc"], "cambiar_code_por_token",
                        lambda cliente, code: (visto.update({"cliente": cliente, "code": code}),
                                               {"token": "t", "tipo_token": "", "expira_en": None})[1])
    monkeypatch.setattr(app["mc"], "obtener_perfil", lambda t: {"name": "X"})
    monkeypatch.setattr(app["mc"], "listar_activos", lambda t: {"ad_accounts": [], "pages": []})
    with app["c"].session_transaction() as s:
        s["meta_oauth"] = {"state": "st", "cliente": "acme"}
    r = app["c"].get("/meta/callback?state=st&code=abc")
    assert r.status_code == 302
    assert visto == {"cliente": "acme", "code": "abc"}
