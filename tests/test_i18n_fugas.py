"""Pantallas en inglés sin español visible (spec 2026-09-26 §Pruebas). Render
real: atrapa también los textos que vienen de Python (flash, nombres de
constantes, tarjetas de llaves). Cada tarea que traduce una pantalla agrega su
test aquí."""
import json
import re

import pytest

import idiomas
from tests.i18n_util import _con_marca, espanol_visible

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
    # Void element with matching id must have its attributes inspected
    assert espanol_visible('<input id="campo" placeholder="Escribe aquí">', ("campo",)) == ["Escribe aquí"]


def test_deteccion_exige_que_el_id_pedido_exista():
    # Un id renombrado (o que nunca existió) no debe pasar en silencio: sin
    # esto p.region terminaba en 0 tanto si el id se encontró y se cerró bien
    # como si nunca apareció, así que la guardia de una región nunca fallaba.
    with pytest.raises(AssertionError):
        espanol_visible('<div id="otro">x</div>', ("no-existe",))


@pytest.mark.parametrize("url", ["/", "/login", "/recuperar", "/privacidad", "/terminos", "/eliminar-datos"])
def test_publicas_en_ingles(publico_en, url):
    fugas = espanol_visible(html_de(publico_en, url))
    assert not fugas, f"{url}: {fugas[:15]}"


def test_restablecer_en_ingles(publico_en):
    import cuentas
    token = cuentas.emitir("restablecer", "admin", "admin@prueba.local")
    fugas = espanol_visible(html_de(publico_en, f"/restablecer/{token}"))
    assert not fugas, fugas[:15]


def test_panel_en_ingles(admin_en):
    fugas = espanol_visible(html_de(admin_en, "/panel"))
    assert not fugas, fugas[:15]


def test_esqueleto_del_proyecto_en_ingles(admin_en):
    fugas = espanol_visible(html_de(admin_en, "/cliente/acme"), ("sidebar", "barra-superior"))
    assert not fugas, fugas[:15]


def test_config_puesta_y_conexiones_admin(admin_en):
    fugas = espanol_visible(html_de(admin_en, "/cliente/acme"), ("config-ap-puesta", "config-ap-conexiones"))
    assert not fugas, fugas[:15]


def test_config_conexiones_cliente(cliente_en):
    fugas = espanol_visible(html_de(cliente_en, "/cliente/acme"), ("config-ap-conexiones",))
    assert not fugas, fugas[:15]


def test_configuracion_entera_admin(admin_en):
    fugas = espanol_visible(html_de(admin_en, "/cliente/acme"), ("tab-settings",))
    assert not fugas, fugas[:15]


def test_configuracion_entera_cliente(cliente_en):
    fugas = espanol_visible(html_de(cliente_en, "/cliente/acme"), ("tab-settings",))
    assert not fugas, fugas[:15]


def test_bloqueo_cambio_forma_en_ingles_y_espanol_intacto(app_i18n, monkeypatch):
    """El aviso de _bloqueo_cambio_forma (Configuración > Meta, mostrado dentro
    de config-ap-conexiones vía _meta_conectar.html y en los flash de
    meta_forma/meta_agencia_salir) va con ngettext/gettext desde 6e5c9... — se
    prueba la función directo (más liviano que armar un experimento vivo de
    verdad + una publicación orgánica en_cola solo para renderizar la página):
    en español (sin catálogo) tiene que salir BYTE a byte igual que antes de
    envolverla, y en inglés no puede dejar ninguna marca de español."""
    monkeypatch.setattr(app_i18n.experimentos, "cargar", lambda cliente: [{"estado": "corriendo"}])
    monkeypatch.setattr(app_i18n.organico, "listar", lambda cliente: [{"estado": "en_cola"}, {"estado": "en_cola"}])

    with idiomas.en_idioma("es"):
        es = app_i18n._bloqueo_cambio_forma("acme")
    assert es == "Termina o cierra primero: 1 experimento vivo · 2 publicaciones en curso"

    with idiomas.en_idioma("en"):
        en = app_i18n._bloqueo_cambio_forma("acme")
    assert not _con_marca(en), en
    assert en == "Finish or close first: 1 live experiment · 2 posts in progress"

    # Un solo caso (singular real, no monkeypatch de una lista con un elemento
    # cualquiera) para que la concordancia "1 ... vivo" / "1 live experiment"
    # (sin la "s") quede probada de verdad, no solo el plural.
    monkeypatch.setattr(app_i18n.organico, "listar", lambda cliente: [])
    with idiomas.en_idioma("es"):
        es_singular = app_i18n._bloqueo_cambio_forma("acme")
    assert es_singular == "Termina o cierra primero: 1 experimento vivo"
    with idiomas.en_idioma("en"):
        en_singular = app_i18n._bloqueo_cambio_forma("acme")
    assert en_singular == "Finish or close first: 1 live experiment"


_ONSUBMIT_FORM_LOGO = re.compile(
    r'<form[^>]*action="[^"]*logos/[^"]*eliminar[^"]*"[^>]*onsubmit=([\'"])(.*?)\1', re.S)


def test_logo_quitar_onsubmit_bien_formado(app_i18n, tmp_path):
    """Regresión (task-6 fix round 1): `onsubmit="return confirm({{ ... |
    tojson }});"` con el atributo entre comillas dobles se rompe — tojson
    emite comillas dobles, que cierran el atributo a la mitad y el manejador
    nunca compila (ni el confirm sale, en ningún idioma). Con un logo
    presente, comprueba que el atributo va entre comillas simples y que
    adentro hay un `confirm("...")` con un string JSON válido, en español Y
    en inglés.

    OJO: `_tab_catalogo.html` tiene un panel «logo» DUPLICADO (mismo
    `eliminar_logo`, mismo `nombre`) con un `onsubmit` hardcodeado en español
    sin `tojson` — no forma parte de este bug (no usa tojson) y cliente.html
    renderiza las dos pestañas en la misma página, así que el texto sale dos
    veces; por eso se acota la búsqueda al recorte de `config-ap-marca`
    (Configuración › Marca), que es la única instancia que toca esta task."""
    carpeta = tmp_path / "clientes" / "acme" / "logos"
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "logo1.png").write_bytes(b"fake-png")

    for idioma in ("es", "en"):
        idiomas.guardar_de_usuario("admin", idioma)
        c = app_i18n.app.test_client()
        with c.session_transaction() as s:
            s["usuario"] = "admin"
            s["rol"] = "admin"
            s["cliente"] = None
        html = html_de(c, "/cliente/acme")
        recorte = html[html.index('id="config-ap-marca"'):html.index('id="config-ap-generacion"')]
        m = _ONSUBMIT_FORM_LOGO.search(recorte)
        assert m, f"[{idioma}] no encontré el <form> de Quitar logo con onsubmit en Configuración > Marca"
        comillas, contenido = m.group(1), m.group(2)
        assert comillas == "'", f"[{idioma}] el atributo onsubmit debe ir con comillas simples: {contenido!r}"
        cm = re.fullmatch(r"return confirm\((\".*\")\);", contenido, re.S)
        assert cm, f"[{idioma}] onsubmit mal formado (falta confirm(...); dentro del mismo atributo): {contenido!r}"
        json.loads(cm.group(1))  # el argumento de confirm() tiene que ser un string JSON válido
