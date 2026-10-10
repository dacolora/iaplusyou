"""Rendimiento E2 (5/7): «Evaluar con IA» también para los anuncios de Meta (spec 2026-10-09 §6 E2 y A6; PND-192).

Una tienda de Triple Whale en Noruega (USD) y una cuenta de Meta en Suecia (SEK), las mismas de las pruebas de la
galería única. La evaluación de los anuncios de Meta usa la misma fila (`tw_evaluacion`), el mismo pedido
(`triple_whale.pedidos.pedir_evaluacion`: precio a la vista, Cobros antes de crear nada, `max_intentos=1`, una por
proyecto) y la misma tarea (`tw_evaluar`), con la marca `extra["fuente"] = "meta"` para que el prompt diga «de Meta».
Con el alcance mezclado hay DOS botones, uno por fuente: los números de Triple Whale y los del Pixel de Meta no se
comparan en un mismo prompt. Claude, Meta y R2 nunca se llaman de verdad."""
import logging

import pytest

import db
import gastos
import proyectos
from meta_rendimiento import cuentas as mcuentas
from meta_rendimiento import datos as mdatos
from tests.test_rendimiento_e2_galeria import SE, TOKEN, _cobra, _hace, _sembrar
from tests.test_rutas_configuracion import app  # noqa: F401  (fixture)
from tests.test_rutas_meta_rendimiento import _ad, _dia, _tasa
from tests.test_rutas_triple_whale import _tareas
from tests.test_triple_whale_analisis import respuesta
from tests.test_triple_whale_evaluacion import REGLAS, anuncio
from triple_whale import analisis, evaluacion
from triple_whale import datos as twdatos

POST = {"Sec-Fetch-Site": "same-origin"}
URL = "/cliente/acme/rendimiento/evaluar"


@pytest.fixture(autouse=True)
def _aislado(tmp_path, monkeypatch):
    """Preferencias y aprendizajes viven en clientes/<c>/proyecto.json: que las pruebas no escriban en el repo."""
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))


@pytest.fixture()
def mixto(app, monkeypatch):  # noqa: F811
    """Meta conectado (solo métricas, sin cuenta de lanzamiento) además de lo que el proyecto tenga de Triple Whale."""
    monkeypatch.setattr(app["dashboard"].meta_conexion, "cargar", lambda c: {"token": TOKEN, "page_id": None})
    with app["dashboard"].app.test_request_context():
        yield app


@pytest.fixture()
def vivos(monkeypatch):
    """`trabajos.en_curso` de verdad (la fixture `app` lo apaga): una tarea pendiente o en curso está viva."""
    import cola
    import trabajos
    monkeypatch.setattr(trabajos, "en_curso", lambda job_id: (cola.consultar_por_job(job_id) or {}).get("estado")
                        in ("pendiente", "en_curso"))


def _solo_meta():
    """Un proyecto sin Triple Whale: la cuenta de Suecia con m1 y m2 (y un anuncio de muy pocos datos)."""
    mcuentas.elegir("acme", [{"id": SE, "name": "HappyFlops Sweden", "currency": "SEK", "pais": "SE"}])
    for n in range(5):
        f = _hace(n)
        mdatos.reemplazar_cuenta_dias("acme", SE, f, f, [_dia(f, 700, 1400, compras=3)])
        _tasa(f, 0.1, "SEK")
        mdatos.reemplazar_anuncio_dias("acme", SE, f, f, [_ad(f, "m1", 200, 400, compras=1),
                                                          _ad(f, "m2", 500, 1000, compras=1),
                                                          dict(_ad(f, "mn", 1, 0), impresiones=20)])


def _evaluar(app, fuente, entrada="", follow=True, cliente=None, **headers):  # noqa: F811
    c = cliente or app["c"]
    return c.post(URL, data={"fuente": fuente, "entrada": entrada, "dias": "0", "canal": ""},
                  headers=dict(POST, **headers), follow_redirects=follow)


def _panel(app, entrada=""):  # noqa: F811
    return app["c"].get(f"/cliente/acme/rendimiento/panel?entrada={entrada}").data.decode()


def _seccion_ia(html):
    ini = html.index('id="tw-ia"')
    return html[ini:html.index("</section>", ini)]


def _formularios(html):
    """[(fuente, html del formulario)] de «Evaluar con IA» en la sección."""
    ia = _seccion_ia(html)
    salida = []
    for trozo in ia.split("<form")[1:]:
        trozo = trozo.split("</form>")[0]
        if 'name="fuente"' in trozo:
            fuente = trozo.split('name="fuente" value="')[1].split('"')[0]
            salida.append((fuente, trozo))
    return salida


def _precio(n):
    return gastos.estimar("evaluacion_tw", n=n)


# ----------------------------------------------------------------------------------------- solo Meta ---

def test_solo_meta_crea_la_evaluacion_con_su_extra_su_precio_y_su_cobro(mixto, vivos):
    """La entrada de Suecia (solo Meta): la muestra sale del alcance de Meta, la fila guarda `extra` con la fuente y
    las cuentas, se reserva el precio que vio la persona y la tarea corre una vez."""
    _sembrar()
    libro = _cobra()
    usd = _precio(2)["usd"]
    with db.conectar() as con:
        libro.acreditar(con, "acme", "ajuste", libro.precio_milesimas(usd, libro.margen_precio("acme")), "ajuste",
                        usuario="admin", detalle="prueba")
    html = _evaluar(mixto, "meta", entrada="SE").data.decode()
    assert "Evaluando 2 anuncio(s) con IA" in html
    [fila] = twdatos.evaluaciones("acme")
    assert fila["estado"] == "en_cola" and fila["moneda"] == "SEK" and fila["pedido_por"] == "admin"
    assert {a["ad_id"] for a in fila["anuncios"]} == {"m1", "m2"}                 # ni t1 ni t2 (Noruega)
    assert {a["canal"] for a in fila["anuncios"]} == {"facebook-ads"}
    extra = fila["extra"]
    assert extra["fuente"] == "meta" and extra["cuentas"] == [SE] and extra["pais"] == "SE"
    assert extra["modelo"] == "Pixel de Meta" and extra["ventana"] == "Meta" and extra["tienda_id"] is None
    assert "benchmarks" in extra and "meta_roas" in extra
    [tarea] = _tareas("tw_evaluar")
    assert tarea["max_intentos"] == 1 and tarea["payload"] == {"cliente": "acme", "evaluacion_id": fila["id"]}
    assert libro.disponible("acme") == 0                       # reservó exactamente el precio del botón
    # Un segundo clic no crea otra ni cobra; tampoco una de Triple Whale mientras corre (una por proyecto).
    for fuente, entrada in (("meta", "SE"), ("tw", "NO")):
        html = _evaluar(mixto, fuente, entrada=entrada).data.decode()
        assert "Ya hay una evaluación con IA en curso" in html
    assert len(twdatos.evaluaciones("acme")) == 1 and len(_tareas("tw_evaluar")) == 1


def test_la_entrada_de_meta_ofrece_un_boton_con_su_precio(mixto):
    _sembrar()
    forms = _formularios(_panel(mixto, "SE"))
    assert [f for f, _ in forms] == ["meta"]
    _, form = forms[0]
    assert 'action="/cliente/acme/rendimiento/evaluar"' in form and 'name="entrada" value="SE"' in form
    precio = _precio(2)["texto"]
    assert f"Evaluar 2 anuncio(s) con IA · {precio}" in form and "aprox." in precio
    assert "/triple-whale/evaluar" not in _panel(mixto, "SE")


def test_sin_saldo_no_crea_nada(mixto):
    _sembrar()
    _cobra()
    html = _evaluar(mixto, "meta", entrada="SE").data.decode()
    assert "Saldo insuficiente" in html and "Recargar saldo" in html
    assert twdatos.evaluaciones("acme") == [] and _tareas("tw_evaluar") == []


def test_un_proyecto_sin_triple_whale_evalua_sus_anuncios_de_meta(mixto, vivos):
    """Sin Triple Whale la sección igual aparece (antes solo existía con tiendas), con su barra mientras corre, y la
    evaluación lista dice que es de Meta y de qué país, no «Todas las tiendas»."""
    _solo_meta()
    forms = _formularios(_panel(mixto))
    assert [f for f, _ in forms] == ["meta"] and "Evaluar 2 anuncio(s) con IA" in forms[0][1]
    _evaluar(mixto, "meta")
    [fila] = twdatos.evaluaciones("acme")
    assert fila["extra"]["fuente"] == "meta" and fila["extra"]["pais"] == "SE" and fila["extra"]["cuentas"] == [SE]
    ia = _seccion_ia(_panel(mixto))
    assert 'data-poll-job="acme__tw_evaluar"' in ia and _formularios(_panel(mixto)) == []
    twdatos.actualizar_evaluacion(fila["id"], estado="lista", usd=0.1,
                                  resultado=analisis.parsear(respuesta(), {a["ref"] for a in fila["anuncios"]}, ""))
    _tarea_terminada()
    ia = _seccion_ia(_panel(mixto))
    cab = ia[ia.index('class="tw-eval-cab"'):][:400]
    assert "Suecia en Meta" in cab and "Todas las tiendas" not in cab
    assert "Caja que se abre sola" in ia and "Llevar a Crear" in ia


def _tarea_terminada():
    """La tarea de evaluar ya no está viva (terminó): la sección vuelve a ofrecer los botones."""
    import sqlalchemy as sa
    with db.conectar() as con:
        con.execute(sa.delete(db.tarea).where(db.tarea.c.tipo == "tw_evaluar"))


# ------------------------------------------------------------------------------------------- mezcla ---

def test_la_mezcla_ofrece_dos_botones_cada_uno_con_su_precio(mixto):
    """«Todas» con una tienda y una cuenta sin tienda: un botón por fuente, nunca uno que mezcle las dos."""
    _sembrar()
    html = _panel(mixto)
    forms = dict(_formularios(html))
    assert set(forms) == {"tw", "meta"}
    precio = _precio(2)["texto"]
    assert f"Evaluar los 2 de tus tiendas · {precio}" in forms["tw"]
    assert f"Evaluar los 2 de tus cuentas de Meta · {precio}" in forms["meta"]
    assert "de tus tiendas con IA? Costo:" in forms["tw"] and "de tus cuentas de Meta con IA? Costo:" in forms["meta"]
    for form in forms.values():
        assert 'action="/cliente/acme/rendimiento/evaluar"' in form and 'name="entrada" value=""' in form
    assert "Triple Whale y Meta miden distinto" in _seccion_ia(html)
    assert "/triple-whale/evaluar" not in html


def test_en_la_mezcla_el_boton_de_tus_tiendas_evalua_solo_triple_whale(mixto):
    """Como hoy: sin `fuente` (se lee como Triple Whale) y con la tienda del alcance (con una sola, esa)."""
    tid = _sembrar()
    _evaluar(mixto, "tw")
    [fila] = twdatos.evaluaciones("acme")
    assert {a["ad_id"] for a in fila["anuncios"]} == {"t1", "t2"} and fila["moneda"] == "USD"
    assert fila["extra"].get("fuente") is None and fila["extra"]["tienda_id"] == tid and fila["extra"]["pais"] == "NO"
    assert fila["extra"]["modelo"] == "Triple Attribution" and "cuentas" not in fila["extra"]


def test_en_la_mezcla_el_boton_de_meta_evalua_solo_las_cuentas_sin_tienda(mixto):
    _sembrar()
    _evaluar(mixto, "meta")
    [fila] = twdatos.evaluaciones("acme")
    assert {a["ad_id"] for a in fila["anuncios"]} == {"m1", "m2"} and fila["moneda"] == "SEK"
    assert fila["extra"]["fuente"] == "meta" and fila["extra"]["cuentas"] == [SE] and fila["extra"]["pais"] is None


def test_la_entrada_de_triple_whale_ofrece_solo_su_boton(mixto):
    _sembrar()
    forms = _formularios(_panel(mixto, "NO"))
    assert [f for f, _ in forms] == ["tw"] and "Evaluar 2 anuncio(s) con IA" in forms[0][1]
    assert 'name="entrada" value="NO"' in forms[0][1]


# --------------------------------------------------------------------------------------- la tarea ---

@pytest.fixture()
def tarea_sin_red(monkeypatch):
    """La tarea sin Meta, R2 ni Claude de verdad: el contenido que recibiría Claude queda en `recibido`."""
    from tareas import triple_whale as t
    monkeypatch.setattr(t.trabajos, "reportar", lambda *a, **k: None)
    monkeypatch.setattr(analisis, "medios_meta", lambda cliente, anuncios: {})
    monkeypatch.setattr(analisis, "system", lambda idioma: "SYSTEM")
    recibido = {}

    def _llamar(content, system_):
        recibido["texto"] = content[0]["text"]
        return respuesta(), 1000, 500
    monkeypatch.setattr(analisis, "_llamar", _llamar)
    return t, recibido


def _gastos():
    import sqlalchemy as sa
    with db.conectar() as con:
        return [dict(r._mapping) for r in con.execute(sa.select(db.gasto.c.tipo, db.gasto.c.referencia,
                                                                db.gasto.c.detalle))]


def test_el_prompt_de_una_evaluacion_de_meta_dice_de_meta(mixto, tarea_sin_red):
    t, recibido = tarea_sin_red
    _sembrar()
    _evaluar(mixto, "meta", entrada="SE")
    [fila] = twdatos.evaluaciones("acme")
    t.tw_evaluar({"id": 5, "payload": {"cliente": "acme", "evaluacion_id": fila["id"]}})
    assert "con sus métricas de Meta del" in recibido["texto"] and "de Triple Whale" not in recibido["texto"]
    assert "moneda SEK" in recibido["texto"] and "«Pixel de Meta»" in recibido["texto"]
    assert twdatos.evaluacion("acme", fila["id"])["estado"] == "lista"
    [g] = _gastos()
    assert g["tipo"] == "evaluacion" and g["referencia"] == f"tw_eval:{fila['id']}:t5" and "de Meta" in g["detalle"]


def test_el_prompt_de_una_evaluacion_de_triple_whale_sigue_igual(mixto, tarea_sin_red):
    t, recibido = tarea_sin_red
    _sembrar()
    _evaluar(mixto, "tw", entrada="NO")
    [fila] = twdatos.evaluaciones("acme")
    t.tw_evaluar({"id": 6, "payload": {"cliente": "acme", "evaluacion_id": fila["id"]}})
    assert "con sus métricas de Triple Whale del" in recibido["texto"]
    assert "de Triple Whale" in _gastos()[0]["detalle"]


# ------------------------------------------------------------------------------------ las miniaturas ---

def test_medios_meta_lee_con_el_token_de_la_conexion_sin_cuenta_de_lanzamiento(monkeypatch, caplog):
    """Un proyecto «solo métricas» (sin Página ni cuenta de lanzamiento) también lee las miniaturas: el token sale de
    `meta_conexion.cargar`, no de `credenciales_ads`. Una miniatura que no es de un host de Meta no se usa, y el token
    no llega a ningún registro."""
    import meta_conexion

    def _exige_lanzamiento(cliente):
        raise meta_conexion.MetaConexionError("falta la cuenta de lanzamiento")
    monkeypatch.setattr(meta_conexion, "credenciales_ads", _exige_lanzamiento)
    monkeypatch.setattr(meta_conexion, "cargar", lambda c: {"token": "EAAB-llave-de-prueba", "page_id": None})
    tokens = []

    def _graph(ruta, token, params):
        tokens.append(token)
        if ruta == "ad_malo":
            raise RuntimeError("Meta respondió 400")
        if ruta == "ad_otro_host":
            return {"thumbnail_url": "https://evil.example/t.jpg", "title": "X", "body": "Y"}
        return {"thumbnail_url": "https://scontent.xx.fbcdn.net/t.jpg", "title": "T", "body": "B",
                "object_type": "VIDEO"}
    monkeypatch.setattr(analisis, "_graph", _graph)
    with caplog.at_level(logging.INFO):
        medios = analisis.medios_meta("acme", [{"canal": "facebook-ads", "ad_id": "a1", "creative_id": "cr1"},
                                               {"canal": "facebook-ads", "ad_id": "ad_malo", "creative_id": "ad_malo"},
                                               {"canal": "facebook-ads", "ad_id": "o1", "creative_id": "ad_otro_host"}])
    assert medios["a1"] == {"imagen": "https://scontent.xx.fbcdn.net/t.jpg", "titulo": "T", "texto": "B",
                            "tipo": "video"}
    assert medios["o1"]["imagen"] is None and "ad_malo" not in medios
    assert set(tokens) == {"EAAB-llave-de-prueba"} and "EAAB-llave-de-prueba" not in caplog.text


@pytest.mark.parametrize("conexion", [None, {}, {"token": ""}, {"page_id": None}])
def test_medios_meta_sin_token_no_falla(monkeypatch, conexion):
    import meta_conexion
    monkeypatch.setattr(meta_conexion, "cargar", lambda c: conexion)
    monkeypatch.setattr(analisis, "_graph", lambda *a: pytest.fail("sin token no se llama a Meta"))
    assert analisis.medios_meta("acme", [{"canal": "facebook-ads", "ad_id": "1"}]) == {}


def test_medios_meta_con_la_conexion_ilegible_no_falla(monkeypatch):
    import meta_conexion

    def _rota(cliente):
        raise ValueError("meta.json ilegible")
    monkeypatch.setattr(meta_conexion, "cargar", _rota)
    assert analisis.medios_meta("acme", [{"canal": "facebook-ads", "ad_id": "1"}]) == {}


# --------------------------------------------------------------------------------- la muestra ---

def _ganadores_por_gasto(n=7):
    """`n` ganadores donde el que más gasta es el que menos vende, ordenados como los ordena la copia de Meta
    (veredicto y gasto)."""
    lista = [anuncio(f"g{i}", gasto=100 + 10 * i, pedidos=5, ingresos=1000 - 50 * i) for i in range(n)]
    lista += [anuncio(f"p{i}", gasto=400 + i) for i in range(2)]
    ev = evaluacion.evaluar(lista, reglas=REGLAS)
    assert {a["veredicto"] for a in ev["anuncios"] if a["ad_id"].startswith("g")} == {"ganador"}
    orden = {v: i for i, v in enumerate(evaluacion.VEREDICTOS)}
    ev["anuncios"].sort(key=lambda a: (orden[a["veredicto"]], -a["m"]["gasto"], a["ad_id"]))
    return ev


def test_la_muestra_elige_los_ganadores_que_mas_venden_aunque_lleguen_por_gasto():
    """La copia de Meta ordena por veredicto y gasto; la muestra toma los ganadores por ingresos, como con Triple
    Whale: con 7 queda fuera el que menos vende (g6), no el que menos gasta (g0)."""
    m = analisis.muestra(_ganadores_por_gasto())
    buenos = [a["ad_id"] for a in m if a["veredicto"] == "ganador"]
    assert buenos == ["g0", "g1", "g2", "g3", "g4", "g5"] and m[0]["ref"] == "A1"


def test_la_muestra_de_triple_whale_no_cambia():
    """Con el orden de Triple Whale (veredicto, ingresos, gasto) la muestra es la de siempre: los primeros."""
    ev = _ganadores_por_gasto()
    orden = {v: i for i, v in enumerate(evaluacion.VEREDICTOS)}
    ev["anuncios"].sort(key=lambda a: (orden[a["veredicto"]], -a["m"]["ingresos"], -a["m"]["gasto"], a["ad_id"]))
    antes = [a["ad_id"] for a in ev["anuncios"] if a["veredicto"] in ("ganador", "prometedor")][:analisis.MAX_BUENOS]
    assert [a["ad_id"] for a in analisis.muestra(ev)][:analisis.MAX_BUENOS] == antes


# ---------------------------------------------------------------------------------------- seguridad ---

def test_un_post_de_otro_sitio_es_403_y_no_crea_nada(mixto):
    _sembrar()
    r = _evaluar(mixto, "meta", entrada="SE", follow=False, **{"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403 and twdatos.evaluaciones("acme") == [] and _tareas("tw_evaluar") == []


def test_sin_correo_verificado_un_cliente_no_evalua(mixto):
    import usuarios
    from tests.test_rutas_meta_rendimiento import _como_cliente
    _sembrar()
    usuarios.actualizar("user_acme", correo_verificado=False)
    r = _evaluar(mixto, "meta", entrada="SE", follow=False, cliente=_como_cliente(mixto))
    assert r.status_code == 302 and r.headers["Location"].endswith("#settings")
    assert twdatos.evaluaciones("acme") == [] and _tareas("tw_evaluar") == []


def test_otro_proyecto_no_evalua(mixto):
    from tests.test_rutas_meta_rendimiento import _como_cliente
    _sembrar()
    r = _evaluar(mixto, "meta", entrada="SE", follow=False, cliente=_como_cliente(mixto, usuario="otro",
                                                                                   cliente="otro"))
    assert r.status_code in (302, 403, 404) and twdatos.evaluaciones("acme") == []


def test_una_fuente_rara_o_una_entrada_vieja_no_crean_nada(mixto):
    _sembrar()
    assert _evaluar(mixto, "otra", entrada="SE", follow=False).status_code == 404
    html = _evaluar(mixto, "meta", entrada="DK").data.decode()          # un país que ya no está: no se ensancha
    assert "Esa vista ya no existe" in html
    html = _evaluar(mixto, "meta", entrada="NO").data.decode()          # Noruega no tiene cuentas sin tienda
    assert "Esa vista ya no existe" in html
    assert twdatos.evaluaciones("acme") == [] and _tareas("tw_evaluar") == []


def test_sin_meta_conectado_no_evalua_los_de_meta(app):  # noqa: F811
    with app["dashboard"].app.test_request_context():
        _sembrar()
    html = _evaluar(app, "meta", entrada="SE").data.decode()
    assert "Esa vista ya no existe" in html and twdatos.evaluaciones("acme") == []


def test_la_ruta_vieja_de_triple_whale_ya_no_existe(mixto):
    _sembrar()
    r = mixto["c"].post("/cliente/acme/triple-whale/evaluar", data={"dias": "0"}, headers=POST)
    assert r.status_code in (404, 405) and twdatos.evaluaciones("acme") == []
