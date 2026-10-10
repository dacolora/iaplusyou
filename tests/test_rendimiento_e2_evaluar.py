"""«Evaluar con IA» de Triple Whale en la pestaña Rendimiento (`POST /rendimiento/evaluar`, E2 tarea 5).

Una tienda de Triple Whale en Noruega (USD) y una cuenta de Meta en Suecia (SEK), las mismas de las pruebas de la
galería única. E2 tarea 5 había hecho que esta ruta evaluara también los anuncios de Meta (un botón por fuente, la marca
`extra["fuente"] = "meta"`); al integrar main (2026-10-10, INT-2) esa rama se jubiló en favor de la «Evaluación con IA»
de Meta rendimiento E2 (la de producción: `meta_rendimiento.rutas.evaluar`, sus pruebas en
`tests/test_rendimiento_meta_e2.py` y `tests/test_rutas_meta_rendimiento.py`). Esta ruta queda para la parte Triple
Whale del alcance: la muestra se vuelve a armar con `panel.alcances` (lo que se cobra es lo que se vio), el pedido es
`triple_whale.pedidos.pedir_evaluacion` (precio a la vista, Cobros antes de crear nada, `max_intentos=1`, una por
proyecto) y exige correo verificado. Claude, Meta y R2 nunca se llaman de verdad."""
import pytest

import db
import gastos
import proyectos
from meta_rendimiento import cuentas as mcuentas
from meta_rendimiento import datos as mdatos
from tests.test_rendimiento_e2_galeria import SE, TOKEN, _cobra, _hace, _sembrar
from tests.test_rutas_configuracion import app  # noqa: F401  (fixture)
from tests.test_rutas_meta_rendimiento import _ad, _dia, _tasa
from tests.test_rutas_triple_whale import _tareas, lo_que_manda_el_boton
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


def _evaluar(app, fuente, entrada="", follow=True, cliente=None, boton=None, **headers):  # noqa: F811
    """Postea lo que manda el botón de esa entrada (`boton`: otros `n`/`precio_visto`, para probar la guarda G3)."""
    c = cliente or app["c"]
    boton = lo_que_manda_el_boton(c, entrada) if boton is None else boton
    return c.post(URL, data=dict({"fuente": fuente, "entrada": entrada, "dias": "0", "canal": ""}, **boton),
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


# ------------------------------------------------------------------------------------- Triple Whale ---

def test_la_entrada_de_triple_whale_ofrece_solo_su_boton(mixto):
    _sembrar()
    forms = _formularios(_panel(mixto, "NO"))
    assert [f for f, _ in forms] == ["tw"] and "Evaluar 2 anuncio(s) con IA" in forms[0][1]
    assert 'name="entrada" value="NO"' in forms[0][1]


def test_en_la_mezcla_un_solo_boton_el_de_tus_tiendas_y_la_evaluacion_de_meta_aparte(mixto):
    """«Todas» con una tienda y una cuenta sin tienda: «Lo que hace ganar en tu cuenta» ofrece el botón de Triple Whale
    (y dice que mira las tiendas) y la de las cuentas de Meta es la sección «Evaluación con IA» de Meta rendimiento E2,
    que postea a su ruta con la entrada: nunca un prompt con las dos fuentes."""
    _sembrar()
    html = _panel(mixto)
    forms = _formularios(html)
    assert [f for f, _ in forms] == ["tw"]
    precio = _precio(2)["texto"]
    assert f"Evaluar 2 anuncio(s) con IA · {precio}" in forms[0][1] and 'name="entrada" value=""' in forms[0][1]
    assert "La evaluación con IA mira los anuncios de tus tiendas en Triple Whale." in _seccion_ia(html)
    assert "de tus cuentas de Meta" not in _seccion_ia(html) and "Triple Whale y Meta miden distinto" not in html
    ini = html.index('id="meta-evaluacion"')
    meta = html[ini:html.index("</section>", ini)]
    assert 'action="/cliente/acme/meta-rendimiento/evaluar"' in meta and 'name="entrada" value=""' in meta
    assert "/triple-whale/evaluar" not in html


def test_en_la_mezcla_el_boton_de_tus_tiendas_evalua_solo_triple_whale(mixto, vivos):
    """Como hoy: sin `fuente` (se lee como Triple Whale) y con la tienda del alcance (con una sola, esa). Un segundo
    envío no crea otra (una por proyecto)."""
    tid = _sembrar()
    _evaluar(mixto, "tw")
    [fila] = twdatos.evaluaciones("acme")
    assert {a["ad_id"] for a in fila["anuncios"]} == {"t1", "t2"} and fila["moneda"] == "USD"
    assert fila["extra"].get("fuente") is None and fila["extra"]["tienda_id"] == tid and fila["extra"]["pais"] == "NO"
    assert fila["extra"]["modelo"] == "Triple Attribution" and "cuentas" not in fila["extra"]
    [tarea] = _tareas("tw_evaluar")
    assert tarea["max_intentos"] == 1
    assert "Ya hay una evaluación con IA en curso" in _evaluar(mixto, "tw").data.decode()
    assert len(twdatos.evaluaciones("acme")) == 1 and len(_tareas("tw_evaluar")) == 1


def test_sin_saldo_no_crea_nada(mixto):
    _sembrar()
    _cobra()
    html = _evaluar(mixto, "tw", entrada="NO").data.decode()
    assert "Saldo insuficiente" in html and "Recargar saldo" in html
    assert twdatos.evaluaciones("acme") == [] and _tareas("tw_evaluar") == []


def test_evaluar_compara_el_numero_y_el_precio_que_mostro_el_boton(mixto, vivos):
    """G3 (revisión final de Rendimiento E2, guardián de gasto, 2026-10-10): la guarda E2-R6 de la evaluación de Meta
    también para la de Triple Whale. El botón manda cuántos anuncios mostró (`n`) y el precio que vio la persona
    (`precio_visto`); si falta alguno o no coincide con lo que la ruta calcula al llegar, no se crea ni se encola nada y
    el aviso dice el precio de ahora. Con lo que mandó el botón, sí."""
    _sembrar()
    boton = lo_que_manda_el_boton(mixto["c"], "NO")
    assert boton["n"] == "2" and float(boton["precio_visto"]) == pytest.approx(_precio(2)["usd"])
    aviso = f"Revisa el precio y vuelve a confirmar: ahora son 2 anuncio(s) por {_precio(2)['texto']}."
    for cambio in ({"n": "3"}, {"precio_visto": "0.01"}, {"n": ""}, {"precio_visto": ""}, {"precio_visto": "abc"}):
        html = _evaluar(mixto, "tw", entrada="NO", boton=dict(boton, **cambio)).data.decode()
        assert aviso in html, cambio
        assert twdatos.evaluaciones("acme") == [] and _tareas("tw_evaluar") == []
    assert aviso in _evaluar(mixto, "tw", entrada="NO", boton={}).data.decode()        # un formulario viejo, sin campos
    assert twdatos.evaluaciones("acme") == []
    assert "Evaluando 2 anuncio(s) con IA" in _evaluar(mixto, "tw", entrada="NO", boton=boton).data.decode()
    assert len(twdatos.evaluaciones("acme")) == 1 and len(_tareas("tw_evaluar")) == 1


def test_con_margen_el_boton_manda_el_precio_nunca_el_costo_y_la_ruta_lo_acepta(mixto):
    """Un proyecto que cobra: `precio_visto` es el precio con el margen (vuelve a costo una sola vez en la ruta)."""
    _sembrar()
    libro = _cobra(100_000)
    boton = lo_que_manda_el_boton(mixto["c"], "NO")
    margen = libro.margen_precio("acme")
    assert margen != 1 and float(boton["precio_visto"]) == pytest.approx(_precio(2)["usd"] * margen, abs=1e-4)
    assert "Evaluando 2 anuncio(s) con IA" in _evaluar(mixto, "tw", entrada="NO", boton=boton).data.decode()
    assert len(twdatos.evaluaciones("acme")) == 1


def test_sin_triple_whale_no_hay_seccion_de_triple_whale(mixto):
    """Un proyecto solo Meta no tiene «Lo que hace ganar en tu cuenta» de Triple Whale: su evaluación es la de Meta."""
    _solo_meta()
    html = _panel(mixto)
    assert 'id="tw-ia"' not in html and 'id="meta-evaluacion"' in html


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


def test_el_prompt_de_una_evaluacion_de_triple_whale_sigue_igual(mixto, tarea_sin_red):
    t, recibido = tarea_sin_red
    _sembrar()
    _evaluar(mixto, "tw", entrada="NO")
    [fila] = twdatos.evaluaciones("acme")
    t.tw_evaluar({"id": 6, "payload": {"cliente": "acme", "evaluacion_id": fila["id"]}})
    assert "con sus métricas de Triple Whale del" in recibido["texto"]
    [g] = _gastos()
    assert g["referencia"] == f"tw_eval:{fila['id']}:t6" and "de Triple Whale" in g["detalle"]


# --------------------------------------------------------------------------------- la muestra ---

def test_la_muestra_de_triple_whale_no_cambia():
    """Con el orden de Triple Whale (veredicto, ingresos, gasto) la muestra son los primeros, como siempre (la de main:
    el reordenamiento por ingresos de E2 tarea 5 se jubiló con su rama Meta)."""
    lista = [anuncio(f"g{i}", gasto=100 + 10 * i, pedidos=5, ingresos=1000 - 50 * i) for i in range(7)]
    lista += [anuncio(f"p{i}", gasto=400 + i) for i in range(2)]
    ev = evaluacion.evaluar(lista, reglas=REGLAS)
    antes = [a["ad_id"] for a in ev["anuncios"] if a["veredicto"] in ("ganador", "prometedor")][:analisis.MAX_BUENOS]
    assert [a["ad_id"] for a in analisis.muestra(ev)][:analisis.MAX_BUENOS] == antes


# ---------------------------------------------------------------------------------------- seguridad ---

def test_un_post_de_otro_sitio_es_403_y_no_crea_nada(mixto):
    _sembrar()
    r = _evaluar(mixto, "tw", entrada="NO", follow=False, **{"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403 and twdatos.evaluaciones("acme") == [] and _tareas("tw_evaluar") == []


def test_sin_correo_verificado_un_cliente_no_evalua(mixto):
    import usuarios
    from tests.test_rutas_meta_rendimiento import _como_cliente
    _sembrar()
    usuarios.actualizar("user_acme", correo_verificado=False)
    r = _evaluar(mixto, "tw", entrada="NO", follow=False, cliente=_como_cliente(mixto))
    assert r.status_code == 302 and r.headers["Location"].endswith("#settings")
    assert twdatos.evaluaciones("acme") == [] and _tareas("tw_evaluar") == []


def test_otro_proyecto_no_evalua(mixto):
    from tests.test_rutas_meta_rendimiento import _como_cliente
    _sembrar()
    r = _evaluar(mixto, "tw", entrada="NO", follow=False, cliente=_como_cliente(mixto, usuario="otro",
                                                                                 cliente="otro"))
    assert r.status_code in (302, 403, 404) and twdatos.evaluaciones("acme") == []


def test_la_fuente_meta_o_una_rara_es_404_y_una_entrada_vieja_no_crea_nada(mixto):
    """`fuente=meta` ya no es de esta ruta (INT-2): 404 sin leer nada; una entrada que ya no existe no se ensancha."""
    _sembrar()
    assert _evaluar(mixto, "meta", entrada="SE", follow=False).status_code == 404
    assert _evaluar(mixto, "otra", entrada="NO", follow=False).status_code == 404
    html = _evaluar(mixto, "tw", entrada="DK").data.decode()          # un país que ya no está: no se ensancha
    assert "Esa vista ya no existe" in html
    html = _evaluar(mixto, "tw", entrada="SE").data.decode()          # Suecia no tiene tienda
    assert "Esa vista ya no existe" in html
    assert twdatos.evaluaciones("acme") == [] and _tareas("tw_evaluar") == []


def test_la_ruta_vieja_de_triple_whale_ya_no_existe(mixto):
    _sembrar()
    r = mixto["c"].post("/cliente/acme/triple-whale/evaluar", data={"dias": "0"}, headers=POST)
    assert r.status_code in (404, 405) and twdatos.evaluaciones("acme") == []
