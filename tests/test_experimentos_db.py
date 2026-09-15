import pytest
import sqlalchemy as sa

PAISES = [{"pais": "CO", "idioma": "es", "presupuesto_dia": 20000.0},
          {"pais": "MX", "idioma": "es", "presupuesto_dia": 150.0}]


def _pieza(db, cliente="acme", tipo="final", estado="listo", pais="CO", idioma="es", legado="cf_1__es_CO", url="https://r2/f.mp4"):
    with db.conectar() as con:
        ahora = db.ahora()
        cid = con.execute(db.concepto.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, origen="manual", legado_id="cf_1", extra={})).inserted_primary_key[0]
        return con.execute(db.pieza.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, concepto_id=cid, tipo=tipo, estado=estado,
            pais=pais, idioma=idioma, url_video=url, legado_id=legado, extra={})).inserted_primary_key[0]


def test_crear_y_cargar_experimento(base_temporal):
    import experimentos as ex
    eid = ex.crear("acme", "Cojín abrazable", PAISES, "OUTCOME_TRAFFIC", 7, 500000.0, "https://tienda.co/p", "COP")
    lista = ex.cargar("acme")
    assert [e["id"] for e in lista] == [eid]
    e = lista[0]
    assert e["estado"] == "armando" and e["modo"] == "manual" and e["moneda"] == "COP"
    assert e["paises"][0] == {"pais": "CO", "idioma": "es", "presupuesto_dia": 20000.0, "meta_adset_id": None, "estado": "en_cola"}
    assert e["edad_min"] == 18 and e["edad_max"] == 65 and e["piezas"] == [] and e["resumen"]["total"] == 0
    assert ex.cargar("otro") == []
    assert ex.obtener("acme", 999) is None


def test_cargar_excluye_legado(base_temporal):
    import ads
    import experimentos as ex
    ads.crear("acme", "creative_flow", "cf_9", "https://r2/v.mp4", "video", "suelto")
    assert ex.cargar("acme") == []


def test_agregar_quitar_piezas_y_unicidad(base_temporal):
    import experimentos as ex
    pid = _pieza(base_temporal)
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ep1 = ex.agregar_pieza("acme", eid, pid, "CO")
    assert ex.agregar_pieza("acme", eid, pid, "CO") == ep1
    ep2 = ex.agregar_pieza("acme", eid, pid, "MX")
    assert ep1 != ep2
    piezas = ex.piezas("acme", eid)
    assert [p["pais"] for p in piezas] == ["CO", "MX"]
    assert piezas[0]["url_video"] == "https://r2/f.mp4" and piezas[0]["metricas"] == {} and piezas[0]["estado"] == "en_cola"
    assert ex.quitar_pieza("acme", eid, ep2) is True
    ex.actualizar_pieza("acme", ep1, meta_ad_id="120", estado="pausado")
    assert ex.quitar_pieza("acme", eid, ep1) is False  # ya está en Meta
    assert ex.quitar_pieza("otro", eid, ep1) is False


def test_agregar_pieza_rechaza_cruce_de_cliente(base_temporal):
    """M8: agregar_pieza debe verificar que el experimento sea de `cliente`
    (y no legado) y que la pieza también lo sea — sin esto, un llamador que
    se saltara la validación de la ruta podría meter una pieza de otro
    cliente a un experimento ajeno."""
    import ads
    import experimentos as ex
    pid_acme = _pieza(base_temporal, cliente="acme")
    pid_otro = _pieza(base_temporal, cliente="otro")
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    # Experimento inexistente.
    assert ex.agregar_pieza("acme", 999999, pid_acme, "CO") is None
    # Experimento de otro cliente.
    assert ex.agregar_pieza("otro", eid, pid_otro, "CO") is None
    # Pieza de otro cliente sobre un experimento propio.
    assert ex.agregar_pieza("acme", eid, pid_otro, "CO") is None
    assert ex.piezas("acme", eid) == []
    # Experimento legado ("Anuncios sueltos", visto por ads.py): agregar_pieza
    # no debe tocarlo, es de otro mundo (ver docstring del módulo).
    ads.crear("acme", "creative_flow", "cf_legado", "https://r2/v.mp4", "video", "suelto")
    import db as db_mod
    with base_temporal.conectar() as con:
        eid_legado = con.execute(sa.select(db_mod.experimento.c.id).where(
            db_mod.experimento.c.cliente == "acme", db_mod.experimento.c.legado.is_(True))).scalar()
    assert ex.agregar_pieza("acme", eid_legado, pid_acme, "CO") is None
    # Camino feliz de control: sí funciona con cliente y pieza correctos.
    assert ex.agregar_pieza("acme", eid, pid_acme, "CO") is not None
    assert [p["pieza_id"] for p in ex.piezas("acme", eid)] == [pid_acme]


def test_actualizar_pais_y_experimento(base_temporal):
    import experimentos as ex
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ex.actualizar_pais("acme", eid, "MX", meta_adset_id="777", estado="pausado")
    ex.actualizar("acme", eid, estado="pausado", meta_campaign_id="555", gasto_acumulado=12.5)
    e = ex.obtener("acme", eid)
    assert e["paises"][1]["meta_adset_id"] == "777" and e["paises"][1]["estado"] == "pausado"
    assert e["paises"][0]["meta_adset_id"] is None
    assert e["estado"] == "pausado" and e["meta_campaign_id"] == "555" and e["gasto_acumulado"] == 12.5
    with pytest.raises(ValueError):
        ex.actualizar("acme", eid, legado=True)


def test_snapshot_y_ultima_metrica(base_temporal):
    import experimentos as ex
    pid = _pieza(base_temporal)
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ep = ex.agregar_pieza("acme", eid, pid, "CO")
    assert ex.ultima_metrica(ep) == {}
    ex.snapshot(ep, {"impresiones": 100, "clics_enlace": 5, "gasto": 3.5, "ctr": 5.0, "estado_meta_texto": "Activo"})
    ex.snapshot(ep, {"impresiones": 250, "clics_enlace": 9, "gasto": 8.0, "ctr": 3.6, "cpc": 0.9, "thruplay": 40})
    m = ex.ultima_metrica(ep)
    assert m["impresiones"] == 250 and m["cpc"] == 0.9 and m["thruplay"] == 40 and m["tomado_en"]
    assert "estado_meta_texto" not in m  # la segunda no lo trajo
    p = ex.piezas("acme", eid)[0]
    assert p["metricas"]["gasto"] == 8.0
    e = ex.obtener("acme", eid)
    assert e["resumen"]["gasto"] == 8.0 and e["resumen"]["mejor_cpc"] == 0.9


def test_eventos(base_temporal):
    import experimentos as ex
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ex.registrar_evento("acme", eid, "lanzamiento", "Campaña creada", {"campaign_id": "1"})
    ex.registrar_evento("acme", eid, "estado", "Activado")
    evs = ex.eventos("acme", eid)
    assert [e["tipo"] for e in evs] == ["estado", "lanzamiento"]
    assert evs[1]["datos"] == {"campaign_id": "1"} and evs[0]["creado_en"]
    assert len(ex.eventos("acme", eid, limite=1)) == 1
    assert ex.obtener("acme", eid)["eventos"][0]["mensaje"] == "Activado"


def test_elegibles(base_temporal):
    import experimentos as ex
    db = base_temporal
    f_ok = _pieza(db)                                                   # final lista CO
    _pieza(db, estado="generando", legado="cf_1__es_MX", pais="MX")     # final generando: no
    clon = _pieza(db, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_1")
    _pieza(db, tipo="imagen", estado="listo", pais=None, idioma=None, legado="cf_2")   # imagen: no
    _pieza(db, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_3", url=None)  # sin url: no
    _pieza(db, cliente="otro", legado="cf_7__es_CO")
    el = ex.elegibles("acme")
    assert {(p["pieza_id"], p["tipo"], p["pais"]) for p in el} == {(f_ok, "final", "CO"), (clon, "clon", None)}
    assert all(p["nombre"] for p in el)


def test_pieza_id_por_legado(base_temporal):
    import creative_flow as cf
    pid = _pieza(base_temporal)
    assert cf.pieza_id_por_legado("acme", "cf_1__es_CO") == pid
    assert cf.pieza_id_por_legado("acme", "nada") is None
    assert cf.pieza_id_por_legado("otro", "cf_1__es_CO") is None
