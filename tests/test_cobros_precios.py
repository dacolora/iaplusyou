"""Los precios que se ven (cobros, spec 2026-10-08 §6): en un proyecto que
cobra, todo «≈ US$» y toda tarifa que el navegador usa para calcular es precio
(costo × margen); `gastos.estimar(...)["usd"]` sigue siendo el costo."""
import re

import pytest

from tests.test_rutas_guiones_pipeline import catalogo_vacio, subidas  # noqa: F401 — fixtures

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


@pytest.mark.parametrize("usuario,rol,proyecto", [("user_acme", "cliente", "acme"), ("admin", "admin", None)])
def test_evaluar_con_ia_de_meta_muestra_el_precio_y_lo_cobrado_nunca_el_costo(libro, pagina, monkeypatch, usuario,
                                                                               rol, proyecto):
    """El panel de la pestaña Meta (por fetch, no viene en la página): el botón «Evaluar con IA» y su `precio_visto`
    llevan el margen; lo ya gastado de una evaluación es lo cobrado para el cliente. Y lo que manda el botón es lo que
    la ruta acepta: crea la evaluación y reserva el precio."""
    import dashboard
    import db
    import gastos
    import sqlalchemy as sa
    from meta_rendimiento import analisis, datos
    from tests.test_rutas_meta_rendimiento import A, _hace, _sembrar
    monkeypatch.setattr(dashboard.meta_conexion, "cargar",
                        lambda c: {"token": "tok-prueba", "ad_account_id": A, "page_id": None})
    _cobra(libro, milesimas=50_000)
    _sembrar()
    eid = datos.crear_evaluacion("acme", [A], _hace(29), _hace(0), "SEK", [], [], extra={"cuenta": None})
    datos.actualizar_evaluacion(eid, estado="lista", usd=0.2, resultado={
        "resumen": "Va bien.", "plan": [{"prioridad": 1, "accion": "revisar", "objetos": [], "que_hacer": "Mira",
                                         "por_que": "", "impacto": None, "enlace": None}]})
    gastos.registrar("acme", "evaluacion", 0.2, f"meta_eval:{eid}:t1")     # costo 0,20 → cobrado 0,30
    c = pagina(usuario, rol, proyecto)
    html = c.get("/cliente/acme/meta-rendimiento/panel").get_data(as_text=True)
    n = len(analisis.preparar("acme", 30, "")["muestra"])
    costo = gastos.estimar("evaluacion_meta", n=n)["usd"]
    assert f'name="precio_visto" value="{round(costo * MARGEN, 4)}"' in html
    assert f"Evaluar {n} anuncio(s) con IA · {gastos.formatear(costo * MARGEN)}" in html
    assert gastos.formatear(costo) not in html and f'value="{costo}"' not in html
    cabecera = html[html.index(f'id="meta-eval-{eid}"'):]
    cabecera = cabecera[:cabecera.index("</p>")]
    if rol == "cliente":
        assert "US$ 0,30" in cabecera and "US$ 0,20" not in cabecera
    else:
        assert "US$ 0,20" in cabecera
    campos = dict(re.findall(r'<input type="hidden" name="([a-z_]+)" value="([^"]*)"',
                             html[html.index('id="meta-evaluacion"'):html.index("</form>", html.index('id="meta-evaluacion"'))]))
    assert c.post("/cliente/acme/meta-rendimiento/evaluar", data=campos).status_code == 302
    with db.conectar() as con:
        reserva, = con.execute(sa.select(db.reserva_saldo)).mappings().all()
    assert reserva["job_id"] == "acme__meta_eval" and reserva["milesimas"] == libro.precio_milesimas(costo, MARGEN)


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
    assert f"Kling: US$ {recargo:.3f}".replace(".", ",") + " más por segundo" in html
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


# --- Nicho: el texto con margen, la cifra que vuelve como costo -----------------------------

@pytest.fixture()
def nicho_app(libro, monkeypatch, tmp_path):
    from tests.test_rutas_nicho import app as fixture_nicho
    monkeypatch.setenv("APIFY_TOKEN", "t")
    monkeypatch.setenv("YOUTUBE_API_KEY", "k")
    return fixture_nicho.__wrapped__(None, monkeypatch, tmp_path)


def _exigidos(monkeypatch, modulo):
    """Lo que `modulo.libro.exigir` recibe (sin cambiar lo que hace)."""
    pedidos = []
    original = modulo.libro.exigir
    monkeypatch.setattr(modulo.libro, "exigir", lambda c, usd, **k: (pedidos.append(usd), original(c, usd, **k))[1])
    return pedidos


def _como_user_acme(c):
    with c.session_transaction() as s:
        s["usuario"] = "user_acme"; s["rol"] = "cliente"; s["cliente"] = "acme"
    return c


def test_nicho_al_navegador_solo_precios_y_al_libro_el_costo(libro, nicho_app, monkeypatch):
    import gastos
    from nicho import avatares, datos, investigacion
    from nicho import rutas as nicho_rutas
    _cobra(libro, milesimas=50_000)
    c = _como_user_acme(nicho_app["c"])
    eid = datos.crear_estudio("acme", "X", tema="pantuflas", pais="SE")
    d = c.get(f"/cliente/acme/nicho/{eid}/recolectar/apify/estimar?actor=tiktok_comentarios&max=400").get_json()
    assert d["usd"] == 0.75 and d["texto"] == gastos.formatear(0.5 * MARGEN)    # costo 0,50: no llega
    d = c.get(f"/cliente/acme/nicho/{eid}/investigacion/estimar?pais=SE&plataformas=amazon&consultas=2").get_json()
    e = investigacion.estimar(datos.estudio("acme", eid), "SE", ["amazon"], [], investigacion.normalizar_topes({"consultas": 2}))
    assert d["total_usd"] == round(e["total_usd"] * MARGEN, 4) and d["texto"] == gastos.formatear(e["total_usd"] * MARGEN)
    assert d["claude_usd"] == round(e["claude_usd"] * MARGEN, 4) and d["avatares_usd"] == round(e["avatares_usd"] * MARGEN, 4)
    assert d["filas"][0]["busqueda_usd"] == round(e["filas"][0]["busqueda_usd"] * MARGEN, 4)
    # Iniciar con el precio visto: arranca y el libro recibe el COSTO
    pedidos = _exigidos(monkeypatch, nicho_rutas)
    monkeypatch.setattr(nicho_rutas.tareas_investigacion, "avanzar", lambda c_, e_: None)
    r = c.post(f"/cliente/acme/nicho/{eid}/investigacion",
               data={"pais": "SE", "plataformas": "amazon", "consultas": "2", "total_visto": str(d["total_usd"])})
    assert r.status_code == 302 and pedidos == [pytest.approx(e["total_usd"])]
    assert datos.investigacion("acme", eid).get("estado")                       # arrancó
    # Completar avatares: el hidden lleva el precio; con él se encola, con el costo no
    monkeypatch.setattr(avatares, "estimar_completar", lambda cl, ei: {"usd": 0.4, "avatares": 2})
    html = c.get(f"/cliente/acme/nicho/{eid}").get_data(as_text=True)
    assert 'name="total_visto"' in html, "el formulario de completar no se pintó"
    assert 'name="total_visto" value="0.6"' in html and 'value="0.4"' not in html
    encolados = []
    monkeypatch.setattr(nicho_rutas.tareas_nicho, "encolar_completar",
                        lambda cl, ei, costo_estimado=None: encolados.append(costo_estimado) or True)
    datos.actualizar_investigacion("acme", eid, lambda i: {**i, "estado": "lista"})
    c.post(f"/cliente/acme/nicho/{eid}/completar", data={"total_visto": "0.4"})  # el costo NO es lo que vio
    assert encolados == []
    c.post(f"/cliente/acme/nicho/{eid}/completar", data={"total_visto": "0.6"})
    assert encolados == [0.4]


@pytest.fixture()
def editor_app(libro, monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "clave-de-prueba-larga-1234567890")
    import dashboard
    import trabajos
    dashboard.app.config["TESTING"] = True
    monkeypatch.setattr(trabajos, "encolar", lambda *a, **k: True)
    return dashboard


def test_editor_estimados_solo_con_precio(libro, editor_app):
    import gastos
    from tests.test_rutas_editor import _edicion
    _cobra(libro, milesimas=50_000)
    ed, _c, _v = _edicion()
    c = _como_user_acme(editor_app.app.test_client())
    j = c.post(f"/cliente/acme/ediciones/{ed['id']}/voz/estimar",
               json={"texto": "Hola mundo", "voz": "Rachel", "idioma": "es", "velocidad": "normal"}).get_json()
    costo = gastos.estimar("voz_editor", caracteres=len("Hola mundo"))["usd"]
    assert j["usd"] == round(costo * MARGEN, 4) and j["usd"] != costo
    assert j["precio"] == gastos.formatear(costo * MARGEN) + " aprox."


@pytest.fixture()
def pipeline(libro, monkeypatch, tmp_path):
    from tests.test_rutas_guiones_pipeline import app as fixture_pipeline
    return fixture_pipeline.__wrapped__(None, monkeypatch, tmp_path)


def test_cadena_de_escenas_ve_el_precio_y_cobra_el_costo(libro, pipeline, monkeypatch, catalogo_vacio, subidas):
    import re as _re

    from guiones import cadena, datos
    from guiones import rutas_pipeline
    from tests.test_rutas_guiones_pipeline import BASE, _con_imagenes, _video_armado
    gid, vid = _video_armado(pipeline)
    _con_imagenes(pipeline, vid, subidas)
    _cobra(libro, milesimas=50_000)
    c = _como_user_acme(pipeline["c"])
    costo = cadena.precio(datos.video("acme", vid))
    html = c.get(f"{BASE}/panel?guion={gid}&video={vid}").get_data(as_text=True)
    vistos = [float(x) for x in _re.findall(r'&#34;total_visto&#34;: ([0-9.]+)|"total_visto": ([0-9.]+)', html) for x in x if x]
    assert vistos == [round(costo * MARGEN, 6)]                                  # al navegador, solo el precio
    assert f"{costo * MARGEN:.2f}" in html
    pedidos = _exigidos(monkeypatch, rutas_pipeline)
    r = c.post(f"{BASE}/videos/{vid}/cadena", json={"total_visto": costo})        # el costo NO es lo que vio
    assert r.status_code == 409 and r.get_json()["precio"] == round(costo * MARGEN, 4) and pedidos == []
    r = c.post(f"{BASE}/videos/{vid}/cadena", json={"total_visto": vistos[0]})
    assert r.status_code == 202, r.get_json()
    assert pedidos and all(p == pytest.approx(costo) for p in pedidos)          # la ruta y el encolar: costo
    assert cadena.estado(datos.video("acme", vid))["aprobado_usd"] == costo


def test_el_filtro_no_se_congela_al_compilar(libro):
    """Jinja pliega al compilar los filtros sobre constantes: la MISMA plantilla
    compilada, pintada con dos márgenes, tiene que dar dos cifras."""
    import dashboard
    from flask import g
    plantilla = dashboard.app.jinja_env.from_string("{{ 2|precio }}|{% if margen_precio() == 1 %}sin{% else %}con{% endif %}")
    with dashboard.app.test_request_context("/cliente/acme"):
        g.margen_precio = MARGEN
        assert plantilla.render() == "3.0|con"
    with dashboard.app.test_request_context("/cliente/acme"):
        g.margen_precio = 1.0
        assert plantilla.render() == "2.0|sin"


def test_si_el_margen_no_se_puede_leer_el_precio_no_cae_al_costo(libro, monkeypatch):
    """Revisión final 2026-10-08 (M1): una lectura del margen que falla da
    «precio no disponible», nunca el costo con cara de precio. El costo
    (`usd`) sigue ahí para las reservas y el libro."""
    import dashboard
    import gastos
    from flask import g
    _cobra(libro)
    monkeypatch.setattr(libro, "margen_precio", lambda c: (_ for _ in ()).throw(RuntimeError("base caída")))
    with dashboard.app.test_request_context("/cliente/acme"):
        g.cliente_precio = "acme"
        e = gastos.estimar("guion")
        texto = gastos.texto_precio(0.13)
    assert e["usd"] == gastos.TARIFAS["guion"]
    assert e["usd_precio"] is None and e["texto"] == "precio no disponible"
    assert texto == "precio no disponible"
