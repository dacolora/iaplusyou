"""Con los valores de producción (DEFECTO="en", ACTIVO_PARA_TODOS=True), una
persona SIN idioma guardado ve TODA la app en inglés: las pestañas, la barra
lateral, el encabezado, las páginas públicas y las de admin (cierre de la
fase 6, spec 2026-09-26 §Pruebas). Excepciones a propósito, con su guardia:
el contenido del mapa del código y los textos de la doctrina (documentación
interna en español)."""
import re

import pytest

import idiomas
from tests.i18n_util import espanol_visible
from tests.test_i18n_fugas import app_i18n, html_de  # noqa: F401  (fixture)

PESTANAS = ("tab-alertas", "tab-rendimiento", "tab-referentes", "tab-creativeflowplus",
            "tab-final", "tab-experimentos", "tab-sprints", "tab-catalogo", "tab-settings", "sidebar", "barra-superior")


@pytest.fixture()
def produccion(app_i18n, monkeypatch):
    monkeypatch.setattr(idiomas, "DEFECTO", "en")
    monkeypatch.setattr(idiomas, "ACTIVO_PARA_TODOS", True)
    return app_i18n


def _sesion(dashboard, usuario, rol, cliente):
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"], s["rol"], s["cliente"] = usuario, rol, cliente
    return c


@pytest.mark.parametrize("usuario, rol, cliente", [("admin", "admin", None), ("user_acme", "cliente", "acme")])
def test_proyecto_entero_en_ingles_sin_idioma_guardado(produccion, usuario, rol, cliente):
    html = html_de(_sesion(produccion, usuario, rol, cliente), "/cliente/acme")
    assert '<html lang="en">' in html
    ids = tuple(i for i in PESTANAS if f'id="{i}"' in html)
    assert {"tab-creativeflowplus", "tab-final", "tab-settings", "sidebar"} <= set(ids)
    # Una pestaña nueva (como la de Triple Whale, que llegó con una fusión de
    # main) entra a la barrida por construcción: si la página trae un
    # id="tab-…" que PESTANAS no conoce, se avisa en vez de dejarlo sin mirar.
    pestanas_de_la_pagina = set(re.findall(r'<section id="(tab-[a-z0-9_-]+)"', html))
    assert pestanas_de_la_pagina <= set(PESTANAS), sorted(pestanas_de_la_pagina - set(PESTANAS))
    fugas = espanol_visible(html, ids)
    assert not fugas, fugas[:20]


@pytest.mark.parametrize("url", ["/panel", "/admin/meta", "/admin/referentes", "/admin/salud", "/admin/salud/registros", "/admin/estilos",
                                 "/admin/cobros"])
def test_paginas_de_admin_en_ingles_sin_idioma_guardado(produccion, url):
    fugas = espanol_visible(html_de(_sesion(produccion, "admin", "admin", None), url))
    assert not fugas, (url, fugas[:15])


def test_salud_con_un_404_medido_sigue_en_ingles(produccion):
    """PND-280: si antes corrió una petición sin ruta (un 404), /admin/salud la lista
    con su etiqueta traducida, no con «(sin ruta)» en español (fallaba según el orden)."""
    import monitoreo
    monitoreo.METRICAS.reiniciar()
    c = _sesion(produccion, "admin", "admin", None)
    assert c.get("/no-existe-pnd-280").status_code == 404
    html = html_de(c, "/admin/salud")
    assert "(sin ruta)" not in html and "(no route)" in html
    fugas = espanol_visible(html)
    assert not fugas, fugas[:15]
    monitoreo.METRICAS.reiniciar()


@pytest.mark.parametrize("url", ["/", "/login", "/recuperar", "/privacidad", "/terminos", "/eliminar-datos"])
def test_paginas_publicas_en_ingles_sin_cookie(produccion, url):
    fugas = espanol_visible(html_de(produccion.app.test_client(), url))
    assert not fugas, (url, fugas[:15])
