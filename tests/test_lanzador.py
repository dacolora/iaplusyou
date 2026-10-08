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
        adset = types.SimpleNamespace(crear_adset=lambda nombre, cid, obj, targeting, centavos, dias, dry_run=False, promoted_object=None:
                                      self._id("adset", nombre=nombre, objetivo=obj, targeting=targeting, centavos=centavos, dias=dias,
                                               promoted_object=promoted_object),
                                      actualizar_presupuesto=lambda oid, c, dry_run=False: self._id("presupuesto", oid=oid, centavos=c),
                                      actualizar_estado=lambda oid, status, dry_run=False: self._id("estado", oid=oid, status=status))
        creative = types.SimpleNamespace(subir_video=lambda url, titulo="", dry_run=False, esperar_seg=180: "vid_1",
                                         crear_creative_video=lambda nombre, vid, mini, msg, link, cta_type="LEARN_MORE", instagram_user_id=None, dry_run=False, url_tags=None:
                                         self._id("creative", nombre=nombre, link=link, url_tags=url_tags, cta_type=cta_type),
                                         crear_creative_imagen=lambda nombre, imagen_url, msg, link, cta_type="LEARN_MORE", instagram_user_id=None, dry_run=False, url_tags=None:
                                         self._id("creative_imagen", nombre=nombre, link=link, imagen_url=imagen_url, url_tags=url_tags, cta_type=cta_type))
        ad = types.SimpleNamespace(crear_ad=lambda nombre, adset_id, creative_id, dry_run=False: self._id("ad", nombre=nombre, adset_id=adset_id),
                                   actualizar_estado=lambda oid, status, dry_run=False: self._id("estado", oid=oid, status=status))
        insights = types.SimpleNamespace(obtener_resultados=lambda ad_id, objetivo=None:
                                         {"impresiones": 100, "reach": 90, "alcance": 90, "clics_enlace": 4, "ctr": 4.0, "cpc": 0.5,
                                          "gasto_usd": 2.0, "thruplay": 10, "thruplay_rate": 0.1, "compras": 0, "ingresos": 0.0,
                                          "roas": 0.0, "estado_meta": "ACTIVE", "estado_meta_texto": "Activo", "motivo_rechazo": None})
        auth = types.SimpleNamespace(configurar=lambda *a, **k: None, limpiar=lambda: None,
                                     llamar=lambda *a, **kw: {"success": True})
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


# Instalaciones de la app (spec 2026-10-07): mismo presupuesto en los dos
# países para poder comprobar el reparto entre plataformas.
PRESUPUESTO_PAIS = 20000.0
PAISES_APP = [{"pais": "CO", "idioma": "es", "presupuesto_dia": PRESUPUESTO_PAIS},
              {"pais": "MX", "idioma": "es", "presupuesto_dia": PRESUPUESTO_PAIS}]
URL_IOS = "https://apps.apple.com/co/app/forja/id123"
URL_ANDROID = "https://play.google.com/store/apps/details?id=com.forja"


def _entorno_app(base_temporal, monkeypatch, app):
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
    monkeypatch.setattr(lanzador.meta_conexion, "cargar_app_anunciada", lambda c: "12345")
    # Triple Whale conectado: sus parámetros NO deben viajar en un anuncio de tienda.
    monkeypatch.setattr(lanzador.triple_whale_tiendas, "kw_url_tags", lambda c: {"url_tags": "tw_source=meta"})
    monkeypatch.setattr(lanzador, "_miniatura_para_ad", lambda cliente, ad_id, url: "https://r2/mini.jpg")
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_app")
    datos = dict(nombre="Forja", paises=PAISES_APP, objetivo_meta="OUTCOME_APP_PROMOTION", dias=7, tope_total=500000.0,
                 destino_url=app.get("ios_url") or app.get("android_url"), moneda="COP", app=app)
    eid = ex.crear_con_piezas("acme", datos, [(clon, "CO"), (clon, "MX")])
    return {"ex": ex, "lanzador": lanzador, "meta": meta, "eid": eid, "monkeypatch": monkeypatch}


@pytest.fixture()
def entorno_app(base_temporal, monkeypatch):
    return _entorno_app(base_temporal, monkeypatch, {"ios_url": URL_IOS, "android_url": URL_ANDROID})


@pytest.fixture()
def entorno_app_android(base_temporal, monkeypatch):
    return _entorno_app(base_temporal, monkeypatch, {"android_url": URL_ANDROID})


def test_app_dos_plataformas_crea_un_conjunto_por_pais_y_plataforma(entorno_app):
    e = entorno_app
    e["lanzador"].lanzar("acme", e["eid"])
    adsets = [kw for tipo, kw in e["meta"].llamadas if tipo == "adset"]
    assert len(adsets) == 2 * len(PAISES_APP)          # país × plataforma
    sistemas = {tuple(a["targeting"]["user_os"]) for a in adsets}
    assert sistemas == {("iOS",), ("Android",)}
    assert all(a["targeting"]["device_platforms"] == ["mobile"] for a in adsets)
    assert sorted((a["targeting"]["geo_locations"]["countries"][0], a["targeting"]["user_os"][0]) for a in adsets) == [
        ("CO", "Android"), ("CO", "iOS"), ("MX", "Android"), ("MX", "iOS")]
    for a in adsets:
        assert a["promoted_object"]["application_id"] == "12345"
        assert a["promoted_object"]["object_store_url"] == (URL_IOS if a["targeting"]["user_os"] == ["iOS"] else URL_ANDROID)
        assert a["objetivo"] == "OUTCOME_APP_PROMOTION"
    # presupuesto del país partido en dos (centavos del país // 2)
    assert all(a["centavos"] == e["lanzador"].centavos(PRESUPUESTO_PAIS, "COP") // 2 for a in adsets)
    ex = e["ex"].obtener("acme", e["eid"])
    assert ex["estado"] == "pausado"
    assert all(set(p["meta_adsets"]) == {"ios", "android"} and not p.get("meta_adset_id") for p in ex["paises"])
    # cada anuncio cae en el conjunto de su país y su plataforma
    por_pais = {p["pais"]: p["meta_adsets"] for p in ex["paises"]}
    assert all(pz["meta_adset_id"] == por_pais[pz["pais"]][pz["extra"]["plataforma"]] for pz in ex["piezas"])
    assert all(pz["estado"] == "pausado" and pz["meta_ad_id"] for pz in ex["piezas"])


def test_app_el_anuncio_y_el_creative_llevan_la_tienda_en_el_nombre(entorno_app):
    """Revisión final, ola 2 (2026-10-08): en Meta la misma pieza tiene un anuncio por tienda; el sufijo los
    distingue. Fuera de apps el nombre no cambia."""
    e = entorno_app
    e["lanzador"].lanzar("acme", e["eid"])
    ads = [kw["nombre"] for t, kw in e["meta"].llamadas if t == "ad"]
    creatives = [kw["nombre"] for t, kw in e["meta"].llamadas if t == "creative"]
    assert len(ads) == 4 and sum(n.endswith(" · iOS") for n in ads) == 2 and sum(n.endswith(" · Android") for n in ads) == 2
    assert sorted(creatives) == sorted(ads)
    assert all(" — CO · " in n or " — MX · " in n for n in ads)


def test_trafico_el_nombre_del_anuncio_no_lleva_tienda(entorno):
    entorno["lanzador"].lanzar("acme", entorno["eid"])
    ads = [kw["nombre"] for t, kw in entorno["meta"].llamadas if t == "ad"]
    assert ads and not any("iOS" in n or "Android" in n for n in ads)
    assert all(n.endswith((" — CO", " — MX")) for n in ads)


def test_app_el_anuncio_lleva_la_url_de_tienda_sin_utm(entorno_app):
    e = entorno_app
    e["lanzador"].lanzar("acme", e["eid"])
    creativos = [kw for tipo, kw in e["meta"].llamadas if tipo in ("creative", "creative_imagen")]
    links = [kw["link"] for kw in creativos]
    assert len(links) == 4 and all("utm_" not in l and l.startswith("https://") for l in links)
    assert any("play.google.com" in l for l in links) and any("apps.apple.com" in l for l in links)
    assert all(kw["cta_type"] == "INSTALL_MOBILE_APP" and kw["url_tags"] is None for kw in creativos)
    # la misma pieza en dos plataformas comparte la subida del video
    ex = e["ex"].obtener("acme", e["eid"])
    assert {(pz.get("extra") or {}).get("meta_video_id") for pz in ex["piezas"]} == {"vid_1"}


@pytest.mark.parametrize("moneda,presupuesto", [("CLP", 1003.0), ("USD", 10.05), ("COP", 20001.0)])
def test_app_reparto_nunca_sobrepasa_el_presupuesto_del_pais(entorno_app, moneda, presupuesto):
    e = entorno_app
    paises = [{**p, "presupuesto_dia": presupuesto} for p in e["ex"].obtener("acme", e["eid"])["paises"]]
    import db
    with db.conectar() as con:  # la moneda no se cambia por la API: se fija acá, como al crear
        con.execute(db.experimento.update().where(db.experimento.c.id == e["eid"]).values(moneda=moneda, paises=paises))
    e["lanzador"].lanzar("acme", e["eid"])
    adsets = [kw for tipo, kw in e["meta"].llamadas if tipo == "adset"]
    total = e["lanzador"].centavos(presupuesto, moneda)
    for pais in ("CO", "MX"):
        del_pais = [a["centavos"] for a in adsets if a["targeting"]["geo_locations"]["countries"] == [pais]]
        assert len(del_pais) == 2 and sum(del_pais) <= total
        assert del_pais == [total // 2, total // 2]


def test_app_pieza_sin_plataforma_valida_falla_antes_de_tocar_meta(entorno_app):
    e = entorno_app
    # La URL de Android ya no está: sus filas no tienen conjunto donde caer.
    e["ex"].actualizar_extra("acme", e["eid"], lambda extra: {**extra, "app": {"ios_url": URL_IOS}})
    with pytest.raises(ValueError, match="plataforma"):
        e["lanzador"].lanzar("acme", e["eid"])
    assert not e["meta"].llamadas
    assert e["ex"].obtener("acme", e["eid"])["estado"] != "lanzando"


def test_app_una_sola_plataforma_crea_la_mitad(entorno_app_android):
    e = entorno_app_android
    e["lanzador"].lanzar("acme", e["eid"])
    adsets = [kw for tipo, kw in e["meta"].llamadas if tipo == "adset"]
    assert len(adsets) == len(PAISES_APP) and all(a["targeting"]["user_os"] == ["Android"] for a in adsets)
    # una sola plataforma: el presupuesto del país entero
    assert all(a["centavos"] == e["lanzador"].centavos(PRESUPUESTO_PAIS, "COP") for a in adsets)
    links = [kw["link"] for tipo, kw in e["meta"].llamadas if tipo == "creative"]
    assert links == [URL_ANDROID, URL_ANDROID]


def test_app_sin_app_id_falla_antes_de_tocar_meta(entorno_app):
    e = entorno_app
    e["monkeypatch"].setattr(e["lanzador"].meta_conexion, "cargar_app_anunciada", lambda c: None)
    with pytest.raises(ValueError):
        e["lanzador"].lanzar("acme", e["eid"])
    assert not e["meta"].llamadas
    assert e["ex"].obtener("acme", e["eid"])["estado"] != "lanzando"


def test_app_usa_el_app_id_aprobado_al_crear_no_el_del_proyecto(base_temporal, monkeypatch):
    e = _entorno_app(base_temporal, monkeypatch, {"ios_url": URL_IOS, "android_url": URL_ANDROID, "app_id": "777"})
    # El proyecto ya anuncia otra app (12345, en _entorno_app): el experimento usa la suya.
    e["lanzador"].lanzar("acme", e["eid"])
    pos = {kw["promoted_object"]["application_id"] for t, kw in e["meta"].llamadas if t == "adset"}
    assert pos == {"777"}


def test_app_sin_app_id_propio_usa_el_del_proyecto(entorno_app):
    e = entorno_app
    e["lanzador"].lanzar("acme", e["eid"])
    pos = {kw["promoted_object"]["application_id"] for t, kw in e["meta"].llamadas if t == "adset"}
    assert pos == {"12345"}


def test_app_url_que_no_es_de_tienda_falla_antes_de_tocar_meta(entorno_app):
    e = entorno_app
    e["ex"].actualizar_extra("acme", e["eid"], lambda extra: {**extra, "app": {**extra["app"], "ios_url": "https://forja.co"}})
    with pytest.raises(ValueError):
        e["lanzador"].lanzar("acme", e["eid"])
    assert not e["meta"].llamadas


def test_app_retoma_sin_duplicar_conjuntos(entorno_app):
    e = entorno_app
    e["meta"].fallar_en = "ad"
    with pytest.raises(Exception):
        e["lanzador"].lanzar("acme", e["eid"])
    n = len([1 for t, _ in e["meta"].llamadas if t == "adset"])
    assert n == 2 * len(PAISES_APP)
    e["meta"].fallar_en = None
    e["lanzador"].lanzar("acme", e["eid"])
    assert len([1 for t, _ in e["meta"].llamadas if t == "adset"]) == n
    assert len([1 for t, _ in e["meta"].llamadas if t == "campaign"]) == 1
    ex = e["ex"].obtener("acme", e["eid"])
    assert ex["estado"] == "pausado" and all(pz["meta_ad_id"] for pz in ex["piezas"])


def test_app_retoma_con_un_solo_conjunto_creado(entorno_app):
    """Falla al crear el segundo conjunto: el reintento crea solo los que faltan."""
    e = entorno_app
    meta = e["meta"]
    original = meta._id
    def _falla_en_el_segundo_adset(tipo, **kw):
        if tipo == "adset" and sum(1 for t, _ in meta.llamadas if t == "adset") == 1:
            meta.llamadas.append((tipo, kw))
            raise RuntimeError("Meta falló en adset")
        return original(tipo, **kw)
    meta._id = _falla_en_el_segundo_adset
    campaign, adset, creative, ad, insights, auth = meta.modulos()
    e["monkeypatch"].setattr(e["lanzador"], "meta_adset", adset)
    with pytest.raises(RuntimeError):
        e["lanzador"].lanzar("acme", e["eid"])
    co = next(p for p in e["ex"].obtener("acme", e["eid"])["paises"] if p["pais"] == "CO")
    assert list(co["meta_adsets"]) == ["ios"]
    meta._id = original
    campaign, adset, creative, ad, insights, auth = meta.modulos()
    e["monkeypatch"].setattr(e["lanzador"], "meta_adset", adset)
    meta.llamadas.clear()
    e["lanzador"].lanzar("acme", e["eid"])
    nuevos = [kw for t, kw in meta.llamadas if t == "adset"]
    assert len(nuevos) == 3 and ("CO", "iOS") not in {(a["targeting"]["geo_locations"]["countries"][0],
                                                       a["targeting"]["user_os"][0]) for a in nuevos}


def test_app_no_agrega_piezas_nuevas_despues_de_lanzar(entorno_app):
    e = entorno_app
    e["lanzador"].lanzar("acme", e["eid"])
    with pytest.raises(ValueError):
        e["lanzador"].lanzar_piezas_nuevas("acme", e["eid"])


def _conjuntos_app(e):
    """{(país, plataforma): adset_id} de un experimento de apps ya lanzado."""
    return {(p["pais"], plat): i for p in e["ex"].obtener("acme", e["eid"])["paises"]
            for plat, i in (p.get("meta_adsets") or {}).items()}


def test_app_activar_experimento_activa_todos_los_conjuntos(entorno_app):
    e = entorno_app
    e["lanzador"].lanzar("acme", e["eid"])
    conjuntos = _conjuntos_app(e)
    assert len(conjuntos) == 4
    e["meta"].llamadas.clear()
    e["lanzador"].cambiar_estado("acme", e["eid"], "ACTIVE")
    activos = {kw["oid"] for t, kw in e["meta"].llamadas if t == "estado" and kw["status"] == "ACTIVE"}
    ex = e["ex"].obtener("acme", e["eid"])
    assert ex["meta_campaign_id"] in activos
    assert set(conjuntos.values()) <= activos
    assert all(p["estado"] == "activo" for p in ex["paises"])


def test_app_pausar_un_pais_pausa_sus_dos_conjuntos(entorno_app):
    e = entorno_app
    e["lanzador"].lanzar("acme", e["eid"])
    e["lanzador"].cambiar_estado("acme", e["eid"], "ACTIVE")
    conjuntos = _conjuntos_app(e)
    e["meta"].llamadas.clear()
    e["lanzador"].cambiar_estado("acme", e["eid"], "PAUSED", pais="CO")
    pausados = {kw["oid"] for t, kw in e["meta"].llamadas if t == "estado" and kw["status"] == "PAUSED"}
    assert {conjuntos[("CO", "ios")], conjuntos[("CO", "android")]} <= pausados
    assert not {conjuntos[("MX", "ios")], conjuntos[("MX", "android")]} & pausados


def test_app_activar_un_pais_activa_sus_dos_conjuntos(entorno_app):
    """Tras fusionar el centro de resultados (2026-10-08): «Activar país» comprobaba solo meta_adset_id y en apps
    decía «Ese país no tiene conjunto en Meta»; ahora mira los conjuntos por tienda (_adsets_de_pais)."""
    e = entorno_app
    e["lanzador"].lanzar("acme", e["eid"])
    conjuntos = _conjuntos_app(e)
    e["meta"].llamadas.clear()
    e["lanzador"].cambiar_estado("acme", e["eid"], "ACTIVE", pais="CO")
    activos = {kw["oid"] for t, kw in e["meta"].llamadas if t == "estado" and kw["status"] == "ACTIVE"}
    assert {conjuntos[("CO", "ios")], conjuntos[("CO", "android")]} <= activos
    assert not {conjuntos[("MX", "ios")], conjuntos[("MX", "android")]} & activos
    # Simétrica a pausar, más la campaña: el experimento no corría, así que la campaña se activa también
    # (si no, los conjuntos quedan ACTIVE y no entregan) y el experimento pasa a «corriendo».
    ex = e["ex"].obtener("acme", e["eid"])
    assert ex["meta_campaign_id"] in activos
    assert ex["estado"] == "corriendo"
    assert next(p for p in ex["paises"] if p["pais"] == "CO")["estado"] == "activo"


def test_app_presupuesto_del_pais_se_reparte_entre_sus_conjuntos(entorno_app):
    e = entorno_app
    lz = e["lanzador"]
    lz.lanzar("acme", e["eid"])
    conjuntos = _conjuntos_app(e)
    e["meta"].llamadas.clear()
    lz.cambiar_presupuesto_pais("acme", e["eid"], "CO", 20000)
    llamadas = [kw for t, kw in e["meta"].llamadas if t == "presupuesto"]
    assert {kw["oid"] for kw in llamadas} == {conjuntos[("CO", "ios")], conjuntos[("CO", "android")]}
    assert all(kw["centavos"] == lz.centavos(10000, "COP") for kw in llamadas) and len(llamadas) == 2
    co = next(p for p in e["ex"].obtener("acme", e["eid"])["paises"] if p["pais"] == "CO")
    assert co["presupuesto_dia"] == 20000


@pytest.mark.parametrize("moneda,presupuesto", [("CLP", 1003), ("USD", 10.05), ("COP", 20001)])
def test_app_cambiar_presupuesto_nunca_sobrepasa_el_del_pais(entorno_app, moneda, presupuesto):
    e = entorno_app
    lz = e["lanzador"]
    lz.lanzar("acme", e["eid"])
    import db
    with db.conectar() as con:  # la moneda no se cambia por la API: se fija acá, como al crear
        con.execute(db.experimento.update().where(db.experimento.c.id == e["eid"]).values(moneda=moneda))
    e["meta"].llamadas.clear()
    lz.cambiar_presupuesto_pais("acme", e["eid"], "CO", presupuesto)
    partes = [kw["centavos"] for t, kw in e["meta"].llamadas if t == "presupuesto"]
    total = lz.centavos(presupuesto, moneda)
    assert len(partes) == 2 and sum(partes) <= total and all(c == total // 2 for c in partes)


def _presupuesto_que_falla(e, fallar_en_llamada, fallar_restauracion=False):
    """Cambia actualizar_presupuesto del adset falso por uno que falla en la
    llamada número `fallar_en_llamada` (1 = la primera) y, si se pide,
    también en todas las siguientes (la restauración)."""
    import types as _t
    lz = e["lanzador"]
    vistas = []
    original = lz.meta_adset

    def _actualizar(oid, c, dry_run=False):
        vistas.append((oid, c))
        if len(vistas) == fallar_en_llamada or (fallar_restauracion and len(vistas) > fallar_en_llamada):
            raise RuntimeError("Meta dijo que no")
        return {"id": oid}

    e["monkeypatch"].setattr(lz, "meta_adset", _t.SimpleNamespace(crear_adset=original.crear_adset,
                                                                   actualizar_estado=original.actualizar_estado,
                                                                   actualizar_presupuesto=_actualizar))
    return vistas


def test_app_presupuesto_que_falla_a_medias_vuelve_y_no_cambia_lo_guardado(entorno_app):
    e = entorno_app
    lz = e["lanzador"]
    lz.lanzar("acme", e["eid"])
    conjuntos = _conjuntos_app(e)
    vistas = _presupuesto_que_falla(e, fallar_en_llamada=2)
    with pytest.raises(ValueError, match="se dejó como estaba"):
        lz.cambiar_presupuesto_pais("acme", e["eid"], "CO", 40000)
    antes = lz.centavos(PRESUPUESTO_PAIS, "COP") // 2
    nuevo = lz.centavos(40000, "COP") // 2
    primero = vistas[0][0]
    assert primero in {conjuntos[("CO", "ios")], conjuntos[("CO", "android")]}
    assert vistas[0] == (primero, nuevo)
    assert vistas[-1] == (primero, antes)  # el primer conjunto volvió a su valor
    ex = e["ex"].obtener("acme", e["eid"])
    co = next(p for p in ex["paises"] if p["pais"] == "CO")
    assert co["presupuesto_dia"] == PRESUPUESTO_PAIS
    evento = [ev for ev in e["ex"].eventos("acme", e["eid"]) if ev["tipo"] == "presupuesto"]
    assert evento and "se dejó como estaba" in evento[0]["mensaje"]  # eventos(): el más nuevo primero


def test_app_presupuesto_que_tampoco_se_restaura_avisa_que_quedo_a_medias(entorno_app):
    e = entorno_app
    lz = e["lanzador"]
    lz.lanzar("acme", e["eid"])
    _presupuesto_que_falla(e, fallar_en_llamada=2, fallar_restauracion=True)
    with pytest.raises(ValueError, match="quedó a medias"):
        lz.cambiar_presupuesto_pais("acme", e["eid"], "CO", 40000)
    co = next(p for p in e["ex"].obtener("acme", e["eid"])["paises"] if p["pais"] == "CO")
    assert co["presupuesto_dia"] == PRESUPUESTO_PAIS


def _presupuesto_que_falla_con(e, exc):
    import types as _t
    lz = e["lanzador"]
    original = lz.meta_adset

    def _actualizar(oid, c, dry_run=False):
        raise exc

    e["monkeypatch"].setattr(lz, "meta_adset", _t.SimpleNamespace(crear_adset=original.crear_adset,
                                                                   actualizar_estado=original.actualizar_estado,
                                                                   actualizar_presupuesto=_actualizar))


def test_presupuesto_con_un_conjunto_propaga_el_error_original_de_meta(entorno):
    """Revisión final, ola 2 (2026-10-08): con UN conjunto el error de Meta sale tal cual (sin envolverlo en el
    mensaje de «todos los conjuntos»), así el aviso o la propuesta pendiente conserva el motivo real."""
    lz = entorno["lanzador"]
    lz.lanzar("acme", entorno["eid"])
    original = RuntimeError("Meta Ads (adset) respondió 400: presupuesto muy bajo")
    _presupuesto_que_falla_con(entorno, original)
    with pytest.raises(RuntimeError) as info:
        lz.cambiar_presupuesto_pais("acme", entorno["eid"], "CO", 40000)
    assert info.value is original


def test_app_presupuesto_con_un_conjunto_propaga_el_error_original(entorno_app_android):
    e = entorno_app_android
    lz = e["lanzador"]
    lz.lanzar("acme", e["eid"])
    original = RuntimeError("Meta Ads (adset) respondió 400: presupuesto muy bajo")
    _presupuesto_que_falla_con(e, original)
    with pytest.raises(RuntimeError) as info:
        lz.cambiar_presupuesto_pais("acme", e["eid"], "CO", 40000)
    assert info.value is original


def test_app_presupuesto_con_dos_conjuntos_dice_el_motivo_sin_token(entorno_app):
    e = entorno_app
    lz = e["lanzador"]
    lz.lanzar("acme", e["eid"])
    _presupuesto_que_falla_con(e, RuntimeError(
        "presupuesto muy bajo access_token=EAABsecreto123"))  # llave-de-prueba
    with pytest.raises(ValueError) as info:
        lz.cambiar_presupuesto_pais("acme", e["eid"], "CO", 40000)
    texto = str(info.value)
    assert "se dejó como estaba" in texto and "presupuesto muy bajo" in texto
    assert "EAABsecreto123" not in texto  # llave-de-prueba
    evento = [ev for ev in e["ex"].eventos("acme", e["eid"]) if ev["tipo"] == "presupuesto"][0]
    assert "presupuesto muy bajo" in evento["mensaje"]
    assert "EAABsecreto123" not in str(evento)  # llave-de-prueba


def test_app_escalar_pais_reparte_el_nuevo_total(entorno_app):
    e = entorno_app
    lz = e["lanzador"]
    lz.lanzar("acme", e["eid"])
    e["meta"].llamadas.clear()
    nuevo = lz.escalar_pais("acme", e["eid"], "CO", 50)
    assert nuevo == PRESUPUESTO_PAIS * 1.5
    partes = [kw["centavos"] for t, kw in e["meta"].llamadas if t == "presupuesto"]
    assert len(partes) == 2 and sum(partes) == lz.centavos(nuevo, "COP")
    co = next(p for p in e["ex"].obtener("acme", e["eid"])["paises"] if p["pais"] == "CO")
    assert co["presupuesto_dia"] == nuevo


def test_app_activar_pieza_android_reactiva_solo_su_conjunto(entorno_app):
    e = entorno_app
    lz = e["lanzador"]
    lz.lanzar("acme", e["eid"])
    conjuntos = _conjuntos_app(e)
    ex = e["ex"].obtener("acme", e["eid"])
    android = next(pz for pz in ex["piezas"] if pz["pais"] == "CO" and (pz.get("extra") or {}).get("plataforma") == "android")
    assert android["meta_adset_id"] == conjuntos[("CO", "android")]
    e["meta"].llamadas.clear()
    lz.activar_pieza("acme", android["id"])
    activos = {kw["oid"] for t, kw in e["meta"].llamadas if t == "estado" and kw["status"] == "ACTIVE"}
    assert conjuntos[("CO", "android")] in activos and conjuntos[("CO", "ios")] not in activos
    # La pieza iOS de CO, activada después (el país ya «activo»), reactiva SU conjunto.
    ios = next(pz for pz in ex["piezas"] if pz["pais"] == "CO" and (pz.get("extra") or {}).get("plataforma") == "ios")
    e["meta"].llamadas.clear()
    lz.activar_pieza("acme", ios["id"])
    activos = {kw["oid"] for t, kw in e["meta"].llamadas if t == "estado" and kw["status"] == "ACTIVE"}
    assert conjuntos[("CO", "ios")] in activos and conjuntos[("CO", "android")] not in activos


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
    e = ex.obtener("acme", eid)
    # Bloque 5: el link de cada anuncio lleva el id de la experimento_pieza (uno por país), no el de la pieza
    assert sorted(c["link"].rsplit("utm_content=", 1)[1] for c in creativos) == sorted(str(p["id"]) for p in e["piezas"])
    assert e["estado"] == "pausado" and e["meta_campaign_id"] == "campaign_1"
    assert {p["pais"]: p["meta_adset_id"] for p in e["paises"]} == {"CO": "adset_2", "MX": "adset_3"}
    assert all(p["estado"] == "pausado" and p["meta_ad_id"] for p in e["piezas"])
    assert etapas == [nombre for nombre, _peso in lz.ETAPAS_LANZAR]
    assert any(ev["tipo"] == "lanzamiento" for ev in e["eventos"])


def test_lanzar_con_imagen_usa_creative_de_imagen(entorno):
    import db
    from tests.test_experimentos_db import _pieza_imagen
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    img = _pieza_imagen(db)
    ex.agregar_pieza("acme", eid, img, "CO")
    lz.lanzar("acme", eid)
    tipos = [t for t, _ in meta.llamadas]
    assert tipos.count("creative_imagen") == 1 and tipos.count("creative") == 3 and tipos.count("ad") == 4
    kw = next(kw for t, kw in meta.llamadas if t == "creative_imagen")
    assert kw["imagen_url"] == "https://r2/i.png" and "utm_content=" in kw["link"]
    e = ex.obtener("acme", eid)
    pz = next(p for p in e["piezas"] if p["pieza_id"] == img)
    assert pz["estado"] == "pausado" and pz["meta_ad_id"] and (pz.get("extra") or {}).get("meta_video_id") is None


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
    # ad_9: campaign_1, adset_2/3, y por cada pieza creative+ad (el clon
    # tiene un creative por país desde Bloque 5: utm_content=ep id).
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


def _tw_conectado(lz, monkeypatch, moneda="COP"):
    """Triple Whale conectado (sin tocar la base) y la sincronización previa
    reemplazada por un contador: los tests siembran la copia a mano."""
    config = {"dominio_tienda": "acme.myshopify.com", "modelo_atribucion": "Triple Attribution",
              "ventana_atribucion": "lifetime", "moneda": moneda}
    monkeypatch.setattr(lz.triple_whale_tiendas, "obtener", lambda cliente: config)
    llamadas = []
    monkeypatch.setattr(lz.tw_sync, "sincronizar_si_hace_falta", lambda cliente: llamadas.append(cliente))
    return llamadas


def _sembrar_pixel(ad_id, dias, otros=()):
    """dias: [(fecha, pedidos, ingresos)] del Triple Pixel para ese anuncio de
    Meta; otros: [(ad_id, fecha, pedidos, ingresos)] de otros anuncios. Una
    sola llamada: reemplazar_anuncios_pixel pisa todo el rango."""
    from triple_whale import datos as tw_datos
    filas = [(ad_id, f, p, i) for f, p, i in dias] + list(otros)
    fechas = [f for _, f, _, _ in filas]
    tw_datos.reemplazar_anuncios_pixel("acme", min(fechas), max(fechas), [
        {"canal": "facebook-ads", "ad_id": a, "fecha": f, "pedidos": p, "ingresos": i} for a, f, p, i in filas])


def test_refrescar_con_triple_whale_toma_trafico_de_meta_y_ventas_del_pixel(entorno, monkeypatch):
    """Spec 2026-09-28 §7: impresiones, gasto y estado siguen saliendo de
    Meta; compras e ingresos, de lo que el Triple Pixel atribuyó a ESE
    anuncio desde que se creó la pieza (sumado: snapshot acumulado). Antes se
    usaban las `conversions` de ads_table, que son las que reporta Meta."""
    ex, lz = entorno["ex"], entorno["lanzador"]
    eid = entorno["eid"]
    ex.actualizar("acme", eid, atribucion="triple_whale")
    lz.lanzar("acme", eid)
    pieza = ex.obtener("acme", eid)["piezas"][0]
    ad_id, creado = pieza["meta_ad_id"], pieza["creado_en"][:10]
    llamadas = _tw_conectado(lz, monkeypatch)
    _sembrar_pixel(ad_id, [(creado, 1.0, 80.0), ("2099-01-01", 1.4, 40.0), ("2000-01-01", 50.0, 9999.0)],
                   otros=[("otro_anuncio", creado, 99.0, 99999.0)])

    assert lz.refrescar("acme", eid) == 3
    assert llamadas == ["acme"]   # una sola puesta al día por experimento, no por pieza
    m = ex.obtener("acme", eid)["piezas"][0]["metricas"]
    assert m["impresiones"] == 100 and m["gasto"] == 2.0 and m["estado_meta_texto"] == "Activo"
    # 1 + 1,4 pedidos (modelo lineal) = 2; lo de antes de crear la pieza no cuenta.
    assert m["compras"] == 2 and m["ingresos"] == 120.0
    assert m["roas"] == round(120.0 / 2.0, 4) and m["cpa"] == 1.0
    assert m["fuente_ventas"] == "triple_whale"
    # Una pieza que Triple Whale no tiene se queda con lo de Meta.
    otra = ex.obtener("acme", eid)["piezas"][1]["metricas"]
    assert otra["compras"] == 0 and otra["fuente_ventas"] == "ninguna"


def test_lanzar_con_triple_whale_pone_sus_parametros_de_url_en_cada_creative(entorno, monkeypatch):
    """Spec 2026-09-28 §10: Triple Whale atribuye por tw_source/tw_adid, que
    Meta resuelve en los Parámetros de URL (url_tags) del creative. Van solo
    si el proyecto tiene Triple Whale conectado, y el link sigue llevando el
    utm_content de la pieza (la atribución por tienda no se pierde)."""
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    monkeypatch.setattr(lz.triple_whale_tiendas, "obtener", lambda cliente: {"dominio_tienda": "acme.myshopify.com"})
    lz.lanzar("acme", eid)
    creativos = [kw for t, kw in meta.llamadas if t.startswith("creative")]
    assert len(creativos) == 3
    assert {kw["url_tags"] for kw in creativos} == {"tw_source={{site_source_name}}&tw_adid={{ad.id}}"}
    assert all("utm_content=" in kw["link"] for kw in creativos)


def test_lanzar_sin_triple_whale_no_manda_parametros_de_url(entorno):
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    lz.lanzar("acme", eid)
    assert {kw["url_tags"] for t, kw in meta.llamadas if t.startswith("creative")} == {None}


def test_refrescar_con_triple_whale_distingue_sin_ventas_de_sin_dato(entorno, monkeypatch):
    """Meta reporta 3 compras. Si el Pixel de Triple Whale respondió para ese
    anuncio sin atribuirle nada, las compras son 0; si el Pixel no respondió
    (solo hay filas de canal), se queda lo de Meta."""
    from triple_whale import datos as tw_datos
    ex, lz = entorno["ex"], entorno["lanzador"]
    eid = entorno["eid"]
    ex.actualizar("acme", eid, atribucion="triple_whale")
    lz.lanzar("acme", eid)
    piezas = ex.obtener("acme", eid)["piezas"]
    hoy = piezas[0]["creado_en"][:10]
    _tw_conectado(lz, monkeypatch)
    monkeypatch.setattr(lz.meta_insights, "obtener_resultados", lambda ad_id, objetivo=None: {
        "impresiones": 100, "gasto_usd": 30.0, "compras": 3, "ingresos": 90.0, "roas": 3.0,
        "estado_meta": "ACTIVE", "estado_meta_texto": "Activo"})
    canal = [{"canal": "facebook-ads", "ad_id": p["meta_ad_id"], "fecha": hoy, "gasto": 30} for p in piezas[:2]]
    tw_datos.reemplazar_anuncios_canal("acme", hoy, hoy, canal)
    # El Pixel respondió para ese día, con pedidos solo para la primera pieza.
    tw_datos.reemplazar_anuncios_pixel("acme", hoy, hoy, [
        {"canal": "facebook-ads", "ad_id": piezas[0]["meta_ad_id"], "fecha": hoy, "pedidos": 1, "ingresos": 45}])
    lz.refrescar("acme", eid)
    m = [p["metricas"] for p in ex.obtener("acme", eid)["piezas"]]
    assert (m[0]["compras"], m[0]["ingresos"], m[0]["fuente_ventas"]) == (1, 45.0, "triple_whale")
    assert (m[1]["compras"], m[1]["ingresos"], m[1]["fuente_ventas"]) == (0, 0.0, "ninguna")
    # Sin respuesta del Pixel (una fila de canal nueva, sin consulta del Pixel): queda lo de Meta.
    manana = "2099-12-31"
    tw_datos.reemplazar_anuncios_canal("acme", manana, manana, [
        {"canal": "facebook-ads", "ad_id": piezas[2]["meta_ad_id"], "fecha": manana, "gasto": 1}])
    lz.refrescar("acme", eid)
    tercera = ex.obtener("acme", eid)["piezas"][2]["metricas"]
    assert tercera["compras"] == 3 and tercera["fuente_ventas"] == "meta"


def test_refrescar_con_triple_whale_sin_conectar_cae_a_meta(entorno, monkeypatch):
    """Sin Triple Whale conectado no se intenta sincronizar y el snapshot es
    exactamente el de Meta."""
    ex, lz = entorno["ex"], entorno["lanzador"]
    eid = entorno["eid"]
    ex.actualizar("acme", eid, atribucion="triple_whale")
    lz.lanzar("acme", eid)
    monkeypatch.setattr(lz.tw_sync, "sincronizar_si_hace_falta",
                        lambda cliente: (_ for _ in ()).throw(AssertionError("no debía sincronizar")))
    assert lz.refrescar("acme", eid) == 3
    m = ex.obtener("acme", eid)["piezas"][0]["metricas"]
    assert m["impresiones"] == 100 and m["gasto"] == 2.0 and m["fuente_ventas"] == "ninguna"


def test_refrescar_con_triple_whale_error_de_sync_registra_evento_y_usa_la_copia(entorno, monkeypatch):
    ex, lz = entorno["ex"], entorno["lanzador"]
    eid = entorno["eid"]
    ex.actualizar("acme", eid, atribucion="triple_whale")
    lz.lanzar("acme", eid)
    pieza = ex.obtener("acme", eid)["piezas"][0]
    _tw_conectado(lz, monkeypatch)

    def _revienta(cliente):
        raise lz.triple_whale.ErrorTripleWhale("límite de tasa x-api-key=tw_secreto")
    monkeypatch.setattr(lz.tw_sync, "sincronizar_si_hace_falta", _revienta)
    _sembrar_pixel(pieza["meta_ad_id"], [(pieza["creado_en"][:10], 3.0, 30.0)])

    assert lz.refrescar("acme", eid) == 3
    eventos = ex.eventos("acme", eid)
    assert any("Triple Whale" in (e.get("mensaje") or "") for e in eventos)
    assert ex.obtener("acme", eid)["piezas"][0]["metricas"]["compras"] == 3


def test_refrescar_con_triple_whale_en_otra_moneda_deja_roas_en_cero(entorno, monkeypatch):
    """Ingresos de Triple Whale en USD y cuenta en COP: el ROAS no es
    comparable (queda 0 y un aviso), el CPA sí."""
    ex, lz = entorno["ex"], entorno["lanzador"]
    eid = entorno["eid"]
    ex.actualizar("acme", eid, atribucion="triple_whale")
    lz.lanzar("acme", eid)
    pieza = ex.obtener("acme", eid)["piezas"][0]
    _tw_conectado(lz, monkeypatch, moneda="USD")
    _sembrar_pixel(pieza["meta_ad_id"], [(pieza["creado_en"][:10], 2.0, 50.0)])
    lz.refrescar("acme", eid)
    m = ex.obtener("acme", eid)["piezas"][0]["metricas"]
    assert m["compras"] == 2 and m["roas"] == 0.0 and m["cpa"] == 1.0
    assert ex.obtener("acme", eid)["extra"].get("aviso_moneda") == "USD"


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


def test_lanzar_mismo_clon_en_dos_paises_comparte_video_no_creative(entorno):
    """M4 + Bloque 5: el fixture ya agrega el mismo clon a CO y a MX — la
    subida del video (hasta 180s bajo _LOCK) se hace una sola vez, pero el
    creative es por país: el link lleva utm_content=<experimento_pieza.id>,
    distinto en cada uno, para que las ventas de la tienda caigan en el
    anuncio que las generó."""
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    llamadas_subir = []
    original = lz.meta_creative.subir_video

    def contando(*a, **k):
        llamadas_subir.append(1)
        return original(*a, **k)

    entorno["monkeypatch"].setattr(lz.meta_creative, "subir_video", contando)
    lz.lanzar("acme", eid)
    tipos = [t for t, _ in meta.llamadas]
    assert tipos.count("creative") == 3  # f_co + un creative por país del clon (CO y MX)
    assert len(llamadas_subir) == 2       # f_co sube su video, el clon sube el suyo una sola vez
    e = ex.obtener("acme", eid)
    clones = [p for p in e["piezas"] if p["tipo"] == "clon"]
    assert len(clones) == 2
    assert clones[0]["meta_creative_id"] != clones[1]["meta_creative_id"]
    assert clones[0]["extra"].get("meta_video_id") == clones[1]["extra"].get("meta_video_id") == "vid_1"
    links = {kw["link"] for t, kw in meta.llamadas if t == "creative"}
    assert all(any(link.endswith(f"utm_content={p['id']}") for link in links) for p in clones)


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


def test_lanzar_piezas_nuevas_acepta_experimento_decidido(entorno, base_temporal):
    """Bloque 4 (I-1 del review de decidir): un rescate aprobado después de
    que el experimento ya pasó a 'decidido' tiene que poder crear su anuncio
    en Meta — si no, el escalón queda producido (créditos gastados) pero
    nunca entra a Meta."""
    ex, lz, eid = entorno["ex"], entorno["lanzador"], entorno["eid"]
    lz.lanzar("acme", eid)
    ex.actualizar("acme", eid, estado="decidido")
    nueva = _pieza(base_temporal, tipo="final", legado="cf_1__es_CO__v4", pais="CO")
    ex.agregar_pieza("acme", eid, nueva, "CO")
    assert lz.lanzar_piezas_nuevas("acme", eid) == 1
    p = [p for p in ex.piezas("acme", eid) if p["pieza_id"] == nueva][0]
    assert p["estado"] == "pausado" and p["meta_ad_id"]


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


def test_activar_pieza_acepta_experimento_decidido(entorno):
    """Bloque 4 (I-1 del review de decidir): activar una pieza rescatada con
    el experimento ya 'decidido' no debe fallar, y lo devuelve a 'corriendo'
    para que exp_decidir_todos vuelva a evaluarlo (si no, la pieza rescatada
    nunca recibe veredicto)."""
    ex, lz, eid = entorno["ex"], entorno["lanzador"], entorno["eid"]
    lz.lanzar("acme", eid)
    lz.cambiar_estado("acme", eid, "ACTIVE")
    ep = ex.piezas("acme", eid)[0]
    lz.pausar_pieza("acme", ep["id"])
    ex.actualizar("acme", eid, estado="decidido")
    lz.activar_pieza("acme", ep["id"])
    assert ex.piezas("acme", eid)[0]["estado"] == "activo"
    assert ex.obtener("acme", eid)["estado"] == "corriendo"


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
    corrida de lanzar_piezas_nuevas deben compartir el cache de video —
    antes cada llamada a _crear_anuncios recibía un cache vacío propio y
    repetía subir_video para la segunda. El creative sí es uno por país
    (Bloque 5: utm_content por experimento_pieza)."""
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
    assert tipos.count("creative") == 2
    assert len(llamadas_subir) == 1
    nuevas = [p for p in ex.piezas("acme", eid) if p["pieza_id"] == clon_nuevo]
    assert len(nuevas) == 2
    assert all(p["meta_ad_id"] for p in nuevas)
    assert nuevas[0]["meta_creative_id"] != nuevas[1]["meta_creative_id"]
    assert nuevas[0]["extra"]["meta_video_id"] == nuevas[1]["extra"]["meta_video_id"]


def test_lanzar_piezas_nuevas_reusa_video_de_pieza_vieja_con_mismo_pieza_id(entorno, base_temporal):
    """Fix round 1 (Important #1), segundo caso: una pieza nueva cuyo
    pieza_id YA subió video en otra pieza ya lanzada (de una corrida
    anterior, en otro país) no debe volver a subirlo — sí crea su propio
    creative (link con su ep id) y su ad. Experimento aparte con 3 países
    (CO, MX, BR) para que BR ya tenga su conjunto en Meta antes de agregarle
    la pieza reusada."""
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
    assert tipos.count("creative") == 1
    assert len(llamadas_subir) == 0
    piezas = ex.piezas("acme", eid)
    br_clon = [p for p in piezas if p["pieza_id"] == clon and p["pais"] == "BR"][0]
    co_clon = [p for p in piezas if p["pieza_id"] == clon and p["pais"] == "CO"][0]
    assert br_clon["meta_ad_id"] and br_clon["meta_creative_id"] != co_clon["meta_creative_id"]
    assert br_clon["extra"]["meta_video_id"] == co_clon["extra"]["meta_video_id"]
    assert [kw for t, kw in meta.llamadas if t == "creative"][0]["link"].endswith(f"utm_content={br_clon['id']}")


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


def test_refrescar_avisa_rechazo_de_meta_solo_al_cambiar(entorno):
    ex, lz, eid = entorno["ex"], entorno["lanzador"], entorno["eid"]
    avisos = []
    entorno["monkeypatch"].setattr(lz.notificaciones, "avisar", lambda c, tipo, asunto, cuerpo: (avisos.append((tipo, asunto, cuerpo)), True)[1])
    lz.lanzar("acme", eid)
    lz.refrescar("acme", eid)   # ACTIVE: nada
    assert avisos == []
    base = lz.meta_insights.obtener_resultados("x")
    lz.meta_insights.obtener_resultados = lambda ad_id, objetivo=None: {**base, "estado_meta": "DISAPPROVED", "motivo_rechazo": "texto engañoso"}
    lz.refrescar("acme", eid)
    assert [a[0] for a in avisos] == ["rechazo_meta"] * 3 and "texto engañoso" in avisos[0][2]
    assert sum(1 for e in ex.eventos("acme", eid) if e["tipo"] == "rechazo_meta") == 3
    lz.refrescar("acme", eid)   # sigue DISAPPROVED: no repite el aviso
    assert len(avisos) == 3
    assert all(p["estado_meta"] == "DISAPPROVED" for p in ex.obtener("acme", eid)["piezas"])


def test_lanzar_con_error_avisa(entorno):
    lz, eid = entorno["lanzador"], entorno["eid"]
    avisos = []
    entorno["monkeypatch"].setattr(lz.notificaciones, "avisar", lambda c, tipo, asunto, cuerpo: (avisos.append((tipo, asunto, cuerpo)), True)[1])
    entorno["meta"].fallar_en = "adset"
    with pytest.raises(RuntimeError):
        lz.lanzar("acme", eid)
    assert [a[0] for a in avisos] == ["error_lanzamiento"] and "Meta falló en adset" in avisos[0][2]


def test_cambiar_estado_active_no_reactiva_piezas_retiradas_por_el_decisor(entorno):
    """I-1 (review final): al reactivar el experimento entero, las piezas con
    veredicto perdedor/inconcluso o marcadas `archivado`/`rescatado_en_escalon`
    se quedan en pausa en Meta; el evento dice cuáles se saltaron."""
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    lz.lanzar("acme", eid)
    p1, p2, p3 = [p["id"] for p in ex.obtener("acme", eid)["piezas"]]
    ex.actualizar_pieza("acme", p1, veredicto="perdedor")
    ex.marcar_pieza("acme", p1, rescatado_en_escalon=1)
    ex.marcar_pieza("acme", p2, archivado=True)
    meta.llamadas.clear()
    lz.cambiar_estado("acme", eid, "ACTIVE")
    ads_activados = [kw["oid"] for t, kw in meta.llamadas if t == "estado" and kw["oid"].startswith("ad_")]
    e = ex.obtener("acme", eid)
    estados = {p["id"]: p["estado"] for p in e["piezas"]}
    assert estados == {p1: "pausado", p2: "pausado", p3: "activo"}
    assert ads_activados == [next(p["meta_ad_id"] for p in e["piezas"] if p["id"] == p3)]
    assert e["estado"] == "corriendo"
    ev = next(v for v in e["eventos"] if v["tipo"] == "estado" and "Activado" in v["mensaje"])
    assert "Siguen en pausa" in ev["mensaje"] and sorted(ev["datos"]["saltadas"]) == sorted([p1, p2])
    # Inconcluso también cuenta como retirada; pausar sí toca todas.
    ex.actualizar_pieza("acme", p3, veredicto="inconcluso")
    lz.cambiar_estado("acme", eid, "PAUSED")
    meta.llamadas.clear()
    lz.cambiar_estado("acme", eid, "ACTIVE")
    assert not any(kw["oid"].startswith("ad_") for t, kw in meta.llamadas if t == "estado")
    assert all(p["estado"] == "pausado" for p in ex.obtener("acme", eid)["piezas"])
    assert lz.pieza_retirada({"veredicto": "ganador", "extra": {}}) is False


def test_activar_pieza_y_lanzar_escriben_extra_sin_pisar_lo_que_llego_entre_medio(entorno):
    """Menor (review final): `activado_en` y `meta_video_id` de la pieza van
    por `marcar_pieza` (RMW bajo lock), no por `actualizar_pieza(extra=foto
    vieja)`: una bandera escrita mientras se hablaba con Meta sobrevive."""
    ex, lz, eid, mp = entorno["ex"], entorno["lanzador"], entorno["eid"], entorno["monkeypatch"]
    lz.lanzar("acme", eid)
    ep = ex.obtener("acme", eid)["piezas"][0]["id"]
    assert ex.piezas("acme", eid)[0]["extra"]["meta_video_id"] == "vid_1"
    original = lz._con_credenciales

    def _meta(cliente, fn):
        ex.marcar_pieza("acme", ep, rescatado_en_escalon=1)   # el worker escribe mientras Meta responde
        return original(cliente, fn)

    mp.setattr(lz, "_con_credenciales", _meta)
    lz.activar_pieza("acme", ep)
    extra = next(p for p in ex.piezas("acme", eid) if p["id"] == ep)["extra"]
    assert extra["activado_en"] and extra["rescatado_en_escalon"] == 1 and extra["meta_video_id"] == "vid_1"


# Meta rechaza crear el anuncio cuando la app del proyecto sigue en modo
# Desarrollo (subcode 1885183): la persona debe pasarla a Live, no hay nada
# que el código pueda hacer. El experimento queda en `error` con un mensaje
# que dice eso en claro (no el JSON crudo), el evento conserva el detalle
# crudo para diagnosticar, y el reintento retoma sin duplicar.
_ERROR_DEV_MODE = ('Meta Ads (act_1/adcreatives) respondió 400: {"error":{"message":"Invalid parameter",'
                   '"type":"OAuthException","code":100,"error_subcode":1885183,"is_transient":false,'
                   '"error_user_title":"La publicaci\\u00f3n con contenido publicitario se cre\\u00f3 con una app '
                   'que se encuentra en modo de desarrollo","error_user_msg":"Debe estar en modo p\\u00fablico '
                   'para crear este anuncio.","fbtrace_id":"A_x"}}')


def test_lanzar_traduce_app_en_modo_desarrollo(entorno):
    ex, lz, eid = entorno["ex"], entorno["lanzador"], entorno["eid"]

    def rechaza(*a, **k):
        raise RuntimeError(_ERROR_DEV_MODE)

    entorno["monkeypatch"].setattr(lz.meta_creative, "crear_creative_video", rechaza)
    avisos = []
    entorno["monkeypatch"].setattr(lz.notificaciones, "avisar", lambda c, tipo, asunto, cuerpo: (avisos.append(cuerpo), True)[1])
    with pytest.raises(RuntimeError):
        lz.lanzar("acme", eid)
    e = ex.obtener("acme", eid)
    assert e["estado"] == "error" and e["meta_campaign_id"]  # el reintento retoma desde la campaña ya creada
    assert "modo Desarrollo" in e["error"] and "Live" in e["error"] and "1885183" in e["error"]
    assert "error_subcode" not in e["error"]  # nada de JSON crudo en pantalla
    assert "modo Desarrollo" in avisos[0]
    ev = next(ev for ev in e["eventos"] if ev["tipo"] == "error")
    assert "modo Desarrollo" in ev["mensaje"] and "error_subcode" in ev["datos"]["detalle"]


def test_traducir_error_meta():
    lz = __import__("lanzador")
    assert "Creatv" in lz.traducir_error_meta(_ERROR_DEV_MODE, modo="agencia")
    assert "developers.facebook.com" in lz.traducir_error_meta(_ERROR_DEV_MODE, modo="propia")
    # Lo que no se reconoce pasa tal cual (los demás tests cuentan con "Meta falló en …").
    assert lz.traducir_error_meta("Meta falló en creative") == "Meta falló en creative"


def test_url_tags_solo_viaja_cuando_hay_triple_whale(monkeypatch):
    """Un servidor con el submódulo meta_ads sin actualizar (sin el argumento
    `url_tags`) sigue creando anuncios mientras ningún proyecto tenga Triple
    Whale: el argumento solo se pasa cuando hay parámetros."""
    import triple_whale_tiendas
    monkeypatch.setattr(triple_whale_tiendas, "url_tags", lambda cliente: None)
    assert triple_whale_tiendas.kw_url_tags("acme") == {}
    monkeypatch.setattr(triple_whale_tiendas, "url_tags", lambda cliente: "tw_source=x&tw_adid=y")
    assert triple_whale_tiendas.kw_url_tags("acme") == {"url_tags": "tw_source=x&tw_adid=y"}


def test_exp_refrescar_sigue_aunque_el_detalle_reviente(entorno, monkeypatch, caplog):
    import meta_detalle
    import tareas
    from tareas import experimentos as _t_exp  # noqa: F401 — registra las tareas de experimentos
    ex, lz, eid = entorno["ex"], entorno["lanzador"], entorno["eid"]
    lz.lanzar("acme", eid)
    llamado = []

    def explota(cliente, experimento_id, hoy=None):
        llamado.append(experimento_id)
        raise RuntimeError("no debería pasar, pero si pasa no tumba nada: access_token=TOKEN-SECRETO")

    monkeypatch.setattr(meta_detalle, "refrescar_detalle", explota)
    with caplog.at_level("WARNING", logger="creatv.tareas.experimentos"):
        texto = tareas.REGISTRO["exp_refrescar"]({"payload": {"cliente": "acme", "experimento_id": eid}, "job_id": "j"})
    assert llamado == [eid] and "3" in texto
    # el log (sin traza completa) lleva el error sin token
    avisos = [r for r in caplog.records if r.name == "creatv.tareas.experimentos"]
    assert avisos and all(r.levelname == "WARNING" and r.exc_info is None for r in avisos)
    assert "TOKEN-SECRETO" not in caplog.text and "no debería pasar" in caplog.text
    assert ex.obtener("acme", eid)["gasto_acumulado"] == 6.0


@pytest.mark.parametrize('via', ['experimento', 'pais', 'pieza'])
def test_pnd113_fin_desde_primera_activacion_sin_extender_al_reanudar(entorno, monkeypatch, via):
    import time
    lz, ex, eid, meta = entorno['lanzador'], entorno['ex'], entorno['eid'], entorno['meta']
    lz.lanzar('acme', eid)
    ahora = 1800000000
    monkeypatch.setattr(time, 'time', lambda: ahora)
    def llamar(metodo, oid, payload):
        return meta._id('fin', metodo=metodo, oid=oid, payload=payload)
    monkeypatch.setattr(lz.meta_auth, 'llamar', llamar, raising=False)
    def activar():
        if via == 'pieza':
            lz.activar_pieza('acme', ex.obtener('acme', eid)['piezas'][0]['id'])
        else:
            lz.cambiar_estado('acme', eid, 'ACTIVE', pais='CO' if via == 'pais' else None)
    antes = ex.obtener('acme', eid)
    meta.llamadas.clear()
    activar()
    fines = [kw for t, kw in meta.llamadas if t == 'fin']
    assert len(fines) == 2
    assert all(kw['payload'] == {'end_time': ahora + 7 * 86400} for kw in fines)
    assert [t for t, _ in meta.llamadas][:2] == ['fin', 'fin']
    assert ex.obtener('acme', eid)['tope_total'] == antes['tope_total']
    lz.cambiar_estado('acme', eid, 'PAUSED')
    meta.llamadas.clear()
    ahora += 86400
    activar()
    assert not any(t == 'fin' for t, _ in meta.llamadas)


@pytest.mark.parametrize('via', ['experimento', 'pais', 'pieza'])
def test_pnd113_apps_fin_en_cada_conjunto_de_tienda_sin_extender_al_reanudar(entorno_app, monkeypatch, via):
    """Prueba de mutación (2026-10-08): el fin de la primera activación se mandaba solo a `meta_adset_id`, que en apps
    está vacío; los conjuntos de cada tienda (`meta_adsets`) quedaban sin `end_time` y gastaban sin plazo."""
    import time
    e = entorno_app
    lz, ex, eid, meta = e['lanzador'], e['ex'], e['eid'], e['meta']
    lz.lanzar('acme', eid)
    conjuntos = _conjuntos_app(e)
    assert len(conjuntos) == 4
    ahora = 1800000000
    monkeypatch.setattr(time, 'time', lambda: ahora)

    def llamar(metodo, oid, payload):
        return meta._id('fin', metodo=metodo, oid=oid, payload=payload)
    monkeypatch.setattr(lz.meta_auth, 'llamar', llamar, raising=False)

    def activar():
        if via == 'pieza':
            lz.activar_pieza('acme', ex.obtener('acme', eid)['piezas'][0]['id'])
        else:
            lz.cambiar_estado('acme', eid, 'ACTIVE', pais='CO' if via == 'pais' else None)
    meta.llamadas.clear()
    activar()
    fines = [kw for t, kw in meta.llamadas if t == 'fin']
    # un end_time por cada conjunto de tienda de TODOS los países, antes de activar nada
    assert sorted(kw['oid'] for kw in fines) == sorted(conjuntos.values())
    assert all(kw['payload'] == {'end_time': ahora + 7 * 86400} for kw in fines)
    assert [t for t, _ in meta.llamadas][:4] == ['fin'] * 4
    lz.cambiar_estado('acme', eid, 'PAUSED')
    meta.llamadas.clear()
    ahora += 86400
    activar()
    assert not any(t == 'fin' for t, _ in meta.llamadas)


def test_pnd113_fallo_fecha_no_activa_y_reintento_conserva_fin(entorno, monkeypatch):
    lz, ex, eid, meta = entorno['lanzador'], entorno['ex'], entorno['eid'], entorno['meta']
    lz.lanzar('acme', eid)
    meta.llamadas.clear()
    vistos = []
    def fallar(metodo, oid, payload):
        vistos.append(payload)
        raise RuntimeError('fecha rechazada')
    monkeypatch.setattr(lz.meta_auth, 'llamar', fallar, raising=False)
    for _ in range(2):
        with pytest.raises(RuntimeError, match='fecha rechazada'):
            lz.cambiar_estado('acme', eid, 'ACTIVE')
    assert vistos[0] == vistos[1]
    assert meta.llamadas == []
    assert ex.obtener('acme', eid)['estado'] == 'pausado'


@pytest.mark.parametrize('estado', ['corriendo', 'decidido'])
@pytest.mark.parametrize('via', ['experimento', 'pieza'])
def test_pnd113_experimento_que_ya_corre_sin_activado_en_no_mueve_el_fin(entorno, monkeypatch, estado, via):
    """Revisión del lote 2: un experimento activado antes de que existiera la
    marca `activado_en` (estado corriendo/decidido, sin marca) ya tiene su pauta:
    reactivarlo no manda ningún `end_time` ni fija una reserva (alargarla sin
    que nadie lo apruebe es plata)."""
    lz, ex, eid, meta = entorno['lanzador'], entorno['ex'], entorno['eid'], entorno['meta']
    lz.lanzar('acme', eid)
    ex.actualizar('acme', eid, estado=estado)
    assert 'activado_en' not in (ex.obtener('acme', eid).get('extra') or {})
    def llamar(metodo, oid, payload):
        return meta._id('fin', metodo=metodo, oid=oid, payload=payload)
    monkeypatch.setattr(lz.meta_auth, 'llamar', llamar, raising=False)
    meta.llamadas.clear()
    if via == 'pieza':
        lz.activar_pieza('acme', ex.obtener('acme', eid)['piezas'][0]['id'])
    else:
        lz.cambiar_estado('acme', eid, 'ACTIVE')
    assert not any(t == 'fin' for t, _ in meta.llamadas)
    assert 'fin_primera_activacion' not in (ex.obtener('acme', eid).get('extra') or {})


def test_pnd113_reintento_tras_pasar_la_reserva_reenvia_un_fin_futuro(entorno, monkeypatch):
    """Revisión del lote 2: si el primer intento falló y el reintento llega
    después del plazo reservado, el `end_time` reenviado se recalcula desde
    ahora (uno vencido dejaría la activación bloqueada para siempre)."""
    import time
    lz, ex, eid, meta = entorno['lanzador'], entorno['ex'], entorno['eid'], entorno['meta']
    lz.lanzar('acme', eid)
    ahora = 1800000000
    monkeypatch.setattr(time, 'time', lambda: ahora)
    def fallar(metodo, oid, payload):
        raise RuntimeError('fecha rechazada')
    monkeypatch.setattr(lz.meta_auth, 'llamar', fallar, raising=False)
    with pytest.raises(RuntimeError, match='fecha rechazada'):
        lz.cambiar_estado('acme', eid, 'ACTIVE')
    assert ex.obtener('acme', eid)['extra']['fin_primera_activacion'] == ahora + 7 * 86400

    ahora += 8 * 86400  # el reintento llega después del plazo reservado
    def llamar(metodo, oid, payload):
        return meta._id('fin', metodo=metodo, oid=oid, payload=payload)
    monkeypatch.setattr(lz.meta_auth, 'llamar', llamar, raising=False)
    meta.llamadas.clear()
    lz.cambiar_estado('acme', eid, 'ACTIVE')
    fines = [kw['payload']['end_time'] for t, kw in meta.llamadas if t == 'fin']
    assert fines and all(f == ahora + 7 * 86400 for f in fines)
    assert all(f > ahora for f in fines)


def test_pnd113_reserva_a_menos_de_una_hora_tambien_se_recalcula(entorno, monkeypatch):
    import time
    lz, ex, eid, meta = entorno['lanzador'], entorno['ex'], entorno['eid'], entorno['meta']
    lz.lanzar('acme', eid)
    ahora = 1800000000
    monkeypatch.setattr(time, 'time', lambda: ahora)
    ex.actualizar_extra('acme', eid, lambda e: {**e, 'fin_primera_activacion': ahora + 1800})
    def llamar(metodo, oid, payload):
        return meta._id('fin', metodo=metodo, oid=oid, payload=payload)
    monkeypatch.setattr(lz.meta_auth, 'llamar', llamar, raising=False)
    meta.llamadas.clear()
    lz.cambiar_estado('acme', eid, 'ACTIVE')
    fines = [kw['payload']['end_time'] for t, kw in meta.llamadas if t == 'fin']
    assert fines and all(f == ahora + 7 * 86400 for f in fines)
