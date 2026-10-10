"""Las partes de Meta que pinta la pestaña Rendimiento (spec 2026-10-08 meta rendimiento §8; desde el 2026-10-09 su
`contexto` se jubiló con la pestaña «Meta», spec 2026-10-09 R1): el veredicto de cada anuncio contra SU cuenta, la
paginación, el estado de la copia y pocas consultas para todo. Las reglas de moneda que vigilaba la pestaña vieja
(«Todas» en USD con la tasa de cada día, nunca una tasa inventada, una cuenta sin moneda) se vigilan ahora donde se
suman las cuentas: `pestana_rendimiento.resumen`, con las mismas siembras."""
from datetime import date, timedelta

import pytest
from sqlalchemy import event

import db
import idiomas
from meta_rendimiento import cuentas, datos, panel
from pestana_rendimiento import entradas as E
from pestana_rendimiento import resumen

HOY = date(2026, 10, 8)
A, B, C = "act_1", "act_2", "act_3"
DESDE, HASTA = "2026-09-09", "2026-10-08"          # 30 días hasta HOY


@pytest.fixture
def conectado(monkeypatch):
    monkeypatch.setattr(panel.proyectos, "reglas_defecto", lambda cliente: {})


def _cuentas(*pares):
    cuentas.elegir("hf", [{"id": act, "name": f"HappyFlops {act}", "currency": moneda, "pais": pais}
                          for act, moneda, pais in pares])


def _dia(fecha, gasto, valor, compras=1, impresiones=1000):
    return dict(fecha=fecha, gasto=gasto, impresiones=impresiones, alcance=800, clics=20, clics_salida=10,
                compras=compras, valor=valor, vistas_3s=300, thruplays=100)


def _ad(fecha, ad, gasto, valor, compras=0, impresiones=5000, campaign="c1", adset="s1"):
    return dict(fecha=fecha, campaign_id=campaign, adset_id=adset, ad_id=ad, gasto=gasto, impresiones=impresiones,
                clics=100, clics_salida=60, compras=compras, valor=valor, vistas_3s=1500, thruplays=500,
                p25=900, p50=700, p75=500, p100=300)


def _tasa(moneda, fecha, usd):
    with db.conectar() as con:
        con.execute(db.tasa_cambio.insert().values(fecha=fecha, moneda=moneda, usd_por_unidad=usd, fuente="bce",
                                                   creado_en=db.ahora()))


def _por_id():
    return {c["ad_account_id"]: c for c in panel.lista("hf")}


def _anuncios(ids, pagina=0):
    with idiomas.en_idioma("es"):
        return panel.anuncios_evaluados("hf", ids, DESDE, HASTA, HOY, _por_id(), pagina)


# ---- las partes -------------------------------------------------------------------------------------------

def test_la_lista_trae_el_pais_en_palabras_y_su_bandera(base_temporal):
    _cuentas((A, "SEK", "NO"), (B, "SEK", None))
    with idiomas.en_idioma("es"):
        por_id = _por_id()
    assert por_id[A]["nombre_pais"] == "Noruega" and por_id[A]["bandera"]
    assert por_id[B]["nombre_pais"] == "" and not por_id[B]["bandera"]


def test_sin_dias_copiados_las_partes_vienen_vacias(base_temporal, conectado):
    """Con cuentas pero sin nada copiado no se rompe nada: ni anuncios, ni campañas, ni días."""
    _cuentas((A, "SEK", "NO"), (B, "SEK", "SE"))
    an = _anuncios([A, B])
    assert an["anuncios"] == [] and an["n_anuncios"] == 0 and an["ev"]["hay_ventas"] is False
    es = panel.estructura("hf", [A, B], DESDE, HASTA, 30, _por_id())
    assert es["campanas"] == [] and es["conjuntos"] == [] and es["hay_mas_conjuntos"] is False
    assert panel.estado_copia("hf", list(_por_id().values()))["rango"]["filas"] == 0


def test_veredicto_por_anuncio_contra_su_propia_cuenta(base_temporal, conectado, monkeypatch):
    _cuentas((A, "SEK", "NO"), (B, "SEK", "SE"))
    datos.reemplazar_cuenta_dias("hf", A, "2026-10-05", "2026-10-05", [_dia("2026-10-05", 400, 1000)])
    datos.reemplazar_cuenta_dias("hf", B, "2026-10-05", "2026-10-05", [_dia("2026-10-05", 10000, 0)])
    datos.reemplazar_anuncio_dias("hf", A, "2026-10-05", "2026-10-05", [
        _ad("2026-10-05", "gana", 100, 1000, compras=5), _ad("2026-10-05", "pierde", 300, 0, compras=0)])
    # En la otra cuenta, un anuncio caro con muchas compras: si se mezclaran las cuentas, el costo por venta subiría
    # (de 80 a casi 700) y «pierde» dejaría de ser perdedor.
    datos.reemplazar_anuncio_dias("hf", B, "2026-10-05", "2026-10-05", [
        _ad("2026-10-05", "grande", 10000, 30000, compras=10, campaign="c2", adset="s2")])
    datos.guardar_objetos("hf", A, [{"nivel": "anuncio", "objeto_id": "gana", "nombre": "Video gana",
                                     "estado": "ACTIVE", "miniatura_url": "https://scontent.xx.fbcdn.net/gana.jpg"}])
    leer = datos.totales_por_anuncio

    def con_rastreo_roto(*a, **k):                  # «sin_rastreo» es de Triple Whale: aquí nunca se muestra
        return [dict(t, utm_ok=False) for t in leer(*a, **k)]
    monkeypatch.setattr(panel.datos, "totales_por_anuncio", con_rastreo_roto)
    an = _anuncios([A, B])
    por_id = {a["ad_id"]: a for a in an["anuncios"]}
    assert por_id["gana"]["veredicto"] == "ganador" and por_id["pierde"]["veredicto"] == "perdedor"
    assert [a["ad_id"] for a in an["anuncios"]] == ["grande", "gana", "pierde"]   # veredicto y luego gasto
    assert all("sin_rastreo" not in a["problemas"] for a in an["anuncios"])
    assert por_id["gana"]["ad_account_id"] == A and por_id["gana"]["moneda"] == "SEK"
    assert por_id["gana"]["estado"] == "ACTIVE" and por_id["gana"]["miniatura_url"] == "https://scontent.xx.fbcdn.net/gana.jpg"
    assert por_id["gana"]["nombre"] == "Video gana" and por_id["grande"]["ad_account_id"] == B
    assert an["conteo"]["ganador"] == 2 and an["conteo"]["perdedor"] == 1 and an["meta_roas"] == 2.0
    # Campañas y conjuntos en la moneda de su cuenta.
    es = panel.estructura("hf", [A, B], DESDE, HASTA, 30, _por_id())
    assert {c["campaign_id"]: c["moneda"] for c in es["campanas"]} == {"c1": "SEK", "c2": "SEK"}
    assert es["conjuntos"][0]["adset_id"] == "s2" and es["conjuntos"][0]["m"]["roas"] == 3


def test_paginacion_de_anuncios(base_temporal, conectado):
    _cuentas((A, "SEK", "NO"))
    datos.reemplazar_cuenta_dias("hf", A, "2026-10-05", "2026-10-05", [_dia("2026-10-05", 300, 0)])
    datos.reemplazar_anuncio_dias("hf", A, "2026-10-05", "2026-10-05",
                                  [_ad("2026-10-05", f"a{i:02d}", 10 + i, 0) for i in range(30)])
    primera = _anuncios([A])
    assert len(primera["anuncios"]) == panel.POR_PAGINA == 24 and primera["hay_mas_anuncios"] is True
    assert primera["n_anuncios"] == 30 and len(primera["ev"]["anuncios"]) == 30
    segunda = _anuncios([A], pagina=1)
    assert len(segunda["anuncios"]) == 6 and segunda["hay_mas_anuncios"] is False
    vistos = [a["ad_id"] for a in primera["anuncios"] + segunda["anuncios"]]
    assert len(set(vistos)) == 30
    assert _anuncios([A], pagina="x")["anuncios"] == primera["anuncios"]
    assert _anuncios([A], pagina="99999999999999999999999")["anuncios"] == []     # un OFFSET enorme no revienta


def test_jobs_sync_y_ultima_copia_del_alcance(base_temporal, conectado, monkeypatch):
    _cuentas((A, "SEK", "NO"), (B, "SEK", "SE"))
    cuentas.actualizar("hf", A, ultima_copia="2026-10-08T06:00:00")
    cuentas.actualizar("hf", B, ultima_copia="2026-10-08T03:00:00")
    monkeypatch.setattr(panel.tareas_mr, "syncs_en_curso", lambda cliente: [panel.tareas_mr.job_id_sync("hf", B)])
    por_id = _por_id()
    estado = panel.estado_copia("hf", [por_id[A], por_id[B]])
    assert estado["ultima_copia"] == "2026-10-08T03:00:00" and estado["sync_ocupado"] is False
    assert [j["cuenta"]["ad_account_id"] for j in estado["jobs_sync"]] == [B]
    estado = panel.estado_copia("hf", [por_id[A]])
    assert estado["ultima_copia"] == "2026-10-08T06:00:00" and estado["jobs_sync"] == []
    assert panel.estado_copia("hf", [por_id[B]])["sync_ocupado"] is True


def test_pocas_consultas_con_tres_cuentas(base_temporal, conectado):
    _cuentas((A, "SEK", "NO"), (B, "NOK", "SE"), (C, "EUR", "FI"))
    for act in (A, B, C):
        datos.reemplazar_cuenta_dias("hf", act, "2026-08-15", "2026-10-07",
                                     [_dia("2026-08-15", 10, 20), _dia("2026-10-07", 30, 90)])
        datos.reemplazar_anuncio_dias("hf", act, "2026-09-25", "2026-10-07",
                                      [_ad(f, f"{act}-{i}", 5, 10, compras=1) for f in ("2026-09-25", "2026-10-07")
                                       for i in range(5)])
        datos.guardar_alcance("hf", act, [{"nivel": "campana", "objeto_id": "c1", "ventana": 30, "alcance": 10,
                                           "frecuencia": 1.0}])
    por_id = _por_id()
    consultas = []

    def contar(conn, cursor, statement, parameters, context, executemany):
        consultas.append(statement)
    event.listen(db.engine(), "before_cursor_execute", contar)
    try:
        with idiomas.en_idioma("es"):
            an = panel.anuncios_evaluados("hf", [A, B, C], DESDE, HASTA, HOY, por_id)
            panel.estructura("hf", [A, B, C], DESDE, HASTA, 30, por_id)
            panel.estado_copia("hf", list(por_id.values()))
    finally:
        event.remove(db.engine(), "before_cursor_execute", contar)
    assert len(an["anuncios"]) == 15
    assert len(consultas) <= 10, consultas


# ---- las monedas, donde ahora se suman las cuentas (pestana_rendimiento.resumen, R6) ------------------------

def _hace(n):
    return (date.today() - timedelta(days=n)).isoformat()


def _resumen(clave=None):
    es = E.armar([], panel.lista("hf"), {})
    actual = E.elegir(es, clave)
    with idiomas.en_idioma("es"):
        return resumen.contexto("hf", es, actual, E.alcance(es, actual), 0, date.today(), "USD")


def _tarjetas(c):
    return {t["clave"]: t["valor"] for t in c["resultados"]["tarjetas"]}


def test_todas_en_usd_con_la_tasa_de_cada_dia(base_temporal):
    """Dos cuentas en monedas distintas: «Todas» en USD, cada día de cada cuenta con SU tasa de ese día."""
    _cuentas((A, "SEK", "NO"), (B, "NOK", "SE"))
    for n, tasa_sek in ((2, 0.1), (1, 0.2)):
        f = _hace(n)
        datos.reemplazar_cuenta_dias("hf", A, f, f, [_dia(f, 100, 300, compras=2)])
        datos.reemplazar_cuenta_dias("hf", B, f, f, [_dia(f, 50, 100, compras=1)])
        _tasa("SEK", f, tasa_sek)
        _tasa("NOK", f, 0.1)
    c = _resumen()
    assert c["moneda"] == "USD" and c["usd_ok"] is True
    t = _tarjetas(c)
    assert t["gasto"] == pytest.approx(100 * 0.1 + 100 * 0.2 + 2 * 50 * 0.1)
    assert t["ventas"] == pytest.approx(300 * 0.1 + 300 * 0.2 + 2 * 100 * 0.1)
    # «Por país»: cada cuenta en su moneda y en USD.
    por = {f["entrada"]["clave"]: f for f in c["por_pais"]}
    assert por["NO"]["moneda"] == "SEK" and por["NO"]["gasto"] == 200 and por["NO"]["gasto_usd"] == pytest.approx(30)
    # Una cuenta sola se ve en su moneda.
    sola = _resumen("NO")
    assert sola["moneda"] == "SEK" and _tarjetas(sola)["gasto"] == 200


def test_tasa_de_hace_cuatro_dias_aun_sirve_y_de_hace_cinco_ya_no(base_temporal):
    """Ruling R24: un día sin tasa publicada usa la última anterior solo si es de hace 4 días o menos; si no, «USD no
    disponible» (nunca una tasa de hace semanas)."""
    _cuentas((A, "SEK", "NO"), (B, "NOK", "SE"))
    _tasa("SEK", _hace(10), 0.1)
    f = _hace(6)                                                       # a 4 días de la última tasa de SEK
    datos.reemplazar_cuenta_dias("hf", A, f, f, [_dia(f, 100, 300)])
    datos.reemplazar_cuenta_dias("hf", B, f, f, [_dia(f, 50, 100)])
    _tasa("NOK", f, 0.1)
    c = _resumen()
    assert c["usd_ok"] is True and _tarjetas(c)["gasto"] == pytest.approx(10 + 5)
    f = _hace(5)                                                       # a 5 días: ya no
    datos.reemplazar_cuenta_dias("hf", A, f, f, [_dia(f, 100, 300)])
    datos.reemplazar_cuenta_dias("hf", B, f, f, [_dia(f, 50, 100)])
    _tasa("NOK", f, 0.1)
    c = _resumen()
    assert c["usd_ok"] is False and c["resultados"] is None


def test_todas_con_una_cuenta_sin_moneda_usd_no_disponible(base_temporal):
    """Una cuenta sin moneda conocida no se convierte (no hay tasa para ella) ni se suma como si fuera de la moneda de
    las demás: «Todas» dice USD no disponible y su fila de «Por país» va sin USD; la cuenta con moneda, sola, sí."""
    _cuentas((A, "SEK", "NO"), (B, "", "SE"))
    f = _hace(1)
    datos.reemplazar_cuenta_dias("hf", A, f, f, [_dia(f, 100, 300)])
    datos.reemplazar_cuenta_dias("hf", B, f, f, [_dia(f, 50, 100)])
    _tasa("SEK", f, 0.1)
    c = _resumen()
    assert c["moneda"] == "USD" and c["usd_ok"] is False and c["resultados"] is None
    por = {f_["entrada"]["clave"]: f_ for f_ in c["por_pais"]}
    assert por["NO"]["gasto_usd"] == pytest.approx(10) and por["SE"]["gasto_usd"] is None
    sola = _resumen("NO")
    assert sola["moneda"] == "SEK" and sola["usd_ok"] is True and _tarjetas(sola)["gasto"] == 100
