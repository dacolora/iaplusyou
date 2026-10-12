"""Rendimiento E2 (3/7): el alcance de Meta habla como el de Triple Whale.

`pestana_rendimiento.alcance_meta.alcance` arma, para una lista de cuentas de Meta, el mismo dict que
`triple_whale.panel.alcance`, para que el flujo pagado («Cómo mejorarlo», el lote, «Evaluar con IA») y la galería lo
lean sin saber de qué fuente son los números. Estas pruebas lo comparan con el de Triple Whale de verdad, miran los
anuncios (canal de Meta, cuenta, moneda), que lo ajeno no entre, la moneda común contra la mezcla, y lo pasan por
`pedidos.pedir_analisis` y por la galería de Triple Whale. Nada llama a Meta: solo lee la copia local."""
from datetime import date

import pytest
from sqlalchemy import event

import db
import idiomas
import proyectos
import triple_whale
import triple_whale_tiendas
from meta_rendimiento import cuentas, panel as meta_panel
from meta_rendimiento import datos as mdatos
from pestana_rendimiento import alcance_meta
from tests.test_rendimiento_e2_pedidos import peticion  # noqa: F401  (fixture: una petición para los textos)
from tests.test_rutas_configuracion import app  # noqa: F401  (fixture que pide `peticion`)
from tests.test_rutas_meta_rendimiento import _ad, _dia, _hace
from tests.test_rutas_triple_whale import _tareas
from triple_whale import analisis, evaluacion, mejorar, pedidos
from triple_whale import datos as twdatos
from triple_whale import panel as tw_panel

SE1, SE2, EUR = "act_se1", "act_se2", "act_eu"
CLAVES_TW = {"config", "tienda", "tienda_id", "dias", "canal", "ev", "desde", "hasta", "params"}


@pytest.fixture(autouse=True)
def _reglas(monkeypatch):
    """Las reglas del proyecto vienen de clientes/<c>/proyecto.json: por defecto, las de siempre (meta de ROAS 2,0)."""
    monkeypatch.setattr(proyectos, "reglas_defecto", lambda cliente: {})
    monkeypatch.setenv("FLASK_SECRET_KEY", "test_secret_key_12345678")    # la llave de una tienda de Triple Whale se cifra


def _cuentas(*filas):
    """(act, moneda, país) -> cuentas de acme, con un día de cuenta cada una para que «desde el inicio» arranque."""
    cuentas.elegir("acme", [{"id": act, "name": f"HappyFlops {act}", "currency": moneda, "pais": pais}
                            for act, moneda, pais in filas])
    for act, _, _ in filas:
        f = _hace(9)
        mdatos.reemplazar_cuenta_dias("acme", act, f, f, [_dia(f, 100, 200)])


def _anuncios(act, *filas, cliente="acme"):
    """filas: (ad_id, gasto, valor, compras). Siete días de datos para cada anuncio, en la cuenta `act`."""
    for n in range(2, 7):
        f = _hace(n)
        mdatos.reemplazar_anuncio_dias(cliente, act, f, f, [
            _ad(f, ad, gasto, valor, compras=compras, adset=f"s_{act}", campaign=f"c_{act}")
            for ad, gasto, valor, compras in filas])


def _dos_suecas():
    """Dos cuentas en SEK: una con un ganador y perdedores, la otra con una mezcla."""
    _cuentas((SE1, "SEK", "SE"), (SE2, "SEK", "SE"))
    _anuncios(SE1, ("a1", 100, 500, 5), ("a2", 80, 0, 0), ("a3", 60, 240, 2), ("a4", 40, 0, 0))
    _anuncios(SE2, ("b1", 50, 0, 0), ("b2", 70, 280, 2), ("b3", 90, 225, 1))


def _alc(ids, dias=30, params=None, **k):
    with idiomas.en_idioma("es"):
        return alcance_meta.alcance("acme", ids, dias, date.today(), params or {"entrada": "SE", "dias": dias}, **k)


# ------------------------------------------------------------------------------------------- la forma ---

def test_tiene_las_mismas_claves_que_el_alcance_de_triple_whale(base_temporal):
    """Se compara con el de verdad: una tienda de Triple Whale con anuncios de Meta y el alcance que arma su panel."""
    tid = triple_whale_tiendas.agregar("tw", "tw_llave_123", "tw.myshopify.com", "NO", moneda="USD")  # llave-de-prueba
    for n in range(2, 7):
        f = _hace(n)
        twdatos.reemplazar_anuncios_canal("tw", tid, f, f, [
            {"canal": "facebook-ads", "ad_id": ad, "fecha": f, "anuncio": f"Anuncio {ad}", "gasto": gasto,
             "impresiones": 3000, "clics": 60, "vistas_3s": 900, "thruplays": 300} for ad, gasto in
            (("t1", 40), ("t2", 30), ("t3", 20))])
        twdatos.reemplazar_anuncios_pixel("tw", tid, f, f, [
            {"canal": "facebook-ads", "ad_id": ad, "fecha": f, "pedidos": p, "ingresos": i}
            for ad, p, i in (("t1", 2, 160), ("t2", 0, 0), ("t3", 1, 50))])
    tw = tw_panel.alcance("tw", 30)
    assert set(tw) == CLAVES_TW
    _dos_suecas()
    meta = _alc([SE1, SE2])
    assert set(meta) == CLAVES_TW | {"fuente"} and meta["fuente"] == "meta" and "fuente" not in tw
    assert set(meta["ev"]) == set(tw["ev"])
    assert set(meta["ev"]["cuenta"]) == set(tw["ev"]["cuenta"])
    assert set(meta["ev"]["benchmarks"]) == set(tw["ev"]["benchmarks"])
    assert set(meta["ev"]["benchmarks_canal"]) == {triple_whale.CANAL_META}
    assert set(tw["ev"]["anuncios"][0]) <= set(meta["ev"]["anuncios"][0])
    # Lo que `pedidos` lee de `config` está, en palabras de Meta y sin pasar por el catálogo (nombres propios).
    assert meta["config"] == {"moneda": "SEK", "modelo_atribucion": "Pixel de Meta", "ventana_atribucion": "Meta"}
    assert {"moneda", "modelo_atribucion", "ventana_atribucion"} <= set(tw["config"])
    assert meta["tienda"] is None and meta["tienda_id"] is None and meta["canal"] is None
    assert alcance_meta.FUENTE in analisis.FUENTES and meta["fuente"] == alcance_meta.FUENTE


def test_los_anuncios_llevan_el_canal_de_meta_su_cuenta_y_su_moneda(base_temporal):
    _dos_suecas()
    alc = _alc([SE1, SE2])
    anuncios = alc["ev"]["anuncios"]
    assert sorted(a["ad_id"] for a in anuncios) == ["a1", "a2", "a3", "a4", "b1", "b2", "b3"]
    assert {a["canal"] for a in anuncios} == {triple_whale.CANAL_META} == {"facebook-ads"}
    por_id = {a["ad_id"]: a for a in anuncios}
    assert por_id["a1"]["ad_account_id"] == SE1 and por_id["b2"]["ad_account_id"] == SE2
    assert {a["moneda"] for a in anuncios} == {"SEK"}
    a = por_id["a1"]
    assert a["nombre"] and a["veredicto"] in evaluacion.VEREDICTOS and a["m"]["gasto"] == 500
    assert set(a["anillos"]) == set(evaluacion.ANILLOS) and "creative_id" in a and "campana" in a
    assert a["campana"] is None or isinstance(a["campana"], str)
    # La clave (canal, ad_id) del flujo pagado encuentra el anuncio; la de «meta» (como lo guarda la copia) no.
    assert pedidos.anuncio_del_alcance(alc, "facebook-ads", "a1") is a
    assert pedidos.anuncio_del_alcance(alc, "meta", "a1") is None


def test_lo_que_no_es_del_alcance_no_aparece(base_temporal):
    _dos_suecas()
    _cuentas((SE1, "SEK", "SE"), (SE2, "SEK", "SE"))
    solo_una = _alc([SE1])
    assert sorted(a["ad_id"] for a in solo_una["ev"]["anuncios"]) == ["a1", "a2", "a3", "a4"]
    assert {a["ad_account_id"] for a in solo_una["ev"]["anuncios"]} == {SE1}
    assert pedidos.anuncio_del_alcance(solo_una, "facebook-ads", "b1") is None
    assert solo_una["ev"]["cuenta"]["n"] == 4


def test_una_cuenta_de_otro_proyecto_no_se_lee_ni_con_su_id(base_temporal):
    """Los ids llegan de la pestaña: uno que no es de este proyecto se ignora, y si no queda ninguno, no hay alcance."""
    _dos_suecas()
    cuentas.elegir("otro", [{"id": "act_ajena", "name": "Ajena", "currency": "SEK", "pais": "SE"}])
    _anuncios("act_ajena", ("x1", 500, 0, 0), ("x2", 400, 0, 0), ("x3", 300, 0, 0), cliente="otro")
    alc = _alc([SE1, "act_ajena", "act_inventada"])
    assert {a["ad_account_id"] for a in alc["ev"]["anuncios"]} == {SE1}
    assert not any(a["ad_id"].startswith("x") for a in alc["ev"]["anuncios"])
    assert _alc(["act_ajena"]) is None and _alc(["act_inventada"]) is None


def test_sin_cuentas_no_hay_alcance(base_temporal):
    _dos_suecas()
    assert _alc([]) is None
    assert _alc(None) is None


def test_una_cuenta_repetida_se_lee_una_vez(base_temporal):
    _dos_suecas()
    alc = _alc([SE1, SE1, SE2, SE1])
    assert len(alc["ev"]["anuncios"]) == 7 and alc["ev"]["cuenta"]["n"] == 7


# -------------------------------------------------------------------------- lo que lee el flujo pagado ---

def test_la_cuenta_y_las_medianas_son_las_del_canal_de_meta(base_temporal):
    _dos_suecas()
    alc = _alc([SE1, SE2])
    ev = alc["ev"]
    [canal] = ev["cuenta"]["canales"]
    assert canal["canal"] == "facebook-ads"
    assert canal["gasto"] == 5 * (100 + 80 + 60 + 40 + 50 + 70 + 90) and canal["pedidos"] == 5 * (5 + 2 + 2 + 1)
    assert canal["anuncios"] == 7
    ms = [a["m"] for a in ev["anuncios"]]
    esperado = evaluacion.benchmarks(ms)
    assert ev["benchmarks"] == esperado and ev["benchmarks_canal"] == {"facebook-ads": esperado}
    assert esperado["n"] == 7 and esperado["ctr"] is not None and esperado["roas"] is not None
    assert ev["conteo"] == {v: sum(1 for a in ev["anuncios"] if a["veredicto"] == v) for v in evaluacion.VEREDICTOS}
    assert sum(ev["conteo"].values()) == 7 and ev["hay_ventas"] is True
    assert ev["meta_roas"] == 2.0                 # la meta del proyecto (REGLAS_DEFECTO) manda sobre las medianas


def test_con_una_sola_cuenta_las_medianas_son_las_de_esa_cuenta(base_temporal):
    """Un alcance de una cuenta (una entrada del selector) da lo mismo que `evaluacion.evaluar` sobre sus filas."""
    _dos_suecas()
    alc = _alc([SE1])
    desde, hasta = alc["desde"], alc["hasta"]
    filas = mdatos.totales_por_anuncio("acme", [SE1], desde, hasta)
    de_verdad = evaluacion.evaluar(filas, None, None, {})
    assert alc["ev"]["benchmarks"] == de_verdad["benchmarks"]
    assert alc["ev"]["meta_roas"] == de_verdad["meta_roas"] == 2.0


def test_la_meta_de_roas_del_proyecto_o_la_mediana_del_alcance(base_temporal, monkeypatch):
    _dos_suecas()
    monkeypatch.setattr(proyectos, "reglas_defecto", lambda cliente: {"roas_min": 4.0})
    assert _alc([SE1, SE2])["ev"]["meta_roas"] == 4.0
    # Sin meta (apagada), cada cuenta se mide con su mediana; el alcance de las dos da UNA: la de todos sus anuncios.
    monkeypatch.setattr(proyectos, "reglas_defecto", lambda cliente: {"roas_min": None})
    alc = _alc([SE1, SE2])
    assert alc["ev"]["meta_roas"] == alc["ev"]["benchmarks"]["roas"] == 2.5
    # Y una cuenta sola, la suya.
    uno = _alc([SE1])
    assert uno["ev"]["meta_roas"] == uno["ev"]["benchmarks"]["roas"]


def test_el_veredicto_de_cada_anuncio_sigue_siendo_contra_su_cuenta(base_temporal):
    """El alcance no vuelve a evaluar: lo que dice `meta_panel.anuncios_evaluados` para cada anuncio es lo que queda."""
    _dos_suecas()
    alc = _alc([SE1, SE2])
    desde, hasta = alc["desde"], alc["hasta"]
    por_id = {c["ad_account_id"]: c for c in meta_panel.lista("acme")}
    with idiomas.en_idioma("es"):
        base = meta_panel.anuncios_evaluados("acme", [SE1, SE2], desde, hasta, date.today(), por_id)["ev"]["anuncios"]
    assert {(a["ad_id"], a["veredicto"], a["motivo"]) for a in alc["ev"]["anuncios"]} == \
        {(a["ad_id"], a["veredicto"], a["motivo"]) for a in base}


# --------------------------------------------------------------------------------------------- la moneda ---

def test_cuentas_en_la_misma_moneda_dan_esa_moneda(base_temporal):
    _dos_suecas()
    assert _alc([SE1])["config"]["moneda"] == "SEK" and _alc([SE1, SE2])["config"]["moneda"] == "SEK"


def _con_euros():
    _dos_suecas()
    _cuentas((SE1, "SEK", "SE"), (SE2, "SEK", "SE"), (EUR, "EUR", "NL"))
    _anuncios(EUR, ("e1", 20, 100, 2), ("e2", 30, 0, 0), ("e3", 25, 50, 1))


def test_con_monedas_distintas_la_del_alcance_es_none_y_cada_anuncio_lleva_la_suya(base_temporal):
    _con_euros()
    alc = _alc([SE1, EUR])
    assert alc["config"]["moneda"] is None
    assert alc["config"]["modelo_atribucion"] == "Pixel de Meta" and alc["config"]["ventana_atribucion"] == "Meta"
    monedas = {a["ad_id"]: a["moneda"] for a in alc["ev"]["anuncios"]}
    assert monedas == {"a1": "SEK", "a2": "SEK", "a3": "SEK", "a4": "SEK", "e1": "EUR", "e2": "EUR", "e3": "EUR"}
    # Con una sola de las cuentas vuelve a haber moneda común.
    assert _alc([EUR])["config"]["moneda"] == "EUR"


def test_mezclar_monedas_no_inventa_cifras_en_dinero(base_temporal):
    """El costo por mil impresiones y el costo por venta del canal serían una mezcla de SEK y EUR: no se dan."""
    _con_euros()
    alc = _alc([SE1, EUR])
    ev = alc["ev"]
    assert ev["benchmarks"]["cpm"] is None and ev["benchmarks_canal"]["facebook-ads"]["cpm"] is None
    assert ev["benchmarks"]["ctr"] is not None and ev["benchmarks"]["roas"] is not None    # cocientes: sí valen
    assert ev["cuenta"]["canales"] == []                       # el costo por venta del canal queda sin dato
    # Con una sola moneda, ambos existen.
    junto = _alc([SE1, SE2])["ev"]
    assert junto["benchmarks"]["cpm"] is not None and junto["cuenta"]["canales"]


def test_una_cuenta_sin_moneda_conocida_no_se_da_por_la_de_las_demas(base_temporal):
    _dos_suecas()
    with db.conectar() as con:
        con.execute(db.meta_cuenta.update().where(db.meta_cuenta.c.ad_account_id == SE2).values(moneda=None))
    assert _alc([SE1, SE2])["config"]["moneda"] is None
    assert _alc([SE2])["config"]["moneda"] is None
    assert _alc([SE1])["config"]["moneda"] == "SEK"


# ---------------------------------------------------------------------------------------- el periodo ---

def test_el_periodo_y_los_params(base_temporal):
    _dos_suecas()
    params = {"entrada": "SE", "dias": 7}
    alc = _alc([SE1, SE2], 7, params)
    hoy = date.today()
    assert alc["dias"] == 7 and alc["hasta"] == hoy.isoformat() and alc["desde"] == _hace(6)
    assert alc["params"] == params and alc["params"] is not params     # una copia: quien la pasó puede seguir usándola
    # «Desde el inicio»: el primer día de ANUNCIOS copiado de ESAS cuentas (B2; el de cuenta es _hace(9)).
    inicio = _alc([SE1, SE2], 0)
    assert inicio["dias"] == 0 and inicio["desde"] == _hace(6) and inicio["hasta"] == hoy.isoformat()


@pytest.mark.parametrize("raro", [5, None, "30", True, 1.5, -7, 365])
def test_un_periodo_raro_cae_en_desde_el_inicio(base_temporal, raro):
    _dos_suecas()
    alc = _alc([SE1], raro)
    assert alc["dias"] == 0 and alc["desde"] == _hace(6)


def test_desde_el_inicio_arranca_en_el_primer_dia_de_anuncios_copiado(base_temporal):
    """B2 (revisión final de Rendimiento E2, 2026-10-10; enmienda A2: los anuncios usan el «Desde el inicio» de SU
    copia). La copia de cuentas guarda unos 400 días y la de anuncios 90: con el primer día de CUENTA, el alcance de los
    anuncios decía «desde hace 390 días» y cada análisis guardaba un `desde` que no es el de los números que mira. Solo
    las cuentas pedidas cuentan, y sin anuncios copiados no se toma el primer día de cuenta."""
    cuentas.elegir("acme", [{"id": SE1, "name": "HappyFlops Sweden", "currency": "SEK", "pais": "SE"},
                            {"id": SE2, "name": "HappyFlops Sverige", "currency": "SEK", "pais": "SE"}])
    mdatos.reemplazar_cuenta_dias("acme", SE1, _hace(389), _hace(0), [_dia(_hace(n), 100, 200) for n in range(390)])
    for n in range(5):
        f = _hace(n)
        mdatos.reemplazar_anuncio_dias("acme", SE1, f, f, [_ad(f, "a1", 100, 300, compras=2)])
    mdatos.reemplazar_anuncio_dias("acme", SE2, _hace(40), _hace(40), [_ad(_hace(40), "b1", 50, 0)])   # otra cuenta
    alc = _alc([SE1], 0)
    assert alc["desde"] == _hace(4) and alc["hasta"] == date.today().isoformat()
    assert _alc([SE1, SE2], 0)["desde"] == _hace(40)                       # el primero entre las cuentas pedidas
    assert _alc([SE1], 30)["desde"] == _hace(29)                           # un periodo fijo no cambia
    mdatos.reemplazar_anuncio_dias("acme", SE1, _hace(4), _hace(0), [])
    assert _alc([SE1], 0)["desde"] == date.today().isoformat()            # sin anuncios: hoy, nunca hace 389 días


def test_sin_params_el_alcance_igual_sale(base_temporal):
    _dos_suecas()
    with idiomas.en_idioma("es"):
        alc = alcance_meta.alcance("acme", [SE1], 30, date.today(), None)
    assert alc["params"] == {}


def test_hoy_es_el_de_quien_llama(base_temporal):
    """`hoy` entra por parámetro (como en `triple_whale.panel.alcance`): el mismo periodo, otro día de referencia."""
    _dos_suecas()
    with idiomas.en_idioma("es"):
        alc = alcance_meta.alcance("acme", [SE1], 7, date(2026, 1, 15), {})
    assert alc["hasta"] == "2026-01-15" and alc["desde"] == "2026-01-09" and alc["ev"]["anuncios"] == []


# ------------------------------------------------------------------- consultas y lo que no hace ---

def test_pocas_consultas_aunque_haya_muchos_anuncios(base_temporal):
    """Un número fijo de lecturas: no depende de cuántos anuncios ni de cuántas cuentas (skill escala-y-salud)."""
    _dos_suecas()
    cuentas_por_id = {c["ad_account_id"]: c for c in meta_panel.lista("acme")}

    def contar(ids):
        n = []

        def al_ejecutar(conn, cursor, statement, params, context, executemany):
            n.append(statement)
        event.listen(db.engine(), "before_cursor_execute", al_ejecutar)
        try:
            _alc(ids, 30, cuentas_por_id=cuentas_por_id)
        finally:
            event.remove(db.engine(), "before_cursor_execute", al_ejecutar)
        return len(n)
    pocas = contar([SE1])
    _anuncios(SE1, *[(f"m{i:02d}", 10 + i, 20 * i, i % 3) for i in range(60)])
    _anuncios(SE2, *[(f"n{i:02d}", 10 + i, 20 * i, i % 3) for i in range(60)])
    assert contar([SE1, SE2]) == pocas <= 8


def test_las_cuentas_ya_leidas_no_se_vuelven_a_pedir(base_temporal):
    _dos_suecas()
    por_id = {c["ad_account_id"]: c for c in meta_panel.lista("acme")}
    con = _alc([SE1], cuentas_por_id=por_id)
    sin = _alc([SE1])
    assert [a["ad_id"] for a in con["ev"]["anuncios"]] == [a["ad_id"] for a in sin["ev"]["anuncios"]]
    assert con["config"] == sin["config"] and con["ev"]["benchmarks"] == sin["ev"]["benchmarks"]


def test_no_cuenta_ni_cobra_nada(base_temporal):
    """Solo lee la copia: ni una tarea, ni un gasto, ni una fila de análisis."""
    _dos_suecas()
    _alc([SE1, SE2])
    with db.conectar() as con:
        assert con.execute(db.tarea.select()).first() is None
        assert con.execute(db.tw_analisis.select()).first() is None
        assert con.execute(db.gasto.select()).first() is None


# ------------------------------------------------- el flujo pagado y la galería lo leen sin saber de dónde viene ---

def test_la_galeria_de_triple_whale_pinta_el_alcance_de_meta(base_temporal):
    _dos_suecas()
    alc = _alc([SE1, SE2])
    with idiomas.en_idioma("es"):
        g = tw_panel.galeria("acme", alc["ev"], "", alcance=alc)
    assert g["total"] == sum(1 for a in alc["ev"]["anuncios"] if a["veredicto"] != "sin_datos")   # «Todos» sin los de pocos datos
    assert {t["canal"] for t in g["tarjetas"]} == {"facebook-ads"} and g["lote"]["n"] >= 1
    assert all(t["ofrecer_analisis"] and t["precio_analisis"]["usd"] is not None for t in g["tarjetas"]
               if t["veredicto"] != "sin_datos")


def test_pedir_analisis_guarda_lo_de_la_cuenta_y_la_moneda_del_alcance(peticion):  # noqa: F811
    _dos_suecas()
    alc = _alc([SE1, SE2])
    a = pedidos.anuncio_del_alcance(alc, "facebook-ads", "a2")
    assert a["veredicto"] != "sin_datos"
    ok, mensaje = pedidos.pedir_analisis("acme", alc, a, "daniel")
    assert ok is True, mensaje
    [fila] = twdatos.ultimos_analisis("acme", [("facebook-ads", "a2")]).values()
    assert fila["tienda_id"] is None and fila["moneda"] == "SEK" and fila["pedido_por"] == "daniel"
    assert (fila["desde"], fila["hasta"]) == (alc["desde"], alc["hasta"])
    cuenta = fila["foto"]["cuenta"]
    assert cuenta["modelo"] == "Pixel de Meta" and cuenta["ventana"] == "Meta" and cuenta["meta_roas"] == 2.0
    assert cuenta["benchmarks"] == alc["ev"]["benchmarks"]
    assert cuenta["cpa_canal"] == pytest.approx(2450 / 50)    # el gasto y las compras de todo el alcance
    assert [t["job_id"] for t in _tareas("tw_analizar_anuncio")] == ["acme__tw_anuncio__facebook-ads__a2"]
    # Un alcance de otra cuenta no encuentra ese anuncio: no se puede pedir con una clave ajena.
    otro = _alc([SE2])
    assert pedidos.anuncio_del_alcance(otro, "facebook-ads", "a2") is None


def test_pedir_analisis_con_monedas_mezcladas_no_guarda_una_moneda_ni_un_costo_inventados(peticion):  # noqa: F811
    """Sin moneda común en el alcance, el análisis guarda la de la cuenta del anuncio (E2 tarea 4: `pedir_analisis`
    toma `a["moneda"]` antes que la del alcance; hasta entonces guardaba None), y ni un costo por venta ni un CPM de
    monedas mezcladas."""
    _con_euros()
    alc = _alc([SE1, EUR])
    ok, mensaje = pedidos.pedir_analisis("acme", alc, pedidos.anuncio_del_alcance(alc, "facebook-ads", "a2"), "daniel")
    assert ok is True, mensaje
    [fila] = twdatos.ultimos_analisis("acme", [("facebook-ads", "a2")]).values()
    assert alc["config"]["moneda"] is None
    assert fila["moneda"] == "SEK" and fila["foto"]["cuenta"]["cpa_canal"] is None
    assert fila["foto"]["fuente"] == "meta" and fila["foto"]["ad_account_id"] == SE1 and fila["foto"]["metodo"] == 2
    assert fila["foto"]["cuenta"]["benchmarks"]["cpm"] is None
    assert fila["foto"]["m"]["gasto"] == 400          # la cifra del anuncio es la suya, en la moneda de su cuenta


@pytest.mark.parametrize("ahora_es_de", [None, "otro"])
def test_pedir_analisis_de_una_cuenta_que_se_solto_en_medio_no_deja_fila_ni_encola(peticion, monkeypatch,  # noqa: F811
                                                                                  ahora_es_de):
    """PND-295 (3), 2026-10-12: la cuenta se suelta justo después de crear la fila (el barrido de `cuentas.elegir` ya
    había pasado). Ninguna suelta posterior la alcanzaría (solo borran las cuentas que sueltan): el pedido la borra él
    mismo antes de encolar, así no se reserva ni se cobra nada. Da igual si la cuenta quedó libre o en otro proyecto."""
    _dos_suecas()
    alc = _alc([SE1, SE2])
    a = pedidos.anuncio_del_alcance(alc, "facebook-ads", "a2")
    crear, creadas = twdatos.crear_analisis, []

    def _crear(*args, **kw):
        creadas.append(crear(*args, **kw))
        with db.conectar() as con:
            if ahora_es_de:
                con.execute(db.meta_cuenta.update().where(db.meta_cuenta.c.ad_account_id == SE1)
                            .values(cliente=ahora_es_de))
            else:
                con.execute(db.meta_cuenta.delete().where(db.meta_cuenta.c.ad_account_id == SE1))
        return creadas[-1]
    monkeypatch.setattr(twdatos, "crear_analisis", _crear)
    from tareas import triple_whale as tareas_tw
    monkeypatch.setattr(tareas_tw, "encolar_analisis", lambda *a, **k: pytest.fail("no se encola ni se reserva"))
    assert pedidos.pedir_analisis("acme", alc, a, "daniel") == (False, "Esa cuenta de Meta ya no está en este proyecto.")
    assert len(creadas) == 1 and twdatos.analisis_anuncio("acme", creadas[0]) is None
    assert _tareas("tw_analizar_anuncio") == []


def test_la_foto_del_anuncio_de_meta_se_arma_con_lo_que_trae_el_alcance(base_temporal):
    _dos_suecas()
    alc = _alc([SE1, SE2])
    a = pedidos.anuncio_del_alcance(alc, "facebook-ads", "a1")
    foto = mejorar.foto(a, None, {"benchmarks": alc["ev"]["benchmarks"]}, mejorar.ganadores_del_canal(alc["ev"], a, {}),
                        fuente="meta", ad_account_id=a["ad_account_id"])
    assert foto["fuente"] == "meta" and foto["ad_account_id"] == SE1 and foto["canal"] == "facebook-ads"
    assert foto["m"]["gasto"] == 500 and set(foto["anillos"]) == set(evaluacion.ANILLOS)
    # La muestra de «Evaluar con IA» lee los mismos anuncios (y `medios_meta` solo mira el canal de Meta).
    muestra = analisis.muestra(alc["ev"])
    assert muestra and {m["canal"] for m in muestra} == {"facebook-ads"}
