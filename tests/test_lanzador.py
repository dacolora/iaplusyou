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
    assert etapas == [nombre for nombre, _peso in lz.ETAPAS_LANZAR]
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
    # ad_8, no ad_9: M4 comparte el creative del clon entre CO y MX, un
    # "creative_N" menos que antes corre la numeración de todo lo posterior.
    assert ids == ["adset_3", "ad_8"]
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


def test_cambiar_estado_activa_campana_al_activar_un_pais_pausado(entorno):
    """Activar un solo país mientras la campaña sigue en pausa en Meta no debe
    quedar como 'corriendo' sin entregar: hay que activar también la campaña."""
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    lz.lanzar("acme", eid)
    e = ex.obtener("acme", eid)
    assert e["estado"] == "pausado"
    meta.llamadas.clear()
    lz.cambiar_estado("acme", eid, "ACTIVE", pais="CO")
    ids = [(t, kw["oid"]) for t, kw in meta.llamadas if t == "estado"]
    assert ("estado", "campaign_1") in ids
    assert ids[0] == ("estado", "campaign_1")  # campaña antes que el conjunto
    e = ex.obtener("acme", eid)
    assert e["estado"] == "corriendo"

    # Un segundo país activado con la campaña ya corriendo no debe repetir la llamada.
    meta.llamadas.clear()
    lz.cambiar_estado("acme", eid, "ACTIVE", pais="MX")
    ids = [(t, kw["oid"]) for t, kw in meta.llamadas if t == "estado"]
    assert ("estado", "campaign_1") not in ids


def test_cambiar_estado_pausar_un_pais_no_toca_la_campana(entorno):
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    lz.lanzar("acme", eid)
    lz.cambiar_estado("acme", eid, "ACTIVE")
    meta.llamadas.clear()
    lz.cambiar_estado("acme", eid, "PAUSED", pais="MX")
    ids = [(t, kw["oid"]) for t, kw in meta.llamadas if t == "estado"]
    assert ("estado", "campaign_1") not in ids


def test_cambiar_estado_y_presupuesto_rechazan_experimento_cerrado(entorno):
    ex, lz, eid = entorno["ex"], entorno["lanzador"], entorno["eid"]
    lz.lanzar("acme", eid)
    lz.cerrar("acme", eid)
    with pytest.raises(ValueError, match="cerrado"):
        lz.cambiar_estado("acme", eid, "ACTIVE")
    with pytest.raises(ValueError, match="cerrado"):
        lz.cambiar_presupuesto_pais("acme", eid, "CO", 300)


def test_cambiar_presupuesto_pais_rechaza_valor_no_positivo(entorno):
    ex, lz, eid = entorno["ex"], entorno["lanzador"], entorno["eid"]
    lz.lanzar("acme", eid)
    with pytest.raises(ValueError):
        lz.cambiar_presupuesto_pais("acme", eid, "CO", 0)
    with pytest.raises(ValueError):
        lz.cambiar_presupuesto_pais("acme", eid, "CO", -100)


def test_lanzar_reintenta_creative_sin_volver_a_subir_video(entorno, base_temporal):
    from tests.test_experimentos_db import PAISES, _pieza
    ex, lz, meta = entorno["ex"], entorno["lanzador"], entorno["meta"]
    # Experimento aparte con una sola pieza para no mezclar el orden de subidas
    # de las otras piezas del fixture compartido.
    pid = _pieza(base_temporal, pais="CO")
    eid2 = ex.crear("acme", "Solo", PAISES[:1], "OUTCOME_TRAFFIC", 7, 100000.0, "https://t.co/x", "COP")
    ex.agregar_pieza("acme", eid2, pid, "CO")

    llamadas_subir = []
    original = lz.meta_creative.subir_video

    def contando(*a, **k):
        llamadas_subir.append(1)
        return original(*a, **k)

    entorno["monkeypatch"].setattr(lz.meta_creative, "subir_video", contando)
    meta.fallar_en = "creative"
    with pytest.raises(RuntimeError):
        lz.lanzar("acme", eid2)
    assert len(llamadas_subir) == 1
    e = ex.obtener("acme", eid2)
    assert e["piezas"][0]["extra"].get("meta_video_id") == "vid_1"

    meta.fallar_en = None
    lz.lanzar("acme", eid2)
    assert len(llamadas_subir) == 1  # no se resubió el video en el reintento
    assert ex.obtener("acme", eid2)["estado"] == "pausado"


def test_lanzar_falla_deja_piezas_en_cola_no_publicando(entorno):
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    meta.fallar_en = "ad"
    with pytest.raises(RuntimeError):
        lz.lanzar("acme", eid)
    e = ex.obtener("acme", eid)
    assert e["estado"] == "error"
    # La pieza que falló en 'ad' quedó sin meta_ad_id: debe volver a en_cola, no publicando.
    fallida = [p for p in e["piezas"] if not p["meta_ad_id"]]
    assert fallida and all(p["estado"] == "en_cola" for p in fallida)


def test_refrescar_continua_si_falla_una_pieza(entorno):
    ex, lz, eid = entorno["ex"], entorno["lanzador"], entorno["eid"]
    lz.lanzar("acme", eid)

    original = lz.meta_insights.obtener_resultados
    llamados = []

    def fallando(ad_id, objetivo=None):
        llamados.append(ad_id)
        if len(llamados) == 1:
            raise RuntimeError("ad eliminado en Ads Manager")
        return original(ad_id, objetivo=objetivo)

    lz.meta_insights.obtener_resultados = fallando
    try:
        n = lz.refrescar("acme", eid)
    finally:
        lz.meta_insights.obtener_resultados = original
    assert n == 2  # 3 piezas, 1 falló
    e = ex.obtener("acme", eid)
    assert any(ev["tipo"] == "error" for ev in e["eventos"])


def test_encolar_exp_lanzar_con_etapas_reales_no_rompe_consultar(base_temporal):
    """I1: ETAPAS_LANZAR debe ser [(nombre, peso), ...] como cualquier otra
    lista de etapas — antes eran strings sueltos y cola.encolar los guardaba
    como '[list(e) for e in etapas]', partiendo cada nombre en caracteres
    ("Campaña" -> ['C','a','m','p','a','ñ','a']). trabajos.consultar()
    reventaba con ValueError al desempacar esas 'tuplas' de un carácter."""
    import cola
    import lanzador
    import trabajos
    job_id = "acme__exp1__lanzar"
    arranco = trabajos.encolar(job_id, "exp_lanzar", {"cliente": "acme", "experimento_id": 1},
                               cliente="acme", duracion_estimada=120, etapas=lanzador.ETAPAS_LANZAR, max_intentos=1)
    assert arranco is True
    cola.reclamar()
    info = trabajos.consultar(job_id)  # no debe lanzar ValueError
    assert info["estado"] == "en_progreso"
    cola.reportar(job_id, etapa=lanzador.ETAPAS_LANZAR[0][0])
    info = trabajos.consultar(job_id)
    assert info["etapa"] == lanzador.ETAPAS_LANZAR[0][0]


def test_lanzar_mismo_clon_en_dos_paises_comparte_video_y_creative(entorno):
    """M4: el fixture ya agrega el mismo clon a CO y a MX — subir el video y
    crear el creative para cada país duplicaría una subida que puede tardar
    hasta 180s bajo _LOCK, sin ganar nada (utm_content=pieza_id es igual en
    ambos, es la misma pieza)."""
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    llamadas_subir = []
    original = lz.meta_creative.subir_video

    def contando(*a, **k):
        llamadas_subir.append(1)
        return original(*a, **k)

    entorno["monkeypatch"].setattr(lz.meta_creative, "subir_video", contando)
    lz.lanzar("acme", eid)
    tipos = [t for t, _ in meta.llamadas]
    assert tipos.count("creative") == 2  # f_co + 1 creative compartido por el clon (CO y MX)
    assert len(llamadas_subir) == 2       # f_co sube su video, el clon sube el suyo una sola vez
    e = ex.obtener("acme", eid)
    clones = [p for p in e["piezas"] if p["tipo"] == "clon"]
    assert len(clones) == 2
    assert clones[0]["meta_creative_id"] == clones[1]["meta_creative_id"]
    assert clones[0]["extra"].get("meta_video_id") == clones[1]["extra"].get("meta_video_id")


def test_cambiar_presupuesto_pais_rechaza_lanzando(entorno):
    """M1: mientras el experimento está lanzando, cambiar el presupuesto de un
    país haría un read-modify-write sobre experimento.paises que podría pisar
    el meta_adset_id que lanzador.lanzar acaba de guardar (carrera sin lock)."""
    ex, lz, eid = entorno["ex"], entorno["lanzador"], entorno["eid"]
    ex.actualizar("acme", eid, estado="lanzando")
    ex.actualizar_pais("acme", eid, "CO", meta_adset_id="adset_x")
    with pytest.raises(ValueError, match="todavía no está en Meta"):
        lz.cambiar_presupuesto_pais("acme", eid, "CO", 300)


def test_cambiar_estado_pausar_ultimo_pais_activo_marca_experimento_pausado(entorno):
    """M5: si el país que se pausa era el único que quedaba activo, el
    experimento ya no está 'corriendo' de verdad (todos los conjuntos en
    Meta quedaron PAUSED) — y exp_refrescar_todos solo pule lo 'corriendo'."""
    ex, lz, eid = entorno["ex"], entorno["lanzador"], entorno["eid"]
    lz.lanzar("acme", eid)
    lz.cambiar_estado("acme", eid, "ACTIVE")
    lz.cambiar_estado("acme", eid, "PAUSED", pais="CO")
    assert ex.obtener("acme", eid)["estado"] == "corriendo"  # MX sigue activo
    lz.cambiar_estado("acme", eid, "PAUSED", pais="MX")
    assert ex.obtener("acme", eid)["estado"] == "pausado"


def test_lanzar_piezas_nuevas_solo_crea_anuncios_faltantes(entorno, base_temporal):
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    lz.lanzar("acme", eid)
    from tests.test_experimentos_db import _pieza
    nueva = _pieza(base_temporal, tipo="final", legado="cf_1__es_CO__v1", pais="CO")
    ex.agregar_pieza("acme", eid, nueva, "CO")
    meta.llamadas.clear()
    assert lz.lanzar_piezas_nuevas("acme", eid) == 1
    tipos = [t for t, _ in meta.llamadas]
    assert tipos.count("ad") == 1 and "campaign" not in tipos and "adset" not in tipos
    p = [p for p in ex.piezas("acme", eid) if p["pieza_id"] == nueva][0]
    assert p["estado"] == "pausado" and p["meta_ad_id"]
    assert lz.lanzar_piezas_nuevas("acme", eid) == 0


def test_lanzar_piezas_nuevas_pieza_con_error_sigue_con_las_demas(entorno, base_temporal):
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    lz.lanzar("acme", eid)
    nueva1 = _pieza(base_temporal, tipo="final", legado="cf_1__es_CO__v2", pais="CO")
    nueva2 = _pieza(base_temporal, tipo="final", legado="cf_1__es_CO__v3", pais="CO")
    ex.agregar_pieza("acme", eid, nueva1, "CO")
    ex.agregar_pieza("acme", eid, nueva2, "CO")
    meta.llamadas.clear()
    meta.fallar_en = "ad"
    with pytest.raises(RuntimeError):
        lz.lanzar_piezas_nuevas("acme", eid)
    meta.fallar_en = None
    piezas = {p["id"]: p for p in ex.piezas("acme", eid)}
    fallidas = [p for p in piezas.values() if p["pieza_id"] in (nueva1, nueva2)]
    assert all(p["estado"] == "error" and p["error"] for p in fallidas)
    e = ex.obtener("acme", eid)
    assert any(ev["tipo"] == "error" for ev in e["eventos"])
    assert e["estado"] == "pausado"  # el estado del experimento no lo toca esta función


def test_lanzar_piezas_nuevas_exige_experimento_en_meta(entorno):
    ex, lz, eid = entorno["ex"], entorno["lanzador"], entorno["eid"]
    with pytest.raises(ValueError):
        lz.lanzar_piezas_nuevas("acme", eid)  # aún 'armando', sin meta_campaign_id


def test_pausar_activar_pieza(entorno):
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    lz.lanzar("acme", eid)
    lz.cambiar_estado("acme", eid, "ACTIVE")
    ep = ex.piezas("acme", eid)[0]
    meta.llamadas.clear()
    lz.pausar_pieza("acme", ep["id"])
    assert meta.llamadas[-1] == ("estado", {"oid": ep["meta_ad_id"], "status": "PAUSED"})
    assert ex.piezas("acme", eid)[0]["estado"] == "pausado"
    lz.activar_pieza("acme", ep["id"])
    assert ex.piezas("acme", eid)[0]["estado"] == "activo"


def test_activar_pieza_marca_activado_en_pieza_y_experimento(entorno):
    """Bloque 4 (decisor/escalera): activado_en debe sembrarse en el 'extra'
    de la pieza cada vez que se activa, y en el del experimento solo la
    primera vez que pasa a 'corriendo' — sin pisarse en activaciones
    posteriores."""
    ex, lz, eid = entorno["ex"], entorno["lanzador"], entorno["eid"]
    lz.lanzar("acme", eid)
    e = ex.obtener("acme", eid)
    assert e["estado"] == "pausado" and not e["extra"].get("activado_en")
    ep = e["piezas"][0]
    assert not ep["extra"].get("activado_en")

    lz.activar_pieza("acme", ep["id"])
    e = ex.obtener("acme", eid)
    assert e["estado"] == "corriendo"
    primer_activado_en = e["extra"]["activado_en"]
    assert primer_activado_en
    ep_activada = [p for p in e["piezas"] if p["id"] == ep["id"]][0]
    assert ep_activada["extra"]["activado_en"]

    # Activar otra pieza (experimento ya 'corriendo') no debe pisar el
    # activado_en del experimento.
    otra = [p for p in e["piezas"] if p["id"] != ep["id"]][0]
    lz.activar_pieza("acme", otra["id"])
    e = ex.obtener("acme", eid)
    assert e["extra"]["activado_en"] == primer_activado_en


def test_cambiar_estado_marca_activado_en(entorno):
    ex, lz, eid = entorno["ex"], entorno["lanzador"], entorno["eid"]
    lz.lanzar("acme", eid)
    e = ex.obtener("acme", eid)
    assert not e["extra"].get("activado_en")
    lz.cambiar_estado("acme", eid, "ACTIVE")
    e = ex.obtener("acme", eid)
    assert e["extra"]["activado_en"]
    assert all(p["extra"].get("activado_en") for p in e["piezas"])


def test_escalar_pais(entorno):
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    lz.lanzar("acme", eid)
    assert lz.escalar_pais("acme", eid, "MX", 20) == 180.0
    assert meta.llamadas[-1][0] == "presupuesto"
    assert lz.escalar_pais("acme", eid, "MX", 20, tope_dia=200) == 200.0
    n = len(meta.llamadas)
    assert lz.escalar_pais("acme", eid, "MX", 20, tope_dia=200) == 200.0 and len(meta.llamadas) == n


def test_lanzar_autosana_si_preflight_falla_con_estado_ya_lanzando(entorno):
    """M3: si el llamador (la ruta) ya puso 'lanzando' antes de encolar y el
    pre-flight de lanzar() falla (ej. alguien quitó todas las piezas entre el
    clic y que el worker la tomara), el experimento no debe quedar colgado en
    'lanzando' para siempre — antes esos ValueError se disparaban fuera de
    cualquier try/except que sanara el estado."""
    ex, lz, eid = entorno["ex"], entorno["lanzador"], entorno["eid"]
    ex.actualizar("acme", eid, estado="lanzando")
    for p in ex.piezas("acme", eid):
        ex.quitar_pieza("acme", eid, p["id"])
    with pytest.raises(ValueError):
        lz.lanzar("acme", eid)


def test_lanzar_piezas_nuevas_comparte_cache_entre_piezas_de_la_misma_corrida(entorno, base_temporal):
    """Fix round 1 (Important #1): dos piezas 'en_cola' nuevas con el mismo
    pieza_id (un clon regenerado atado a dos países) agregadas en la misma
    corrida de lanzar_piezas_nuevas deben compartir el cache de video/creative
    — antes cada llamada a _crear_anuncios recibía un cache vacío propio y
    repetía subir_video + crear_creative_video para la segunda."""
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    lz.lanzar("acme", eid)
    clon_nuevo = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_2")
    ex.agregar_pieza("acme", eid, clon_nuevo, "CO")
    ex.agregar_pieza("acme", eid, clon_nuevo, "MX")

    llamadas_subir = []
    original = lz.meta_creative.subir_video

    def contando(*a, **k):
        llamadas_subir.append(1)
        return original(*a, **k)

    entorno["monkeypatch"].setattr(lz.meta_creative, "subir_video", contando)
    meta.llamadas.clear()
    assert lz.lanzar_piezas_nuevas("acme", eid) == 2
    tipos = [t for t, _ in meta.llamadas]
    assert tipos.count("ad") == 2
    assert tipos.count("creative") == 1
    assert len(llamadas_subir) == 1
    nuevas = [p for p in ex.piezas("acme", eid) if p["pieza_id"] == clon_nuevo]
    assert len(nuevas) == 2
    assert all(p["meta_ad_id"] for p in nuevas)
    assert nuevas[0]["meta_creative_id"] == nuevas[1]["meta_creative_id"]


def test_lanzar_piezas_nuevas_reusa_creative_de_pieza_vieja_con_mismo_pieza_id(entorno, base_temporal):
    """Fix round 1 (Important #1), segundo caso: una pieza nueva cuyo
    pieza_id YA tiene creative en otra pieza ya lanzada (de una corrida
    anterior, en otro país) no debe volver a subir video ni crear creative —
    solo el ad. Experimento aparte con 3 países (CO, MX, BR) para que BR ya
    tenga su conjunto en Meta antes de agregarle la pieza reusada."""
    ex, lz, meta = entorno["ex"], entorno["lanzador"], entorno["meta"]
    paises3 = PAISES + [{"pais": "BR", "idioma": "pt", "presupuesto_dia": 100.0}]
    eid = ex.crear("acme", "Cojín BR", paises3, "OUTCOME_TRAFFIC", 7, 500000.0, "https://tienda.co/p", "COP")
    f_co = _pieza(base_temporal, pais="CO", legado="cf_x__co")
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_x")
    f_br = _pieza(base_temporal, pais="BR", idioma="pt", legado="cf_x__br")
    ex.agregar_pieza("acme", eid, f_co, "CO")
    ex.agregar_pieza("acme", eid, clon, "CO")
    ex.agregar_pieza("acme", eid, clon, "MX")
    ex.agregar_pieza("acme", eid, f_br, "BR")
    lz.lanzar("acme", eid)

    llamadas_subir = []
    original = lz.meta_creative.subir_video

    def contando(*a, **k):
        llamadas_subir.append(1)
        return original(*a, **k)

    entorno["monkeypatch"].setattr(lz.meta_creative, "subir_video", contando)
    ex.agregar_pieza("acme", eid, clon, "BR")  # pieza nueva en_cola, mismo pieza_id que el clon ya lanzado
    meta.llamadas.clear()
    assert lz.lanzar_piezas_nuevas("acme", eid) == 1
    tipos = [t for t, _ in meta.llamadas]
    assert tipos.count("ad") == 1
    assert "creative" not in tipos
    assert len(llamadas_subir) == 0
    piezas = ex.piezas("acme", eid)
    br_clon = [p for p in piezas if p["pieza_id"] == clon and p["pais"] == "BR"][0]
    creative_original = [p for p in piezas if p["pieza_id"] == clon and p["pais"] == "CO"][0]["meta_creative_id"]
    assert br_clon["meta_ad_id"] and br_clon["meta_creative_id"] == creative_original


def test_activar_pieza_reactiva_conjunto_de_pais_pausado_individualmente(entorno):
    """Fix round 1 (Important #2): con el experimento 'corriendo' porque otro
    país sigue activo, pausar MX individualmente (cambiar_estado(pais='MX'))
    no debe impedir que activar_pieza sobre una pieza de MX reactive su
    conjunto en Meta — antes primera_activacion solo miraba ex['estado'], que
    seguía 'corriendo', y el conjunto de MX quedaba PAUSED en Meta con el
    anuncio ACTIVE encima."""
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    lz.lanzar("acme", eid)
    lz.cambiar_estado("acme", eid, "ACTIVE")
    lz.cambiar_estado("acme", eid, "PAUSED", pais="MX")
    e = ex.obtener("acme", eid)
    assert e["estado"] == "corriendo"  # CO sigue activo
    mx_pais = [p for p in e["paises"] if p["pais"] == "MX"][0]
    assert mx_pais["estado"] == "pausado" and mx_pais["meta_adset_id"] == "adset_3"
    mx_pieza = [p for p in e["piezas"] if p["pais"] == "MX"][0]

    meta.llamadas.clear()
    lz.activar_pieza("acme", mx_pieza["id"])
    estados = [(t, kw["oid"], kw["status"]) for t, kw in meta.llamadas if t == "estado"]
    assert ("estado", "adset_3", "ACTIVE") in estados
    assert ("estado", mx_pieza["meta_ad_id"], "ACTIVE") in estados
    assert ("estado", "campaign_1", "ACTIVE") not in estados  # la campaña ya estaba ACTIVE

    e = ex.obtener("acme", eid)
    assert [p for p in e["paises"] if p["pais"] == "MX"][0]["estado"] == "activo"
