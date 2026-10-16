"""PND-294 (2026-10-12): los días de «Resultados» que el detalle no puede abrir no se ofrecen. Con un periodo fijo y
fuentes que empezaron en días distintos, la gráfica dibuja días anteriores al primero que el detalle acepta; la ruta
los rechazaba con un 400 y la persona veía «No se pudo cargar ese día.» después de un clic que la pista invitaba a dar.

La invariante que importa, probada por la ruta de verdad y con la URL que la gráfica misma pide (`url_dia`): para cada
día dibujado que no es hoy ni «sin copia», la ruta responde 400 si y solo si la gráfica lo marca `sin_dia`. Se prueba
con las tres formas del alcance (mezcla, Meta sola, Triple Whale sola) y con el borde donde `inicio_datos` de Triple
Whale y el primer día que su detalle acepta NO coinciden (los anuncios se copiaron antes que la tienda)."""
import json
import re
from datetime import date, timedelta

import pytest

import db
import triple_whale_tiendas
from meta_rendimiento import cuentas as mcuentas
from meta_rendimiento import datos as mdatos
from tests.test_rendimiento_e2_dia import _anuncios_tw
from tests.test_rutas_configuracion import app  # noqa: F401  (fixture)
from tests.test_rutas_meta_rendimiento import _dia, _tasa
from triple_whale import datos as twdatos

TOKEN = "t-llave-de-prueba"   # llave-de-prueba
SE = "act_se"


@pytest.fixture(autouse=True)
def _llave_de_cifrado(monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "test_secret_key_12345678")


@pytest.fixture()
def meta_on(app, monkeypatch):  # noqa: F811
    monkeypatch.setattr(app["dashboard"].meta_conexion, "cargar", lambda c: {"token": TOKEN, "page_id": None})
    return app


def _hace(n):
    # Hoy al llamar, no al importar: con «HOY» fijado al importar, una suite que cruzaba la medianoche comparaba
    # el día de ayer con el «hoy» de la ruta (falló el 2026-10-15 a las 00:0x).
    return (date.today() - timedelta(days=n)).isoformat()


def _sembrar(dias_tienda=0, dias_meta=0):
    """La tienda de Noruega (USD) con `dias_tienda` días de totales y la cuenta de Suecia (SEK) con `dias_meta` días,
    contando hacia atrás desde hoy; tasas para los últimos 100 días (así la mezcla nunca se queda sin ellas)."""
    tid = triple_whale_tiendas.agregar("acme", "tw_llave_123", "acme-no.myshopify.com", "NO", moneda="USD")  # llave-de-prueba
    triple_whale_tiendas.actualizar_tienda("acme", tid, ultima_sincronizacion=db.ahora())
    mcuentas.elegir("acme", [{"id": SE, "name": "HappyFlops Sweden", "currency": "SEK", "pais": "SE"}])
    for n in range(dias_tienda):
        f = _hace(n)
        twdatos.reemplazar_tienda("acme", tid, f, f, [{"fecha": f, "gasto": 50, "ingresos": 150, "pedidos": 3}])
    for n in range(dias_meta):
        f = _hace(n)
        mdatos.reemplazar_cuenta_dias("acme", SE, f, f, [_dia(f, 1000, 2000, compras=4)])
    for n in range(100):
        _tasa(_hace(n), 0.1, "SEK")
    return tid


def _montar(tiendas=(), cuentas=()):
    """Varias fuentes a la vez. `tiendas` = [(país, días de totales de la tienda, días de anuncios copiados)] y
    `cuentas` = [(act, país, días)] (cuentas de Meta en SEK), contando hacia atrás desde hoy. Devuelve los ids de las
    tiendas. Las tasas cubren los últimos 100 días."""
    tids = []
    for i, (pais, dias_tienda, dias_anuncios) in enumerate(tiendas):
        tid = triple_whale_tiendas.agregar("acme", f"tw_llave_{i}", f"acme-{pais.lower()}.myshopify.com", pais,  # llave-de-prueba
                                           moneda="USD")
        triple_whale_tiendas.actualizar_tienda("acme", tid, ultima_sincronizacion=db.ahora())
        for n in range(dias_tienda):
            f = _hace(n)
            twdatos.reemplazar_tienda("acme", tid, f, f, [{"fecha": f, "gasto": 50, "ingresos": 150, "pedidos": 3}])
        if dias_anuncios:
            _anuncios_tw(tid, {dias_anuncios - 1: [("t1", 10, 40)], min(1, dias_anuncios - 1): [("t1", 10, 40)]})
        tids.append(tid)
    if cuentas:
        mcuentas.elegir("acme", [{"id": act, "name": f"Cuenta {pais}", "currency": "SEK", "pais": pais}
                                 for act, pais, _ in cuentas])
        for act, _, dias in cuentas:
            for n in range(dias):
                f = _hace(n)
                mdatos.reemplazar_cuenta_dias("acme", act, f, f, [_dia(f, 1000, 2000, compras=4)])
    for n in range(100):
        _tasa(_hace(n), 0.1, "SEK")
    return tids


def _grafica(app, entrada, dias=30):  # noqa: F811
    """Los datos que la gráfica recibe, tal cual los pinta el panel (el JSON inerte de `#tw-resultados-datos`)."""
    r = app["c"].get(f"/cliente/acme/rendimiento/panel?entrada={entrada}&dias={dias}")
    assert r.status_code == 200
    crudo = re.search(r'id="tw-resultados-datos">(.*?)</script>', r.data.decode(), re.S).group(1)
    return json.loads(crudo)


def _estado_del_dia(app, url_dia, fecha):  # noqa: F811
    """El estado HTTP que recibe la gráfica al pedir ese día con la URL que ella misma trae."""
    return app["c"].get(f"{url_dia}{'&' if '?' in url_dia else '?'}fecha={fecha}").status_code


def _revisar(app, datos, **esperado):  # noqa: F811
    """La invariante, día por día, y lo que se espera marcar: devuelve (marcados, abiertos)."""
    dias = datos["dias"]
    assert dias[-1]["f"] == _hace(0)
    marcados, abiertos = [], []
    for d in dias[:-1]:                                   # hoy tiene su propia regla
        if d.get("sin_copia"):
            assert "sin_dia" not in d                     # y los días sin copia, la suya
            continue
        estado = _estado_del_dia(app, datos["url_dia"], d["f"])
        assert estado in (200, 400), (d["f"], estado)
        assert (estado == 400) == bool(d.get("sin_dia")), (d["f"], estado, d.get("sin_dia"))
        (marcados if d.get("sin_dia") else abiertos).append(d["f"])
    assert "sin_dia" not in dias[-1]
    # Con el día que nace la gráfica se pide el detalle: tiene que ser uno que abre (o ninguno), nunca uno marcado.
    inicial = datos["dia_inicial"]
    if inicial:
        assert inicial not in marcados and _estado_del_dia(app, datos["url_dia"], inicial) == 200, inicial
    if "marcados" in esperado:
        assert marcados == esperado["marcados"]
    return marcados, abiertos


def test_mezcla_con_periodo_fijo_los_dias_antes_del_inicio_comun_no_se_ofrecen(meta_on):
    _sembrar(dias_tienda=30, dias_meta=10)               # la cuenta de Meta empezó hace 9 días: inicio común = hace(9)
    datos = _grafica(meta_on, "", dias=30)
    assert datos["fuente"] == "mixta"
    antes = [d["f"] for d in datos["dias"] if d["f"] < _hace(9)]
    assert len(antes) >= 15                              # se dibujan días de antes: una fuente sí tiene datos
    marcados, abiertos = _revisar(meta_on, datos, marcados=antes)
    assert abiertos[0] == _hace(9)                       # el primer día abierto es el primero de la fuente más nueva


def test_meta_sola_con_periodo_fijo(meta_on):
    _sembrar(dias_tienda=30, dias_meta=10)
    datos = _grafica(meta_on, "SE", dias=30)
    assert datos["fuente"] == "meta"
    antes = [d["f"] for d in datos["dias"] if d["f"] < _hace(9)]
    assert antes
    marcados, abiertos = _revisar(meta_on, datos, marcados=antes)
    assert abiertos[0] == _hace(9)


def test_mezcla_en_siete_dias(meta_on):
    _sembrar(dias_tienda=30, dias_meta=4)                # hace(3): solo los 3 días anteriores a él quedan fuera
    datos = _grafica(meta_on, "", dias=7)
    marcados, abiertos = _revisar(meta_on, datos, marcados=[d["f"] for d in datos["dias"] if d["f"] < _hace(3)])
    assert len(marcados) >= 2 and abiertos[0] == _hace(3)


def test_desde_el_inicio_no_marca_ningun_dia(meta_on):
    _sembrar(dias_tienda=30, dias_meta=10)
    datos = _grafica(meta_on, "", dias=0)                # arranca el día en que todas las fuentes ya tienen datos
    marcados, abiertos = _revisar(meta_on, datos)
    assert marcados == [] and abiertos


def test_solo_triple_whale_con_todo_copiado_el_mismo_dia(meta_on):
    tid = _sembrar(dias_tienda=10)                       # la tienda empezó hace 9 días
    _anuncios_tw(tid, {9: [("t1", 10, 40)], 1: [("t1", 10, 40)]})
    datos = _grafica(meta_on, "NO", dias=30)
    assert datos["fuente"] == "tienda" and "/triple-whale/dia" in datos["url_dia"]
    antes = [d["f"] for d in datos["dias"] if d["f"] < _hace(9)]
    assert len(antes) >= 15
    marcados, abiertos = _revisar(meta_on, datos, marcados=antes)
    assert abiertos[0] == _hace(9)


def test_solo_triple_whale_sigue_el_primer_dia_del_detalle_y_no_el_de_la_tienda(meta_on):
    """El borde que un `inicio_datos` a secas habría fallado: los anuncios se copiaron desde hace 20 días y la tienda
    desde hace 9. `contexto_dia` abre desde el primero de los dos (hace 20), así que esos días SE ofrecen."""
    tid = _sembrar(dias_tienda=10)
    _anuncios_tw(tid, {20: [("t1", 10, 40)], 1: [("t1", 10, 40)]})
    datos = _grafica(meta_on, "NO", dias=30)
    antes_de_los_anuncios = [d["f"] for d in datos["dias"] if d["f"] < _hace(20)]
    assert len(antes_de_los_anuncios) >= 5
    marcados, abiertos = _revisar(meta_on, datos, marcados=antes_de_los_anuncios)
    assert abiertos[0] == _hace(20) and _hace(15) in abiertos     # antes de la tienda, pero con detalle
    # La otra ruta que atiende este alcance (la de la pestaña) responde lo mismo día por día.
    for d in datos["dias"][:-1]:
        viejo = _estado_del_dia(meta_on, datos["url_dia"], d["f"])
        nuevo = _estado_del_dia(meta_on, "/cliente/acme/rendimiento/dia?entrada=NO", d["f"])
        assert viejo == nuevo, d["f"]


def test_solo_meta_con_dos_cuentas_de_inicios_distintos(meta_on):
    """Una cuenta con 20 días y otra con 10: en «Todas» (fuente «meta») los días entre las dos copias llevan datos
    reales de una cuenta, la ruta los rechaza y el motivo es «todavía no estaban todas tus fuentes», no «antes de la
    primera copia» (la de la cuenta vieja ya existía)."""
    _montar(cuentas=[("act_se", "SE", 20), ("act_dk", "DK", 10)])
    datos = _grafica(meta_on, "", dias=30)
    assert datos["fuente"] == "meta"
    marcados, abiertos = _revisar(meta_on, datos, marcados=[d["f"] for d in datos["dias"] if d["f"] < _hace(9)])
    assert abiertos[0] == _hace(9)
    intermedio = next(d for d in datos["dias"] if d["f"] == _hace(15))
    assert intermedio["sin_dia"] is True and intermedio["ing"] > 0                  # dibujado con ventas reales
    assert datos["textos"]["sin_dia"] == "todavía no estaban todas tus fuentes"
    # Cada cuenta sola es una sola fuente: el inicio es el suyo y lo anterior sí es «antes de la primera copia».
    for entrada, primer_dia in (("SE", 19), ("DK", 9)):
        sola = _grafica(meta_on, entrada, dias=30)
        _revisar(meta_on, sola, marcados=[d["f"] for d in sola["dias"] if d["f"] < _hace(primer_dia)])
        assert sola["textos"]["sin_dia"] == "antes de la primera copia"


def test_solo_triple_whale_con_dos_tiendas_cada_vista_sigue_a_su_tienda(meta_on):
    """La vista de la tienda más nueva marca desde SU primer día aunque la otra tienda tenga copia desde antes: el
    detalle de una tienda abre desde el primer día de esa tienda (si se calculara con todas, abriría días que dan 400)."""
    _montar(tiendas=[("NO", 25, 25), ("SE", 10, 10)])
    for entrada, primer_dia in (("NO", 24), ("SE", 9), ("", 24)):
        datos = _grafica(meta_on, entrada, dias=30)
        assert datos["fuente"] == "tienda"
        antes = [d["f"] for d in datos["dias"] if d["f"] < _hace(primer_dia)]
        assert antes, entrada
        marcados, abiertos = _revisar(meta_on, datos, marcados=antes)
        assert abiertos[0] == _hace(primer_dia), entrada
        assert datos["textos"]["sin_dia"] == "antes de la primera copia"


def test_mezcla_con_la_tienda_mas_nueva_que_meta(meta_on):
    """La cuenta de Meta trae 30 días y la tienda 10: el inicio común es el de la tienda (la fuente más nueva)."""
    _montar(tiendas=[("NO", 10, 10)], cuentas=[(SE, "SE", 30)])
    datos = _grafica(meta_on, "", dias=30)
    assert datos["fuente"] == "mixta"
    antes = [d["f"] for d in datos["dias"] if d["f"] < _hace(9)]
    assert len(antes) >= 15
    marcados, abiertos = _revisar(meta_on, datos, marcados=antes)
    assert abiertos[0] == _hace(9)
    assert datos["textos"]["sin_dia"] == "todavía no estaban todas tus fuentes"


def test_la_grafica_nace_en_un_dia_que_abre_aunque_la_unica_copia_sea_de_hoy(meta_on):
    """Cuenta de Meta recién conectada con su primer gasto hoy: el inicio común es hoy, ningún día abre y la gráfica
    no puede pedir el detalle de ayer (antes se quedaba en «Cargando…» sin terminar)."""
    _montar(tiendas=[("NO", 30, 30)], cuentas=[(SE, "SE", 1)])
    datos = _grafica(meta_on, "", dias=30)
    marcados, abiertos = _revisar(meta_on, datos)
    assert abiertos == [] and len(marcados) == len(datos["dias"]) - 1
    assert datos["dia_inicial"] == ""
    # Con tres días de copia, el día con el que nace es el último que abre.
    for n in (1, 2):
        f = _hace(n)
        mdatos.reemplazar_cuenta_dias("acme", SE, f, f, [_dia(f, 1000, 2000, compras=4)])
    datos = _grafica(meta_on, "", dias=30)
    marcados, abiertos = _revisar(meta_on, datos)
    assert abiertos == [_hace(2), _hace(1)] and datos["dia_inicial"] == _hace(1)


def test_solo_triple_whale_con_la_unica_copia_de_hoy_nace_sin_dia(meta_on):
    _montar(tiendas=[("NO", 1, 1)])
    datos = _grafica(meta_on, "NO", dias=30)
    marcados, abiertos = _revisar(meta_on, datos)
    assert abiertos == [] and marcados and datos["dia_inicial"] == ""
