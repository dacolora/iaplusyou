"""Los precios que se ven (cobros, spec 2026-10-08 §6): en un proyecto que
cobra, todo «≈ US$» y toda tarifa que el navegador usa para calcular es precio
(costo × margen); `gastos.estimar(...)["usd"]` sigue siendo el costo."""
import re

import pytest

MARGEN = 1.5


@pytest.fixture()
def libro(base_temporal):
    from cobros import libro as mod
    return mod


def _cobra(libro, cliente="acme", milesimas=0):
    import db
    libro.configurar(cliente, usuario="admin", cobrar=True, margen=MARGEN)
    if milesimas:
        with db.conectar() as con:
            libro.acreditar(con, cliente, "ajuste", milesimas, "ajuste", usuario="admin", detalle="prueba")


@pytest.fixture()
def pagina(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import proyectos
    import referencias_flowplus
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    monkeypatch.setattr(referencias_flowplus, "listar", lambda c: [])
    dashboard.app.config["TESTING"] = True

    def cliente_como(usuario="user_acme", rol="cliente", proyecto="acme"):
        c = dashboard.app.test_client()
        with c.session_transaction() as s:
            s["usuario"] = usuario; s["rol"] = rol; s["cliente"] = proyecto
        return c
    return cliente_como


@pytest.fixture()
def app_config(base_temporal, tmp_path, monkeypatch):
    from tests.test_rutas_configuracion import app as fixture_config
    return fixture_config.__wrapped__(base_temporal, tmp_path, monkeypatch)


def _num(v):
    """Como Jinja pinta el número que devuelve el filtro."""
    return str(round(v, 6))


# --- gastos ---------------------------------------------------------------------------------

def test_estimar_dentro_de_una_peticion_trae_costo_y_precio():
    import dashboard
    import gastos
    from flask import g
    with dashboard.app.test_request_context("/cliente/acme"):
        g.margen_precio = MARGEN
        e = gastos.estimar("guion")
    assert e["usd"] == gastos.TARIFAS["guion"]                   # el costo: lo usan reservas y el libro
    assert e["usd_precio"] == round(0.13 * MARGEN, 4)
    assert gastos.formatear(0.13 * MARGEN) in e["texto"]
    assert gastos.formatear(0.13) not in e["texto"]


def test_fuera_de_una_peticion_no_hay_margen():
    import gastos
    e = gastos.estimar("guion")
    assert e["usd"] == e["usd_precio"] == gastos.TARIFAS["guion"]
    assert gastos.formatear(0.13) in e["texto"]
    assert gastos.margen_vigente() == 1.0


def test_sin_precio_sigue_sin_precio():
    import dashboard
    import gastos
    from flask import g
    with dashboard.app.test_request_context("/cliente/acme"):
        g.margen_precio = MARGEN
        e = gastos.estimar("no_existe")
    assert e["usd"] is None and e["usd_precio"] is None and e["texto"] == "precio no disponible"


def test_el_margen_se_lee_una_vez_por_peticion(libro, monkeypatch):
    import dashboard
    import gastos
    from flask import g
    _cobra(libro)
    llamadas = []
    original = libro.margen_precio
    monkeypatch.setattr(libro, "margen_precio", lambda c: (llamadas.append(c), original(c))[1])
    with dashboard.app.test_request_context("/cliente/acme"):
        g.cliente_precio = "acme"
        assert gastos.margen_vigente() == MARGEN
        gastos.estimar("guion"); gastos.estimar("final", paises=2); gastos.texto_precio(1)
    assert llamadas == ["acme"]


def test_el_filtro_precio_multiplica_sin_formatear():
    import dashboard
    from flask import g, render_template_string
    with dashboard.app.test_request_context("/cliente/acme"):
        g.margen_precio = MARGEN
        assert render_template_string("{{ 0.13|precio }}|{{ none|precio }}|{{ ''|precio }}") == "0.195|None|"
        assert render_template_string("{{ 0.13|precio|usd }}") == "US$ 0,20"


# --- la página: humo obligatorio del §6 ------------------------------------------------------

def _atributo(html, nombre, modelo):
    m = re.search(r'value="%s"[^>]*?%s="([^"]*)"' % (re.escape(modelo), re.escape(nombre)), html)
    assert m, f"no encontré {nombre} de {modelo}"
    return m.group(1)


@pytest.mark.parametrize("usuario,rol,proyecto", [("user_acme", "cliente", "acme"), ("admin", "admin", None)])
def test_un_proyecto_que_cobra_muestra_precios_y_no_costos(libro, pagina, usuario, rol, proyecto):
    from providers import flowplus_modelos
    _cobra(libro, milesimas=50_000)
    html = pagina(usuario, rol, proyecto).get("/cliente/acme").get_data(as_text=True)
    wan = flowplus_modelos.VIDEO["wan3"]
    costo_seg = wan["usd_por_segundo_efectivo"]
    assert _atributo(html, "data-usd-seg", "wan3") == _num(costo_seg * MARGEN)
    assert f'data-usd-seg="{costo_seg}"' not in html
    assert f"${costo_seg * MARGEN:.3f}/s" in html and f"${costo_seg:.3f}/s" not in html
    recargo = wan["audio_nativo"]["recargo_usd_s"]
    assert _atributo(html, "data-recargo", "wan3") == _num(recargo * MARGEN)
    seedream = next(iter(flowplus_modelos.IMAGEN))
    costo_img = flowplus_modelos.IMAGEN[seedream]["usd"]
    assert _atributo(html, "data-usd", seedream) == _num(costo_img * MARGEN)
    assert f"${costo_img * MARGEN:.3f}" in html
    from providers import fal_audio
    assert f'data-usd-caracter="{_num(fal_audio.COSTO_USD_POR_CARACTER * MARGEN)}"' in html


def test_un_proyecto_que_no_cobra_muestra_lo_de_hoy(libro, pagina):
    from providers import flowplus_modelos
    html = pagina().get("/cliente/acme").get_data(as_text=True)
    wan = flowplus_modelos.VIDEO["wan3"]
    costo_seg = wan["usd_por_segundo_efectivo"]
    assert _atributo(html, "data-usd-seg", "wan3") == _num(costo_seg)
    assert f"${costo_seg:.3f}/s" in html


def test_el_guion_y_las_finales_muestran_el_precio(libro, app_config, monkeypatch):
    """El «≈» del guion (detalle de Final edition, por fetch) y el de cada final."""
    import creative_flow as cf
    from tests.test_rutas_final_edition import GUION_BASE
    _cobra(libro, milesimas=50_000)
    monkeypatch.setattr(app_config["dashboard"].trabajos, "encolar", lambda *a, **k: True)
    cf_id = cf.crear("acme", [], ["Chancla"], [], "camina", 8, "", "A")
    cf.actualizar("acme", cf_id, estado="video_listo", video_url="https://r2/clon.mp4", enfoque="producto", usd=0.85)
    ruta = f"/cliente/acme/creative_flow/{cf_id}/final/detalle"
    detalle = app_config["c"].get(ruta).data.decode()
    assert "Preparar guion con IA ≈ US$ 0,20" in detalle            # 0,13 × 1,5
    cf.guardar_guion_base("acme", cf_id, GUION_BASE)
    detalle = app_config["c"].get(ruta).data.decode()
    assert ">Producir finales ≈ US$ 0,30 c/u</button>" in detalle   # 0,20 × 1,5


def test_la_comparacion_de_proveedores_no_la_ve_el_cliente_de_un_proyecto_que_cobra(libro, pagina):
    assert 'Ver por qué usamos estos modelos' in pagina().get("/cliente/acme").get_data(as_text=True)
    _cobra(libro, milesimas=50_000)
    assert 'Ver por qué usamos estos modelos' not in pagina().get("/cliente/acme").get_data(as_text=True)
    assert 'Ver por qué usamos estos modelos' in pagina("admin", "admin", None).get("/cliente/acme").get_data(as_text=True)


def test_las_tarifas_escritas_en_configuracion_llevan_el_margen(libro, pagina):
    from providers import fal_audio, flowplus_modelos, wavespeed_imagen
    import gastos
    _cobra(libro, milesimas=50_000)
    html = pagina().get("/cliente/acme").get_data(as_text=True)
    assert f"(+{gastos.formatear(wavespeed_imagen.COSTO_USD_UPSCALE * MARGEN)}, solo aplica a fotos)" in html
    assert f"{gastos.formatear(fal_audio.COSTO_USD_POR_PISTA_MUSICA * MARGEN)} solo la primera vez" in html
    recargo = flowplus_modelos.VIDEO["kling_o3_pro"]["audio_nativo"]["recargo_usd_s"] * MARGEN
    assert f"Kling cobra US$ {recargo:.3f}".replace(".", ",") + " por segundo más" in html
    assert "0,028" not in html and "+$0.04" not in html and "USD 0,02" not in html


# --- lo que vuelve del navegador es costo ---------------------------------------------------

@pytest.fixture()
def hablado_app(libro, monkeypatch, tmp_path):
    from tests.test_rutas_hablado import app as fixture_hablado
    return fixture_hablado.__wrapped__(None, monkeypatch, tmp_path)


def test_anuncio_hablado_muestra_el_precio_y_cobra_desde_el_costo(libro, hablado_app, monkeypatch):
    """La voz responde `precio_video` con margen (hablado.js lo pinta y lo
    devuelve como `precio_visto`); crear lo vuelve costo antes de comparar con
    `hablado.crear_pieza` y de pedir saldo: nada se margina dos veces."""
    import hablado_rutas
    from tests.test_hablado import _foto_subida, _voz
    _cobra(libro, milesimas=50_000)
    pedidos = []
    original = hablado_rutas.libro.exigir
    monkeypatch.setattr(hablado_rutas.libro, "exigir", lambda c, usd: (pedidos.append(usd), original(c, usd))[1])
    _voz(texto="Hola mundo")
    d = hablado_app["c"].post("/cliente/acme/hablado/voz", headers={"X-Requested-With": "fetch"},
                              data={"texto": "Hola mundo", "voz": "Rachel", "idioma": "es", "velocidad": "normal"}).get_json()
    assert d["voz"]["precio_video"] == 0.3                                       # 0,20 × 1,5
    m, v = _foto_subida(), _voz()
    base = {"foto": f"mat:{m['id']}", "voz_hash": v["hash"], "movimiento": ""}
    r = hablado_app["c"].post("/cliente/acme/hablado/crear", headers={"X-Requested-With": "fetch"},
                              data={**base, "precio_visto": "0.2"})                # el costo NO es lo que vio
    assert r.status_code == 409 and "El precio cambió" in r.get_json()["error"]
    r = hablado_app["c"].post("/cliente/acme/hablado/crear", headers={"X-Requested-With": "fetch"},
                              data={**base, "precio_visto": str(d["voz"]["precio_video"])})
    assert r.status_code == 200 and r.get_json()["ok"]
    assert pedidos[-1] == pytest.approx(0.2)                                     # exigir recibe el costo


def test_sin_cobros_el_anuncio_hablado_sigue_igual(hablado_app):
    from tests.test_hablado import _foto_subida, _voz
    m, v = _foto_subida(), _voz()
    r = hablado_app["c"].post("/cliente/acme/hablado/crear", headers={"X-Requested-With": "fetch"},
                              data={"foto": f"mat:{m['id']}", "voz_hash": v["hash"], "movimiento": "", "precio_visto": "0.2"})
    assert r.status_code == 200


def test_la_cadena_de_escenas_compara_el_costo_y_avisa_con_el_precio():
    """`total_visto` viaja como costo en data-gpg-cuerpo; solo el texto lleva margen."""
    import re as _re
    src = open("templates/_gpg_cadena.html", encoding="utf-8").read()
    assert '"total_visto": C.precio}' in src and '"total_visto": f.rehacer_precio}' in src
    assert len(_re.findall(r"\(C\.precio \| precio\)", src)) == 2


# --- Nicho: el texto con margen, la cifra que vuelve como costo -----------------------------

@pytest.fixture()
def nicho_app(libro, monkeypatch, tmp_path):
    from tests.test_rutas_nicho import app as fixture_nicho
    monkeypatch.setenv("APIFY_TOKEN", "t")
    monkeypatch.setenv("YOUTUBE_API_KEY", "k")
    return fixture_nicho.__wrapped__(None, monkeypatch, tmp_path)


def test_nicho_estimados_muestran_precio_y_devuelven_costo(libro, nicho_app):
    import gastos
    from nicho import datos
    _cobra(libro, milesimas=50_000)
    c = nicho_app["c"]
    eid = datos.crear_estudio("acme", "X", tema="pantuflas", pais="SE")
    d = c.get(f"/cliente/acme/nicho/{eid}/recolectar/apify/estimar?actor=tiktok_comentarios&max=400").get_json()
    assert d["usd"] == 0.5 and d["texto"] == gastos.formatear(0.5 * MARGEN)
    d = c.get(f"/cliente/acme/nicho/{eid}/investigacion/estimar?pais=SE&plataformas=amazon&consultas=2").get_json()
    assert d["texto"] == gastos.formatear(d["total_usd"] * MARGEN)             # se ve el precio…
    assert d["claude_texto"] == gastos.formatear(d["claude_usd"] * MARGEN)
    # …y `total_usd` (lo que el formulario manda como `total_visto`) sigue siendo el costo recalculable
    from nicho import investigacion
    e = investigacion.estimar(datos.estudio("acme", eid), "SE", ["amazon"], [], investigacion.normalizar_topes({"consultas": 2}))
    assert d["total_usd"] == e["total_usd"]
