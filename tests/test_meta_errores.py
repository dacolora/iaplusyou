"""Errores de Meta en palabras de persona (2026-09-28): la alerta del Tablero y la
tarjeta del experimento mostraban el JSON crudo que devuelve la Graph API."""
import pytest


def _crudo(cuerpo, edge="act_1/adcreatives", status=400):
    return f"Meta Ads ({edge}) respondió {status}: {cuerpo}"


# El texto real guardado en producción (experimento 2 de colorado_forja, cuenta anonimizada).
REAL_1885183 = _crudo(
    '{"error":{"message":"Invalid parameter","type":"OAuthException","code":100,"error_subcode":1885183,'
    '"is_transient":false,"error_user_title":"La publicaci\\u00f3n con contenido publicitario se cre\\u00f3 con '
    'una app que se encuentra en modo de desarrollo","error_user_msg":"La publicaci\\u00f3n con contenido '
    'publicitario se cre\\u00f3 con una app que se encuentra en modo de desarrollo. Debe estar en modo '
    'p\\u00fablico para crear este anuncio.","fbtrace_id":"AbC"}}')


@pytest.fixture(autouse=True)
def _contexto():
    import dashboard
    with dashboard.app.test_request_context():
        yield


def test_app_en_modo_desarrollo_dice_que_hacer():
    import meta_errores
    t = meta_errores.explicar(REAL_1885183)
    assert "modo Desarrollo" in t and "Live" in t and "{" not in t
    agencia = meta_errores.explicar(REAL_1885183, modo="agencia")
    assert "admin de Creatv" in agencia


def test_token_vencido_pide_reconectar():
    import meta_errores
    t = meta_errores.explicar(_crudo('{"error":{"message":"Error validating access token: Session has expired",'
                                     '"type":"OAuthException","code":190,"error_subcode":463}}'))
    assert "vuelve a conectar" in t and "Experimentos" in t and "{" not in t


def test_permisos_y_limite_de_llamadas():
    import meta_errores
    permiso = meta_errores.explicar(_crudo('{"error":{"message":"(#200) Permissions error","code":200}}'))
    assert "permiso" in permiso and "{" not in permiso
    limite = meta_errores.explicar(_crudo('{"error":{"message":"(#17) User request limit reached","code":17}}'))
    assert "unos minutos" in limite


def test_sin_caso_conocido_usa_las_palabras_de_meta():
    import meta_errores
    t = meta_errores.explicar(_crudo('{"error":{"message":"Invalid parameter","code":100,"error_subcode":99,'
                                     '"error_user_title":"Presupuesto muy bajo","error_user_msg":"El presupuesto '
                                     'diario debe ser mayor a 5 d\\u00f3lares."}}'))
    assert "Presupuesto muy bajo" in t and "5 dólares" in t and "{" not in t


def test_sin_palabras_de_meta_da_el_codigo():
    import meta_errores
    t = meta_errores.explicar(_crudo('{"error":{"message":"Invalid parameter","code":100,"error_subcode":77}}'))
    assert "100" in t and "Invalid parameter" in t and "{" not in t


def test_json_cortado_igual_se_entiende():
    """meta_ads.auth corta la respuesta a 500 caracteres: el JSON puede llegar roto."""
    import meta_errores
    cortado = REAL_1885183[:260]
    assert "{" in cortado and "1885183" in cortado
    t = meta_errores.explicar(cortado)
    assert "modo Desarrollo" in t and "{" not in t


def test_lo_que_no_es_de_meta_pasa_tal_cual():
    import meta_errores
    propio = "El experimento no tiene piezas: agrega al menos una antes de lanzar."
    assert meta_errores.explicar(propio) == propio
    assert meta_errores.explicar(None) == ""
    assert meta_errores.es_crudo(REAL_1885183) and not meta_errores.es_crudo(propio)


def test_el_lanzador_usa_el_mismo_traductor():
    import lanzador
    t = lanzador.traducir_error_meta(REAL_1885183)
    assert "modo Desarrollo" in t and "Live" in t


def test_tarjeta_del_experimento_muestra_el_error_claro_y_el_crudo_plegado(base_temporal, monkeypatch, tmp_path):
    from tests.test_rutas_referentes import app as _app_fixture  # noqa: F401
    import experimentos as ex
    from tests.test_experimentos_db import PAISES
    from tests.test_rutas_referentes import _cliente_admin
    import dashboard
    import meta_conexion
    monkeypatch.setattr(meta_conexion, "estado", lambda c: {"estado": "conectado", "detalle": {}, "verificado": True})
    monkeypatch.setattr(meta_conexion, "estado_pixel", lambda c, solo_cache=False: None)
    eid = ex.crear("acme", "Prueba 1", PAISES, "OUTCOME_TRAFFIC", 7, 500000.0, "https://t", "COP")
    ex.actualizar("acme", eid, estado="error", error=REAL_1885183)
    # E2: la tarjeta de gestión del experimento llega en el fragmento de resultados (`?exp=<id>`).
    from tests.test_rutas_experimentos import _resultados
    html = _resultados(_cliente_admin(dashboard), exp=eid)
    j = html.index('class="detalle-tecnico"')
    claro = html[html.rindex('<p class="tag-error">', 0, j):j]
    assert "modo Desarrollo" in claro and "OAuthException" not in claro
    assert "OAuthException" in html[j:j + 2000]            # el crudo sigue, plegado, para soporte


def test_el_mensaje_ya_explicado_se_vuelve_a_decir_en_el_idioma_de_quien_mira():
    """El lanzador guarda la explicación de 1885183 en el idioma del proyecto; al
    mostrarla en otro idioma se vuelve a armar (la reconoce por el subcódigo)."""
    import idiomas
    import meta_errores
    guardado = meta_errores.explicar(REAL_1885183)                       # español (tests)
    with idiomas.en_idioma("en"):
        otra = meta_errores.explicar(guardado)
    assert "Development mode" in otra and "modo Desarrollo" not in otra


REAL_URL_APP = _crudo(
    '{"error":{"message":"Invalid parameter","type":"OAuthException","code":100,"error_subcode":1815430,'
    '"is_transient":false,"error_user_title":"URL de la app no permitida","error_user_msg":"Solo puede incluirse '
    'la URL de la app con el objetivo de instalaciones de la app.","fbtrace_id":"AbC"}}')


def test_url_de_tienda_sin_objetivo_de_instalaciones_dice_que_hacer():
    import meta_errores
    t = meta_errores.explicar(REAL_URL_APP)
    assert "Instalaciones de la app" in t and "{" not in t and "OAuthException" not in t


def test_url_de_tienda_ya_explicada_se_vuelve_a_decir_en_ingles():
    import idiomas
    import meta_errores
    guardado = meta_errores.explicar(REAL_URL_APP)
    assert meta_errores.explicar(guardado) == guardado
    with idiomas.en_idioma("en"):
        otra = meta_errores.explicar(guardado)
    assert "App installs" in otra and "Instalaciones" not in otra
