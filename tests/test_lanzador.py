import types

import pytest

from tests.test_experimentos_db import PAISES, _pieza


class MetaFalsa:
    """Sustituye los módulos meta_ads.* usados por lanzador con contadores."""
    def __init__(self, fallar_en=None):
        self.llamadas = []
        self.fallar_en = fallar_en
        self.n = 0

    def _id(self, tipo, **kw):
        self.llamadas.append((tipo, kw))
        if self.fallar_en == tipo:
            raise RuntimeError(f"Meta falló en {tipo}")
        self.n += 1
        return {"id": f"{tipo}_{self.n}"}

    def modulos(self):
        campaign = types.SimpleNamespace(crear_campaign=lambda nombre, objetivo, dry_run=False, spend_cap_centavos=None:
                                         self._id("campaign", nombre=nombre, spend_cap=spend_cap_centavos),
                                         actualizar_estado=lambda oid, status, dry_run=False: self._id("estado", oid=oid, status=status))
        adset = types.SimpleNamespace(crear_adset=lambda nombre, cid, obj, targeting, centavos, dias, dry_run=False:
                                      self._id("adset", nombre=nombre, targeting=targeting, centavos=centavos, dias=dias),
                                      actualizar_presupuesto=lambda oid, c, dry_run=False: self._id("presupuesto", oid=oid, centavos=c),
                                      actualizar_estado=lambda oid, status, dry_run=False: self._id("estado", oid=oid, status=status))
        creative = types.SimpleNamespace(subir_video=lambda url, titulo="", dry_run=False, esperar_seg=180: "vid_1",
                                         crear_creative_video=lambda nombre, vid, mini, msg, link, cta_type="LEARN_MORE", instagram_user_id=None, dry_run=False:
                                         self._id("creative", link=link))
        ad = types.SimpleNamespace(crear_ad=lambda nombre, adset_id, creative_id, dry_run=False: self._id("ad", adset_id=adset_id),
                                   actualizar_estado=lambda oid, status, dry_run=False: self._id("estado", oid=oid, status=status))
        insights = types.SimpleNamespace(obtener_resultados=lambda ad_id, objetivo=None:
                                         {"impresiones": 100, "reach": 90, "alcance": 90, "clics_enlace": 4, "ctr": 4.0, "cpc": 0.5,
                                          "gasto_usd": 2.0, "thruplay": 10, "thruplay_rate": 0.1, "compras": 0, "ingresos": 0.0,
                                          "roas": 0.0, "estado_meta": "ACTIVE", "estado_meta_texto": "Activo", "motivo_rechazo": None})
        auth = types.SimpleNamespace(configurar=lambda *a, **k: None, limpiar=lambda: None)
        return campaign, adset, creative, ad, insights, auth


@pytest.fixture()
def entorno(base_temporal, monkeypatch):
    import experimentos as ex
    import lanzador
    meta = MetaFalsa()
    campaign, adset, creative, ad, insights, auth = meta.modulos()
    monkeypatch.setattr(lanzador, "meta_campaign", campaign)
    monkeypatch.setattr(lanzador, "meta_adset", adset)
    monkeypatch.setattr(lanzador, "meta_creative", creative)
    monkeypatch.setattr(lanzador, "meta_ad", ad)
    monkeypatch.setattr(lanzador, "meta_insights", insights)
    monkeypatch.setattr(lanzador, "meta_auth", auth)
    monkeypatch.setattr(lanzador.meta_conexion, "credenciales_ads", lambda c: {"token": "t", "ad_account_id": "1", "page_id": "2", "ig_user_id": None})
    monkeypatch.setattr(lanzador.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(lanzador, "_miniatura_para_ad", lambda cliente, ad_id, url: "https://r2/mini.jpg")
    f_co = _pieza(base_temporal)
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_1")
    eid = ex.crear("acme", "Cojín", PAISES, "OUTCOME_TRAFFIC", 7, 500000.0, "https://tienda.co/p?x=1", "COP")
    ex.agregar_pieza("acme", eid, f_co, "CO")
    ex.agregar_pieza("acme", eid, clon, "CO")
    ex.agregar_pieza("acme", eid, clon, "MX")
    return {"ex": ex, "lanzador": lanzador, "meta": meta, "eid": eid, "monkeypatch": monkeypatch}


def test_centavos_y_url(base_temporal):
    import lanzador
    assert lanzador.centavos(20000, "COP") == 2000000 and lanzador.centavos(1000, "CLP") == 1000
    assert lanzador.url_destino("https://t.co/p", 7) == "https://t.co/p?utm_source=creatv&utm_medium=meta&utm_content=7"
    assert lanzador.url_destino("https://t.co/p?x=1", 7).startswith("https://t.co/p?x=1&utm_source=creatv")


def test_lanzar_crea_campana_conjuntos_y_anuncios(entorno):
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    etapas = []
    lz.lanzar("acme", eid, on_etapa=etapas.append)
    tipos = [t for t, _ in meta.llamadas]
    assert tipos.count("campaign") == 1 and tipos.count("adset") == 2 and tipos.count("ad") == 3
    assert meta.llamadas[0][1]["spend_cap"] == 50000000
    adsets = [kw for t, kw in meta.llamadas if t == "adset"]
    assert adsets[0]["targeting"]["geo_locations"]["countries"] == ["CO"] and adsets[0]["centavos"] == 2000000
    assert adsets[1]["targeting"]["geo_locations"]["countries"] == ["MX"] and adsets[1]["centavos"] == 15000
    creativos = [kw for t, kw in meta.llamadas if t == "creative"]
    assert all("utm_content=" in c["link"] for c in creativos)
    e = ex.obtener("acme", eid)
    assert e["estado"] == "pausado" and e["meta_campaign_id"] == "campaign_1"
    assert {p["pais"]: p["meta_adset_id"] for p in e["paises"]} == {"CO": "adset_2", "MX": "adset_3"}
    assert all(p["estado"] == "pausado" and p["meta_ad_id"] for p in e["piezas"])
    assert etapas == lz.ETAPAS_LANZAR
    assert any(ev["tipo"] == "lanzamiento" for ev in e["eventos"])


def test_lanzar_retoma_sin_duplicar(entorno):
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    meta.fallar_en = "ad"
    with pytest.raises(RuntimeError):
        lz.lanzar("acme", eid)
    e = ex.obtener("acme", eid)
    assert e["estado"] == "error" and "Meta falló" in e["error"] and e["meta_campaign_id"]
    assert all(p["meta_adset_id"] for p in e["paises"])
    meta.fallar_en = None
    meta.llamadas.clear()
    lz.lanzar("acme", eid)
    tipos = [t for t, _ in meta.llamadas]
    assert "campaign" not in tipos and "adset" not in tipos and tipos.count("ad") == 3
    assert ex.obtener("acme", eid)["estado"] == "pausado"


def test_lanzar_exige_piezas_y_estado(entorno):
    ex, lz, eid = entorno["ex"], entorno["lanzador"], entorno["eid"]
    e2 = ex.crear("acme", "Vacío", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    with pytest.raises(ValueError):
        lz.lanzar("acme", e2)
    ex.actualizar("acme", eid, estado="cerrado")
    with pytest.raises(ValueError):
        lz.lanzar("acme", eid)


def test_cambiar_estado_y_presupuesto(entorno):
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    with pytest.raises(ValueError):
        lz.cambiar_estado("acme", eid, "ACTIVE")
    lz.lanzar("acme", eid)
    meta.llamadas.clear()
    lz.cambiar_estado("acme", eid, "ACTIVE")
    ids = [kw["oid"] for t, kw in meta.llamadas if t == "estado"]
    assert ids[0] == "campaign_1" and len(ids) == 1 + 2 + 3
    e = ex.obtener("acme", eid)
    assert e["estado"] == "corriendo" and all(p["estado"] == "activo" for p in e["piezas"]) and all(p["estado"] == "activo" for p in e["paises"])
    meta.llamadas.clear()
    lz.cambiar_estado("acme", eid, "PAUSED", pais="MX")
    ids = [kw["oid"] for t, kw in meta.llamadas if t == "estado"]
    assert ids == ["adset_3", "ad_9"]
    e = ex.obtener("acme", eid)
    assert e["estado"] == "corriendo" and [p["estado"] for p in e["paises"]] == ["activo", "pausado"]
    assert [p["estado"] for p in e["piezas"]] == ["activo", "activo", "pausado"]
    lz.cambiar_presupuesto_pais("acme", eid, "MX", 300)
    assert meta.llamadas[-1] == ("presupuesto", {"oid": "adset_3", "centavos": 30000})
    e = ex.obtener("acme", eid)
    assert e["paises"][1]["presupuesto_dia"] == 300.0 and e["piezas"][2]["presupuesto_dia_actual"] == 300.0
    lz.cerrar("acme", eid)
    assert ex.obtener("acme", eid)["estado"] == "cerrado"


def test_refrescar_guarda_snapshots(entorno):
    ex, lz, eid = entorno["ex"], entorno["lanzador"], entorno["eid"]
    assert lz.refrescar("acme", eid) == 0
    lz.lanzar("acme", eid)
    assert lz.refrescar("acme", eid) == 3
    e = ex.obtener("acme", eid)
    assert e["gasto_acumulado"] == 6.0
    m = e["piezas"][0]["metricas"]
    assert m["impresiones"] == 100 and m["alcance"] == 90 and m["gasto"] == 2.0 and m["thruplay"] == 10
    assert m["estado_meta_texto"] == "Activo" and e["piezas"][0]["estado_meta"] == "ACTIVE"
