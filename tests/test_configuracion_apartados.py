"""Parte 3a de la mejora visual (spec 2026-09-26): Configuración en apartados
y Crear sin «Nueva idea»."""
from tests.test_rutas_referentes import app  # noqa: F401  (fixture: admin en /cliente/acme)


def _pestana(html, tab):
    ini = html.index(f'<section id="tab-{tab}"')
    sig = html.find('<section id="tab-', ini + 10)
    return html[ini:sig if sig > 0 else len(html)]


def test_crear_ya_no_muestra_nueva_idea(app):
    crear = _pestana(app["c"].get("/cliente/acme").data.decode(), "creativeflowplus")
    assert "<h2>Nueva idea</h2>" not in crear and "nueva_idea" not in crear
