"""Guía de estilos (spec 2026-10-02-sistema-de-estilos §8): solo para el admin, con cada token y su contraste."""
import os

import estilos


def _cliente(rol="admin", usuario="admin", cliente=None):
    import dashboard
    dashboard.app.config["TESTING"] = True
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = usuario
        s["rol"] = rol
        s["cliente"] = cliente
    return c


def test_guia_solo_para_el_admin(base_temporal):
    assert _cliente("cliente", "alguien", "acme").get("/admin/estilos").status_code == 302


def test_guia_muestra_cada_token_y_cada_componente(base_temporal):
    r = _cliente().get("/admin/estilos")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    for nombre, _ in estilos.tokens():
        assert nombre in html, f"la guía no muestra {nombre}"
    carpeta = os.path.join(estilos.CARPETA, "componentes")
    for archivo in (os.listdir(carpeta) if os.path.isdir(carpeta) else []):
        if archivo.endswith(".css"):
            assert f'data-componente="{archivo[:-4]}"' in html, f"la guía no muestra el componente {archivo}"
