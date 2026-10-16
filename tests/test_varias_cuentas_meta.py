"""PND-148 (spec 2026-10-16): un experimento lanza cada país en su cuenta publicitaria de Meta. happyflops tiene 7
cuentas en SEK, una por país, y hasta ahora todo se lanzaba en la de `meta.json`. Plata: cada prueba falla si se rompe
la regla que nombra (spec §4). Nunca se llama a Meta: `MetaFalsa` de `tests/test_lanzador.py`, extendida a varias
cuentas (cada objeto anota en qué cuenta nació)."""
from datetime import date

import pytest

from tests.test_experimentos_db import _pieza
from tests.test_lanzador import MetaFalsa
from tests.test_meta_rend_sync import ACT, CLI, HOY, FakeGraph, cuenta  # noqa: F401 — fixture `cuenta`

DEF, SUECIA, FINLANDIA, DINAMARCA = "act_1", "act_2", "act_3", "act_4"
URL = "https://happyflops.se/p"
# 300 + 100 SEK al día × 7 días = 2 800: el tope exacto que arma «Nuevo experimento».
PAISES = [{"pais": "NO", "idioma": "no", "presupuesto_dia": 300.0},
          {"pais": "SE", "idioma": "sv", "presupuesto_dia": 100.0, "ad_account_id": SUECIA}]


def _sembrar(cuentas_=((SUECIA, "HappyFlops Sweden", "SE", "SEK", True),), cliente="acme"):
    """Cuentas de Rendimiento del proyecto (`meta_cuenta`) con lo que la copia guardaría de `user_tasks`."""
    from meta_rendimiento import cuentas
    cuentas.elegir(cliente, [{"id": a, "name": n, "pais": p, "currency": m} for a, n, p, m, _ in cuentas_])
    for a, _, _, _, puede in cuentas_:
        cuentas.actualizar_extra(cliente, a, {"puede_lanzar": puede})


def _parchar(lanzador, meta, monkeypatch, moneda="SEK"):
    campaign, adset, creative, ad, insights, auth = meta.modulos()
    for nombre, modulo in (("meta_campaign", campaign), ("meta_adset", adset), ("meta_creative", creative),
                           ("meta_ad", ad), ("meta_insights", insights), ("meta_auth", auth)):
        monkeypatch.setattr(lanzador, nombre, modulo)
    monkeypatch.setattr(lanzador, "_meta_directo", meta._directo)
    monkeypatch.setattr(lanzador.meta_conexion, "credenciales_ads",
                        lambda c: {"token": "t", "ad_account_id": DEF, "page_id": "2", "ig_user_id": None})
    monkeypatch.setattr(lanzador.meta_conexion, "cargar",
                        lambda c: {"moneda": moneda, "ad_account_id": DEF, "ad_account_nombre": "HappyFlops Norway"})
    monkeypatch.setattr(lanzador, "_miniatura_para_ad", lambda cliente, ad_id, url: "https://r2/mini.jpg")
    # Las cuentas de lanzamiento de todos los proyectos (meta.json): solo la de acme, sin leer clientes/ del disco.
    monkeypatch.setattr(lanzador.meta_conexion, "cuentas_de_lanzamiento", lambda: {DEF: "acme"})


@pytest.fixture()
def dos(base_temporal, monkeypatch):
    import experimentos as ex
    import lanzador
    meta = MetaFalsa(moneda="SEK")
    _parchar(lanzador, meta, monkeypatch)
    _sembrar()
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_1")
    eid = ex.crear("acme", "Chanclas", PAISES, "OUTCOME_TRAFFIC", 7, 2800.0, URL, "SEK")
    ex.agregar_pieza("acme", eid, clon, "NO")
    ex.agregar_pieza("acme", eid, clon, "SE")
    return {"ex": ex, "lz": lanzador, "meta": meta, "eid": eid, "clon": clon, "db": base_temporal,
            "monkeypatch": monkeypatch}


def _creados(meta, tipo):
    """[(id, kw, cuenta)] de los objetos `tipo` creados, en orden."""
    return [(i, kw, c) for t, i, kw, c in meta.objetos if t == tipo]


def _por_pais(ex, eid):
    return {p["pais"]: p for p in ex.obtener("acme", eid)["paises"]}


# ---------- lanzar: una campaña por cuenta ----------

def test_dos_paises_en_dos_cuentas_crean_una_campana_en_cada_una(dos):
    ex, lz, meta, eid = dos["ex"], dos["lz"], dos["meta"], dos["eid"]
    lz.lanzar("acme", eid)
    campanas = {cuenta: (cid, kw) for cid, kw, cuenta in _creados(meta, "campaign")}
    assert set(campanas) == {DEF, SUECIA}
    # mismo nombre, con el de la cuenta al final
    assert campanas[DEF][1]["nombre"] == "Chanclas — HappyFlops Norway"
    assert campanas[SUECIA][1]["nombre"] == "Chanclas — HappyFlops Sweden"
    paises = _por_pais(ex, eid)
    # cada conjunto en la cuenta de su país y dentro de la campaña de esa cuenta
    assert meta.cuenta_de[paises["NO"]["meta_adset_id"]] == DEF
    assert meta.cuenta_de[paises["SE"]["meta_adset_id"]] == SUECIA
    assert meta.campana_de_conjunto[paises["NO"]["meta_adset_id"]] == campanas[DEF][0]
    assert meta.campana_de_conjunto[paises["SE"]["meta_adset_id"]] == campanas[SUECIA][0]
    # la campaña queda en cada país; la del experimento es la de la cuenta por defecto
    assert paises["NO"]["meta_campaign_id"] == campanas[DEF][0]
    assert paises["SE"]["meta_campaign_id"] == campanas[SUECIA][0]
    assert ex.obtener("acme", eid)["meta_campaign_id"] == campanas[DEF][0]
    # anuncios y creatives en la cuenta de su país; el video se sube una vez POR CUENTA (un id de una cuenta no
    # sirve en otra)
    for pz in ex.obtener("acme", eid)["piezas"]:
        cuenta_pais = DEF if pz["pais"] == "NO" else SUECIA
        assert meta.cuenta_de[pz["meta_ad_id"]] == cuenta_pais and meta.cuenta_de[pz["meta_creative_id"]] == cuenta_pais
    assert sorted(c for _, c in meta.subidas) == [DEF, SUECIA]
    assert ex.obtener("acme", eid)["estado"] == "pausado"


def test_moneda_y_minimos_de_todas_las_cuentas_antes_del_primer_monto(dos):
    """Spec §2.4: comprobar_moneda y la lectura de mínimos corren por cada cuenta antes de mandar un solo monto."""
    ex, lz, meta, eid = dos["ex"], dos["lz"], dos["meta"], dos["eid"]
    orden = []
    original_llamar, original_campana = meta._llamar, meta._campaign

    def llamar(metodo, edge, payload=None, params=None, dry_run=False):
        if metodo == "GET" and edge.startswith("act_"):
            orden.append(("leer", edge))
        return original_llamar(metodo, edge, payload, params, dry_run)

    def campana(*a, **k):
        orden.append(("campaña", meta.cuenta_actual))
        return original_campana(*a, **k)
    meta._llamar, meta._campaign = llamar, campana
    _parchar(lz, meta, dos["monkeypatch"])
    lz.lanzar("acme", eid)
    primera = orden.index(next(o for o in orden if o[0] == "campaña"))
    assert {o[1] for o in orden[:primera] if o[0] == "leer"} == {DEF, SUECIA}


def test_una_cuenta_con_otra_moneda_no_deja_crear_nada_en_ninguna(dos):
    ex, lz, meta, eid = dos["ex"], dos["lz"], dos["meta"], dos["eid"]
    meta.cuentas[SUECIA] = {**meta.cuenta, "currency": "EUR"}
    with pytest.raises(lz.PresupuestoNoCoincide):
        lz.lanzar("acme", eid)
    assert not [t for t, _ in meta.llamadas if t in ("campaign", "adset", "creative", "ad")]
    assert meta.subidas == []
    e = ex.obtener("acme", eid)
    assert e["estado"] == "error" and not e["meta_campaign_id"]


@pytest.mark.parametrize("cambio", ["quitada", "sin_permiso"])
def test_una_cuenta_que_ya_no_puede_lanzar_frena_antes_de_llamar_a_meta(dos, cambio):
    """La cuenta se eligió al crear, pero al lanzar ya no está en el proyecto (o perdió el permiso de anunciar): no
    se lee ni se crea nada en Meta. Aislamiento: una cuenta que salió del proyecto pudo pasar a otro."""
    from meta_rendimiento import cuentas
    ex, lz, meta, eid = dos["ex"], dos["lz"], dos["meta"], dos["eid"]
    if cambio == "quitada":
        cuentas.elegir("acme", [])
    else:
        cuentas.actualizar_extra("acme", SUECIA, {"puede_lanzar": False})
    with pytest.raises(ValueError):
        lz.lanzar("acme", eid)
    assert meta.llamadas == [] and meta.leidas == []
    assert ex.obtener("acme", eid)["estado"] == "error"


def test_otra_cuenta_en_modo_agencia_no_se_usa(dos, monkeypatch):
    ex, lz, meta, eid = dos["ex"], dos["lz"], dos["meta"], dos["eid"]
    monkeypatch.setattr(lz.meta_conexion, "modo", lambda c: lz.meta_conexion.MODO_AGENCIA)
    with pytest.raises(ValueError):
        lz.lanzar("acme", eid)
    assert meta.llamadas == []


def test_reintento_tras_fallar_en_la_segunda_cuenta_no_duplica_la_primera(dos):
    ex, lz, meta, eid = dos["ex"], dos["lz"], dos["meta"], dos["eid"]
    original = meta._campaign
    fallos = []

    def falla_en_suecia(*a, **k):
        if meta.cuenta_actual == SUECIA and not fallos:
            fallos.append(1)
            raise RuntimeError("Meta falló en la campaña de Suecia")
        return original(*a, **k)
    meta._campaign = falla_en_suecia
    _parchar(lz, meta, dos["monkeypatch"])
    with pytest.raises(RuntimeError):
        lz.lanzar("acme", eid)
    assert ex.obtener("acme", eid)["estado"] == "error"
    lz.lanzar("acme", eid)
    assert sorted(c for _, _, c in _creados(meta, "campaign")) == [DEF, SUECIA]
    assert sorted(c for _, _, c in _creados(meta, "adset")) == [DEF, SUECIA]
    assert sorted(c for _, _, c in _creados(meta, "ad")) == [DEF, SUECIA]
    assert sorted(c for _, c in meta.subidas) == [DEF, SUECIA]
    assert ex.obtener("acme", eid)["estado"] == "pausado"


def test_reintento_tras_fallar_un_anuncio_en_la_segunda_cuenta_reusa_su_campana_y_conjunto(dos):
    ex, lz, meta, eid = dos["ex"], dos["lz"], dos["meta"], dos["eid"]
    original = meta._id
    fallos = []

    def falla_el_anuncio_de_suecia(tipo, **kw):
        if tipo == "ad" and meta.cuenta_actual == SUECIA and not fallos:
            fallos.append(1)
            raise RuntimeError("Meta falló en el anuncio")
        return original(tipo, **kw)
    meta._id = falla_el_anuncio_de_suecia
    _parchar(lz, meta, dos["monkeypatch"])
    with pytest.raises(RuntimeError):
        lz.lanzar("acme", eid)
    lz.lanzar("acme", eid)
    assert len(_creados(meta, "campaign")) == 2 and len(_creados(meta, "adset")) == 2
    e = ex.obtener("acme", eid)
    assert e["estado"] == "pausado" and all(pz["meta_ad_id"] for pz in e["piezas"])


# ---------- el tope repartido ----------

def test_el_tope_se_reparte_en_proporcion_a_los_diarios(dos):
    ex, lz, meta, eid = dos["ex"], dos["lz"], dos["meta"], dos["eid"]
    lz.lanzar("acme", eid)
    topes = {c: kw["spend_cap"] for _, kw, c in _creados(meta, "campaign")}
    # 2 800 SEK = 280 000 en la unidad de Meta, repartido 300 : 100
    assert topes == {DEF: 210000, SUECIA: 70000}
    assert sum(topes.values()) <= lz.centavos(2800.0, "SEK")


@pytest.mark.parametrize("diarios, tope, moneda", [
    ([300.0, 100.0], 2800.0, "SEK"), ([333.33, 100.01], 3033.38, "SEK"), ([1.0, 1.0, 1.0], 20.0, "USD"),
    ([4001.0, 4000.0, 4003.0], 84028.0, "COP"), ([15.0, 0.0], 105.0, "SEK"), ([7.77, 3.33, 9.99], 147.0, "EUR")])
def test_la_suma_de_los_topes_repartidos_nunca_pasa_el_total(diarios, tope, moneda):
    import lanzador as lz
    grupos = [[{"presupuesto_dia": d}] for d in diarios]
    partes = lz._repartir_tope(tope, grupos, moneda)
    assert len(partes) == len(grupos) and all(p >= 0 for p in partes)
    assert sum(partes) <= lz.centavos(tope, moneda)
    assert sum(partes) >= lz.centavos(tope, moneda) - len(grupos)   # se reparte casi todo: solo el redondeo queda fuera


def test_una_parte_bajo_el_minimo_de_su_cuenta_va_sin_tope_y_con_fecha_de_fin(dos):
    """Spec §2.5: la parte de Suecia (700 SEK) queda bajo el mínimo de esa cuenta (1 000 SEK): no se manda
    spend_cap y sus conjuntos llevan la fecha de fin; la de Noruega sí lleva su tope."""
    ex, lz, meta, eid = dos["ex"], dos["lz"], dos["meta"], dos["eid"]
    meta.cuentas[SUECIA] = {**meta.cuenta, "min_campaign_group_spend_cap": "100000"}
    lz.lanzar("acme", eid)
    topes = {c: kw["spend_cap"] for _, kw, c in _creados(meta, "campaign")}
    assert topes == {DEF: 210000, SUECIA: None}
    assert {c: kw["dias"] for _, kw, c in _creados(meta, "adset")} == {DEF: 7, SUECIA: 7}
    assert any("HappyFlops Sweden" in e["mensaje"] and "vigilancia" in e["mensaje"]
               for e in ex.eventos("acme", eid))


def test_el_reintento_vuelve_a_leer_el_tope_repartido_de_cada_campana(dos):
    """Una campaña reusada al reintentar se lee de vuelta con SU parte, no con el total."""
    ex, lz, meta, eid = dos["ex"], dos["lz"], dos["meta"], dos["eid"]
    meta.fallar_en = "ad"
    with pytest.raises(RuntimeError):
        lz.lanzar("acme", eid)
    meta.fallar_en = None
    lz.lanzar("acme", eid)
    e = ex.obtener("acme", eid)
    assert e["estado"] == "pausado"
    assert {meta.cuenta_de[c]: meta.topes[c] for c in meta.topes} == {DEF: 210000, SUECIA: 70000}


# ---------- activar, pausar, presupuesto: solo la cuenta del país ----------

def _lanzado(dos):
    dos["lz"].lanzar("acme", dos["eid"])
    dos["meta"].llamadas.clear()
    dos["meta"].leidas.clear()
    return _por_pais(dos["ex"], dos["eid"])


def test_activar_un_pais_solo_toca_su_cuenta(dos):
    ex, lz, meta, eid = dos["ex"], dos["lz"], dos["meta"], dos["eid"]
    paises = _lanzado(dos)
    lz.cambiar_estado("acme", eid, "ACTIVE", pais="SE")
    cambiados = [kw["oid"] for t, kw in meta.llamadas if t == "estado"]
    assert cambiados and all(meta.cuenta_de[oid] == SUECIA for oid in cambiados)
    assert paises["SE"]["meta_campaign_id"] in cambiados and paises["NO"]["meta_campaign_id"] not in cambiados
    assert meta.leidas == [SUECIA]
    assert _por_pais(ex, eid)["NO"]["estado"] == "pausado" and _por_pais(ex, eid)["SE"]["estado"] == "activo"


def test_activar_un_segundo_pais_enciende_la_campana_de_su_cuenta(dos):
    """Con el experimento ya «corriendo» por Noruega, activar Suecia tiene que encender la campaña de Suecia: si
    no, su conjunto quedaría ACTIVE dentro de una campaña en pausa y no entregaría."""
    ex, lz, meta, eid = dos["ex"], dos["lz"], dos["meta"], dos["eid"]
    paises = _lanzado(dos)
    lz.cambiar_estado("acme", eid, "ACTIVE", pais="NO")
    assert ex.obtener("acme", eid)["estado"] == "corriendo"
    meta.llamadas.clear()
    lz.cambiar_estado("acme", eid, "ACTIVE", pais="SE")
    assert ("estado", {"oid": paises["SE"]["meta_campaign_id"], "status": "ACTIVE"}) in meta.llamadas


def test_activar_una_pieza_solo_toca_su_cuenta(dos):
    ex, lz, meta, eid = dos["ex"], dos["lz"], dos["meta"], dos["eid"]
    _lanzado(dos)
    ep = next(pz for pz in ex.obtener("acme", eid)["piezas"] if pz["pais"] == "SE")
    lz.activar_pieza("acme", ep["id"])
    cambiados = [kw["oid"] for t, kw in meta.llamadas if t == "estado"]
    assert cambiados and all(meta.cuenta_de[oid] == SUECIA for oid in cambiados)
    assert meta.leidas == [SUECIA]


def test_activar_todo_comprueba_cada_cuenta_y_enciende_las_dos_campanas(dos):
    ex, lz, meta, eid = dos["ex"], dos["lz"], dos["meta"], dos["eid"]
    paises = _lanzado(dos)
    lz.cambiar_estado("acme", eid, "ACTIVE")
    assert sorted(meta.leidas) == [DEF, SUECIA]
    activos = [kw["oid"] for t, kw in meta.llamadas if t == "estado" and kw["status"] == "ACTIVE"]
    assert paises["NO"]["meta_campaign_id"] in activos and paises["SE"]["meta_campaign_id"] in activos
    assert ex.obtener("acme", eid)["estado"] == "corriendo"


def test_activar_un_pais_en_una_cuenta_que_cambio_de_moneda_no_enciende_nada(dos):
    ex, lz, meta, eid = dos["ex"], dos["lz"], dos["meta"], dos["eid"]
    _lanzado(dos)
    meta.cuentas[SUECIA] = {**meta.cuenta, "currency": "EUR"}
    with pytest.raises(lz.PresupuestoNoCoincide):
        lz.cambiar_estado("acme", eid, "ACTIVE", pais="SE")
    assert not [kw for t, kw in meta.llamadas if t == "estado" and kw["status"] == "ACTIVE"]


def test_activar_en_una_cuenta_que_salio_del_proyecto_no_enciende_nada(dos):
    from meta_rendimiento import cuentas
    ex, lz, meta, eid = dos["ex"], dos["lz"], dos["meta"], dos["eid"]
    _lanzado(dos)
    cuentas.elegir("acme", [])
    with pytest.raises(ValueError):
        lz.cambiar_estado("acme", eid, "ACTIVE", pais="SE")
    assert not [kw for t, kw in meta.llamadas if t == "estado" and kw["status"] == "ACTIVE"]
    # pausar nunca se frena: lo que esté en Meta se puede apagar siempre
    lz.cambiar_estado("acme", eid, "PAUSED")
    assert [kw for t, kw in meta.llamadas if t == "estado" and kw["status"] == "PAUSED"]


def test_cambiar_el_diario_de_un_pais_lee_su_cuenta(dos):
    ex, lz, meta, eid = dos["ex"], dos["lz"], dos["meta"], dos["eid"]
    _lanzado(dos)
    lz.cambiar_estado("acme", eid, "ACTIVE")
    meta.leidas.clear()
    lz.cambiar_presupuesto_pais("acme", eid, "SE", 90.0)
    # primero la cuenta del país; con el reparto vivo del tope, también cada cuenta que recibe un tope nuevo
    assert meta.leidas[0] == SUECIA and set(meta.leidas) == {DEF, SUECIA}
    meta.cuentas[SUECIA] = {**meta.cuenta, "currency": "EUR"}
    with pytest.raises(lz.PresupuestoNoCoincide):
        lz.cambiar_presupuesto_pais("acme", eid, "SE", 80.0)
    assert _por_pais(ex, eid)["SE"]["presupuesto_dia"] == 90.0


def test_pausar_todo_pausa_las_dos_campanas(dos):
    ex, lz, meta, eid = dos["ex"], dos["lz"], dos["meta"], dos["eid"]
    paises = _lanzado(dos)
    lz.cambiar_estado("acme", eid, "ACTIVE")
    meta.llamadas.clear()
    lz.cerrar("acme", eid)
    pausados = [kw["oid"] for t, kw in meta.llamadas if t == "estado" and kw["status"] == "PAUSED"]
    assert paises["NO"]["meta_campaign_id"] in pausados and paises["SE"]["meta_campaign_id"] in pausados


def test_pausar_todo_sigue_con_la_otra_cuenta_si_meta_rechaza_la_primera(dos):
    """Revisión de guardian-gasto: que Meta rechace la pausa en la cuenta de Noruega no puede dejar a Suecia gastando.
    Se pausa todo lo que se pueda y el error sale al final (el experimento no se marca «pausado»)."""
    ex, lz, meta, eid = dos["ex"], dos["lz"], dos["meta"], dos["eid"]
    paises = _lanzado(dos)
    lz.cambiar_estado("acme", eid, "ACTIVE")
    meta.llamadas.clear()
    original = meta._id

    def falla_noruega(tipo, **kw):
        if tipo == "estado" and kw.get("oid") == paises["NO"]["meta_campaign_id"]:
            raise RuntimeError("Meta: sin permiso en esta cuenta")
        return original(tipo, **kw)
    meta._id = falla_noruega
    _parchar(lz, meta, dos["monkeypatch"])
    with pytest.raises(RuntimeError):
        lz.cambiar_estado("acme", eid, "PAUSED")
    pausados = [kw["oid"] for t, kw in meta.llamadas if t == "estado" and kw["status"] == "PAUSED"]
    assert paises["SE"]["meta_campaign_id"] in pausados and paises["SE"]["meta_adset_id"] in pausados
    assert paises["NO"]["meta_adset_id"] in pausados
    e = ex.obtener("acme", eid)
    assert e["estado"] == "corriendo"      # la vigilancia lo sigue mirando
    assert all(pz["estado"] == "pausado" for pz in e["piezas"])


def test_cerrar_sigue_con_todo_si_meta_rechaza_la_pausa_de_una_cuenta(dos):
    """Revisión: `_pausar_todo_en_meta` (cerrar, repausar, dejar sin gastar) sigue con las demás campañas, conjuntos y
    anuncios aunque Meta rechace algo de una cuenta; el error sale al final y el experimento no se cierra."""
    ex, lz, meta, eid = dos["ex"], dos["lz"], dos["meta"], dos["eid"]
    paises = _lanzado(dos)
    lz.cambiar_estado("acme", eid, "ACTIVE")
    meta.llamadas.clear()
    original = meta._id
    rechazados = {paises["NO"]["meta_campaign_id"], paises["NO"]["meta_adset_id"]}

    def falla_noruega(tipo, **kw):
        if tipo == "estado" and kw.get("oid") in rechazados:
            raise RuntimeError("Meta: sin permiso en esta cuenta")
        return original(tipo, **kw)
    meta._id = falla_noruega
    _parchar(lz, meta, dos["monkeypatch"])
    with pytest.raises(RuntimeError):
        lz.cerrar("acme", eid)
    pausados = [kw["oid"] for t, kw in meta.llamadas if t == "estado" and kw["status"] == "PAUSED"]
    assert paises["SE"]["meta_campaign_id"] in pausados and paises["SE"]["meta_adset_id"] in pausados
    assert all(pz["meta_ad_id"] in pausados for pz in ex.obtener("acme", eid)["piezas"])
    e = ex.obtener("acme", eid)
    assert e["estado"] != "cerrado"
    assert _por_pais(ex, eid)["NO"]["estado"] == "activo" and _por_pais(ex, eid)["SE"]["estado"] == "pausado"


def test_cambiar_el_diario_en_una_cuenta_que_salio_del_proyecto_no_manda_nada(dos):
    from meta_rendimiento import cuentas
    ex, lz, meta, eid = dos["ex"], dos["lz"], dos["meta"], dos["eid"]
    _lanzado(dos)
    lz.cambiar_estado("acme", eid, "ACTIVE")
    meta.llamadas.clear()
    meta.leidas.clear()
    cuentas.elegir("acme", [])
    with pytest.raises(ValueError):
        lz.cambiar_presupuesto_pais("acme", eid, "SE", 90.0)
    assert not [t for t, _ in meta.llamadas if t == "presupuesto"] and meta.leidas == []
    assert _por_pais(ex, eid)["SE"]["presupuesto_dia"] == 100.0


def test_una_pieza_nueva_en_una_cuenta_que_salio_del_proyecto_no_se_crea(dos):
    from meta_rendimiento import cuentas
    ex, lz, meta, eid = dos["ex"], dos["lz"], dos["meta"], dos["eid"]
    _lanzado(dos)
    otra = _pieza(dos["db"], tipo="video", estado="listo", pais=None, idioma=None, legado="cf_2", url="https://r2/2.mp4")
    ex.agregar_pieza("acme", eid, otra, "SE")
    n = len(meta.subidas)
    cuentas.elegir("acme", [])
    with pytest.raises(ValueError):
        lz.lanzar_piezas_nuevas("acme", eid)
    assert not [t for t, _ in meta.llamadas if t in ("creative", "ad")] and len(meta.subidas) == n


def test_activar_una_pieza_de_otro_pais_enciende_la_campana_de_su_cuenta(dos):
    """Con el experimento «corriendo» por Noruega, una pieza de Suecia (p. ej. la de un rescate) enciende la campaña de
    Suecia; si no, quedaría «activa» en Creatv dentro de una campaña en pausa y no entregaría."""
    ex, lz, meta, eid = dos["ex"], dos["lz"], dos["meta"], dos["eid"]
    paises = _lanzado(dos)
    lz.cambiar_estado("acme", eid, "ACTIVE", pais="NO")
    assert ex.obtener("acme", eid)["estado"] == "corriendo"
    meta.llamadas.clear()
    ep = next(pz for pz in ex.obtener("acme", eid)["piezas"] if pz["pais"] == "SE")
    lz.activar_pieza("acme", ep["id"])
    assert ("estado", {"oid": paises["SE"]["meta_campaign_id"], "status": "ACTIVE"}) in meta.llamadas
    assert ("estado", {"oid": paises["NO"]["meta_campaign_id"], "status": "ACTIVE"}) not in meta.llamadas


def test_la_cuenta_de_lanzamiento_de_otro_proyecto_nunca_se_ofrece_ni_se_lanza(dos, monkeypatch):
    """Aislamiento (revisión): la cuenta de Suecia quedó en el Rendimiento de acme, pero después otro proyecto la
    conectó como SU cuenta de lanzamiento (meta.json). No se ofrece, `validar` la rechaza y lanzar no llama a Meta."""
    import cuentas_lanzamiento as cl
    ex, lz, meta, eid = dos["ex"], dos["lz"], dos["meta"], dos["eid"]
    monkeypatch.setattr(lz.meta_conexion, "cuentas_de_lanzamiento", lambda: {DEF: "acme", SUECIA: "otro"})
    assert cl.disponibles("acme", "SEK") == []
    with pytest.raises(ValueError):
        cl.validar("acme", "SEK", {"SE": SUECIA})
    with pytest.raises(ValueError):
        lz.lanzar("acme", eid)
    assert meta.llamadas == [] and meta.leidas == []
    # la cuenta de lanzamiento del PROPIO proyecto no cuenta como ajena
    monkeypatch.setattr(lz.meta_conexion, "cuentas_de_lanzamiento", lambda: {DEF: "acme", SUECIA: "acme"})
    assert [c["id"] for c in cl.disponibles("acme", "SEK")] == [SUECIA]


# ---------- la vigilancia sobre el total ----------

def _corriendo(dos):
    paises = _lanzado(dos)
    dos["lz"].cambiar_estado("acme", dos["eid"], "ACTIVE")
    dos["meta"].llamadas.clear()
    return paises["NO"]["meta_campaign_id"], paises["SE"]["meta_campaign_id"]


def test_la_vigilancia_suma_las_campanas_y_pausa_todas_al_llegar_al_tope(dos):
    """Cada campaña está bajo el tope del experimento (2 800) y Noruega bajo su parte (2 100), pero juntas llegan:
    se pausan las dos."""
    ex, lz, meta, eid = dos["ex"], dos["lz"], dos["meta"], dos["eid"]
    c_no, c_se = _corriendo(dos)
    meta.gastos[c_no] = (1900.0, 0.0)
    meta.gastos[c_se] = (900.0, 0.0)
    assert "tope" in lz.vigilar_gasto("acme", eid)
    assert (c_no, {"status": "PAUSED"}) in meta.posts and (c_se, {"status": "PAUSED"}) in meta.posts
    pausados = [kw["oid"] for t, kw in meta.llamadas if t == "estado" and kw["status"] == "PAUSED"]
    assert c_no in pausados and c_se in pausados
    e = ex.obtener("acme", eid)
    assert e["estado"] == "pausado" and e["gasto_acumulado"] == 2800.0


def test_la_vigilancia_no_pausa_si_la_suma_no_llega(dos):
    ex, lz, meta, eid = dos["ex"], dos["lz"], dos["meta"], dos["eid"]
    c_no, c_se = _corriendo(dos)
    meta.gastos[c_no] = (1900.0, 0.0)
    meta.gastos[c_se] = (600.0, 0.0)
    assert lz.vigilar_gasto("acme", eid) is None
    assert ex.obtener("acme", eid)["estado"] == "corriendo" and ex.obtener("acme", eid)["gasto_acumulado"] == 2500.0


def test_la_vigilancia_mira_el_ritmo_de_cada_conjunto_en_su_cuenta(dos):
    ex, lz, meta, eid = dos["ex"], dos["lz"], dos["meta"], dos["eid"]
    c_no, c_se = _corriendo(dos)
    adset_se = _por_pais(ex, eid)["SE"]["meta_adset_id"]
    meta.gastos_conjuntos[adset_se] = 250.0    # más del doble de 100 SEK
    assert "doble" in lz.vigilar_gasto("acme", eid)
    assert ex.obtener("acme", eid)["estado"] == "pausado"


def test_la_vigilancia_repausa_si_alguna_campana_sigue_activa(dos):
    ex, lz, meta, eid = dos["ex"], dos["lz"], dos["meta"], dos["eid"]
    c_no, c_se = _corriendo(dos)
    lz.cambiar_estado("acme", eid, "PAUSED")
    meta.llamadas.clear()
    meta.posts.clear()
    meta.estados_meta[c_se] = "ACTIVE"     # la pausa de Suecia falló a medias en Meta
    assert lz.vigilar_gasto("acme", eid)
    assert (c_se, {"status": "PAUSED"}) in meta.posts


def _directo_que_falla_en(dos, campana):
    meta = dos["meta"]
    original = meta._directo

    def directo(cliente, metodo, edge, params=None, payload=None):
        if metodo == "GET" and edge.split("/")[0] == campana:
            raise RuntimeError("Meta no contestó")
        return original(cliente, metodo, edge, params=params, payload=payload)
    dos["monkeypatch"].setattr(dos["lz"], "_meta_directo", directo)


def test_la_vigilancia_frena_una_cuenta_aunque_otra_no_se_pueda_leer(dos):
    """Revisión de guardian-gasto: Noruega no se puede leer y Suecia gasta hoy más del doble de su diario."""
    ex, lz, meta, eid = dos["ex"], dos["lz"], dos["meta"], dos["eid"]
    c_no, c_se = _corriendo(dos)
    _directo_que_falla_en(dos, c_no)
    meta.gastos_conjuntos[_por_pais(ex, eid)["SE"]["meta_adset_id"]] = 250.0
    assert "doble" in lz.vigilar_gasto("acme", eid)
    assert ex.obtener("acme", eid)["estado"] == "pausado"


def test_la_vigilancia_sin_motivo_pero_con_una_cuenta_sin_leer_avisa_el_error(dos):
    ex, lz, meta, eid = dos["ex"], dos["lz"], dos["meta"], dos["eid"]
    c_no, c_se = _corriendo(dos)
    _directo_que_falla_en(dos, c_no)
    with pytest.raises(RuntimeError):
        lz.vigilar_gasto("acme", eid)
    assert ex.obtener("acme", eid)["estado"] == "corriendo"


def test_el_repausado_mira_la_otra_campana_aunque_una_no_se_pueda_leer(dos):
    ex, lz, meta, eid = dos["ex"], dos["lz"], dos["meta"], dos["eid"]
    c_no, c_se = _corriendo(dos)
    lz.cambiar_estado("acme", eid, "PAUSED")
    meta.posts.clear()
    meta.estados_meta[c_se] = "ACTIVE"
    _directo_que_falla_en(dos, c_no)
    assert lz.vigilar_gasto("acme", eid)
    assert (c_se, {"status": "PAUSED"}) in meta.posts


def test_activar_se_niega_si_la_suma_ya_llego_al_tope(dos):
    ex, lz, meta, eid = dos["ex"], dos["lz"], dos["meta"], dos["eid"]
    paises = _lanzado(dos)
    meta.gastos[paises["NO"]["meta_campaign_id"]] = (2000.0, 0.0)
    meta.gastos[paises["SE"]["meta_campaign_id"]] = (800.0, 0.0)
    with pytest.raises(ValueError, match="tope"):
        lz.cambiar_estado("acme", eid, "ACTIVE", pais="SE")
    assert not [kw for t, kw in meta.llamadas if t == "estado" and kw["status"] == "ACTIVE"]


# ---------- piezas nuevas y derivaciones ----------

def test_una_pieza_nueva_se_crea_en_la_cuenta_de_su_pais(dos):
    ex, lz, meta, eid = dos["ex"], dos["lz"], dos["meta"], dos["eid"]
    _lanzado(dos)
    otra = _pieza(dos["db"], tipo="video", estado="listo", pais=None, idioma=None, legado="cf_2", url="https://r2/2.mp4")
    ep = ex.agregar_pieza("acme", eid, otra, "SE")
    assert lz.lanzar_piezas_nuevas("acme", eid) == 1
    pz = next(p for p in ex.obtener("acme", eid)["piezas"] if p["id"] == ep)
    assert meta.cuenta_de[pz["meta_ad_id"]] == SUECIA and meta.cuenta_de[pz["meta_creative_id"]] == SUECIA
    assert meta.subidas[-1] == ("https://r2/2.mp4", SUECIA)


def test_una_pieza_nueva_no_reusa_un_video_subido_a_otra_cuenta(dos):
    """El clon ya subió su video a Noruega; agregado después en Suecia tiene que subirse a la cuenta de Suecia (un
    video_id de una cuenta no sirve en otra). Y otra vez en Suecia ya no se sube."""
    ex, lz, meta = dos["ex"], dos["lz"], dos["meta"]
    otra = _pieza(dos["db"], tipo="video", estado="listo", pais=None, idioma=None, legado="cf_2", url="https://r2/2.mp4")
    eid = ex.crear("acme", "Dos piezas", PAISES, "OUTCOME_TRAFFIC", 7, 2800.0, URL, "SEK")
    ex.agregar_pieza("acme", eid, dos["clon"], "NO")
    ex.agregar_pieza("acme", eid, otra, "SE")
    lz.lanzar("acme", eid)
    assert set(meta.subidas) == {("https://r2/f.mp4", DEF), ("https://r2/2.mp4", SUECIA)}
    ep = ex.agregar_pieza("acme", eid, dos["clon"], "SE")
    assert lz.lanzar_piezas_nuevas("acme", eid) == 1
    assert meta.subidas[-1] == ("https://r2/f.mp4", SUECIA)
    pz = next(p for p in ex.obtener("acme", eid)["piezas"] if p["id"] == ep)
    assert pz["extra"]["meta_video_id"] == f"vid_{SUECIA}"
    n = len(meta.subidas)
    ex.agregar_pieza("acme", eid, otra, "NO")
    lz.lanzar_piezas_nuevas("acme", eid)
    assert meta.subidas[n:] == [("https://r2/2.mp4", DEF)]


def test_un_hijo_derivado_conserva_la_cuenta_de_cada_pais(dos):
    ex, eid = dos["ex"], dos["eid"]
    ep = ex.obtener("acme", eid)["piezas"][0]["id"]
    hijo = ex.crear_hijo("acme", eid, "Chanclas · derivado", ep)
    assert {p["pais"]: p.get("ad_account_id") for p in ex.obtener("acme", hijo)["paises"]} == {"NO": None, "SE": SUECIA}


# ---------- un experimento viejo: nada cambia ----------

def test_un_experimento_sin_cuenta_por_pais_hace_lo_mismo_que_hoy(dos):
    ex, lz, meta = dos["ex"], dos["lz"], dos["meta"]
    viejo = ex.crear("acme", "Viejo", [{k: v for k, v in p.items() if k != "ad_account_id"} for p in PAISES],
                     "OUTCOME_TRAFFIC", 7, 2800.0, URL, "SEK")
    ex.agregar_pieza("acme", viejo, dos["clon"], "NO")
    ex.agregar_pieza("acme", viejo, dos["clon"], "SE")
    lz.lanzar("acme", viejo)
    (campana,) = _creados(meta, "campaign")
    assert campana[1]["nombre"] == "Viejo" and campana[1]["spend_cap"] == 280000 and campana[2] == DEF
    assert {c for _, _, c in _creados(meta, "adset")} == {DEF} and meta.leidas == [DEF]
    lz.cambiar_estado("acme", viejo, "ACTIVE")
    meta.gastos[campana[0]] = (2800.0, 0.0)
    assert "tope" in lz.vigilar_gasto("acme", viejo)


# ---------- la copia de Rendimiento: quién puede lanzar ----------

@pytest.mark.parametrize("tareas, puede", [(["ADVERTISE", "ANALYZE"], True), (["MANAGE"], True),
                                           (["ANALYZE"], False), ([], False), (None, False)])
def test_la_copia_guarda_si_la_cuenta_puede_lanzar(cuenta, monkeypatch, tareas, puede):  # noqa: F811
    from meta_rendimiento import cuentas, sync
    info = {"name": "HappyFlops SE", "currency": "SEK", "timezone_name": "Europe/Stockholm", "account_status": 1,
            "disable_reason": 0, "amount_spent": "0", "spend_cap": "0"}
    if tareas is not None:
        info["user_tasks"] = tareas
    g = FakeGraph(monkeypatch, info=info)
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    pedidos = [p for e, p in g.de("get") if e == ACT]
    assert "user_tasks" in pedidos[0]["fields"].split(",")
    extra = cuentas.cuenta(CLI, ACT)["extra"]
    assert extra["puede_lanzar"] is puede and extra["lanzar_revisado_en"]


def test_cuentas_disponibles_solo_las_que_pueden_lanzar_en_la_moneda(base_temporal, monkeypatch):
    import cuentas_lanzamiento as cl
    import meta_conexion
    monkeypatch.setattr(meta_conexion, "cargar", lambda c: {"moneda": "SEK", "ad_account_id": DEF})
    monkeypatch.setattr(meta_conexion, "cuentas_de_lanzamiento", lambda: {DEF: "acme"})
    _sembrar(((SUECIA, "HappyFlops Sweden", "SE", "SEK", True), (FINLANDIA, "HappyFlops Finland", "FI", "SEK", False),
              (DINAMARCA, "HappyFlops Denmark", "DK", "DKK", True), (DEF, "HappyFlops Norway", "NO", "SEK", True)))
    _sembrar(((("act_9"), "Otro cliente", "SE", "SEK", True),), cliente="otro")
    assert [c["id"] for c in cl.disponibles("acme", "SEK")] == [SUECIA]
    assert cl.sugeridas(["NO", "SE", "FI"], cl.disponibles("acme", "SEK"), DEF) == {"NO": DEF, "SE": SUECIA, "FI": DEF}
    assert cl.validar("acme", "SEK", {"SE": SUECIA, "NO": DEF, "FI": ""}) == {"SE": SUECIA}
    for mala in (FINLANDIA, DINAMARCA, "act_9", "act_777"):
        with pytest.raises(ValueError):
            cl.validar("acme", "SEK", {"SE": mala})


# ---------- la pantalla y la ruta ----------

@pytest.fixture()
def app_sek(base_temporal, monkeypatch):
    from tests.test_rutas_experimentos import _cliente_admin
    import dashboard
    monkeypatch.setattr(dashboard.meta_conexion, "cargar",
                        lambda c: {"moneda": "SEK", "ad_account_id": DEF, "ad_account_nombre": "HappyFlops Norway"})
    monkeypatch.setattr(dashboard.meta_conexion, "estado",
                        lambda c: {"estado": "conectado", "verificado": True, "detalle": {}})
    monkeypatch.setattr(dashboard.meta_conexion, "cuentas_de_lanzamiento", lambda: {DEF: "acme"})
    encolados = []
    monkeypatch.setattr(dashboard.trabajos, "encolar",
                        lambda job_id, tipo, payload, **kw: (encolados.append({"tipo": tipo, **kw}), True)[1])
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: False)
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard), "encolados": encolados}


def _nuevo(app_sek):
    r = app_sek["c"].get("/cliente/acme/experimentos/nuevo")
    assert r.status_code == 200
    return r.get_data(as_text=True)


def test_el_paso_donde_ofrece_solo_las_cuentas_que_pueden_lanzar(app_sek, base_temporal):
    _sembrar(((SUECIA, "HappyFlops Sweden", "SE", "SEK", True), (FINLANDIA, "HappyFlops Finland", "FI", "SEK", False),
              (DINAMARCA, "HappyFlops Denmark", "DK", "DKK", True)))
    _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_1")
    html = _nuevo(app_sek)
    assert 'name="cuenta_SE"' in html and f'value="{SUECIA}"' in html and "HappyFlops Sweden" in html
    assert FINLANDIA not in html and DINAMARCA not in html and "HappyFlops Finland" not in html
    # Suecia va por defecto a la cuenta de Suecia; Noruega, a la conectada
    sel_se = html[html.index('name="cuenta_SE"'):]
    sel_se = sel_se[:sel_se.index("</select>")]
    assert f'value="{SUECIA}" selected' in sel_se
    sel_no = html[html.index('name="cuenta_NO"'):]
    sel_no = sel_no[:sel_no.index("</select>")]
    assert f'value="{DEF}" selected' in sel_no


def test_sin_otra_cuenta_no_hay_selector(app_sek, base_temporal):
    _sembrar(((FINLANDIA, "HappyFlops Finland", "FI", "SEK", False),))
    _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_1")
    html = _nuevo(app_sek)
    assert 'name="cuenta_' not in html and 'id="exp-cuentas"' not in html and 'id="exp-cuentas-resumen"' not in html


FORM_SEK = {"paises": ["NO", "SE"], "presupuesto_NO": "300", "presupuesto_SE": "100", "dias": "7",
            "tope_total": "2800", "destino_url": URL, "edad_min": "18", "edad_max": "55",
            "objetivo": "OUTCOME_TRAFFIC", "atribucion": "ninguna", "modo": "manual"}


def _form(base_temporal, **cambios):
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_1")
    return dict(FORM_SEK, piezas=[str(clon)], combinaciones=[f"{clon}:NO", f"{clon}:SE"], **cambios)


def test_probar_guarda_la_cuenta_de_cada_pais(app_sek, base_temporal):
    import experimentos as ex
    _sembrar()
    app_sek["c"].post("/cliente/acme/experimentos/probar", data=_form(base_temporal, cuenta_NO=DEF, cuenta_SE=SUECIA))
    (e,) = ex.cargar("acme")
    assert {p["pais"]: p.get("ad_account_id") for p in e["paises"]} == {"NO": None, "SE": SUECIA}
    assert [t["tipo"] for t in app_sek["encolados"]] == ["exp_lanzar"] and app_sek["encolados"][0]["max_intentos"] == 1


def test_probar_sin_campo_de_cuenta_usa_la_de_defecto(app_sek, base_temporal):
    import experimentos as ex
    _sembrar()
    app_sek["c"].post("/cliente/acme/experimentos/probar", data=_form(base_temporal))
    (e,) = ex.cargar("acme")
    assert all(not p.get("ad_account_id") for p in e["paises"])


@pytest.mark.parametrize("mala", [FINLANDIA, DINAMARCA, "act_9", "act_777"])
def test_probar_rechaza_una_cuenta_que_no_puede_lanzar_y_no_crea_nada(app_sek, base_temporal, mala):
    import experimentos as ex
    from tests.test_rutas_bloque4 import _flashes
    _sembrar(((SUECIA, "HappyFlops Sweden", "SE", "SEK", True), (FINLANDIA, "HappyFlops Finland", "FI", "SEK", False),
              (DINAMARCA, "HappyFlops Denmark", "DK", "DKK", True)))
    _sembrar((("act_9", "Otro cliente", "SE", "SEK", True),), cliente="otro")
    app_sek["c"].post("/cliente/acme/experimentos/probar", data=_form(base_temporal, cuenta_SE=mala))
    assert ex.cargar("acme") == [] and app_sek["encolados"] == []
    assert any("cuenta" in m for m in _flashes(app_sek["c"]))


def test_sin_token_otro_envio_que_solo_cambia_la_cuenta_no_es_repetido(app_sek, base_temporal):
    """La huella del formulario (envío sin token) incluye la cuenta de cada país: pedir lo mismo en otra cuenta es
    otro experimento, no un reenvío."""
    import experimentos as ex
    _sembrar()
    datos = _form(base_temporal, cuenta_SE=SUECIA)
    app_sek["c"].post("/cliente/acme/experimentos/probar", data=datos)
    app_sek["c"].post("/cliente/acme/experimentos/probar", data=dict(datos, cuenta_SE=DEF))
    assert sorted(str(p.get("ad_account_id")) for e in ex.cargar("acme") for p in e["paises"] if p["pais"] == "SE") \
        == ["None", SUECIA]


def test_la_pantalla_usa_las_cuentas_para_decidir_el_titular_y_el_resumen(app_sek, base_temporal):
    _sembrar()
    _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_1")
    html = _nuevo(app_sek)
    assert "P.faltaTope(total, gruposCuenta(ps), moneda, topeCampana)" in html
    assert "P.lineasCuentas(PLANTILLA_PAIS_CUENTA, filas)" in html
    assert "partesBajas ? AVISO_SIN_TOPE_VARIAS : AVISO_SIN_TOPE" in html


@pytest.mark.skipif(not __import__("shutil").which("node"), reason="sin Node no se corre el JS")
def test_el_titular_y_el_resumen_en_js():
    """«Máximo que puede gastar» solo si toda campaña lleva tope duro (con varias cuentas, cada parte); el resumen de
    Revisar dice la cuenta de cada país sin interpretar «$&» de un nombre de Meta."""
    import json as _json
    import os
    import shutil
    import subprocess
    ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "presupuesto_exp.js")
    arnes = """const P=require(process.argv[1]); const g=P.gruposPorCuenta([['a',200],['b',200],['a',50]]);
    console.log(JSON.stringify({g:g,
      una:P.faltaTope(2000,[[200,200]],'SEK',1300), dos:P.faltaTope(2000,[[200],[200]],'SEK',1300),
      dosGrande:P.faltaTope(3000,[[200],[200]],'SEK',1300), chico:P.faltaTope(800,[[200],[200]],'SEK',1300),
      desigual:P.faltaTope(2800,[[300],[100]],'SEK',1300),
      lineas:P.lineasCuentas('{pais} · se lanza en {nombre}', [['🇸🇪 Suecia','HF $& Sweden'],['🇳🇴 Noruega','HF Norway']])}));"""
    r = subprocess.run([shutil.which("node"), "-e", arnes, ruta], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    d = _json.loads(r.stdout)
    assert d["g"] == [[200, 50], [200]]
    assert d["una"] is None and d["dos"] == "partes" and d["dosGrande"] is None and d["chico"] == "total"
    assert d["desigual"] == "partes"           # 2 100 + 700: la parte de Suecia no llega a 1 300
    assert d["lineas"] == ["🇸🇪 Suecia · se lanza en HF $& Sweden", "🇳🇴 Noruega · se lanza en HF Norway"]


def test_la_gestion_dice_la_cuenta_de_cada_pais(app_sek, base_temporal):
    import experimentos as ex
    from tests.test_rutas_experimentos import _resultados
    _sembrar()
    eid = ex.crear("acme", "Chanclas", PAISES, "OUTCOME_TRAFFIC", 7, 2800.0, URL, "SEK")
    html = _resultados(app_sek["c"], exp=eid)
    assert "HappyFlops Sweden" in html and "HappyFlops Norway" in html


# ---------- el detalle de Meta: cada campaña en su cuenta ----------

def test_el_detalle_pide_cada_campana_en_su_cuenta(monkeypatch, base_temporal):
    import json as _json

    import experimentos as ex
    import lanzador
    import meta_detalle as md
    monkeypatch.setattr(lanzador.meta_conexion, "credenciales_ads",
                        lambda c: {"token": "TOKEN", "ad_account_id": DEF, "page_id": "2"})
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_1")
    eid = ex.crear("acme", "Chanclas", PAISES, "OUTCOME_TRAFFIC", 7, 2800.0, URL, "SEK")
    ep1 = ex.agregar_pieza("acme", eid, clon, "NO")
    ep2 = ex.agregar_pieza("acme", eid, clon, "SE")
    ex.actualizar_pieza("acme", ep1, meta_ad_id="ad_1")
    ex.actualizar_pieza("acme", ep2, meta_ad_id="ad_2")
    ex.actualizar("acme", eid, meta_campaign_id="cmp_1")
    ex.actualizar_pais("acme", eid, "NO", meta_campaign_id="cmp_1")
    ex.actualizar_pais("acme", eid, "SE", meta_campaign_id="cmp_2")
    pedidos = []

    def llamar(metodo, edge, payload=None, params=None, dry_run=False):
        campana = _json.loads(params["filtering"])[0]["value"]
        pedidos.append((edge, campana))
        return {"data": []}
    monkeypatch.setattr(md.auth, "llamar", llamar)
    r = md.refrescar_detalle("acme", eid, hoy=date(2026, 10, 16))
    assert r["errores"] == {}
    assert {(e, c) for e, c in pedidos} == {("act_1/insights", "cmp_1"), ("act_2/insights", "cmp_2")}


# ---------- la pantalla: el reparto del tope en JS es el mismo que el del lanzador ----------

@pytest.mark.skipif(not __import__("shutil").which("node"), reason="sin Node no se corre el JS")
def test_el_reparto_del_tope_en_js_da_lo_mismo_que_el_lanzador():
    """De esta cuenta depende que la pantalla diga «Máximo que puede gastar» (cada parte con tope duro) o «Presupuesto
    planeado»: tiene que ser la de `lanzador._repartir_tope`."""
    import json as _json
    import os
    import random
    import shutil
    import subprocess

    import lanzador as lz
    azar = random.Random(20261016)
    casos = [(2800.0, [[300.0], [100.0]], "SEK"), (3033.38, [[333.33], [100.01]], "SEK"), (20.0, [[1.0], [1.0], [1.0]], "USD"),
             (84028.0, [[4001.0, 4000.0], [4003.0]], "COP"), (105.0, [[15.0], [0.0]], "SEK"), (147.0, [[7.77, 3.33], [9.99]], "EUR"),
             (5000.0, [[300.0, 100.0]], "SEK")]
    for _ in range(300):
        moneda = azar.choice(["SEK", "NOK", "COP", "USD", "EUR", "CLP", "MXN"])
        dec = 0 if moneda in ("COP", "CLP") else 2
        grupos = [[round(azar.uniform(1, 5000), dec) for _ in range(azar.randint(1, 3))] for _ in range(azar.randint(1, 4))]
        casos.append((round(azar.uniform(10, 900000), dec), grupos, moneda))
    arnes = ("const P=require(process.argv[1]); let d='';process.stdin.on('data',c=>d+=c).on('end',()=>{"
             "console.log(JSON.stringify(JSON.parse(d).map(c=>P.partesTope(c[0],c[1],c[2]))));});")
    ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "presupuesto_exp.js")
    r = subprocess.run([shutil.which("node"), "-e", arnes, ruta], input=_json.dumps(casos), capture_output=True,
                       text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    for (tope, grupos, moneda), js in zip(casos, _json.loads(r.stdout)):
        esperado = [lz.monedas_meta.desde_unidad_meta(x, moneda)
                    for x in lz._repartir_tope(tope, [[{"presupuesto_dia": d} for d in g] for g in grupos], moneda)]
        assert js == pytest.approx(esperado, abs=1e-9), (tope, grupos, moneda)


# ---------- reparto vivo del tope (decisión de quien orquesta, 2026-10-16) ----------
# Con varias cuentas, cambiar el diario de un país (a mano o al escalar) recalcula el reparto del tope y actualiza el
# spend_cap de cada campaña: cada parte = max(lo ya gastado hacia arriba, su parte proporcional), un tope que ya está en
# Meta no baja del mínimo de su cuenta y la suma nunca pasa el tope del experimento; si no cabe, no se sube el diario.

def _holgado(dos, min_suecia=None):
    """Experimento con margen: 300 + 100 SEK al día por 7 días (2 800) con un tope de 4 200, lanzado y activo.
    Partes al lanzar: 3 150 (Noruega) y 1 050 (Suecia)."""
    ex, lz, meta = dos["ex"], dos["lz"], dos["meta"]
    if min_suecia is not None:
        meta.cuentas[SUECIA] = {**meta.cuenta, "min_campaign_group_spend_cap": str(min_suecia)}
    eid = ex.crear("acme", "Holgado", PAISES, "OUTCOME_TRAFFIC", 7, 4200.0, URL, "SEK")
    ex.agregar_pieza("acme", eid, dos["clon"], "NO")
    ex.agregar_pieza("acme", eid, dos["clon"], "SE")
    lz.lanzar("acme", eid)
    lz.cambiar_estado("acme", eid, "ACTIVE")
    meta.llamadas.clear()
    meta.posts.clear()
    meta.leidas.clear()
    p = _por_pais(ex, eid)
    return eid, p["NO"]["meta_campaign_id"], p["SE"]["meta_campaign_id"]


def _topes_mandados(meta):
    return [(edge, pl["spend_cap"]) for edge, pl in meta.posts if "spend_cap" in pl]


def _diarios_mandados(meta):
    return [kw["centavos"] for t, kw in meta.llamadas if t == "presupuesto"]


def test_subir_el_diario_de_un_pais_reparte_otra_vez_el_tope(dos):
    ex, lz, meta = dos["ex"], dos["lz"], dos["meta"]
    eid, c_no, c_se = _holgado(dos)
    assert meta.topes[c_no] == 315000 and meta.topes[c_se] == 105000
    lz.cambiar_presupuesto_pais("acme", eid, "SE", 200.0)
    # 4 200 repartido 300 : 200; primero baja el que baja (en cada paso la suma no pasa el tope), después sube el otro
    assert _topes_mandados(meta) == [(c_no, 252000), (c_se, 168000)]
    assert meta.topes[c_no] + meta.topes[c_se] <= lz.centavos(4200.0, "SEK")
    assert _diarios_mandados(meta) == [20000]
    assert _por_pais(ex, eid)["SE"]["presupuesto_dia"] == 200.0
    # cada cuenta a la que se le manda un tope pasa por comprobar_moneda
    assert sorted(set(meta.leidas)) == [DEF, SUECIA]
    assert any("HappyFlops Sweden" in e["mensaje"] and "HappyFlops Norway" in e["mensaje"]
               for e in ex.eventos("acme", eid) if e["tipo"] == "presupuesto")


def test_escalar_un_pais_tambien_reparte_el_tope(dos):
    ex, lz, meta = dos["ex"], dos["lz"], dos["meta"]
    eid, c_no, c_se = _holgado(dos)
    assert lz.escalar_pais("acme", eid, "SE", 100) == 200.0
    assert _topes_mandados(meta) == [(c_no, 252000), (c_se, 168000)]


def test_si_lo_gastado_no_deja_repartir_no_se_sube_el_diario(dos):
    ex, lz, meta = dos["ex"], dos["lz"], dos["meta"]
    eid, c_no, c_se = _holgado(dos)
    meta.gastos[c_no] = (3000.0, 0.0)     # Noruega ya gastó más que su parte nueva (2 520)
    with pytest.raises(ValueError, match="no alcanza"):
        lz.cambiar_presupuesto_pais("acme", eid, "SE", 200.0)
    assert _topes_mandados(meta) == [] and _diarios_mandados(meta) == []
    assert _por_pais(ex, eid)["SE"]["presupuesto_dia"] == 100.0


def test_bajar_un_diario_cuando_no_cabe_baja_el_diario_y_deja_los_topes(dos):
    ex, lz, meta = dos["ex"], dos["lz"], dos["meta"]
    eid, c_no, c_se = _holgado(dos)
    meta.gastos[c_no] = (3200.0, 0.0)     # la parte nueva de Noruega sería 3 000
    lz.cambiar_presupuesto_pais("acme", eid, "NO", 250.0)
    assert _topes_mandados(meta) == [] and _diarios_mandados(meta) == [25000]
    assert _por_pais(ex, eid)["NO"]["presupuesto_dia"] == 250.0
    assert meta.topes[c_no] == 315000 and meta.topes[c_se] == 105000
    assert any("se dejó como estaba" in e["mensaje"] for e in ex.eventos("acme", eid))


def test_un_tope_que_quedaria_bajo_el_minimo_de_su_cuenta_no_deja_subir(dos):
    """El tope de Suecia (1 050) ya está en Meta y su mínimo es 1 000: subir Noruega a 400 lo dejaría en 840."""
    ex, lz, meta = dos["ex"], dos["lz"], dos["meta"]
    eid, c_no, c_se = _holgado(dos, min_suecia=100000)
    assert meta.topes[c_se] == 105000
    with pytest.raises(ValueError, match="no alcanza"):
        lz.cambiar_presupuesto_pais("acme", eid, "NO", 400.0)
    assert _topes_mandados(meta) == [] and _diarios_mandados(meta) == []


def test_una_campana_sin_tope_que_llega_al_minimo_estrena_su_tope(dos):
    ex, lz, meta = dos["ex"], dos["lz"], dos["meta"]
    eid, c_no, c_se = _holgado(dos, min_suecia=120000)
    assert meta.topes[c_se] is None              # 1 050 < 1 200: lanzó sin tope
    lz.cambiar_presupuesto_pais("acme", eid, "SE", 200.0)
    assert _topes_mandados(meta) == [(c_no, 252000), (c_se, 168000)]


def test_una_campana_sin_tope_que_sigue_bajo_el_minimo_sigue_sin_tope(dos):
    ex, lz, meta = dos["ex"], dos["lz"], dos["meta"]
    eid, c_no, c_se = _holgado(dos, min_suecia=200000)
    lz.cambiar_presupuesto_pais("acme", eid, "SE", 150.0)
    assert _topes_mandados(meta) == [(c_no, 280000)]     # Suecia: 1 400 < 2 000, sigue con fecha de fin y vigilancia
    assert _diarios_mandados(meta) == [15000]


def test_un_tope_que_meta_guarda_distinto_pausa_la_campana_y_no_cambia_el_diario(dos):
    ex, lz, meta = dos["ex"], dos["lz"], dos["meta"]
    eid, c_no, c_se = _holgado(dos)
    meta.tope_distinto = {c_se}           # Noruega baja bien; Suecia, la que sube, queda distinta
    with pytest.raises(lz.PresupuestoNoCoincide, match="quedó en pausa"):
        lz.cambiar_presupuesto_pais("acme", eid, "SE", 200.0)
    assert ("estado", {"oid": c_se, "status": "PAUSED"}) in meta.llamadas
    assert _diarios_mandados(meta) == [] and _por_pais(ex, eid)["SE"]["presupuesto_dia"] == 100.0
    # la campaña quedó en pausa en Meta: su país también aquí, y la bitácora dice el tope que sí cambió
    assert _por_pais(ex, eid)["SE"]["estado"] == "pausado" and _por_pais(ex, eid)["NO"]["estado"] == "activo"
    eventos = [e["mensaje"] for e in ex.eventos("acme", eid) if e["tipo"] == "presupuesto"]
    assert any("tope distinto" in m for m in eventos)
    assert any("HappyFlops Norway" in m and "2.520" in m for m in eventos)
    assert "repartiendo" not in (ex.obtener("acme", eid)["extra"] or {})


def test_un_tope_distinto_que_tampoco_se_puede_pausar_lo_dice(dos):
    ex, lz, meta = dos["ex"], dos["lz"], dos["meta"]
    eid, c_no, c_se = _holgado(dos)
    meta.tope_distinto = {c_se}
    original = meta._id

    def no_pausa(tipo, **kw):
        if tipo == "estado" and kw.get("oid") == c_se:
            raise RuntimeError("Meta no contestó")
        return original(tipo, **kw)
    meta._id = no_pausa
    _parchar(lz, meta, dos["monkeypatch"])
    with pytest.raises(lz.PresupuestoNoCoincide, match="NO se pudo pausar"):
        lz.cambiar_presupuesto_pais("acme", eid, "SE", 200.0)
    assert _por_pais(ex, eid)["SE"]["estado"] == "activo"     # sigue «activo»: la vigilancia lo sigue mirando


def test_el_margen_de_un_dia_cuenta_como_gastado(dos):
    """Lo gastado viene de los insights, con retraso: se le suma un día del diario de la campaña. Noruega reporta
    2 300 y su parte nueva sería 2 520: sin margen cabría, con los 300 del día no."""
    ex, lz, meta = dos["ex"], dos["lz"], dos["meta"]
    eid, c_no, c_se = _holgado(dos)
    meta.gastos[c_no] = (2300.0, 0.0)
    with pytest.raises(ValueError, match="no alcanza"):
        lz.cambiar_presupuesto_pais("acme", eid, "SE", 200.0)
    assert _topes_mandados(meta) == []


def test_primero_bajan_despues_estrenan_y_al_final_suben(dos):
    """Noruega lanzó sin tope (su mínimo es 3 200) y Suecia con 1 050: al subir Noruega a 400, Suecia baja a 840 ANTES
    de que Noruega estrene su tope de 3 360; si el segundo envío fallara, la suma no pasaría el total."""
    ex, lz, meta = dos["ex"], dos["lz"], dos["meta"]
    meta.cuentas[DEF] = {**meta.cuenta, "min_campaign_group_spend_cap": "320000"}
    eid, c_no, c_se = _holgado(dos)
    assert meta.topes[c_no] is None and meta.topes[c_se] == 105000
    lz.cambiar_presupuesto_pais("acme", eid, "NO", 400.0)
    assert _topes_mandados(meta) == [(c_se, 84000), (c_no, 336000)]


def test_dos_cambios_a_la_vez_no_reparten_el_tope_dos_veces(dos):
    """Un reparto a la vez por experimento, también entre la web y el worker: con otro cambio en curso, subir se niega
    y bajar sigue sin tocar los topes. Una marca vieja no frena a nadie y la marca se suelta al terminar."""
    import db
    ex, lz, meta = dos["ex"], dos["lz"], dos["meta"]
    eid, c_no, c_se = _holgado(dos)
    ex.actualizar_extra("acme", eid, lambda extra: {**extra, "repartiendo": {"en": db.ahora(), "token": "otro"}})
    with pytest.raises(ValueError, match="en curso"):
        lz.cambiar_presupuesto_pais("acme", eid, "SE", 200.0)
    lz.cambiar_presupuesto_pais("acme", eid, "NO", 250.0)
    assert _topes_mandados(meta) == [] and _diarios_mandados(meta) == [25000]
    assert any("en curso" in e["mensaje"] for e in ex.eventos("acme", eid))
    assert ex.obtener("acme", eid)["extra"]["repartiendo"]["token"] == "otro"     # la ajena no se toca
    ex.actualizar_extra("acme", eid, lambda extra: {**extra, "repartiendo": {"en": "2026-01-01T00:00:00", "token": "x"}})
    lz.cambiar_presupuesto_pais("acme", eid, "SE", 200.0)
    assert _topes_mandados(meta)
    assert "repartiendo" not in ex.obtener("acme", eid)["extra"]


def test_bajar_un_diario_no_se_frena_si_otra_cuenta_salio_del_proyecto(dos):
    """Bajar nunca se frena por el reparto: Suecia salió del proyecto, Noruega baja igual y los topes quedan."""
    from meta_rendimiento import cuentas
    ex, lz, meta = dos["ex"], dos["lz"], dos["meta"]
    eid, c_no, c_se = _holgado(dos)
    cuentas.elegir("acme", [])
    lz.cambiar_presupuesto_pais("acme", eid, "NO", 250.0)
    assert _topes_mandados(meta) == [] and _diarios_mandados(meta) == [25000]
    assert _por_pais(ex, eid)["NO"]["presupuesto_dia"] == 250.0
    assert any("se dejó como estaba" in e["mensaje"] for e in ex.eventos("acme", eid))
    with pytest.raises(ValueError):
        lz.cambiar_presupuesto_pais("acme", eid, "NO", 260.0)     # subir sí se frena


def test_el_reparto_no_manda_un_tope_a_una_cuenta_que_cambio_de_moneda(dos):
    """Subir Noruega toca el tope de Suecia: Suecia también pasa por comprobar_moneda antes de recibirlo."""
    ex, lz, meta = dos["ex"], dos["lz"], dos["meta"]
    eid, c_no, c_se = _holgado(dos)
    meta.cuentas[SUECIA] = {**meta.cuenta, "currency": "EUR"}
    with pytest.raises(lz.PresupuestoNoCoincide):
        lz.cambiar_presupuesto_pais("acme", eid, "NO", 350.0)
    assert _topes_mandados(meta) == [] and _diarios_mandados(meta) == []


def test_un_experimento_de_una_sola_cuenta_no_reparte_nada(dos):
    ex, lz, meta = dos["ex"], dos["lz"], dos["meta"]
    viejo = ex.crear("acme", "Viejo", [{k: v for k, v in p.items() if k != "ad_account_id"} for p in PAISES],
                     "OUTCOME_TRAFFIC", 7, 4200.0, URL, "SEK")
    ex.agregar_pieza("acme", viejo, dos["clon"], "NO")
    ex.agregar_pieza("acme", viejo, dos["clon"], "SE")
    lz.lanzar("acme", viejo)
    lz.cambiar_estado("acme", viejo, "ACTIVE")
    meta.posts.clear()
    gets = []
    original = meta._llamar

    def llamar(metodo, edge, payload=None, params=None, dry_run=False):
        if metodo == "GET":
            gets.append(edge)
        return original(metodo, edge, payload, params, dry_run)
    meta._llamar = llamar
    _parchar(lz, meta, dos["monkeypatch"])
    lz.cambiar_presupuesto_pais("acme", viejo, "SE", 200.0)
    assert _topes_mandados(meta) == [] and not [g for g in gets if g.endswith("/insights")]


# ---------- Pixel y app: usables desde cada cuenta antes de crear nada ----------

def _ventas(dos, monkeypatch):
    ex, lz = dos["ex"], dos["lz"]
    monkeypatch.setattr(lz.meta_conexion, "estado_pixel", lambda c, solo_cache=False: {"estado": "ok", "pixel_id": "px_9"})
    eid = ex.crear("acme", "Ventas", PAISES, "OUTCOME_SALES", 7, 2800.0, URL, "SEK", atribucion="pixel")
    ex.agregar_pieza("acme", eid, dos["clon"], "NO")
    ex.agregar_pieza("acme", eid, dos["clon"], "SE")
    return eid


def test_compras_con_un_pixel_que_otra_cuenta_no_ve_no_lanza_nada(dos, monkeypatch):
    ex, lz, meta = dos["ex"], dos["lz"], dos["meta"]
    eid = _ventas(dos, monkeypatch)
    meta.pixeles = {DEF: ["px_9"], SUECIA: ["px_1"]}
    with pytest.raises(ValueError) as e:
        lz.lanzar("acme", eid)
    assert "HappyFlops Sweden" in str(e.value) and "px_9" in str(e.value) and "Business" in str(e.value)
    assert not [t for t, _ in meta.llamadas if t in ("campaign", "adset", "ad")]
    assert ex.obtener("acme", eid)["estado"] == "error"
    meta.pixeles[SUECIA] = ["px_1", "px_9"]
    lz.lanzar("acme", eid)
    assert {kw["promoted_object"]["pixel_id"] for _, kw, _ in _creados(meta, "adset")} == {"px_9"}


def test_compras_en_una_sola_cuenta_no_pregunta_nada_mas(dos, monkeypatch):
    ex, lz, meta = dos["ex"], dos["lz"], dos["meta"]
    monkeypatch.setattr(lz.meta_conexion, "estado_pixel", lambda c, solo_cache=False: {"estado": "ok", "pixel_id": "px_9"})
    eid = ex.crear("acme", "Ventas", [{k: v for k, v in p.items() if k != "ad_account_id"} for p in PAISES],
                   "OUTCOME_SALES", 7, 2800.0, URL, "SEK", atribucion="pixel")
    ex.agregar_pieza("acme", eid, dos["clon"], "NO")
    ex.agregar_pieza("acme", eid, dos["clon"], "SE")
    gets = []
    original = meta._llamar

    def llamar(metodo, edge, payload=None, params=None, dry_run=False):
        gets.append(edge)
        return original(metodo, edge, payload, params, dry_run)
    meta._llamar = llamar
    _parchar(lz, meta, dos["monkeypatch"])
    lz.lanzar("acme", eid)
    assert not [g for g in gets if g.endswith(("/adspixels", "/advertisable_applications"))]


def test_una_app_que_otra_cuenta_no_puede_anunciar_no_lanza_nada(dos, monkeypatch):
    ex, lz, meta = dos["ex"], dos["lz"], dos["meta"]
    monkeypatch.setattr(lz.meta_conexion, "cargar_app_anunciada", lambda c: "12345")
    datos = dict(nombre="App", paises=PAISES, objetivo_meta="OUTCOME_APP_PROMOTION", dias=7, tope_total=2800.0,
                 destino_url="https://play.google.com/store/apps/details?id=com.hf", moneda="SEK",
                 app={"android_url": "https://play.google.com/store/apps/details?id=com.hf", "app_id": "12345"})
    eid = ex.crear_con_piezas("acme", datos, [(dos["clon"], "NO"), (dos["clon"], "SE")])
    meta.apps = {DEF: ["12345"]}
    with pytest.raises(ValueError) as e:
        lz.lanzar("acme", eid)
    assert "HappyFlops Sweden" in str(e.value) and "12345" in str(e.value)
    assert not [t for t, _ in meta.llamadas if t in ("campaign", "adset", "ad")]
    meta.apps[SUECIA] = ["12345"]
    lz.lanzar("acme", eid)
    assert ex.obtener("acme", eid)["estado"] == "pausado"


# ---------- el detalle de Meta: los errores de dos campañas se juntan ----------

def test_el_detalle_junta_los_errores_de_las_dos_campanas(monkeypatch, base_temporal):
    import json as _json

    import experimentos as ex
    import lanzador
    import meta_detalle as md
    monkeypatch.setattr(lanzador.meta_conexion, "credenciales_ads",
                        lambda c: {"token": "TOKEN", "ad_account_id": DEF, "page_id": "2"})
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_1")
    eid = ex.crear("acme", "Chanclas", PAISES, "OUTCOME_TRAFFIC", 7, 2800.0, URL, "SEK")
    for pais, ad, cmp in (("NO", "ad_1", "cmp_1"), ("SE", "ad_2", "cmp_2")):
        ep = ex.agregar_pieza("acme", eid, clon, pais)
        ex.actualizar_pieza("acme", ep, meta_ad_id=ad)
        ex.actualizar_pais("acme", eid, pais, meta_campaign_id=cmp)
    ex.actualizar("acme", eid, meta_campaign_id="cmp_1")

    def llamar(metodo, edge, payload=None, params=None, dry_run=False):
        campana = _json.loads(params["filtering"])[0]["value"]
        if "time_increment" in params:
            raise RuntimeError(f"Meta falló en el diario de {campana}")
        return {"data": []}
    monkeypatch.setattr(md.auth, "llamar", llamar)
    r = md.refrescar_detalle("acme", eid, hoy=date(2026, 10, 16))
    assert "cmp_1" in r["errores"]["diario"] and "cmp_2" in r["errores"]["diario"]
    assert set(r["errores"]) == {"diario"}


# ---------- ronda 3 de guardian-gasto: la marca se vuelve a mirar antes de cada tope; nada grave se traga ----------
# Reproducciones de guardian-gasto (scratchpad g148_head_r2/tests/test_g148_repro.py), cambiadas para exigir lo bueno.

def test_r1_otro_reparto_que_toma_la_marca_corta_el_primero_antes_de_su_siguiente_tope(dos):
    """La web sube SE a 200; entre su primer tope (Noruega baja) y el segundo (Suecia sube) pasa más que la ventana y el
    worker, en OTRO proceso (su propio candado), toma la marca y escala NO a 400. La web vuelve a mirar la marca antes
    de mandar su segundo tope, ve que ya no es suya y corta: la suma de los topes en Meta nunca pasa el total."""
    import threading
    ex, lz, meta = dos["ex"], dos["lz"], dos["meta"]
    eid, c_no, c_se = _holgado(dos)
    dos["monkeypatch"].setattr(lz, "_LOCK", threading.RLock())   # otro proceso = otro candado: aquí, reentrante
    real = lz._renovar_marca_reparto
    llamadas = []

    def renovar(cliente, experimento_id, token):
        llamadas.append(token)
        if len(llamadas) == 3:                     # la web, justo antes de mandar su segundo tope
            ventana = lz._VENTANA_REPARTO_S
            lz._VENTANA_REPARTO_S = -1             # su marca venció (Meta tardó más que la ventana)
            try:
                lz.cambiar_presupuesto_pais("acme", eid, "NO", 400.0)   # el worker (escalar) en su proceso
            finally:
                lz._VENTANA_REPARTO_S = ventana
        return real(cliente, experimento_id, token)
    dos["monkeypatch"].setattr(lz, "_renovar_marca_reparto", renovar)
    with pytest.raises(lz.RepartoCortado, match="Se cortó"):
        lz.cambiar_presupuesto_pais("acme", eid, "SE", 200.0)   # la web
    assert meta.topes[c_no] + meta.topes[c_se] <= lz.centavos(4200.0, "SEK")
    assert (c_se, 168000) not in _topes_mandados(meta)
    p = _por_pais(ex, eid)
    assert p["SE"]["presupuesto_dia"] == 100.0 and p["NO"]["presupuesto_dia"] == 400.0
    assert "repartiendo" not in (ex.obtener("acme", eid)["extra"] or {})


def test_r1_si_una_llamada_dura_mas_que_la_ventana_y_los_topes_pasan_el_total_se_pausa_todo(dos, monkeypatch):
    """La reproducción exacta de guardian-gasto: el worker entra EN MEDIO del POST del segundo tope de la web (una
    llamada más larga que la ventana, que no debería pasar). La web lo nota al volver a mirar la marca después del
    envío, lee los topes en Meta (3 360 + 1 680 > 4 200) y pausa todas las campañas: nada gasta por encima del tope."""
    import threading
    ex, lz, meta = dos["ex"], dos["lz"], dos["meta"]
    eid, c_no, c_se = _holgado(dos)
    avisos = []
    monkeypatch.setattr(lz.notificaciones, "avisar", lambda c, tipo, a, b: avisos.append(tipo))
    monkeypatch.setattr(lz.notificaciones, "avisar_admin", lambda tipo, a, b, cliente="": avisos.append(tipo))
    dos["monkeypatch"].setattr(lz, "_LOCK", threading.RLock())
    original = meta._llamar
    hecho = []

    def llamar(metodo, edge, payload=None, params=None, dry_run=False):
        if metodo == "POST" and edge == c_se and (payload or {}).get("spend_cap") == 168000 and not hecho:
            hecho.append(1)
            ventana = lz._VENTANA_REPARTO_S
            lz._VENTANA_REPARTO_S = -1
            try:
                lz.cambiar_presupuesto_pais("acme", eid, "NO", 400.0)
            finally:
                lz._VENTANA_REPARTO_S = ventana
        return original(metodo, edge, payload, params, dry_run)
    meta._llamar = llamar
    _parchar(lz, meta, dos["monkeypatch"])
    meta.llamadas.clear()
    with pytest.raises(lz.RepartoCortado, match="se pausaron todas sus campañas"):
        lz.cambiar_presupuesto_pais("acme", eid, "SE", 200.0)
    pausados = [kw["oid"] for t, kw in meta.llamadas if t == "estado" and kw["status"] == "PAUSED"]
    assert c_no in pausados and c_se in pausados
    assert ex.obtener("acme", eid)["estado"] == "pausado" and "tope" in avisos


def test_r1_la_ventana_de_la_marca_es_mayor_que_el_peor_caso_entre_dos_renovaciones():
    import lanzador as lz
    # del plan al primer tope: 3 lecturas por cuenta (7 cuentas, 30 s cada una); entre topes: un POST (60 s) + su lectura
    assert lz._VENTANA_REPARTO_S > 7 * 3 * 30 and lz._VENTANA_REPARTO_S > 60 + 30


def _sin_pausa_en(dos, cid):
    meta = dos["meta"]
    original = meta._id

    def no_pausa(tipo, **kw):
        if tipo == "estado" and kw.get("oid") == cid:
            raise RuntimeError("Meta no contestó")
        return original(tipo, **kw)
    meta._id = no_pausa
    _parchar(dos["lz"], meta, dos["monkeypatch"])


def test_r2_bajar_con_un_tope_distinto_que_no_se_pudo_pausar_llega_a_la_persona(dos, monkeypatch):
    ex, lz, meta = dos["ex"], dos["lz"], dos["meta"]
    eid, c_no, c_se = _holgado(dos)
    avisos = []
    monkeypatch.setattr(lz.notificaciones, "avisar", lambda c, tipo, a, b: avisos.append(("proyecto", tipo)))
    monkeypatch.setattr(lz.notificaciones, "avisar_admin", lambda tipo, a, b, cliente="": avisos.append(("admin", tipo)))
    meta.tope_distinto = {c_se}
    _sin_pausa_en(dos, c_se)
    with pytest.raises(lz.PresupuestoNoCoincide) as e:
        lz.cambiar_presupuesto_pais("acme", eid, "NO", 250.0)
    assert "NO se pudo pausar" in str(e.value) and "bajó" in str(e.value)
    assert _por_pais(ex, eid)["NO"]["presupuesto_dia"] == 250.0      # bajar el diario sí se hizo
    assert ("proyecto", "tope") in avisos and ("admin", "tope") in avisos
    eventos = [m["mensaje"] for m in ex.eventos("acme", eid)]
    assert not any("se dejó como estaba" in m for m in eventos)
    assert any("solo cambiaron" in m and "HappyFlops Norway" in m for m in eventos)


def test_r2b_bajar_que_si_movio_un_tope_dice_cuales(dos):
    ex, lz, meta = dos["ex"], dos["lz"], dos["meta"]
    eid, c_no, c_se = _holgado(dos)
    original = meta._llamar

    def llamar(metodo, edge, payload=None, params=None, dry_run=False):
        if metodo == "POST" and edge == c_se and "spend_cap" in (payload or {}):
            raise RuntimeError("Meta Ads (c_se) respondió 400: algo")
        return original(metodo, edge, payload, params, dry_run)
    meta._llamar = llamar
    _parchar(lz, meta, dos["monkeypatch"])
    lz.cambiar_presupuesto_pais("acme", eid, "NO", 250.0)
    eventos = [e["mensaje"] for e in ex.eventos("acme", eid)]
    assert meta.topes[c_no] != 315000
    assert not any("se dejó como estaba" in m for m in eventos)
    assert any("solo cambiaron" in m and "HappyFlops Norway" in m for m in eventos)
    assert _por_pais(ex, eid)["NO"]["presupuesto_dia"] == 250.0


def test_subir_con_topes_movidos_y_el_diario_rechazado_lo_dice(dos):
    ex, lz, meta = dos["ex"], dos["lz"], dos["meta"]
    eid, c_no, c_se = _holgado(dos)
    meta.fallar_en = "presupuesto"
    with pytest.raises(RuntimeError) as e:
        lz.cambiar_presupuesto_pais("acme", eid, "SE", 200.0)
    assert "ya se habían movido" in str(e.value) and "HappyFlops Norway" in str(e.value)
    assert _por_pais(ex, eid)["SE"]["presupuesto_dia"] == 100.0


def test_un_reintento_que_ya_creo_cosas_no_dice_que_no_se_creo_nada(dos, monkeypatch):
    ex, lz, meta = dos["ex"], dos["lz"], dos["meta"]
    eid = _ventas(dos, monkeypatch)
    meta.pixeles = {DEF: ["px_9"], SUECIA: ["px_9"]}
    meta.fallar_en = "ad"
    with pytest.raises(RuntimeError):
        lz.lanzar("acme", eid)
    meta.fallar_en = None
    meta.pixeles[SUECIA] = []          # entre un intento y otro dejaron de compartirle el Pixel
    with pytest.raises(ValueError) as e:
        lz.lanzar("acme", eid)
    assert "No se creó nada" not in str(e.value) and "sigue en pausa" in str(e.value)
