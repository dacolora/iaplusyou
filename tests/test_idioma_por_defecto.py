"""Inglés por defecto para todos (decisión de Daniel, 2026-09-28; spec
2026-09-26-idioma-y-modo-oscuro §B2-§B3): `idiomas.py` trae de fábrica
DEFECTO="en" y ACTIVO_PARA_TODOS=True, aunque `tests/conftest.py` los fija en
"es"/False (autouse) para que la suite existente —que compara textos en
español— no se rompa. Este archivo prueba el comportamiento REAL sin
depender de ese pin: `test_valores_de_fabrica` lee el código fuente de
idiomas.py directo (nunca el módulo ya importado, que a esta altura del test
run puede tener el pin puesto), y el resto vuelve a poner los valores reales
con monkeypatch (se deshace solo al terminar cada test, como ya hacen
tests/test_rutas_idioma.py y el resto de esta suite)."""
import ast
import os

import pytest

import idiomas
from tests.test_i18n_fugas import app_i18n  # noqa: F401  (fixture)

RUTA_IDIOMAS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "idiomas.py")


def _valores_de_fabrica():
    """DEFECTO/ACTIVO_PARA_TODOS tal como quedan escritos en idiomas.py (ast
    sobre el archivo, no import): así el resultado nunca depende de qué
    monkeypatch de otro test siga vivo sobre el módulo en sys.modules."""
    with open(RUTA_IDIOMAS, encoding="utf-8") as f:
        cuerpo = ast.parse(f.read()).body
    valores = {}
    for nodo in cuerpo:
        si_es_constante = isinstance(nodo, ast.Assign) and isinstance(nodo.targets[0], ast.Name) \
            and isinstance(nodo.value, ast.Constant)
        if si_es_constante:
            valores[nodo.targets[0].id] = nodo.value.value
    return valores


def test_valores_de_fabrica():
    valores = _valores_de_fabrica()
    assert valores["DEFECTO"] == "en"
    assert valores["ACTIVO_PARA_TODOS"] is True


def _sesion(dashboard, usuario, rol, cliente):
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = usuario
        s["rol"] = rol
        s["cliente"] = cliente
    return c


@pytest.fixture()
def produccion(app_i18n, monkeypatch):
    """Vuelve a poner los valores reales de producción (DEFECTO="en",
    ACTIVO_PARA_TODOS=True) por encima del pin de tests/conftest.py, solo
    para los tests de este archivo."""
    monkeypatch.setattr(idiomas, "DEFECTO", "en")
    monkeypatch.setattr(idiomas, "ACTIVO_PARA_TODOS", True)
    return app_i18n


def test_cliente_sin_idioma_guardado_ve_ingles_y_el_selector(produccion):
    """USUARIOS_PRUEBA["user_acme"] (tests/conftest.py) no trae campo
    "idioma": con los valores reales cae a inglés, como cualquier cliente que
    no haya elegido idioma el día del cambio. Ve su selector de cuenta pero
    NO el del proyecto (eso lo sigue eligiendo el admin, spec §B3)."""
    html = _sesion(produccion, "user_acme", "cliente", "acme").get("/cliente/acme").get_data(as_text=True)
    assert '<html lang="en">' in html
    assert 'id="config-idioma"' in html
    assert 'id="config-idioma-proyecto"' not in html


def test_visitante_anonimo_ve_ingles_y_los_enlaces(produccion):
    """Sin sesión ni cookie, /login cae a DEFECTO (ahora inglés) y muestra
    los enlaces «English · Español» — visibles solo con ACTIVO_PARA_TODOS
    (spec §B3)."""
    c = produccion.app.test_client()
    html = c.get("/login").get_data(as_text=True)
    assert '<html lang="en">' in html
    assert 'class="idioma-enlaces"' in html
    assert ">English<" in html and ">Español<" in html


def test_registro_sin_cookie_guarda_ingles(produccion, monkeypatch):
    """dashboard.crear_proyecto: con ACTIVO_PARA_TODOS real y sin cookie de
    idioma, `elegido = idiomas.normalizar(cookie) or idiomas.DEFECTO` cae al
    DEFECTO real (inglés), tanto para la cuenta como para el proyecto
    recién creado."""
    monkeypatch.setattr(produccion, "BASE_DIR", str(produccion.proyectos.BASE_DIR))
    c = produccion.app.test_client()
    r = c.post("/proyectos/nuevo", data={"nombre": "Nueva Marca", "usuario": "nueva",
                                          "correo": "nueva@prueba.local", "password": "una-clave-larga-123"})
    assert r.status_code == 302
    assert idiomas.de_usuario("nueva") == "en"
    assert idiomas.de_proyecto("nueva_marca") == "en"


def test_quien_eligio_espanol_sigue_en_espanol(produccion):
    """Aunque el DEFECTO real sea inglés, un usuario con idioma guardado
    ("es") nunca lo pierde: `de_usuario` siempre prefiere el campo guardado
    sobre DEFECTO."""
    idiomas.guardar_de_usuario("user_acme", "es")
    html = _sesion(produccion, "user_acme", "cliente", "acme").get("/cliente/acme").get_data(as_text=True)
    assert '<html lang="es">' in html
