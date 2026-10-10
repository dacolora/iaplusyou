"""Recomendaciones de las cuentas de Meta en «Lo que necesita tu atención» (Rendimiento E2, tarea 6; spec meta
rendimiento §9, PND-192 sin los desgloses). Reglas puras y gratis sobre lo que Creatv ya copia de Meta: una prueba por
regla con su umbral y su borde, los textos en español y con las cifras de los datos; después la única lectura nueva
(una consulta, sin importar cuántas cuentas) y el cableado en el contexto de la pestaña."""
from datetime import date, timedelta

import pytest
from sqlalchemy import event

import db
import idiomas
from meta_rendimiento import cuentas as cuentas_mod
from meta_rendimiento import datos
from meta_rendimiento import panel as meta_panel
from meta_rendimiento import recomendaciones as R
from tests.test_rendimiento_resumen import _llave_de_cifrado  # noqa: F401  (fixture autouse: cifra la llave)


def _cuenta(act="act_1", nombre="HappyFlops Norway", moneda="SEK", **info):
    return {"ad_account_id": act, "nombre": nombre, "moneda": moneda,
            "extra": {"cuenta": dict({"account_status": 1, "disable_reason": 0, "amount_spent": "0",
                                      "spend_cap": "0"}, **info)}}


def _conjunto(oid, gasto=0.0, aprendizaje="SUCCESS", estado="ACTIVE", presupuesto=None, act="act_1", nombre=None):
    return {"nivel": "conjunto", "objeto_id": oid, "ad_account_id": act, "padre_id": "c1", "campaign_id": "c1",
            "nombre": nombre or f"Conjunto {oid}", "estado": estado, "aprendizaje": aprendizaje,
            "presupuesto_diario": presupuesto, "gasto": gasto, "frecuencia_7": None}


def _anuncio(oid, conjunto="s1", gasto=0.0, estado="ACTIVE", act="act_1", frecuencia=None, nombre=None):
    return {"nivel": "anuncio", "objeto_id": oid, "ad_account_id": act, "padre_id": conjunto, "campaign_id": "c1",
            "nombre": nombre or f"Anuncio {oid}", "estado": estado, "aprendizaje": None, "presupuesto_diario": None,
            "gasto": gasto, "frecuencia_7": frecuencia}


def _ev(ad_id, adset_id="s1", veredicto="en_prueba", fatiga=False, act="act_1", gasto=10.0):
    return {"ad_id": ad_id, "adset_id": adset_id, "campaign_id": "c1", "ad_account_id": act, "nombre": f"Anuncio {ad_id}",
            "conjunto": f"Conjunto {adset_id}", "veredicto": veredicto, "fatiga": fatiga, "m": {"gasto": gasto}}


def _recomendar(cuentas=None, objetos=(), anuncios=()):
    with idiomas.en_idioma("es"):
        return R.recomendar(cuentas if cuentas is not None else [_cuenta()], list(objetos), list(anuncios))


def _textos(salida):
    return [r["texto"] for r in salida]


# ---- 1. Aprendizaje limitado -------------------------------------------------------------------------------

def test_aprendizaje_limitado_con_30_por_ciento_del_gasto_es_media():
    salida = _recomendar(objetos=[_conjunto("s1", 30, "FAIL"), _conjunto("s2", 50), _conjunto("s3", 20, "LEARNING")])
    assert salida == [{"nivel": "media", "texto":
                       "1 de 3 conjuntos activos está en aprendizaje limitado (30% del gasto): júntalo con otro o sube "
                       "su presupuesto para que salga de ahí. Meta necesita unas 50 conversiones por semana en cada "
                       "conjunto."}]


def test_aprendizaje_limitado_en_plural():
    salida = _recomendar(objetos=[_conjunto("s1", 40, "FAIL"), _conjunto("s2", 30, "FAIL"), _conjunto("s3", 30)])
    assert _textos(salida) == [
        "2 de 3 conjuntos activos están en aprendizaje limitado (70% del gasto): junta conjuntos o sube su "
        "presupuesto para que salgan de ahí. Meta necesita unas 50 conversiones por semana en cada conjunto."]


def test_aprendizaje_limitado_por_debajo_del_30_por_ciento_no_se_dice():
    salida = _recomendar(objetos=[_conjunto("s1", 29.9, "FAIL"), _conjunto("s2", 70.1)])
    assert salida == []


def test_aprendizaje_limitado_solo_cuenta_conjuntos_activos_y_con_gasto():
    # Un conjunto en pausa con aprendizaje limitado no cuenta (ni en N ni en M); sin gasto no hay porcentaje.
    assert _recomendar(objetos=[_conjunto("s1", 90, "FAIL", estado="PAUSED"), _conjunto("s2", 10)]) == []
    assert _recomendar(objetos=[_conjunto("s1", 0, "FAIL"), _conjunto("s2", 0)]) == []


def test_aprendizaje_limitado_no_suma_monedas_distintas():
    # 30 SEK de 100 en Noruega (30 %) y 10 EUR de 100 en Finlandia (10 %): sumar daría 40 de 200 «20 %» y callaría
    # Noruega. Con varias monedas cada una habla por su lado.
    cuentas = [_cuenta("act_1", moneda="SEK"), _cuenta("act_2", "HappyFlops Finland", moneda="EUR")]
    salida = _recomendar(cuentas, [_conjunto("s1", 30, "FAIL"), _conjunto("s2", 70),
                                   _conjunto("f1", 10, "FAIL", act="act_2"), _conjunto("f2", 90, act="act_2")])
    assert len(salida) == 1 and salida[0]["nivel"] == "media"
    assert salida[0]["texto"].startswith("Cuentas en SEK: 1 de 2 conjuntos activos está en aprendizaje limitado (30%")


# ---- 2. Rechazados o con problemas ---------------------------------------------------------------------------

def test_anuncios_rechazados_o_con_problemas_es_alta():
    salida = _recomendar(objetos=[_anuncio("a1", estado="DISAPPROVED"), _anuncio("a2", estado="WITH_ISSUES"),
                                  _anuncio("a3")])
    assert salida == [{"nivel": "alta", "texto": "2 anuncios están rechazados o con problemas: revisa en Meta qué "
                                                 "piden para que vuelvan a entregar."}]


def test_un_anuncio_rechazado_en_singular_y_los_conjuntos_tambien_cuentan():
    assert _textos(_recomendar(objetos=[_anuncio("a1", estado="DISAPPROVED")])) == [
        "1 anuncio está rechazado o con problemas: revisa en Meta qué pide para que vuelva a entregar."]
    assert _textos(_recomendar(objetos=[_conjunto("s9", estado="WITH_ISSUES")])) == [
        "1 conjunto está rechazado o con problemas: revisa en Meta qué pide para que vuelva a entregar."]
    assert _textos(_recomendar(objetos=[_anuncio("a1", estado="DISAPPROVED"), _conjunto("s9", estado="WITH_ISSUES"),
                                        _conjunto("s8", estado="DISAPPROVED")])) == [
        "1 anuncio y 2 conjuntos están rechazados o con problemas: revisa en Meta qué piden para que vuelvan a "
        "entregar."]


def test_pausados_o_en_revision_no_son_rechazados():
    objetos = [_anuncio("a1", estado="PAUSED"), _anuncio("a2", estado="PENDING_REVIEW"), _anuncio("a3", estado=None)]
    assert _recomendar(objetos=objetos) == []


# ---- 3. Cuenta con problema ----------------------------------------------------------------------------------

def test_cuenta_desactivada_con_motivo_conocido_es_alta():
    salida = _recomendar([_cuenta(account_status=2, disable_reason=3)])
    assert salida == [{"nivel": "alta", "texto": "La cuenta «HappyFlops Norway» tiene un problema en Meta "
                                                 "(Desactivada, motivo: riesgo en los pagos): revísala en el "
                                                 "Administrador de anuncios."}]


def test_cuenta_con_estado_raro_y_motivo_desconocido():
    salida = _recomendar([_cuenta(account_status=77, disable_reason=99)])
    assert _textos(salida) == ["La cuenta «HappyFlops Norway» tiene un problema en Meta (Otro estado): revísala en "
                               "el Administrador de anuncios."]


def test_cuenta_activa_o_sin_datos_de_meta_no_dice_nada():
    assert _recomendar([_cuenta(account_status=1)]) == []
    assert _recomendar([{"ad_account_id": "act_1", "nombre": "X", "moneda": "SEK", "extra": {}}]) == []
    assert _recomendar([_cuenta(account_status=None)]) == []


def test_limite_de_gasto_con_menos_del_10_por_ciento_disponible_es_media():
    # Meta manda amount_spent y spend_cap en centavos y como texto: quedan 99,99 SEK de 1.000.
    salida = _recomendar([_cuenta(spend_cap="100000", amount_spent="90001")])
    assert salida == [{"nivel": "media", "texto": "A la cuenta «HappyFlops Norway» le quedan 99,99 SEK de su límite "
                                                  "de gasto de 1.000 SEK: súbelo en Meta antes de que sus anuncios "
                                                  "se detengan."}]


def test_limite_de_gasto_con_10_por_ciento_justo_o_sin_limite_no_dice_nada():
    assert _recomendar([_cuenta(spend_cap="100000", amount_spent="90000")]) == []
    assert _recomendar([_cuenta(spend_cap="0", amount_spent="90000")]) == []
    assert _recomendar([_cuenta(spend_cap=None, amount_spent=None)]) == []


def test_limite_de_gasto_agotado_y_moneda_sin_decimales():
    salida = _recomendar([_cuenta(moneda="JPY", spend_cap="50000", amount_spent="51000")])
    assert _textos(salida) == ["A la cuenta «HappyFlops Norway» le quedan 0 JPY de su límite de gasto de 50.000 JPY: "
                               "súbelo en Meta antes de que sus anuncios se detengan."]


# ---- 4. Ganadores con poco presupuesto -----------------------------------------------------------------------

def _tres_conjuntos_con_presupuesto(act="act_1", escala=1):
    return [_conjunto("s1", 10, presupuesto=50 * escala, act=act), _conjunto("s2", 10, presupuesto=100 * escala, act=act),
            _conjunto("s3", 10, presupuesto=200 * escala, act=act), _conjunto("s4", 10, presupuesto=None, act=act)]


def test_ganador_en_un_conjunto_con_presupuesto_bajo_la_mediana_es_bien():
    salida = _recomendar(objetos=_tres_conjuntos_con_presupuesto(), anuncios=[_ev("a1", "s1", "ganador")])
    assert salida == [{"nivel": "bien", "texto": "Sube el presupuesto de «Conjunto s1»: tiene 1 anuncio ganador y su "
                                                 "presupuesto diario (50 SEK) está por debajo de la mediana de los "
                                                 "conjuntos activos de su cuenta (100 SEK). Súbelo de a 20% para no "
                                                 "reiniciar el aprendizaje."}]


def test_ganador_con_presupuesto_igual_a_la_mediana_o_sin_presupuesto_propio_no_dice_nada():
    objetos = _tres_conjuntos_con_presupuesto()
    assert _recomendar(objetos=objetos, anuncios=[_ev("a2", "s2", "ganador")]) == []      # 100 = la mediana
    assert _recomendar(objetos=objetos, anuncios=[_ev("a4", "s4", "ganador")]) == []      # presupuesto en la campaña
    assert _recomendar(objetos=objetos, anuncios=[_ev("a1", "s1", "prometedor")]) == []   # no es ganador


def test_la_mediana_es_la_de_la_cuenta_del_ganador_y_varios_conjuntos_van_juntos():
    # En la cuenta 2 todo vale 10 veces más: s1 de la cuenta 1 (50) queda bajo SU mediana (100), no bajo la de todas.
    cuentas = [_cuenta("act_1"), _cuenta("act_2", "HappyFlops Sweden")]
    objetos = _tres_conjuntos_con_presupuesto("act_1") + [
        _conjunto("t1", 10, presupuesto=500, act="act_2"), _conjunto("t2", 10, presupuesto=1000, act="act_2"),
        _conjunto("t3", 10, presupuesto=2000, act="act_2")]
    salida = _recomendar(cuentas, objetos, [_ev("a1", "s1", "ganador"), _ev("a9", "s1", "ganador"),
                                            _ev("b1", "t1", "ganador", act="act_2")])
    assert _textos(salida) == [
        "Sube el presupuesto de 2 conjuntos con anuncios ganadores y presupuesto diario por debajo de la mediana de "
        "los conjuntos activos de su cuenta: «Conjunto s1», «Conjunto t1». Súbelos de a 20% para no reiniciar el "
        "aprendizaje."]


# ---- 5. Concentración ---------------------------------------------------------------------------------------

def test_un_anuncio_con_60_por_ciento_del_gasto_de_un_conjunto_de_3_es_media():
    objetos = [_conjunto("s1", 100), _anuncio("a1", "s1", 60), _anuncio("a2", "s1", 25), _anuncio("a3", "s1", 15)]
    assert _recomendar(objetos=objetos) == [{"nivel": "media", "texto":
        "El anuncio «Anuncio a1» se lleva el 60% del gasto de su conjunto «Conjunto s1», que tiene 3 anuncios "
        "activos: si se cansa, el conjunto cae con él. Prueba variantes nuevas para no depender de un solo creativo."}]


def test_concentracion_bajo_el_60_por_ciento_o_con_menos_de_3_anuncios_no_dice_nada():
    assert _recomendar(objetos=[_conjunto("s1", 100), _anuncio("a1", "s1", 59.9), _anuncio("a2", "s1", 30),
                                _anuncio("a3", "s1", 10.1)]) == []
    assert _recomendar(objetos=[_conjunto("s1", 100), _anuncio("a1", "s1", 90), _anuncio("a2", "s1", 10)]) == []
    # Un anuncio en pausa no cuenta entre los del conjunto (el gasto del conjunto sí incluye lo que gastó).
    assert _recomendar(objetos=[_conjunto("s1", 100), _anuncio("a1", "s1", 70), _anuncio("a2", "s1", 20),
                                _anuncio("a3", "s1", 10, estado="PAUSED")]) == []


def test_concentracion_en_varios_conjuntos_da_un_ejemplo():
    objetos = [_conjunto("s1", 100), _anuncio("a1", "s1", 80), _anuncio("a2", "s1", 10), _anuncio("a3", "s1", 10),
               _conjunto("s2", 400), _anuncio("b1", "s2", 300), _anuncio("b2", "s2", 50), _anuncio("b3", "s2", 50)]
    assert _textos(_recomendar(objetos=objetos)) == [
        "En 2 conjuntos un solo anuncio se lleva el 60% o más del gasto, como «Anuncio b1» (75% de «Conjunto s2»): si "
        "se cansa, el conjunto cae con él. Prueba variantes nuevas para no depender de un solo creativo."]


# ---- 6. Fatiga con frecuencia ---------------------------------------------------------------------------------

def test_anuncio_cansado_en_campana_con_frecuencia_3_es_media():
    salida = _recomendar(objetos=[_anuncio("a1", frecuencia=3.0)], anuncios=[_ev("a1", fatiga=True,
                                                                                    veredicto="ganador")])
    assert salida == [{"nivel": "media", "texto": "1 anuncio se está cansando y su campaña ya tiene una frecuencia de "
                                                  "3,0 en 7 días: haz variantes nuevas en Crear para no cansar más a "
                                                  "la misma gente."}]


def test_fatiga_con_frecuencia_bajo_3_sin_fatiga_o_perdedor_no_dice_nada():
    assert _recomendar(objetos=[_anuncio("a1", frecuencia=2.99)], anuncios=[_ev("a1", fatiga=True)]) == []
    assert _recomendar(objetos=[_anuncio("a1", frecuencia=5.0)], anuncios=[_ev("a1", fatiga=False)]) == []
    assert _recomendar(objetos=[_anuncio("a1", frecuencia=5.0)], anuncios=[_ev("a1", "s1", "perdedor", True)]) == []
    # Un anuncio cansado que ya no está activo no aparece en las filas: nada que hacer.
    assert _recomendar(objetos=[], anuncios=[_ev("a1", fatiga=True)]) == []


def test_varios_anuncios_cansados_dicen_la_frecuencia_mas_alta():
    objetos = [_anuncio("a1", frecuencia=3.2), _anuncio("a2", frecuencia=4.26), _anuncio("a3", frecuencia=1.5)]
    salida = _recomendar(objetos=objetos, anuncios=[_ev(a, fatiga=True) for a in ("a1", "a2", "a3")])
    assert _textos(salida) == ["2 anuncios se están cansando en campañas con una frecuencia de hasta 4,3 en 7 días: "
                               "haz variantes nuevas en Crear para no cansar más a la misma gente."]


# ---- orden e idioma -------------------------------------------------------------------------------------------

def test_primero_lo_alto_despues_lo_medio_y_al_final_lo_bueno():
    objetos = _tres_conjuntos_con_presupuesto() + [_anuncio("a7", "s2", estado="DISAPPROVED")]
    objetos[0]["aprendizaje"] = "FAIL"
    objetos[0]["gasto"] = 30
    salida = _recomendar([_cuenta(account_status=3)], objetos, [_ev("a1", "s1", "ganador")])
    assert [r["nivel"] for r in salida] == ["alta", "alta", "media", "bien"]


def test_en_ingles_sale_traducido():
    with idiomas.en_idioma("en"):
        salida = R.recomendar([_cuenta(account_status=2, disable_reason=3)], [_anuncio("a1", estado="DISAPPROVED")],
                              [])
    textos = _textos(salida)
    assert all("cuenta" not in t and "anuncio" not in t for t in textos), textos


# ---- la lectura: una consulta, sin importar cuántas cuentas ---------------------------------------------------

HOY = date(2026, 10, 8)
DESDE, HASTA = "2026-10-01", "2026-10-08"


def _ad(fecha, ad, gasto, adset="s1", campaign="c1"):
    return dict(fecha=fecha, campaign_id=campaign, adset_id=adset, ad_id=ad, gasto=gasto, impresiones=1000, clics=10,
                clics_salida=5, compras=0, valor=0, vistas_3s=100, thruplays=50, p25=40, p50=30, p75=20, p100=10)


def _sembrar_cuenta(cliente, act, moneda="SEK"):
    """Una cuenta con un conjunto activo en aprendizaje limitado (`<act>-s1`: dos anuncios activos, uno en pausa y uno
    rechazado), otro conjunto en pausa y la frecuencia de 7 y de 30 días de su campaña. Los ids llevan la cuenta: un
    objeto es único por (cliente, objeto_id)."""
    s1, s2, c1 = f"{act}-s1", f"{act}-s2", f"{act}-c1"
    cuentas_mod.elegir(cliente, [{"id": a, "name": f"HappyFlops {a}", "currency": moneda}
                                 for a in cuentas_mod.ids(cliente) + [act]])
    datos.reemplazar_anuncio_dias(cliente, act, DESDE, HASTA, [
        _ad("2026-10-02", f"{act}-a1", 60, s1, c1), _ad("2026-10-03", f"{act}-a1", 20, s1, c1),
        _ad("2026-10-02", f"{act}-a2", 10, s1, c1), _ad("2026-10-02", f"{act}-a3", 10, s1, c1)])
    datos.reemplazar_anuncio_dias(cliente, act, "2026-09-20", "2026-09-20", [
        _ad("2026-09-20", f"{act}-a1", 999, s1, c1)])                                    # fuera del rango leído
    datos.guardar_objetos(cliente, act, [
        {"nivel": "campana", "objeto_id": c1, "nombre": "Campaña", "estado": "ACTIVE"},
        {"nivel": "conjunto", "objeto_id": s1, "padre_id": c1, "campaign_id": c1, "nombre": "Conjunto 1",
         "estado": "ACTIVE", "aprendizaje": "FAIL", "presupuesto_diario": 100.0},
        {"nivel": "conjunto", "objeto_id": s2, "padre_id": c1, "campaign_id": c1, "nombre": "En pausa",
         "estado": "PAUSED", "aprendizaje": "FAIL"},
        {"nivel": "anuncio", "objeto_id": f"{act}-a1", "padre_id": s1, "campaign_id": c1, "nombre": "Uno",
         "estado": "ACTIVE"},
        {"nivel": "anuncio", "objeto_id": f"{act}-a2", "padre_id": s1, "campaign_id": c1, "nombre": "Dos",
         "estado": "ACTIVE"},
        {"nivel": "anuncio", "objeto_id": f"{act}-a3", "padre_id": s1, "campaign_id": c1, "nombre": "Tres",
         "estado": "PAUSED"},
        {"nivel": "anuncio", "objeto_id": f"{act}-a4", "padre_id": s1, "campaign_id": c1, "nombre": "Cuatro",
         "estado": "DISAPPROVED"}])
    datos.guardar_alcance(cliente, act, [{"nivel": "campana", "objeto_id": c1, "ventana": 7, "alcance": 100,
                                          "frecuencia": 3.4},
                                         {"nivel": "campana", "objeto_id": c1, "ventana": 30, "alcance": 200,
                                          "frecuencia": 9.0}])


def test_la_lectura_trae_activos_y_rechazados_con_su_gasto_del_rango(base_temporal):
    _sembrar_cuenta("hf", "act_1")
    _sembrar_cuenta("otro", "act_9")          # otro proyecto: nunca entra
    filas = {f["objeto_id"]: f for f in datos.objetos_para_recomendar("hf", ["act_1"], DESDE, HASTA)}
    assert set(filas) == {"act_1-s1", "act_1-a1", "act_1-a2", "act_1-a4"}   # sin pausados ni campañas
    # El gasto del conjunto suma TODOS sus anuncios del rango, también el que está en pausa (60+20+10+10).
    s1 = filas["act_1-s1"]
    assert s1["gasto"] == 100 and s1["aprendizaje"] == "FAIL" and s1["nivel"] == "conjunto"
    assert s1["presupuesto_diario"] == 100.0 and s1["frecuencia_7"] is None and s1["ad_account_id"] == "act_1"
    assert filas["act_1-a1"]["gasto"] == 80 and filas["act_1-a1"]["padre_id"] == "act_1-s1"
    assert filas["act_1-a1"]["frecuencia_7"] == 3.4                           # la de 7 días de su campaña
    assert filas["act_1-a4"]["gasto"] == 0 and filas["act_1-a4"]["estado"] == "DISAPPROVED"
    assert datos.objetos_para_recomendar("hf", [], DESDE, HASTA) == []


def _contar_consultas(funcion):
    consultas = []

    def contar(conn, cursor, statement, parameters, context, executemany):
        consultas.append(statement)
    event.listen(db.engine(), "before_cursor_execute", contar)
    try:
        resultado = funcion()
    finally:
        event.remove(db.engine(), "before_cursor_execute", contar)
    return resultado, consultas


@pytest.mark.parametrize("n_cuentas", [1, 3])
def test_recomendar_las_cuentas_hace_una_sola_consulta(base_temporal, n_cuentas):
    acts = [f"act_{i}" for i in range(1, n_cuentas + 1)]
    for act in acts:
        _sembrar_cuenta("hf", act)
    por_id = {c["ad_account_id"]: c for c in meta_panel.lista("hf")}
    with idiomas.en_idioma("es"):
        salida, consultas = _contar_consultas(
            lambda: meta_panel.recomendaciones("hf", acts, DESDE, HASTA, por_id, []))
    assert len(consultas) == 1, consultas
    textos = _textos(salida)
    # Por cuenta: 1 anuncio rechazado; el único conjunto activo está en aprendizaje limitado con todo el gasto.
    assert textos[0] == (f"{n_cuentas} anuncio está rechazado o con problemas: revisa en Meta qué pide para que "
                         "vuelva a entregar." if n_cuentas == 1 else
                         f"{n_cuentas} anuncios están rechazados o con problemas: revisa en Meta qué piden para que "
                         "vuelvan a entregar.")
    assert any("aprendizaje limitado (100% del gasto)" in t for t in textos)


def test_sin_cuentas_no_consulta_nada(base_temporal):
    salida, consultas = _contar_consultas(lambda: meta_panel.recomendaciones("hf", [], DESDE, HASTA, {}, []))
    assert salida == [] and consultas == []


# ---- el cableado: «Lo que necesita tu atención» de la pestaña -------------------------------------------------

def test_lo_que_necesita_tu_atencion_trae_las_recomendaciones_de_las_cuentas(base_temporal, monkeypatch):
    import meta_conexion
    from pestana_rendimiento import panel
    from tests.test_rendimiento_resumen import _sembrar
    monkeypatch.setattr(meta_conexion, "cargar", lambda c: {"token": "t-llave-de-prueba", "page_id": None})  # llave-de-prueba
    _sembrar()
    cuentas_mod.actualizar_extra("acme", "act_se", {"cuenta": {"account_status": 2, "disable_reason": 1}})
    with idiomas.en_idioma("es"):
        r = panel.contexto("acme", 0, hoy=date.today())
        solo_no = panel.contexto("acme", 0, entrada="NO", hoy=date.today())
    esperado = ("La cuenta «HappyFlops Sweden» tiene un problema en Meta (Desactivada, motivo: incumplimiento de las "
                "políticas de publicidad): revísala en el Administrador de anuncios.")
    assert {"nivel": "alta", "texto": esperado} in r["atencion"]
    # La entrada de Noruega no lee la cuenta de Suecia: su aviso no aparece ahí.
    assert all(a["texto"] != esperado for a in solo_no["atencion"])


def test_el_aviso_de_la_cuenta_usa_el_rango_de_la_estructura(base_temporal, monkeypatch):
    """`_meta` pide las recomendaciones con el rango de la estructura (todas las cuentas del alcance)."""
    import meta_conexion
    from pestana_rendimiento import panel
    from tests.test_rendimiento_resumen import _sembrar
    monkeypatch.setattr(meta_conexion, "cargar", lambda c: {"token": "t-llave-de-prueba", "page_id": None})  # llave-de-prueba
    _sembrar()
    visto = {}
    original = meta_panel.recomendaciones

    def espia(cliente, ids, desde, hasta, cuentas_por_id, anuncios=()):
        visto.update(ids=list(ids), desde=desde, hasta=hasta, n_anuncios=len(list(anuncios)))
        return original(cliente, ids, desde, hasta, cuentas_por_id, anuncios)
    monkeypatch.setattr(meta_panel, "recomendaciones", espia)
    with idiomas.en_idioma("es"):
        r = panel.contexto("acme", 0, hoy=date.today())
    assert visto["ids"] == r["meta"]["ids_estructura"]
    assert (visto["desde"], visto["hasta"]) == (r["meta"]["estructura"]["desde"], r["meta"]["estructura"]["hasta"])
    hoy = date.today()
    assert visto["hasta"] == hoy.isoformat() and visto["desde"] <= (hoy - timedelta(days=1)).isoformat()
