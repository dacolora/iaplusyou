"""Las partes de Meta que pinta la pestaña Rendimiento (spec 2026-10-08 meta rendimiento §8; desde el 2026-10-09 su
`contexto` se jubiló con la pestaña «Meta», spec 2026-10-09 R1): el veredicto de cada anuncio contra SU cuenta, la
paginación, el estado de la copia y pocas consultas para todo. Las reglas de moneda que vigilaba la pestaña vieja
(«Todas» en USD con la tasa de cada día, nunca una tasa inventada, una cuenta sin moneda) se vigilan ahora donde se
suman las cuentas: `pestana_rendimiento.resumen`, con las mismas siembras.

Desde la integración con main (2026-10-10) también lo de Meta rendimiento E2 que la vieja pestaña armaba en su
`contexto` (Diagnóstico, Segmentos, «Evaluación con IA»): hoy lo arma `panel.diagnostico` sobre las cuentas que le pasa
la pestaña Rendimiento, y estas pruebas de main lo vigilan igual por medio de `_contexto` (la cuenta pedida o todas,
como la entrada de un país o «Todas»)."""
from datetime import date, datetime, timedelta

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


def test_cuenta_elegida():
    """`cuenta_elegida` volvió con la integración con main: la usa `analisis.preparar` cuando la evaluación pagada llega
    con `cuenta` (sin `entrada`), como la pedía la vieja pestaña."""
    unas = [{"ad_account_id": A}, {"ad_account_id": B}]
    assert panel.cuenta_elegida(unas, B) is unas[1]
    assert panel.cuenta_elegida(unas, "2") is unas[1]
    assert panel.cuenta_elegida(unas, "act_9") is None and panel.cuenta_elegida(unas, "") is None
    assert panel.cuenta_elegida(unas, None) is None and panel.cuenta_elegida(unas, ["x"]) is None
    assert panel.cuenta_elegida(unas[:1], None) is unas[0]           # con una sola cuenta, siempre esa
    assert panel.cuenta_elegida([], A) is None


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


# ---------------------------------------------------------- Meta rendimiento E2 (de main, integración 2026-10-10) ---

def _contexto(dias=30, cuenta=None, hoy=HOY):
    """Lo que la vieja pestaña Meta armaba con `panel.contexto` para el Diagnóstico, los Segmentos y la «Evaluación con
    IA», hoy por partes como lo pide la pestaña Rendimiento: `panel.diagnostico` sobre la cuenta pedida (una entrada) o
    todas («Todas»), con las mismas cuentas como estructura y como fuente, y los anuncios ya evaluados del periodo (los
    de la galería) en `evaluados_periodo`. Más `anuncios`: la primera página de esos anuncios (lo que la tabla vieja
    mostraba)."""
    por_id = _por_id()
    en = [por_id[cuenta]] if cuenta else list(por_id.values())
    ids = [c["ad_account_id"] for c in en]
    desde, hasta, _, _ = panel.rango_fechas("hf", ids, dias, hoy)
    with idiomas.en_idioma("es"):
        an = panel.anuncios_evaluados("hf", ids, desde, hasta, hoy, por_id)
        vivos = set(panel.tareas_mr.trabajos_del_panel("hf"))
        ctx = panel.diagnostico("hf", en, ids, dias, hoy, por_id, vivos, evaluados_periodo=an["ev"]["anuncios"])
    return dict(ctx, anuncios=an["anuncios"])


def _ev(estado, cliente="hf", **campos):
    eid = datos.crear_evaluacion(cliente, [A], "2026-09-09", "2026-10-08", "SEK", [], [],
                                 extra={"cuenta": None, "resumen": []})
    if estado != "en_cola":
        datos.actualizar_evaluacion(eid, estado=estado, **campos)
    return eid


def test_el_diagnostico_hace_pocas_consultas_fijas(base_temporal, conectado):
    """De la vieja `test_pocas_consultas_con_tres_cuentas` de main (E2): el Diagnóstico, los Segmentos y la sección
    «Evaluación con IA» suman un número fijo de lecturas que no crece con las cuentas, las filas ni las evaluaciones
    guardadas (diez, la peor forma: una lista tras nueve que fallaron): días de cuenta, las tres de anuncios de 30 días,
    la frecuencia de 7 días, los desgloses, los objetos activos y UNA de evaluaciones. Con otro periodo y sin los
    anuncios del periodo ya evaluados, tres más (dos con 7 días)."""
    _cuentas((A, "SEK", "NO"), (B, "NOK", "SE"), (C, "EUR", "FI"))
    for act in (A, B, C):
        datos.reemplazar_cuenta_dias("hf", act, "2026-08-15", "2026-10-07",
                                     [_dia("2026-08-15", 10, 20), _dia("2026-10-07", 30, 90)])
        datos.reemplazar_anuncio_dias("hf", act, "2026-09-25", "2026-10-07",
                                      [_ad(f, f"{act}-{i}", 5, 10, compras=1) for f in ("2026-09-25", "2026-10-07")
                                       for i in range(5)])
    _ev("lista", resultado={"resumen": "vieja", "plan": []})
    for _ in range(9):
        _ev("error", error="falló")
    por_id = _por_id()
    en = list(por_id.values())
    for dias, con_periodo, tope in ((0, False, 8), (30, False, 8), (14, True, 8), (14, False, 11), (7, False, 10),
                                    (90, False, 11)):
        consultas = []

        def contar(conn, cursor, statement, parameters, context, executemany):
            consultas.append(statement)
        desde, hasta, _, _ = panel.rango_fechas("hf", [A, B, C], dias, HOY)
        evaluados = (panel.anuncios_evaluados("hf", [A, B, C], desde, hasta, HOY, por_id)["ev"]["anuncios"]
                     if con_periodo else None)
        event.listen(db.engine(), "before_cursor_execute", contar)
        try:
            ctx = panel.diagnostico("hf", en, [A, B, C], dias, HOY, por_id, set(), evaluados_periodo=evaluados)
        finally:
            event.remove(db.engine(), "before_cursor_execute", contar)
        assert len(consultas) <= tope, (dias, con_periodo, len(consultas))
        assert sum("FROM meta_evaluacion" in q for q in consultas) == 1
        assert ctx["evaluacion"]["ultima_lista"]["resultado"]["resumen"] == "vieja" and ctx["evaluacion"]["n"] > 0


# ---- Diagnóstico y Segmentos (E2) ----

def _seg(clave, gasto, valor=0.0, compras=0):
    return dict(clave=clave, gasto=gasto, impresiones=1000, clics=40, clics_salida=25, compras=compras, valor=valor)


def _sembrar_diagnostico():
    """Cuenta A (SEK) con ROAS 0,3 en 30 días (cuenta_roas_bajo, alta), un perdedor activo que gasta en la última
    semana y un desglose por país donde SE es caro. Cuenta B (SEK) sana."""
    _cuentas((A, "SEK", "NO"), (B, "SEK", "SE"))
    dias = [f"2026-09-{d:02d}" for d in range(9, 31)] + [f"2026-10-{d:02d}" for d in range(1, 9)]
    datos.reemplazar_cuenta_dias("hf", A, dias[0], dias[-1], [_dia(f, 1000, 300) for f in dias])
    datos.reemplazar_cuenta_dias("hf", B, dias[0], dias[-1], [_dia(f, 100, 400) for f in dias])
    datos.reemplazar_anuncio_dias("hf", A, "2026-10-05", "2026-10-05", [
        _ad("2026-10-05", "gana", 100, 1000, compras=5), _ad("2026-10-05", "pierde", 3000, 0, compras=0)])
    datos.guardar_objetos("hf", A, [{"nivel": "anuncio", "objeto_id": "pierde", "nombre": "Video pierde",
                                     "estado": "ACTIVE"}])
    datos.reemplazar_desgloses("hf", A, 30, "pais", [_seg("NO", 800, 2400, 8), _seg("SE", 200, 0, 0)])
    datos.reemplazar_desgloses("hf", A, 7, "pais", [_seg("NO", 80, 240, 1)])
    datos.reemplazar_desgloses("hf", B, 30, "pais", [_seg("NO", 50, 200, 2), _seg("SE", 10, 40, 1)])


def _por_tipo(recs):
    return {(r["tipo"], r["cuenta"]): r for r in recs}


def test_el_diagnostico_trae_las_reglas_de_cada_cuenta(base_temporal, conectado):
    _sembrar_diagnostico()
    ctx = _contexto()
    recs = _por_tipo(ctx["recomendaciones"])
    assert recs[("cuenta_roas_bajo", A)]["nivel"] == "alta"
    perdedores = recs[("perdedores_gastando", A)]
    assert perdedores["objetos"][0]["id"] == "pierde" and perdedores["nivel"] == "alta"
    assert ("segmento_caro", A) in recs and not [r for r in ctx["recomendaciones"] if r["cuenta"] == B]
    assert ctx["conteo_recomendaciones"]["alta"] == 2 and ctx["conteo_recomendaciones"]["media"] >= 1
    # Una cuenta: solo las suyas.
    una = _contexto(cuenta=B)
    assert una["recomendaciones"] == []


def _sembrar_ventanas_distintas():
    """`_sembrar_diagnostico` más tres anuncios que cada ventana ve distinto (hoy 2026-10-08): `rechazado`
    (DISAPPROVED) gastó SOLO hace 20 días, así que lo ven los 30 días y no los 7; `viejo` (WITH_ISSUES) gastó hace 49
    días, así que solo lo ve una ventana de 90; `mixto` (activo) gastó 3 000 sin vender hace 20 días y 100 con ROAS 10
    hace 2: en 30 días es perdedor que sigue gastando, en 7 días es ganador."""
    _sembrar_diagnostico()
    datos.reemplazar_anuncio_dias("hf", A, "2026-09-18", "2026-09-18", [
        _ad("2026-09-18", "rechazado", 500, 0), _ad("2026-09-18", "mixto", 3000, 0)])
    datos.reemplazar_anuncio_dias("hf", A, "2026-10-06", "2026-10-06", [_ad("2026-10-06", "mixto", 100, 1000, compras=5)])
    datos.reemplazar_anuncio_dias("hf", A, "2026-08-20", "2026-08-20", [_ad("2026-08-20", "viejo", 400, 0)])
    datos.guardar_objetos("hf", A, [
        {"nivel": "anuncio", "objeto_id": "rechazado", "nombre": "Video rechazado", "estado": "DISAPPROVED"},
        {"nivel": "anuncio", "objeto_id": "viejo", "nombre": "Video viejo", "estado": "WITH_ISSUES"},
        {"nivel": "anuncio", "objeto_id": "mixto", "nombre": "Video mixto", "estado": "ACTIVE"}])


def _objetos_de(recs, tipo):
    return sorted(o["id"] for r in recs if r["tipo"] == tipo for o in r["objetos"])


def test_las_reglas_miran_siempre_7_y_30_dias_sea_cual_sea_el_periodo(base_temporal, conectado):
    """Lo que el período cambia es la tabla de anuncios, no el Diagnóstico: sus recomendaciones COMPLETAS (texto,
    cifras, objetos) son las mismas con 7, 14, 30 y 90 días. Los datos sembrados dan resultados distintos según la
    ventana (un rechazado de hace 20 días, uno con problemas de hace 49, un perdedor de 30 días que en 7 gana): una
    regla que mirara el período en vez de 7 y 30 daría otra lista."""
    _sembrar_ventanas_distintas()
    por_periodo = {d: _contexto(d)["recomendaciones"] for d in panel.PERIODOS}
    base = por_periodo[30]
    # Lo esperado de las ventanas de 7 y 30 días: el rechazado (solo gastó en los 30) y el perdedor de 30 días que
    # gastó esta semana cuentan; el de hace 49 días no entra en ninguna.
    assert _objetos_de(base, "anuncios_con_problemas") == ["rechazado"]
    assert _objetos_de(base, "perdedores_gastando") == ["mixto", "pierde"]
    for dias in (7, 14, 90):
        assert por_periodo[dias] == base, dias


def test_el_analisis_de_ia_lee_las_mismas_recomendaciones_que_el_diagnostico_sea_cual_sea_el_periodo(
        base_temporal, conectado):
    """La evaluación con IA (`analisis.preparar`) y el Diagnóstico del panel calculan las reglas por separado: con
    cualquier período tienen que dar las mismas (si no, Claude comentaría recomendaciones que la persona no ve)."""
    from meta_rendimiento import analisis
    _sembrar_ventanas_distintas()
    for dias in panel.PERIODOS:
        del_panel = _contexto(dias)["recomendaciones"]
        prep = analisis.preparar("hf", dias=dias, hoy=HOY)
        assert del_panel and [r["id"] for r in prep["recomendaciones"]] == \
            [r["id"] for r in del_panel][:analisis.MAX_RECOMENDACIONES], dias
    assert [r["id"] for r in analisis.preparar("hf", dias=7, hoy=HOY)["recomendaciones"]] == \
        [r["id"] for r in _contexto(7)["recomendaciones"]]


def test_con_el_periodo_de_30_dias_los_anuncios_se_evaluan_una_sola_vez(base_temporal, conectado, monkeypatch):
    """De main (revisión de la Task 4 de E2): evaluar dos veces lo mismo era un cuarto de la carga. En
    `panel.diagnostico` las reglas evalúan los 30 días UNA vez y la «Evaluación con IA» de 30 días (también la de
    «Desde el inicio») toma de ahí sus anuncios sin volver a evaluar; con otro periodo usa los ya evaluados de la
    galería (`evaluados_periodo`) y solo sin ellos evalúa aparte. Lo que sale es lo mismo."""
    _sembrar_diagnostico()
    sin_reuso = panel.recomendaciones_de_cuenta("hf", A, hoy=HOY)
    por_id = _por_id()
    en = list(por_id.values())
    original, llamadas = panel._evaluar, []

    def contar(*args, **kwargs):
        llamadas.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(panel, "_evaluar", contar)
    for dias, con_periodo, esperadas in ((30, False, 1), (0, False, 1), (7, True, 1), (90, True, 1), (7, False, 2)):
        evaluados = ([{"ad_id": "x", "veredicto": "en_prueba", "m": {"gasto": 1.0}}] if con_periodo else None)
        llamadas.clear()
        with idiomas.en_idioma("es"):
            ctx = panel.diagnostico("hf", en, [A, B], dias, HOY, por_id, set(), evaluados_periodo=evaluados)
        assert len(llamadas) == esperadas, (dias, con_periodo, len(llamadas))
        assert [r["id"] for r in ctx["recomendaciones"] if r["cuenta"] == A] == [r["id"] for r in sin_reuso]
        if dias == 30:
            assert [r for r in ctx["recomendaciones"] if r["cuenta"] == A] == sin_reuso
    # Las cifras de las reglas no se cuelan en las filas de anuncios que pinta la galería.
    llamadas.clear()
    ctx = _contexto(30)
    assert ctx["anuncios"] and not any("gasto_7" in a or "gasto_30" in a for a in ctx["anuncios"])


def test_recomendaciones_de_cuenta_son_las_del_panel_sin_flask(base_temporal, conectado):
    _sembrar_diagnostico()
    del_panel = [r for r in _contexto()["recomendaciones"] if r["cuenta"] == A]
    de_la_copia = panel.recomendaciones_de_cuenta("hf", A, hoy=HOY)
    assert [r["id"] for r in de_la_copia] == [r["id"] for r in del_panel]
    assert panel.recomendaciones_de_cuenta("hf", "act_999", hoy=HOY) == []
    assert panel.recomendaciones_de_cuenta("otro", A, hoy=HOY) == []


def _envejecer_desgloses(act, horas):
    viejo = (datetime.now() - timedelta(hours=horas)).isoformat(timespec="seconds")
    with db.conectar() as con:
        con.execute(db.meta_desglose.update().where(db.meta_desglose.c.ad_account_id == act).values(
            calculado_en=viejo))


def test_un_desglose_de_mas_de_48_horas_no_cuenta_ni_se_muestra_como_actual(base_temporal, conectado):
    _sembrar_diagnostico()
    _envejecer_desgloses(A, 47)
    ctx = _contexto()
    assert ("segmento_caro", A) in _por_tipo(ctx["recomendaciones"]) and ctx["segmentos"]["viejos"] == []
    _envejecer_desgloses(A, 75)
    ctx = _contexto()
    assert ("segmento_caro", A) not in _por_tipo(ctx["recomendaciones"])
    assert [(v["cuenta"]["ad_account_id"], v["dias"]) for v in ctx["segmentos"]["viejos"]] == [(A, 3)]
    # En «Segmentos» solo queda lo vigente (la cuenta B).
    pais, = ctx["segmentos"]["bloques"]
    assert {f["clave"]: f["gasto"] for f in pais["grupos"][0]["filas"]} == {"NO": 50, "SE": 10}
    assert panel.recomendaciones_de_cuenta("hf", A, hoy=HOY) and \
        ("segmento_caro", A) not in _por_tipo(panel.recomendaciones_de_cuenta("hf", A, hoy=HOY))


def test_segmentos_suman_por_clave_si_comparten_moneda_y_marcan_los_caros(base_temporal, conectado):
    _sembrar_diagnostico()
    ctx = _contexto()
    assert ctx["ventana_segmentos"] == 30
    pais, = ctx["segmentos"]["bloques"]
    assert pais["dimension"] == "pais" and pais["nombre"] == "País"
    grupo, = pais["grupos"]
    assert grupo["cuenta"] is None and grupo["moneda"] == "SEK" and grupo["mas"] == 0
    no, se = grupo["filas"]
    assert (no["clave"], no["gasto"], no["valor"], no["compras"]) == ("NO", 850, 2600, 10)
    assert no["roas"] == pytest.approx(2600 / 850) and no["cpa"] == pytest.approx(85)
    assert se["nombre"] == "Suecia" and se["caro_en"] == ["HappyFlops act_1"] and no["caro_en"] == []
    assert se["roas"] == pytest.approx(40 / 210) and se["cpa"] == pytest.approx(210)
    # Con el período de 7 días, la ventana de 7: solo lo copiado para esa ventana.
    siete = _contexto(7)
    assert siete["ventana_segmentos"] == 7
    assert [f["clave"] for f in siete["segmentos"]["bloques"][0]["grupos"][0]["filas"]] == ["NO"]


def test_segmentos_con_monedas_distintas_van_por_cuenta(base_temporal, conectado):
    _cuentas((A, "SEK", "NO"), (B, "EUR", "FI"))
    for act in (A, B):
        datos.reemplazar_cuenta_dias("hf", act, "2026-10-05", "2026-10-05", [_dia("2026-10-05", 100, 300)])
    datos.reemplazar_desgloses("hf", A, 30, "dispositivo", [_seg("mobile_app", 90, 270, 3), _seg("desktop", 10)])
    datos.reemplazar_desgloses("hf", B, 30, "dispositivo", [_seg("mobile_app", 5, 10, 1)])
    ctx = _contexto()
    disp, = ctx["segmentos"]["bloques"]
    assert [(g["cuenta"]["ad_account_id"], g["moneda"]) for g in disp["grupos"]] == [(A, "SEK"), (B, "EUR")]
    assert [f["nombre"] for f in disp["grupos"][0]["filas"]] == ["Celular (app)", "Computador"]
    assert disp["grupos"][0]["filas"][1]["cpa"] is None and disp["grupos"][0]["filas"][1]["roas"] == 0
    # Una sola cuenta: su moneda y su nombre.
    una = _contexto(cuenta=B)
    g, = una["segmentos"]["bloques"][0]["grupos"]
    assert g["moneda"] == "EUR" and [f["gasto"] for f in g["filas"]] == [5]


def test_segmentos_muestran_los_diez_de_mas_gasto(base_temporal, conectado):
    _cuentas((A, "SEK", "NO"))
    datos.reemplazar_cuenta_dias("hf", A, "2026-10-05", "2026-10-05", [_dia("2026-10-05", 100, 300)])
    datos.reemplazar_desgloses("hf", A, 30, "pais", [_seg(c, 100 - i) for i, c in enumerate(
        ["NO", "SE", "FI", "DK", "DE", "NL", "PL", "FR", "ES", "IT", "PT", "BE"])])
    g, = _contexto()["segmentos"]["bloques"][0]["grupos"]
    assert len(g["filas"]) == panel.MAX_SEGMENTOS == 10 and g["mas"] == 2 and g["filas"][0]["clave"] == "NO"


# ---------------------------------------------------------- Evaluación con IA (E2, Task 6) ---

def _sembrar_muestra():
    """Cuenta A con un ganador y perdedores, cuenta B con un anuncio en prueba (en los últimos 7 y 30 días)."""
    _cuentas((A, "SEK", "NO"), (B, "SEK", "SE"))
    for f in ("2026-10-05", "2026-09-20"):
        datos.reemplazar_cuenta_dias("hf", A, f, f, [_dia(f, 400, 1000, compras=5)])
        datos.reemplazar_cuenta_dias("hf", B, f, f, [_dia(f, 200, 300, compras=2)])
    datos.reemplazar_anuncio_dias("hf", A, "2026-09-20", "2026-10-05", [
        _ad(f, ad, gasto, valor, compras=compras) for f in ("2026-09-20", "2026-10-05")
        for ad, gasto, valor, compras in (("gana", 100, 1000, 20), ("p1", 60, 0, 0), ("p2", 55, 0, 0),
                                          ("p3", 52, 0, 0), ("medio", 40, 60, 1))])
    datos.reemplazar_anuncio_dias("hf", B, "2026-10-05", "2026-10-05",
                                  [_ad("2026-10-05", "otra", 200, 300, compras=2, adset="s2", campaign="c2")])


@pytest.mark.parametrize("dias,cuenta", [(30, None), (7, None), (90, None), (30, A), (14, B)])
def test_el_boton_cuenta_los_mismos_anuncios_que_cobra_la_ruta(base_temporal, conectado, dias, cuenta):
    """E2-R6: el N del botón sale de la evaluación que el panel ya hizo (sin `preparar`, que vuelve a leer la copia)
    y es el mismo N que la ruta cobra con `analisis.preparar`; el precio es la tarifa de ese N."""
    import gastos
    from meta_rendimiento import analisis
    _sembrar_muestra()
    ev = _contexto(dias, cuenta)["evaluacion"]
    n = len(analisis.preparar("hf", dias, cuenta, hoy=HOY)["muestra"])
    assert ev["n"] == n
    if n:
        assert ev["estimado"]["usd"] == gastos.estimar("evaluacion_meta", n=n)["usd"]
    else:
        assert ev["estimado"] is None
    assert ev["job"] is None and ev["ultima_lista"] is None and ev["anteriores"] == []


def test_el_boton_cuenta_toda_la_lista_no_la_pagina_de_24(base_temporal, conectado, monkeypatch):
    from meta_rendimiento import analisis
    _sembrar_muestra()
    n = len(analisis.preparar("hf", 30, None, hoy=HOY)["muestra"])
    monkeypatch.setattr(panel, "POR_PAGINA", 1)        # la página ya no trae la muestra entera
    ctx = _contexto()
    assert len(ctx["anuncios"]) == 1 and n > 1 and ctx["evaluacion"]["n"] == n


def test_la_seccion_trae_la_ultima_lista_la_que_fallo_despues_y_las_anteriores(base_temporal, conectado):
    _sembrar_muestra()
    vieja = _ev("lista", resultado={"resumen": "vieja", "plan": []})
    viejas = [_ev("error", error="otra falla") for _ in range(3)]
    lista = _ev("lista", resultado={"resumen": "la buena", "plan": []})
    fallo = _ev("error", error="Claude no devolvió un análisis que se pueda usar.")
    _ev("lista", cliente="otro", resultado={"resumen": "ajena", "plan": []})
    ev = _contexto()["evaluacion"]
    assert ev["ultima_lista"]["id"] == lista and ev["ultima_lista"]["resultado"]["resumen"] == "la buena"
    assert ev["fallida"]["id"] == fallo and "Claude no devolvió" in ev["fallida"]["error"]
    assert [e["id"] for e in ev["anteriores"]] == list(reversed(viejas)) + [vieja]
    assert ev["ultima_lista"]["alcance"] == "Todas las cuentas"
    # Como mucho cinco anteriores (se piden por fetch).
    for _ in range(6):
        _ev("lista", resultado={"resumen": "n", "plan": []})
    ev = _contexto()["evaluacion"]
    assert len(ev["anteriores"]) == panel.MAX_EVALUACIONES_ANTERIORES and ev["fallida"] is None


def test_la_ultima_lista_se_ve_aunque_la_sigan_muchas_que_fallaron(base_temporal, conectado):
    """Revisión de E2 (tarea 6): antes se leían ocho filas y la última buena quedaba escondida tras ocho fallos."""
    _sembrar_muestra()
    buena = _ev("lista", resultado={"resumen": "la última buena", "plan": []})
    fallos = [_ev("error", error=f"falla {i}") for i in range(panel.MAX_EVALUACIONES_ANTERIORES + 6)]
    ev = _contexto()["evaluacion"]
    assert ev["ultima_lista"]["id"] == buena and ev["ultima_lista"]["resultado"]["resumen"] == "la última buena"
    assert ev["fallida"]["id"] == fallos[-1] and ev["fallida"]["error"] == f"falla {len(fallos) - 1}"
    assert [e["id"] for e in ev["anteriores"]] == fallos[::-1][1:1 + panel.MAX_EVALUACIONES_ANTERIORES]


def test_las_evaluaciones_del_panel_son_una_sola_lectura_ligera_con_la_fila_entera_de_la_ultima_lista(base_temporal,
                                                                                                      conectado):
    _sembrar_muestra()
    for i in range(5):
        _ev("lista", resultado={"resumen": f"n{i}", "plan": []})
    consultas = []

    def contar(conn, cursor, statement, parameters, context, executemany):
        if "FROM meta_evaluacion" in statement:
            consultas.append(statement)
    event.listen(db.engine(), "before_cursor_execute", contar)
    try:
        ev = _contexto()["evaluacion"]
        panel.evaluacion_panel("sin_evaluaciones", [], set())
    finally:
        event.remove(db.engine(), "before_cursor_execute", contar)
    assert ev["ultima_lista"]["resultado"]["resumen"] == "n4" and len(ev["anteriores"]) == 4
    assert len(consultas) == 2                  # una por llamada: el proyecto con evaluaciones y el que no tiene ninguna


def test_una_evaluacion_en_curso_da_su_barra_y_no_sale_entre_las_anteriores(base_temporal, conectado):
    from tareas import meta_rendimiento as tmr
    _sembrar_muestra()
    lista = _ev("lista", resultado={"resumen": "la buena", "plan": []})
    viva = _ev("en_cola")
    assert _contexto()["evaluacion"]["job"] is None   # la fila sola, sin tarea viva: no hay barra
    tmr.encolar_evaluacion("hf", viva)
    ev = _contexto()["evaluacion"]
    assert ev["job"] == "hf__meta_eval" and ev["ultima_lista"]["id"] == lista
    assert [e["id"] for e in ev["anteriores"]] == []


def test_la_vista_de_una_evaluacion_nombra_los_objetos_y_solo_enlaza_al_administrador(monkeypatch):
    monkeypatch.setenv("R2_PUBLIC_BASE_URL", "https://media.creatv.test")
    ev = {"id": 3, "estado": "lista", "extra": {"cuenta": A, "resumen": [{"ad_account_id": A, "nombre": "Norway"}]},
          "muestra": [{"ref": "A1", "nombre": "Video gana", "veredicto": "ganador",
                       "medio": {"imagen": "https://media.creatv.test/clientes/hf/meta_rendimiento/eval3_A1.jpg"}},
                      {"ref": "A2", "nombre": "Foto pierde", "veredicto": "perdedor",
                       "medio": {"imagen": "https://otro.example/x.jpg"}},
                      {"ref": "A3", "nombre": "Meta", "medio": {"imagen": "https://scontent.xx.fbcdn.net/a.jpg"}}],
          "recomendaciones": [{"ref": "R1", "titulo": "Consolida los conjuntos"}],
          "resultado": {"plan": [
              {"prioridad": 1, "objetos": ["A1", "R1", "A9"], "que_hacer": "x",
               "enlace": "https://adsmanager.facebook.com/adsmanager/manage/ads?act=1&selected_ad_ids=9"},
              {"prioridad": 2, "objetos": [], "que_hacer": "y", "enlace": "javascript:alert(1)"},
              {"prioridad": 3, "objetos": ["A2"], "que_hacer": "z",
               "enlace": "https://adsmanager.facebook.com.evil.example/adsmanager/manage/ads"}],
              "anuncios": {"A1": {"por_que": "gancho claro"}}}}
    v = panel.evaluacion_vista(ev)
    uno, dos, tres = v["resultado"]["plan"]
    assert [(o["ref"], o["nombre"], o["tipo"]) for o in uno["objetos_vista"]] == [
        ("A1", "Video gana", "anuncio"), ("R1", "Consolida los conjuntos", "recomendacion")]
    assert uno["enlace"].startswith("https://adsmanager.facebook.com/adsmanager/manage/")
    assert dos["enlace"] is None and tres["enlace"] is None
    assert v["alcance"] == "Norway" and v["nombres"]["A2"] == "Foto pierde"
    imagenes = {a["ref"]: a["imagen"] for a in v["anuncios_vista"]}
    assert imagenes["A1"].startswith("https://media.creatv.test/") and imagenes["A2"] is None
    assert imagenes["A3"] == "https://scontent.xx.fbcdn.net/a.jpg"
    assert ev["resultado"]["plan"][1]["enlace"] == "javascript:alert(1)"      # la fila guardada no se toca
    # Sin nada que decir por anuncio, no hay «Anuncio por anuncio».
    assert panel.evaluacion_vista(dict(ev, resultado={"plan": []}))["anuncios_vista"] == []


def test_pnd287_el_diagnostico_ve_los_conjuntos_con_problemas_de_la_copia(base_temporal, conectado):
    """PND-287: el Diagnóstico del panel (y lo que la copia guarda para Alertas) incluye los conjuntos WITH_ISSUES o
    DISAPPROVED de la copia, con lo que Meta dice de cada uno, en la misma lectura de objetos."""
    _sembrar_diagnostico()
    datos.guardar_objetos("hf", A, [{"nivel": "conjunto", "objeto_id": "s9", "nombre": "Bloqueado", "campaign_id": "c1",
                                     "estado": "WITH_ISSUES",
                                     "extra": {"problemas": [{"resumen": "Ad set has issues", "mensaje": None}]}}])
    recs = _contexto(30)["recomendaciones"]
    r, = [x for x in recs if x["tipo"] == "conjuntos_con_problemas"]
    assert r["cuenta"] == A and r["nivel"] == "alta" and [o["id"] for o in r["objetos"]] == ["s9"]
    assert r["problemas"] == [{"nombre": "Bloqueado", "texto": "Ad set has issues"}]
    assert "conjuntos_con_problemas" in {x["tipo"] for x in panel.recomendaciones_de_cuenta("hf", A, hoy=HOY)}
