"""Entradas del selector de «Rendimiento» (spec 2026-10-09 R2–R5)."""
from pestana_rendimiento import entradas as E


def _t(id_, pais):
    return {"id": id_, "pais": pais, "dominio": f"t{id_}.myshopify.com"}


def _c(act, pais, moneda="SEK"):
    return {"ad_account_id": act, "pais": pais, "moneda": moneda, "nombre": act}


def test_un_pais_con_tienda_es_triple_whale_y_sin_tienda_es_meta():
    es = E.armar([_t(1, "NO")], [_c("act_no", "NO"), _c("act_se", "SE")])
    por = {e["clave"]: e for e in es}
    assert por["NO"]["fuente"] == E.TW and por["NO"]["tienda"]["id"] == 1
    assert [c["ad_account_id"] for c in por["NO"]["cuentas"]] == ["act_no"]
    assert por["SE"]["fuente"] == E.META and por["SE"]["cuentas_suma"] == ["act_se"]
    assert por["NO"]["cuentas_suma"] == []          # las de una entrada Triple Whale nunca se suman aparte


def test_sin_pais_es_su_propia_entrada():
    es = E.armar([], [_c("act_ww", None), _c("act_se", "SE")])
    assert {e["clave"] for e in es} == {"SE", "cuenta:act_ww"}
    assert es[-1]["clave"] == "cuenta:act_ww"       # las sin país van al final


def test_una_sola_tienda_sin_pais_es_la_fuente_de_todo():
    es = E.armar([_t(7, None)], [_c("act_no", "NO"), _c("act_se", "SE")])
    assert len(es) == 1 and es[0]["fuente"] == E.TW and es[0]["tienda"]["id"] == 7
    assert [c["ad_account_id"] for c in es[0]["cuentas"]] == ["act_no", "act_se"]
    assert E.elegir(es, "") is es[0]


def test_cuenta_cubierta_por_una_tienda_no_se_suma_aparte():
    es = E.armar([_t(1, "NO")], [_c("act_no", "NO"), _c("act_ww", None), _c("act_se", "SE")],
                 cubiertas={1: {"act_no", "act_ww"}})
    por = {e["clave"]: e for e in es}
    assert por["cuenta:act_ww"]["cuentas_suma"] == [] and por["cuenta:act_ww"]["cubierta"] is True
    assert por["SE"]["cuentas_suma"] == ["act_se"] and por["SE"]["cubierta"] is False
    todas = E.alcance(es, None)
    assert todas["fuente"] == "mixta" and todas["tw"] == {"tienda_id": None}
    assert todas["meta_fuente"] == ["act_se"] and set(todas["cubiertas_tw"]) == {"act_no", "act_ww"}
    assert set(todas["meta_estructura"]) == {"act_no", "act_ww", "act_se"}
    sola = E.alcance(es, por["cuenta:act_ww"])        # vista sola, una entrada Meta muestra Meta (R3)
    assert sola["fuente"] == "meta" and sola["meta_fuente"] == ["act_ww"] and sola["tw"] is None


def test_elegir_y_legado():
    es = E.armar([_t(1, "NO"), _t(2, "SE")], [_c("act_fi", "FI")])
    assert E.elegir(es, "SE")["tienda"]["id"] == 2
    assert E.elegir(es, "XX") is None and E.elegir(es, None) is None and E.elegir(es, "tienda:99") is None
    assert E.de_legado(es, tienda="2") == "SE" and E.de_legado(es, cuenta="fi") is None
    assert E.de_legado(es, cuenta="act_fi") == "FI" and E.de_legado(es, tienda="abc") is None


def test_alcance_de_una_tienda_y_de_nada():
    es = E.armar([_t(1, "NO")], [_c("act_no", "NO")])
    a = E.alcance(es, es[0])
    assert a == {"tw": {"tienda_id": 1}, "meta_fuente": [], "meta_estructura": ["act_no"],
                 "cubiertas_tw": ["act_no"], "fuente": "tw"}
    assert E.alcance([], None)["fuente"] is None


def test_r4_una_sola_tienda_sin_pais_alcance():
    # R4: una sola tienda sin país es la fuente de todo; alcance muestra todos los accounts en cubiertas_tw
    es = E.armar([_t(7, None)], [_c("act_no", "NO"), _c("act_se", "SE")])
    elegida = E.elegir(es, "")
    a = E.alcance(es, elegida)
    assert a["cubiertas_tw"] == ["act_no", "act_se"] and a["fuente"] == "tw"


def test_paridad_cubiertas_tw_tw_vs_todas():
    # Parity: accounts en cubiertas_tw de una entrada TW sola son subset de cubiertas_tw en «Todas»
    es = E.armar([_t(1, "NO")], [_c("act_no", "NO"), _c("act_se", "SE")])
    por = {e["clave"]: e for e in es}
    sola_no = E.alcance(es, por["NO"])
    todas = E.alcance(es, None)
    assert set(sola_no["cubiertas_tw"]) <= set(todas["cubiertas_tw"])
    assert sola_no["cubiertas_tw"] == ["act_no"]
