"""/panel rehecho como tablero de operación del admin: totales del mes,
salud del worker, tabla comparativa de proyectos, historial y el CSV del
mes de todos los proyectos. Sigue siendo solo para el rol admin."""
import pytest

from tests.test_rutas_productos import _cliente_admin


@pytest.fixture()
def dashboard(base_temporal, monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "clave-de-prueba-larga-1234567890")
    import dashboard as dash
    import estado
    dash.app.config["TESTING"] = True
    monkeypatch.setattr(estado, "listar_clientes", lambda: ["acme", "beta"])
    monkeypatch.setattr(estado, "cargar", lambda c: {"b1": {"estado": "pendiente"}} if c == "acme" else {})
    monkeypatch.setattr(dash.proyectos, "nombre_visible", lambda c: c.upper())
    monkeypatch.setattr(dash.meta_conexion, "cargar", lambda c: None)
    return dash


def test_panel_muestra_totales_proyectos_y_salud(dashboard):
    import cola
    import gastos
    gastos.registrar("acme", "video", 1.3, "video:1", proveedor="wavespeed")
    gastos.registrar("beta", "swap", 0.5, "swap:1")
    cola.encolar("flowplus_video", {}, cliente="acme", job_id="acme__x__video")

    html = _cliente_admin(dashboard).get("/panel").get_data(as_text=True)

    assert "US$ 1,80" in html                      # generación del mes, todos los proyectos
    assert "US$ 1,30" in html and "US$ 0,50" in html
    assert "ACME" in html and "BETA" in html
    assert 'id="admin-salud"' in html and 'id="admin-proyectos"' in html and 'id="admin-historial"' in html
    assert 'href="/panel/gasto.csv"' in html
    assert 'href="/cliente/acme"' in html          # las tarjetas siguen llevando al proyecto


def test_csv_del_panel_lleva_todos_los_proyectos_y_es_solo_admin(dashboard):
    import gastos
    gastos.registrar("acme", "video", 1.3, "video:1")
    gastos.registrar("beta", "swap", 0.5, "swap:1")

    r = _cliente_admin(dashboard).get("/panel/gasto.csv")
    assert r.status_code == 200 and r.mimetype == "text/csv"
    texto = r.get_data(as_text=True)
    assert "acme;" in texto and "beta;" in texto

    anonimo = dashboard.app.test_client().get("/panel/gasto.csv")
    assert anonimo.status_code == 302 and anonimo.headers["Location"].endswith("/login")
