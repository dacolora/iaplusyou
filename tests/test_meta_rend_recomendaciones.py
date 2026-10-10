"""Reglas de diagnóstico de Meta rendimiento (spec E2 §6) y enlaces al Administrador de anuncios (§7). Todo puro:
sin base, sin Flask, sin red. Cada regla con un caso que la dispara y otro que no, en el umbral exacto."""
import pytest

from meta_rendimiento import administrador
from meta_rendimiento import recomendaciones as rec

ACT, ACT2 = "act_111", "act_222"


def cuenta(act=ACT, nombre="HF Sverige", moneda="SEK", status=1, spend_cap="0", amount_spent="0"):
    return {"ad_account_id": act, "nombre": nombre, "moneda": moneda,
            "extra": {"cuenta": {"account_status": status, "disable_reason": 0, "amount_spent": amount_spent,
                                 "spend_cap": spend_cap}}}


def entrada(**cambios):
    """Una cuenta sana: 1 000 de gasto en 7 días con ROAS 2, 4 000 en 30 días con ROAS 2, y nada más. No dispara
    ninguna regla."""
    base = {"cuentas": [cuenta()],
            "totales_7": {ACT: {"gasto": 1000.0, "valor": 2000.0, "compras": 20.0}},
            "totales_30": {ACT: {"gasto": 4000.0, "valor": 8000.0, "compras": 80.0}},
            "objetos": [], "conjuntos_7": {}, "anuncios": [], "frecuencia_7": {}, "desgloses_30": []}
    base.update(cambios)
    return base


def campana(cid, nombre=None, presupuesto=None, estado="ACTIVE", act=ACT):
    return {"objeto_id": cid, "ad_account_id": act, "nivel": "campana", "nombre": nombre or f"Campaña {cid}",
            "estado": estado, "presupuesto_diario": presupuesto, "aprendizaje": None, "campaign_id": None,
            "padre_id": None}


def conjunto(sid, cid, aprendizaje="SUCCESS", presupuesto=None, estado="ACTIVE", act=ACT, nombre=None):
    return {"objeto_id": sid, "ad_account_id": act, "nivel": "conjunto", "nombre": nombre or f"Conjunto {sid}",
            "estado": estado, "presupuesto_diario": presupuesto, "aprendizaje": aprendizaje, "campaign_id": cid,
            "padre_id": cid}


def anuncio(ad_id, adset_id="900", campaign_id="800", veredicto="en_prueba", estado="ACTIVE", gasto_7=0.0,
            gasto_30=None, problemas=(), act=ACT, gasto=None):
    g = gasto if gasto is not None else (gasto_30 if gasto_30 is not None else gasto_7)
    a = {"ad_id": ad_id, "ad_account_id": act, "adset_id": adset_id, "campaign_id": campaign_id,
         "nombre": f"Anuncio {ad_id}", "conjunto": f"Conjunto {adset_id}", "estado": estado, "veredicto": veredicto,
         "problemas": list(problemas), "m": {"gasto": g, "ingresos": 0.0, "pedidos": 0.0}, "gasto_7": gasto_7}
    if gasto_30 is not None:
        a["gasto_30"] = gasto_30
    return a


def de_tipo(recs, tipo):
    return [r for r in recs if r["tipo"] == tipo]


def una(recs, tipo):
    lista = de_tipo(recs, tipo)
    assert len(lista) == 1, [r["tipo"] for r in recs]
    return lista[0]


# ------------------------------------------------------------ administrador ---

def test_enlace_de_conjuntos_solo_con_ids_numericos_sin_repetir():
    url = administrador.enlace("act_123", "conjunto", ["1", 2, "x", "3;", True, "1", " 4 ", "²", None, "5&a=b"])
    assert url == ("https://adsmanager.facebook.com/adsmanager/manage/adsets?act=123"
                   "&selected_adset_ids=1,2,4")


@pytest.mark.parametrize("nivel, ruta, parametro", [("campana", "campaigns", "selected_campaign_ids"),
                                                    ("conjunto", "adsets", "selected_adset_ids"),
                                                    ("anuncio", "ads", "selected_ad_ids")])
def test_enlace_por_nivel(nivel, ruta, parametro):
    assert administrador.enlace("123", nivel, ["9"]) == (
        f"https://adsmanager.facebook.com/adsmanager/manage/{ruta}?act=123&{parametro}=9")


def test_enlace_como_mucho_50_ids():
    url = administrador.enlace("act_1", "anuncio", [str(i) for i in range(1, 80)])
    ids = url.split("selected_ad_ids=")[1].split(",")
    assert ids == [str(i) for i in range(1, 51)] and administrador.MAX_IDS == 50


@pytest.mark.parametrize("act, nivel, ids", [("act_1", "anuncio", []), ("act_1", "anuncio", ["x", "act_2"]),
                                             ("act_abc", "anuncio", ["1"]), ("", "anuncio", ["1"]),
                                             ("act_1", "cuenta", ["1"]), (None, "campana", ["1"])])
def test_enlace_none_sin_ids_validos_cuenta_o_nivel(act, nivel, ids):
    assert administrador.enlace(act, nivel, ids) is None


def test_enlace_cuenta():
    assert administrador.enlace_cuenta("act_77") == "https://adsmanager.facebook.com/adsmanager/manage/campaigns?act=77"
    assert administrador.enlace_cuenta("act_x7") is None


# ------------------------------------------------------------ base ---

def test_una_cuenta_sana_no_genera_nada():
    assert rec.calcular(entrada()) == []
    assert rec.calcular({}) == [] and rec.calcular(None) == []


def test_una_cuenta_sin_datos_en_el_periodo_no_genera_reglas():
    """Cuenta desactivada, con conjuntos en aprendizaje limitado y anuncios con problemas, pero sin gasto en 30 días:
    nada. La otra cuenta, con datos, sí genera la suya."""
    e = entrada(cuentas=[cuenta(status=2), cuenta(ACT2, "HF Mexico", "MXN", status=2)],
                totales_30={ACT: {"gasto": 0.0, "valor": 0.0, "compras": 0.0}},
                objetos=[campana("800"), conjunto("900", "800", "FAIL")],
                anuncios=[anuncio("1", estado="WITH_ISSUES", gasto_30=50.0)])
    assert rec.calcular(e) == []
    e["totales_30"][ACT2] = {"gasto": 10.0, "valor": 30.0, "compras": 1.0}
    assert [(r["tipo"], r["cuenta"]) for r in rec.calcular(e)] == [("cuenta_estado", ACT2)]


def test_forma_de_cada_recomendacion():
    e = entrada(anuncios=[anuncio("501", veredicto="perdedor", gasto_7=100.0)])
    r = una(rec.calcular(e), "perdedores_gastando")
    assert set(r) == {"id", "nivel", "tipo", "cuenta", "cuenta_nombre", "titulo", "que_hacer", "por_que", "impacto",
                      "objetos", "enlace"}
    assert r["cuenta"] == ACT and r["cuenta_nombre"] == "HF Sverige"
    assert r["objetos"] == [{"nivel": "anuncio", "id": "501", "nombre": "Anuncio 501"}]
    assert r["enlace"] == administrador.enlace(ACT, "anuncio", ["501"])
    assert r["impacto"]["moneda"] == "SEK" and r["impacto"]["monto"] == pytest.approx(100 / 7)
    assert "SEK" in r["impacto"]["texto"]


# ------------------------------------------------------------ aprendizaje limitado ---

def _aprendizaje(gasto_fail, n_fail=1, n_ok=3, compras_7=20.0):
    objetos = [campana("800")] + [conjunto(f"9{i}", "800", "FAIL") for i in range(n_fail)]
    objetos += [conjunto(f"8{i}", "800", "SUCCESS") for i in range(n_ok)]
    conj7 = {f"9{i}": {"gasto": gasto_fail / n_fail, "compras": 0.0, "valor": 0.0} for i in range(n_fail)}
    return entrada(objetos=objetos, conjuntos_7=conj7,
                   totales_7={ACT: {"gasto": 1000.0, "valor": 2000.0, "compras": compras_7}})


def test_aprendizaje_alta_desde_30_por_ciento_del_gasto():
    r = una(rec.calcular(_aprendizaje(300.0)), "aprendizaje_limitado")
    assert r["nivel"] == "alta" and rec.APRENDIZAJE_GASTO_ALTA == 0.30
    assert r["impacto"]["monto"] == pytest.approx(300 / 7)


def test_aprendizaje_media_entre_15_y_30_por_ciento_del_gasto():
    assert una(rec.calcular(_aprendizaje(299.0)), "aprendizaje_limitado")["nivel"] == "media"
    assert una(rec.calcular(_aprendizaje(150.0)), "aprendizaje_limitado")["nivel"] == "media"
    assert rec.APRENDIZAJE_GASTO_MEDIA == 0.15


def test_aprendizaje_nada_bajo_15_por_ciento_y_menos_de_la_mitad_de_los_conjuntos():
    assert de_tipo(rec.calcular(_aprendizaje(149.0)), "aprendizaje_limitado") == []


def test_aprendizaje_alta_con_la_mitad_de_los_conjuntos_aunque_no_gasten():
    assert una(rec.calcular(_aprendizaje(0.0, n_fail=2, n_ok=2)), "aprendizaje_limitado")["nivel"] == "alta"
    assert rec.APRENDIZAJE_CONJUNTOS_ALTA == 0.50
    # 1 de 3 (33 %) sin gasto: nada.
    assert de_tipo(rec.calcular(_aprendizaje(0.0, n_fail=1, n_ok=2)), "aprendizaje_limitado") == []


def test_aprendizaje_cuenta_solo_conjuntos_activos():
    e = _aprendizaje(0.0, n_fail=2, n_ok=2)
    for o in e["objetos"]:
        if o.get("aprendizaje") == "FAIL":
            o["estado"] = "PAUSED"
    assert de_tipo(rec.calcular(e), "aprendizaje_limitado") == []


def test_aprendizaje_dice_cuantos_conjuntos_caben_y_lista_las_3_campanas_con_mas_fail():
    objetos = [campana("801", "Prospecting"), campana("802", "Retargeting"), campana("803", "Broad"),
               campana("804", "DPA")]
    objetos += [conjunto(f"91{i}", "801", "FAIL") for i in range(4)]
    objetos += [conjunto(f"92{i}", "802", "FAIL") for i in range(3)]
    objetos += [conjunto(f"93{i}", "803", "FAIL") for i in range(2)]
    objetos += [conjunto("940", "804", "FAIL"), conjunto("950", "804", "SUCCESS")]
    e = entrada(objetos=objetos, totales_7={ACT: {"gasto": 1000.0, "valor": 2000.0, "compras": 260.0}})
    r = una(rec.calcular(e), "aprendizaje_limitado")
    assert r["nivel"] == "alta"
    assert [o["id"] for o in r["objetos"]] == ["801", "802", "803"]
    assert all(o["nivel"] == "campana" for o in r["objetos"])
    assert r["enlace"] == administrador.enlace(ACT, "campana", ["801", "802", "803"])
    # 260 compras por semana / 50 = 5 conjuntos.
    assert "260" in r["que_hacer"] and "~5 " in r["que_hacer"]
    assert "«Prospecting» (4)" in r["que_hacer"] and "«Broad» (2)" in r["que_hacer"] and "DPA" not in r["que_hacer"]
    assert "10" in r["titulo"] and "11" in r["titulo"]     # 10 de 11 conjuntos activos


def test_aprendizaje_da_para_al_menos_un_conjunto():
    r = una(rec.calcular(_aprendizaje(300.0, compras_7=12.0)), "aprendizaje_limitado")
    assert "~1 " in r["que_hacer"]


def test_aprendizaje_con_miles_usa_separador():
    objetos = [campana("800")] + [conjunto(str(10_000 + i), "800", "FAIL") for i in range(1200)]
    objetos += [conjunto(str(20_000 + i), "800") for i in range(300)]
    r = una(rec.calcular(entrada(objetos=objetos)), "aprendizaje_limitado")
    assert "1.200" in r["titulo"] and "1.500" in r["titulo"]


# ------------------------------------------------------------ perdedores gastando ---

def test_perdedores_alta_desde_20_por_ciento_del_gasto():
    r = una(rec.calcular(entrada(anuncios=[anuncio("1", veredicto="perdedor", gasto_7=120.0),
                                           anuncio("2", veredicto="perdedor", gasto_7=80.0)])), "perdedores_gastando")
    assert r["nivel"] == "alta" and rec.PERDEDORES_GASTO_ALTA == 0.20
    assert [o["id"] for o in r["objetos"]] == ["1", "2"]          # por gasto de 7 días
    assert r["impacto"]["monto"] == pytest.approx(200 / 7)
    assert "2" in r["que_hacer"]


def test_perdedores_media_bajo_20_por_ciento():
    r = una(rec.calcular(entrada(anuncios=[anuncio("1", veredicto="perdedor", gasto_7=199.0)])),
            "perdedores_gastando")
    assert r["nivel"] == "media"


@pytest.mark.parametrize("cambio", [{"gasto_7": 0.0}, {"estado": "PAUSED"}, {"estado": "ADSET_PAUSED"},
                                    {"veredicto": "en_prueba"}, {"veredicto": "ganador"}])
def test_perdedores_nada_sin_gasto_7_dias_pausados_u_otro_veredicto(cambio):
    a = dict(dict(veredicto="perdedor", gasto_7=500.0), **cambio)
    assert de_tipo(rec.calcular(entrada(anuncios=[anuncio("1", **a)])), "perdedores_gastando") == []


def test_perdedores_con_problemas_que_siguen_gastando_cuentan():
    r = una(rec.calcular(entrada(anuncios=[anuncio("1", veredicto="perdedor", estado="WITH_ISSUES", gasto_7=50.0,
                                                   gasto_30=50.0)])), "perdedores_gastando")
    assert r["nivel"] == "media"


def test_perdedores_el_enlace_lleva_como_mucho_50_y_los_objetos_tambien():
    anuncios = [anuncio(str(1000 + i), veredicto="perdedor", gasto_7=1.0 + i) for i in range(70)]
    r = una(rec.calcular(entrada(anuncios=anuncios)), "perdedores_gastando")
    assert len(r["objetos"]) == 50 and r["objetos"][0]["id"] == "1069"
    assert r["enlace"].count(",") == 49
    assert "70" in r["titulo"]


# ------------------------------------------------------------ escalar ---

def _abo(compras=10.0, valor=260.0, aprendizaje="SUCCESS", presupuesto=100.0):
    """ROAS de la cuenta 2,0; el conjunto: gasto 100, `valor`/100 de ROAS (2,6 = 1,3 × 2,0 justo)."""
    return entrada(objetos=[campana("800"), conjunto("900", "800", aprendizaje, presupuesto)],
                   conjuntos_7={"900": {"gasto": 100.0, "compras": compras, "valor": valor}})


def test_escalar_conjunto_abo_en_el_umbral():
    r = una(rec.calcular(_abo()), "escalar")
    assert r["nivel"] == "media"
    assert r["objetos"] == [{"nivel": "conjunto", "id": "900", "nombre": "Conjunto 900"}]
    assert r["enlace"] == administrador.enlace(ACT, "conjunto", ["900"])
    assert "100 SEK" in r["que_hacer"] and "120 SEK" in r["que_hacer"] and "20 %" in r["que_hacer"]
    assert rec.ESCALAR_COMPRAS_MIN == 10 and rec.ESCALAR_FACTOR_ROAS == 1.3 and rec.ESCALAR_SUBIDA == 0.20


@pytest.mark.parametrize("cambio", [{"compras": 9.0}, {"valor": 259.0}, {"aprendizaje": "FAIL"},
                                    {"presupuesto": None}, {"presupuesto": 0}])
def test_escalar_nada_bajo_el_umbral_en_aprendizaje_limitado_o_sin_presupuesto(cambio):
    assert de_tipo(rec.calcular(_abo(**cambio)), "escalar") == []


def test_escalar_nada_si_el_conjunto_no_esta_activo():
    e = _abo()
    e["objetos"][1]["estado"] = "PAUSED"
    assert de_tipo(rec.calcular(e), "escalar") == []


def _cbo(gasto_fail):
    """Campaña con presupuesto 500 y dos conjuntos: uno fuera de aprendizaje y otro FAIL. Entre los dos: gasto 300,
    10 compras, valor 780 (ROAS 2,6)."""
    return entrada(objetos=[campana("700", "CBO ventas", presupuesto=500.0), conjunto("710", "700"),
                            conjunto("720", "700", "FAIL")],
                   conjuntos_7={"710": {"gasto": 300.0 - gasto_fail, "compras": 8.0, "valor": 520.0},
                                "720": {"gasto": gasto_fail, "compras": 2.0, "valor": 260.0}})


def test_escalar_campana_cbo_con_menos_de_la_mitad_del_gasto_en_aprendizaje_limitado():
    r = una(rec.calcular(_cbo(100.0)), "escalar")
    assert r["objetos"] == [{"nivel": "campana", "id": "700", "nombre": "CBO ventas"}]
    assert "500 SEK" in r["que_hacer"] and "600 SEK" in r["que_hacer"]
    assert r["enlace"] == administrador.enlace(ACT, "campana", ["700"])


def test_escalar_campana_cbo_nada_con_la_mitad_del_gasto_en_aprendizaje_limitado():
    assert de_tipo(rec.calcular(_cbo(150.0)), "escalar") == []
    assert rec.ESCALAR_FAIL_MAX_CBO == 0.5


def test_escalar_nada_si_la_cuenta_no_tiene_roas():
    e = _abo()
    e["totales_7"] = {ACT: {"gasto": 1000.0, "valor": 0.0, "compras": 0.0}}
    assert de_tipo(rec.calcular(e), "escalar") == []


# ------------------------------------------------------------ fatiga ---

def _fatiga(frecuencia=3.0, veredicto="ganador", problemas=("fatiga",), estado="ACTIVE"):
    return entrada(anuncios=[anuncio("1", campaign_id="800", veredicto=veredicto, problemas=problemas,
                                     gasto_7=100.0, estado=estado)],
                   frecuencia_7={"800": {"alcance": 5000, "frecuencia": frecuencia}})


def test_fatiga_desde_frecuencia_3():
    r = una(rec.calcular(_fatiga()), "fatiga")
    assert r["nivel"] == "media" and rec.FATIGA_FRECUENCIA_MIN == 3
    assert r["objetos"] == [{"nivel": "anuncio", "id": "1", "nombre": "Anuncio 1"}]
    assert "3" in r["por_que"]
    assert una(rec.calcular(_fatiga(veredicto="prometedor")), "fatiga")


@pytest.mark.parametrize("cambio", [{"frecuencia": 2.99}, {"veredicto": "en_prueba"}, {"problemas": ()},
                                    {"problemas": ("cpm_caro",)}, {"estado": "PAUSED"}])
def test_fatiga_nada_bajo_frecuencia_3_otro_veredicto_o_sin_el_problema(cambio):
    assert de_tipo(rec.calcular(_fatiga(**cambio)), "fatiga") == []


def test_fatiga_nada_sin_frecuencia_de_su_campana():
    e = _fatiga()
    e["frecuencia_7"] = {}
    assert de_tipo(rec.calcular(e), "fatiga") == []


# ------------------------------------------------------------ anuncios con problemas ---

def test_problemas_media_con_gasto_en_30_dias():
    r = una(rec.calcular(entrada(anuncios=[anuncio("1", estado="WITH_ISSUES", gasto_30=60.0)])),
            "anuncios_con_problemas")
    assert r["nivel"] == "media" and r["impacto"]["monto"] == pytest.approx(2.0)
    assert r["enlace"] == administrador.enlace(ACT, "anuncio", ["1"])


def test_problemas_alta_con_un_rechazado_que_gasto_en_7_dias():
    e = entrada(anuncios=[anuncio("1", estado="WITH_ISSUES", gasto_30=60.0),
                          anuncio("2", estado="DISAPPROVED", gasto_7=0.01, gasto_30=10.0)])
    r = una(rec.calcular(e), "anuncios_con_problemas")
    assert r["nivel"] == "alta" and [o["id"] for o in r["objetos"]] == ["1", "2"]


def test_problemas_rechazado_sin_gasto_en_7_dias_es_media():
    e = entrada(anuncios=[anuncio("2", estado="DISAPPROVED", gasto_7=0.0, gasto_30=10.0)])
    assert una(rec.calcular(e), "anuncios_con_problemas")["nivel"] == "media"


def test_problemas_nada_sin_gasto_en_30_dias_o_activos():
    e = entrada(anuncios=[anuncio("1", estado="WITH_ISSUES", gasto_30=0.0), anuncio("2", gasto_30=90.0)])
    assert de_tipo(rec.calcular(e), "anuncios_con_problemas") == []


def test_problemas_sin_gasto_30_usa_el_del_periodo_evaluado():
    e = entrada(anuncios=[anuncio("1", estado="WITH_ISSUES", gasto=30.0)])
    assert una(rec.calcular(e), "anuncios_con_problemas")["impacto"]["monto"] == pytest.approx(1.0)


# ------------------------------------------------------------ cuenta con ROAS bajo ---

def test_cuenta_roas_bajo_alta_bajo_0_5_con_1000_de_gasto():
    e = entrada(totales_30={ACT: {"gasto": 1000.0, "valor": 499.0, "compras": 3.0}},
                objetos=[campana("800"), campana("801")], conjuntos_7={})
    r = una(rec.calcular(e), "cuenta_roas_bajo")
    assert r["nivel"] == "alta" and rec.CUENTA_ROAS_MIN == 0.5 and rec.CUENTA_GASTO_MIN == 1000
    assert "1.000 SEK" in r["que_hacer"] and "0,50" in r["que_hacer"]
    assert {o["id"] for o in r["objetos"]} == {"800", "801"}
    assert r["impacto"]["monto"] == pytest.approx(1000 / 30)


def test_cuenta_roas_bajo_sin_campanas_activas_enlaza_a_la_cuenta():
    e = entrada(totales_30={ACT: {"gasto": 5000.0, "valor": 100.0, "compras": 1.0}})
    r = una(rec.calcular(e), "cuenta_roas_bajo")
    assert r["objetos"] == [] and r["enlace"] == administrador.enlace_cuenta(ACT)


@pytest.mark.parametrize("totales", [{"gasto": 1000.0, "valor": 500.0}, {"gasto": 999.0, "valor": 0.0}])
def test_cuenta_roas_bajo_nada_en_0_5_o_con_menos_de_1000(totales):
    assert de_tipo(rec.calcular(entrada(totales_30={ACT: totales})), "cuenta_roas_bajo") == []


def test_cuenta_roas_bajo_misma_huella_aunque_cambien_sus_campanas():
    e1 = entrada(totales_30={ACT: {"gasto": 5000.0, "valor": 100.0}}, objetos=[campana("800")])
    e2 = entrada(totales_30={ACT: {"gasto": 5000.0, "valor": 100.0}}, objetos=[campana("801")])
    assert una(rec.calcular(e1), "cuenta_roas_bajo")["id"] == una(rec.calcular(e2), "cuenta_roas_bajo")["id"]


# ------------------------------------------------------------ estado de la cuenta ---

@pytest.mark.parametrize("status", [2, 3, 7, 8, 9, 100, 101, 55, "2"])
def test_cuenta_estado_alta_si_no_esta_activa(status):
    r = una(rec.calcular(entrada(cuentas=[cuenta(status=status)])), "cuenta_estado")
    assert r["nivel"] == "alta" and r["por_que"] and r["que_hacer"]
    assert r["enlace"] == administrador.enlace_cuenta(ACT)


def test_cuenta_estado_dice_el_motivo_en_palabras():
    r = una(rec.calcular(entrada(cuentas=[cuenta(status=3)])), "cuenta_estado")
    assert "sin pagar" in r["por_que"]
    r = una(rec.calcular(entrada(cuentas=[cuenta(status=55)])), "cuenta_estado")
    assert "55" in r["por_que"]


def test_cuenta_estado_alta_desde_90_por_ciento_del_tope():
    r = una(rec.calcular(entrada(cuentas=[cuenta(spend_cap="1000000", amount_spent="900000")])), "cuenta_estado")
    assert r["nivel"] == "alta" and rec.TOPE_FRACCION == 0.90
    # Meta manda el tope y lo gastado en centavos: 10 000 SEK de tope, 9 000 gastados.
    assert "9.000 SEK" in r["por_que"] and "10.000 SEK" in r["por_que"]


def test_cuenta_estado_tope_en_moneda_sin_decimales():
    c = cuenta(moneda="JPY", spend_cap="10000", amount_spent="9500")
    r = una(rec.calcular(entrada(cuentas=[c])), "cuenta_estado")
    assert "10.000 JPY" in r["por_que"]


@pytest.mark.parametrize("c", [cuenta(), cuenta(spend_cap="1000000", amount_spent="899999"),
                               cuenta(spend_cap="0", amount_spent="99999999"), cuenta(status=None),
                               {"ad_account_id": ACT, "nombre": "x", "moneda": "SEK", "extra": {}}])
def test_cuenta_estado_nada_activa_y_lejos_del_tope(c):
    assert de_tipo(rec.calcular(entrada(cuentas=[c])), "cuenta_estado") == []


def test_cuenta_estado_junta_los_dos_motivos_en_una():
    r = una(rec.calcular(entrada(cuentas=[cuenta(status=9, spend_cap="100", amount_spent="100")])),
            "cuenta_estado")
    assert "gracia" in r["por_que"] and "tope" in r["por_que"]


# ------------------------------------------------------------ segmento caro ---

def _segmentos(valor_a=99.0, gasto_a=100.0, clave_a="NO", dimension="pais"):
    """Segmento A contra el resto (B, 1 900 de valor): con gasto_a=100 y valor_a=100 la cuenta queda en ROAS 2,0 y
    A justo en la mitad."""
    return entrada(desgloses_30=[
        {"ad_account_id": ACT, "dimension": dimension, "clave": clave_a, "gasto": gasto_a, "compras": 1.0,
         "valor": valor_a},
        {"ad_account_id": ACT, "dimension": dimension, "clave": "SE", "gasto": 1000.0 - gasto_a, "compras": 30.0,
         "valor": 1900.0}])


def test_segmento_caro_con_10_por_ciento_del_gasto_y_menos_de_la_mitad_del_roas():
    r = una(rec.calcular(_segmentos()), "segmento_caro")
    assert r["nivel"] == "media" and rec.SEGMENTO_GASTO_MIN == 0.10 and rec.SEGMENTO_FACTOR_ROAS == 0.5
    assert "NO" in r["que_hacer"] and "País" in r["que_hacer"]
    assert r["objetos"] == [] and r["enlace"] == administrador.enlace_cuenta(ACT)
    assert r["impacto"]["monto"] == pytest.approx(100 / 30)


def test_segmento_caro_nada_en_la_mitad_justa_o_bajo_10_por_ciento():
    assert de_tipo(rec.calcular(_segmentos(valor_a=100.0)), "segmento_caro") == []
    assert de_tipo(rec.calcular(_segmentos(valor_a=0.0, gasto_a=99.0)), "segmento_caro") == []


def test_segmento_caro_ignora_lo_que_meta_no_sabe_clasificar():
    assert de_tipo(rec.calcular(_segmentos(clave_a="unknown")), "segmento_caro") == []
    assert de_tipo(rec.calcular(_segmentos(clave_a="unknown|unknown", dimension="edad_genero")),
                   "segmento_caro") == []
    assert rec.SIN_VALOR == "unknown"


def test_segmento_caro_edad_y_genero_en_palabras_y_huella_por_segmento():
    r = una(rec.calcular(_segmentos(clave_a="55-64|female", dimension="edad_genero")), "segmento_caro")
    assert "55-64 · mujeres" in r["que_hacer"]
    otra = una(rec.calcular(_segmentos(clave_a="65+|female", dimension="edad_genero")), "segmento_caro")
    assert r["id"] != otra["id"]


def test_segmento_caro_solo_de_su_cuenta():
    e = _segmentos()
    for f in e["desgloses_30"]:
        f["ad_account_id"] = ACT2
    assert de_tipo(rec.calcular(e), "segmento_caro") == []


# ------------------------------------------------------------ concentración ---

def _concentracion(gasto_ad=60.0, gasto_conjunto=100.0, estado="ACTIVE"):
    return entrada(anuncios=[anuncio("1", adset_id="900", gasto_7=gasto_ad, estado=estado),
                             anuncio("2", adset_id="900", gasto_7=gasto_conjunto - gasto_ad)],
                   conjuntos_7={"900": {"gasto": gasto_conjunto, "compras": 2.0, "valor": 200.0}})


def test_concentracion_baja_desde_60_por_ciento_en_un_conjunto_con_5_por_ciento():
    r = una(rec.calcular(_concentracion()), "concentracion")
    assert r["nivel"] == "baja" and rec.CONCENTRACION_ANUNCIO_MIN == 0.60 and rec.CONCENTRACION_CONJUNTO_MIN == 0.05
    assert r["objetos"] == [{"nivel": "anuncio", "id": "1", "nombre": "Anuncio 1"}]
    assert "60 %" in r["por_que"]
    assert una(rec.calcular(_concentracion(gasto_ad=50.0, gasto_conjunto=50.0)), "concentracion")


@pytest.mark.parametrize("kw", [{"gasto_ad": 59.0}, {"gasto_ad": 49.0, "gasto_conjunto": 49.0},
                                {"estado": "PAUSED"}])
def test_concentracion_nada_bajo_60_por_ciento_conjunto_chico_o_anuncio_pausado(kw):
    assert de_tipo(rec.calcular(_concentracion(**kw)), "concentracion") == []


# ------------------------------------------------------------ orden, huella, varias cuentas ---

def test_orden_alta_media_baja_y_luego_impacto():
    e = entrada(cuentas=[cuenta(), cuenta(ACT2, "HF Norge", "NOK")],
                totales_7={ACT: {"gasto": 1000.0, "valor": 2000.0}, ACT2: {"gasto": 10000.0, "valor": 20000.0}},
                totales_30={ACT: {"gasto": 4000.0, "valor": 8000.0}, ACT2: {"gasto": 40000.0, "valor": 1000.0}},
                anuncios=[anuncio("1", veredicto="perdedor", gasto_7=70.0),
                          anuncio("2", veredicto="perdedor", gasto_7=700.0, act=ACT2),
                          anuncio("3", adset_id="905", gasto_7=100.0)],
                conjuntos_7={"905": {"gasto": 100.0}})
    recs = rec.calcular(e)
    assert [(r["tipo"], r["cuenta"]) for r in recs] == [
        ("cuenta_roas_bajo", ACT2), ("perdedores_gastando", ACT2), ("perdedores_gastando", ACT),
        ("concentracion", ACT)]
    assert [r["nivel"] for r in recs] == ["alta", "media", "media", "baja"]
    assert recs[2]["impacto"]["moneda"] == "SEK" and recs[1]["impacto"]["moneda"] == "NOK"


def test_sin_impacto_va_despues_dentro_de_su_nivel():
    e = _abo()
    e["anuncios"] = [anuncio("1", veredicto="perdedor", gasto_7=7.0)]
    assert [r["tipo"] for r in rec.calcular(e)] == ["perdedores_gastando", "escalar"]


def test_huella_estable_y_sin_importar_el_orden_de_los_objetos():
    anuncios = [anuncio("1", veredicto="perdedor", gasto_7=10.0), anuncio("2", veredicto="perdedor", gasto_7=20.0)]
    a = una(rec.calcular(entrada(anuncios=anuncios)), "perdedores_gastando")["id"]
    b = una(rec.calcular(entrada(anuncios=list(reversed(anuncios)))), "perdedores_gastando")["id"]
    assert a == b and isinstance(a, str) and len(a) == 16
    # El mismo gasto con otros anuncios, u otra cuenta: otra huella.
    c = una(rec.calcular(entrada(anuncios=anuncios[:1])), "perdedores_gastando")["id"]
    assert c != a
    assert rec.huella("perdedores_gastando", ACT, ["2", "1"]) == a
    assert rec.huella("perdedores_gastando", ACT2, ["1", "2"]) != a


def test_huellas_unicas_en_una_lista_grande():
    e = _segmentos()
    e["anuncios"] = [anuncio("1", veredicto="perdedor", gasto_7=300.0, estado="WITH_ISSUES", gasto_30=300.0)]
    e["cuentas"] = [cuenta(status=2)]
    ids = [r["id"] for r in rec.calcular(e)]
    assert len(ids) == len(set(ids)) >= 4


def test_cada_cuenta_con_su_moneda_y_sus_objetos():
    e = entrada(cuentas=[cuenta(), cuenta(ACT2, "HF Norge", "NOK")],
                totales_7={ACT: {"gasto": 1000.0, "valor": 2000.0}, ACT2: {"gasto": 1000.0, "valor": 2000.0}},
                totales_30={ACT: {"gasto": 4000.0, "valor": 8000.0}, ACT2: {"gasto": 4000.0, "valor": 8000.0}},
                anuncios=[anuncio("1", veredicto="perdedor", gasto_7=50.0),
                          anuncio("2", veredicto="perdedor", gasto_7=60.0, act=ACT2)])
    recs = {r["cuenta"]: r for r in de_tipo(rec.calcular(e), "perdedores_gastando")}
    assert [o["id"] for o in recs[ACT]["objetos"]] == ["1"] and recs[ACT]["impacto"]["moneda"] == "SEK"
    assert [o["id"] for o in recs[ACT2]["objetos"]] == ["2"] and recs[ACT2]["impacto"]["moneda"] == "NOK"
    assert "act=222" in recs[ACT2]["enlace"] and recs[ACT2]["cuenta_nombre"] == "HF Norge"


def test_textos_en_ingles_con_el_catalogo():
    import idiomas
    e = entrada(anuncios=[anuncio("1", veredicto="perdedor", gasto_7=1234.6)],
                totales_7={ACT: {"gasto": 10000.0, "valor": 20000.0}})
    with idiomas.en_idioma("en"):
        r = una(rec.calcular(e), "perdedores_gastando")
    assert "1,235 SEK" in r["por_que"] and "Pause" in r["que_hacer"]
