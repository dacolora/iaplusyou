"""Rendimiento E2 (2/7): el pedido pagado de un análisis vive en `triple_whale/pedidos.py`.

Es una mudanza desde `triple_whale/rutas.py` para que la pestaña Rendimiento lo llame también con anuncios de Meta sin
copiarlo. Estas pruebas llaman a las funciones movidas directamente (sin ruta): conservan su contrato, `usuario` llega
explícito (el módulo no lee `session` ni hace `flash`) y siguen sin cobrar dos veces. Las pruebas de las rutas
(`test_tw_tarjetas_rutas.py`, `test_rutas_triple_whale.py`) siguieron igual, sin tocarlas, hasta E2 tarea 4: desde
entonces «Cómo mejorarlo» y el lote son rutas de la pestaña Rendimiento y esas pruebas apuntan allá."""
import ast
import inspect

import pytest
import sqlalchemy as sa

import db
import proyectos
from tests.test_i18n_mensajes import sueltos
from tests.test_rutas_configuracion import app  # noqa: F401  (fixture)
from tests.test_rutas_triple_whale import _conectar, _sembrar, _tareas
from tests.test_tw_mejorar import respuesta
from triple_whale import datos, mejorar, panel, pedidos


@pytest.fixture(autouse=True)
def _proyecto_aislado(tmp_path, monkeypatch):
    """El aprendizaje y las preferencias viven en clientes/<c>/proyecto.json: que las pruebas no escriban en el repo."""
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))


@pytest.fixture()
def peticion(app):  # noqa: F811
    """Los textos salen con gettext: se llaman dentro de una petición, como desde una ruta."""
    with app["dashboard"].app.test_request_context():
        yield app


def _jobs():
    return sorted(t["job_id"] for t in _tareas("tw_analizar_anuncio"))


def _filas_analisis():
    with db.conectar() as con:
        return con.execute(sa.select(sa.func.count()).select_from(db.tw_analisis)).scalar()


def _anuncio(alc, ad_id, canal="facebook-ads"):
    a = pedidos.anuncio_del_alcance(alc, canal, ad_id)
    assert a is not None, ad_id
    return a


# --- Humo: importan, firmas, y el módulo no toca la sesión ni los avisos -------------------------------------------

def test_las_funciones_movidas_importan_con_su_firma():
    firmas = {nombre: list(inspect.signature(getattr(pedidos, nombre)).parameters) for nombre in (
        "anuncio_del_alcance", "pedir_analisis", "claves_confirmadas", "pedir_lote", "pedir_evaluacion")}
    assert firmas == {"anuncio_del_alcance": ["alc", "canal", "ad_id"],
                      "pedir_analisis": ["cliente", "alc", "a", "usuario"],
                      "claves_confirmadas": ["valores", "tope"],
                      "pedir_lote": ["cliente", "alc", "claves", "usuario", "veredicto"],
                      "pedir_evaluacion": ["cliente", "alc_eval", "usuario"]}
    assert inspect.signature(pedidos.claves_confirmadas).parameters["tope"].default is None
    assert inspect.signature(pedidos.pedir_lote).parameters["veredicto"].default == ""


def test_el_dominio_no_lee_la_sesion_ni_avisa_y_las_rutas_ya_no_tienen_la_copia():
    """`usuario` llega explícito y los avisos y redirects se quedan en las rutas: el dominio devuelve textos y cuentas."""
    from triple_whale import rutas
    with open(pedidos.__file__, encoding="utf-8") as f:
        arbol = ast.parse(f.read())
    importados = {a.name for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom) and n.module == "flask"
                  for a in n.names}
    assert not importados & {"session", "flash", "redirect", "request", "url_for"}
    nombres = {n.id for n in ast.walk(arbol) if isinstance(n, ast.Name)}
    assert not nombres & {"session", "flash", "request"}
    # Una sola copia del pedido pagado: la de las rutas se fue. Desde E2 tarea 4 también las rutas de «Cómo mejorarlo»
    # y del lote (y el alias `_claves_confirmadas` de la prueba de B6): la galería única las tiene en la pestaña.
    assert not hasattr(rutas, "_pedir_analisis") and not hasattr(rutas, "_anuncio_del_alcance")
    for nombre in ("_claves_confirmadas", "galeria", "tarjeta", "analizar_anuncio", "analizar_lote"):
        assert not hasattr(rutas, nombre), nombre


def test_sus_textos_pasan_por_el_catalogo():
    """Al salir de `rutas.py` sus textos dejan la guardia de rutas: la misma guardia los mira aquí."""
    assert sueltos("triple_whale/pedidos.py", "rutas") == []
    assert sueltos("triple_whale/pedidos.py", "worker") == []


# --- Cada función, llamada directo -----------------------------------------------------------------------------------

def test_anuncio_del_alcance_busca_por_canal_y_id():
    alc = {"ev": {"anuncios": [{"canal": "facebook-ads", "ad_id": "1", "n": "a"},
                               {"canal": "tiktok-ads", "ad_id": "1", "n": "b"}]}}
    assert pedidos.anuncio_del_alcance(alc, "tiktok-ads", "1")["n"] == "b"
    assert pedidos.anuncio_del_alcance(alc, "facebook-ads", "1")["n"] == "a"
    assert pedidos.anuncio_del_alcance(alc, "facebook-ads", "2") is None


def test_claves_confirmadas_quita_repetidas_ignora_lo_mal_formado_y_para_en_el_tope():
    valores = ["facebook-ads:p1"] * 3000 + ["mal", "facebook-ads:a/b", ":p2", "facebook-ads:", None] + \
        [f"facebook-ads:x{i}" for i in range(50)]
    claves = pedidos.claves_confirmadas(valores)
    assert claves[0] == ("facebook-ads", "p1") and len(claves) == panel.N_LOTE == len(set(claves))
    assert claves[1:] == [("facebook-ads", f"x{i}") for i in range(panel.N_LOTE - 1)]
    assert pedidos.claves_confirmadas(["tiktok-ads:1", "tiktok-ads:1", "tiktok-ads:2"], tope=5) == \
        [("tiktok-ads", "1"), ("tiktok-ads", "2")]
    assert pedidos.claves_confirmadas(["tiktok-ads:1", "tiktok-ads:2"], tope=1) == [("tiktok-ads", "1")]


def test_pedir_analisis_no_cobra_sin_datos_ni_vivo_ni_fresco_y_guarda_quien_lo_pidio(peticion):
    _conectar()
    _sembrar()
    alc = panel.alcance("acme", 30)
    ok, mensaje = pedidos.pedir_analisis("acme", alc, _anuncio(alc, "n1"), "daniel")
    assert ok is False and "muy pocos datos" in mensaje and _jobs() == [] and _filas_analisis() == 0

    ok, mensaje = pedidos.pedir_analisis("acme", alc, _anuncio(alc, "p1"), "daniel")
    assert ok is True and "Anuncio p1" in mensaje
    [fila] = datos.ultimos_analisis("acme", [("facebook-ads", "p1")]).values()
    assert fila["pedido_por"] == "daniel" and fila["estado"] == "en_cola" and fila["foto"]["alcance_canal"] is None
    [t] = _tareas("tw_analizar_anuncio")
    assert t["job_id"] == "acme__tw_anuncio__facebook-ads__p1" and t["max_intentos"] == 1

    ok, mensaje = pedidos.pedir_analisis("acme", alc, _anuncio(alc, "p1"), "daniel")     # su tarea sigue viva
    assert ok is False and "ya se está analizando" in mensaje and len(_jobs()) == 1 and _filas_analisis() == 1

    # Termina con un análisis listo de este alcance: otra vez no se paga (A1), aunque la pestaña muestre el botón.
    datos.actualizar_analisis(fila["id"], estado="lista", usd=0.08, resultado=mejorar.parsear(respuesta(), "datos"),
                              medios={"visual": "fotogramas", "fotogramas": 6, "copy": True})
    with db.conectar() as con:
        con.execute(db.tarea.update().values(estado="hecha"))
    alc = panel.alcance("acme", 30)
    ok, mensaje = pedidos.pedir_analisis("acme", alc, _anuncio(alc, "p1"), "daniel")
    assert ok is False and "ya tiene un análisis con estos datos" in mensaje
    assert len(_jobs()) == 1 and _filas_analisis() == 1


def test_pedir_analisis_sin_saldo_no_guarda_nada(peticion):
    from cobros import SaldoInsuficiente, libro
    _conectar()
    _sembrar()
    libro.configurar("acme", usuario="admin", cobrar=True)
    alc = panel.alcance("acme", 30)
    with pytest.raises(SaldoInsuficiente):
        pedidos.pedir_analisis("acme", alc, _anuncio(alc, "p1"), "daniel")
    assert _jobs() == [] and _filas_analisis() == 0


def test_pedir_lote_cobra_solo_lo_confirmado_y_elegible_y_un_segundo_envio_no_cobra(peticion):
    _conectar()
    _sembrar()
    alc = panel.alcance("acme", 30)
    confirmadas = [("facebook-ads", "p1"), ("facebook-ads", "n1"), ("facebook-ads", "no-existe"),
                   ("facebook-ads", "p2")]
    assert pedidos.pedir_lote("acme", alc, confirmadas, "daniel") == (2, 0)      # n1 sin datos, el otro no está
    assert _jobs() == ["acme__tw_anuncio__facebook-ads__p1", "acme__tw_anuncio__facebook-ads__p2"]
    assert {f["pedido_por"] for f in datos.ultimos_analisis("acme", confirmadas).values()} == {"daniel"}
    alc = panel.alcance("acme", 30)
    assert pedidos.pedir_lote("acme", alc, confirmadas, "daniel") == (0, 0)      # el mismo formulario otra vez
    assert len(_jobs()) == 2 and _filas_analisis() == 2


def test_pedir_lote_respeta_el_filtro_que_mostro_las_claves(peticion):
    """Lo elegible es lo del filtro de la galería (`veredicto`), como cuando la ruta lo calculaba."""
    _conectar()
    _sembrar()
    alc = panel.alcance("acme", 30)
    perdedor = _anuncio(alc, "p1")["veredicto"]
    otro = next(v for v in panel.FILTROS_GALERIA if v and v != perdedor and v != "cansando")
    assert pedidos.pedir_lote("acme", alc, [("facebook-ads", "p1")], "daniel", veredicto=otro) == (0, 0)
    assert _jobs() == []
    assert pedidos.pedir_lote("acme", alc, [("facebook-ads", "p1")], "daniel", veredicto=perdedor) == (1, 0)


def test_pedir_lote_para_en_el_primero_sin_saldo_y_dice_cuantos_encolo(peticion):
    from cobros import SaldoInsuficiente, libro
    _conectar()
    _sembrar()
    libro.configurar("acme", usuario="admin", cobrar=True)
    clave = ("facebook-ads", "p1")
    usd = panel.precio_analisis(datos.creativos("acme", [clave]).get(clave))["usd"]
    with db.conectar() as con:
        libro.acreditar(con, "acme", "ajuste", libro.precio_milesimas(usd, libro.margen_precio("acme")), "ajuste",
                        usuario="admin", detalle="prueba")
    alc = panel.alcance("acme", 30)
    with pytest.raises(SaldoInsuficiente) as e:
        pedidos.pedir_lote("acme", alc, [clave, ("facebook-ads", "p2"), ("facebook-ads", "g1")], "daniel")
    assert e.value.lote == (1, 0)
    assert _jobs() == ["acme__tw_anuncio__facebook-ads__p1"] and _filas_analisis() == 1


def test_pedir_lote_una_que_falla_no_tumba_las_demas(peticion, monkeypatch, caplog):
    from tareas import triple_whale as tareas_tw
    _conectar()
    _sembrar()
    real = tareas_tw.encolar_analisis

    def a_veces(cliente, aid, canal, ad_id, **k):
        if ad_id == "p1":
            raise RuntimeError("boom token=abc")
        return real(cliente, aid, canal, ad_id, **k)
    monkeypatch.setattr(tareas_tw, "encolar_analisis", a_veces)
    alc = panel.alcance("acme", 30)
    with caplog.at_level("WARNING"):
        assert pedidos.pedir_lote("acme", alc, [("facebook-ads", "p1"), ("facebook-ads", "p2")], "daniel") == (1, 1)
    assert _jobs() == ["acme__tw_anuncio__facebook-ads__p2"] and _filas_analisis() == 1
    assert "RuntimeError" in caplog.text and "token=abc" not in caplog.text


def _alc_eval(cliente="acme"):
    ev, desde, hasta = panel.evaluar_periodo(cliente, 30)
    return {"ev": ev, "desde": desde, "hasta": hasta, "moneda": "USD",
            "extra": {"modelo": "Triple Attribution", "ventana": "7d", "canal": None, "tienda_id": None, "pais": None,
                      "benchmarks": ev["benchmarks"], "meta_roas": ev["meta_roas"]}}


def test_pedir_evaluacion_guarda_su_extra_y_un_segundo_pedido_no_cobra(peticion):
    _conectar()
    _sembrar()
    alc_eval = _alc_eval()
    ok, mensaje = pedidos.pedir_evaluacion("acme", alc_eval, "daniel")
    assert ok is True and "Evaluando" in mensaje
    [fila] = datos.evaluaciones("acme")
    assert fila["estado"] == "en_cola" and fila["pedido_por"] == "daniel" and fila["moneda"] == "USD"
    assert fila["extra"] == alc_eval["extra"] and {a["ad_id"] for a in fila["anuncios"]} >= {"g1", "p1"}
    [t] = _tareas("tw_evaluar")
    assert t["max_intentos"] == 1 and t["payload"] == {"cliente": "acme", "evaluacion_id": fila["id"]}
    ok, mensaje = pedidos.pedir_evaluacion("acme", _alc_eval(), "daniel")      # la primera sigue viva
    assert ok is False and "en curso" in mensaje
    assert len(datos.evaluaciones("acme")) == 1 and len(_tareas("tw_evaluar")) == 1


def test_pedir_evaluacion_sin_muestra_no_crea_nada_y_sin_saldo_tampoco(peticion):
    from cobros import SaldoInsuficiente, libro
    _conectar()
    ok, mensaje = pedidos.pedir_evaluacion("acme", _alc_eval(), "daniel")
    assert ok is None and "datos suficientes" in mensaje                         # None: nada que evaluar (aviso rojo)
    assert datos.evaluaciones("acme") == [] and _tareas("tw_evaluar") == []
    _sembrar()
    libro.configurar("acme", usuario="admin", cobrar=True)
    with pytest.raises(SaldoInsuficiente):
        pedidos.pedir_evaluacion("acme", _alc_eval(), "daniel")
    assert datos.evaluaciones("acme") == [] and _tareas("tw_evaluar") == []
