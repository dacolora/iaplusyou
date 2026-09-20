"""/mapa: el mapa conceptual del código (la versión interactiva de
ESTRUCTURA.md) vive dentro de la app y solo lo ve el administrador. Un
usuario con rol cliente o sin sesión no lo ve ni sabe que existe: se le
redirige al login, igual que con /panel. La plantilla es HTML estático
envuelto en {% raw %}, así que además se comprueba que ningún delimitador
de Jinja llegue crudo al navegador."""
import pytest

from tests.test_rutas_productos import _cliente_admin


@pytest.fixture()
def dashboard(base_temporal, monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "clave-de-prueba-larga-1234567890")
    import dashboard as dash
    dash.app.config["TESTING"] = True
    return dash


def _cliente_con_rol(dashboard, rol, cliente=None):
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "alguien"; s["rol"] = rol; s["cliente"] = cliente
    return c


def test_admin_ve_el_mapa_completo(dashboard):
    r = _cliente_admin(dashboard).get("/mapa")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Mapa de Creatv Machine" in html
    assert 'id="svg-mapa"' in html            # el diagrama con el recorrido del clic
    assert 'id="inv"' in html                 # el inventario con buscador
    assert "Antes de exponerlo" in html       # la sección de riesgos, solo para el admin
    assert "{{" not in html and "{%" not in html
    assert 'href="/panel"' in html            # siempre hay camino de vuelta


def test_rol_cliente_no_entra(dashboard):
    r = _cliente_con_rol(dashboard, "cliente", cliente="acme").get("/mapa")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/login")


def test_sin_sesion_no_entra(dashboard):
    r = dashboard.app.test_client().get("/mapa")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/login")


def test_el_panel_del_admin_enlaza_al_mapa(dashboard, monkeypatch):
    monkeypatch.setattr(dashboard.estado_mod, "listar_clientes", lambda: [])
    html = _cliente_admin(dashboard).get("/panel").get_data(as_text=True)
    assert 'href="/mapa"' in html
