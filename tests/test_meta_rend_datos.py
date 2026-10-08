"""Copias de Meta en la base (spec §4 y §6): reemplazar un tramo es idempotente,
las lecturas agregan en una consulta y quitar una cuenta borra sus copias."""
import sqlalchemy as sa

import db
from meta_rendimiento import datos

A, B = "act_1", "act_2"


def _dia(fecha, gasto, valor, compras=1, **k):
    return dict(fecha=fecha, gasto=gasto, impresiones=1000, alcance=800, clics=20, clics_salida=10,
                compras=compras, valor=valor, vistas_3s=300, thruplays=100, **k)


def _ad(fecha, ad, gasto, valor, campaign="c1", adset="s1", compras=1):
    return dict(fecha=fecha, campaign_id=campaign, adset_id=adset, ad_id=ad, gasto=gasto, impresiones=1000,
                clics=20, clics_salida=10, compras=compras, valor=valor, vistas_3s=300, thruplays=100,
                p25=90, p50=70, p75=50, p100=30)


def _ads(cliente, cuentas, desde="2026-01-01", hasta="2026-12-31"):
    return {a["ad_id"]: a for a in datos.totales_por_anuncio(cliente, cuentas, desde, hasta)}


def test_reemplazar_es_idempotente_y_totales(base_temporal):
    datos.reemplazar_cuenta_dias("hf", A, "2026-10-01", "2026-10-02",
                                 [_dia("2026-10-01", 100, 300), _dia("2026-10-02", 50, 0, compras=0)])
    datos.reemplazar_cuenta_dias("hf", A, "2026-10-02", "2026-10-02", [_dia("2026-10-02", 60, 120)])
    datos.reemplazar_cuenta_dias("hf", B, "2026-10-01", "2026-10-01", [_dia("2026-10-01", 10, 40)])
    t = datos.totales_por_cuenta("hf", [A, B], "2026-10-01", "2026-10-02")
    assert t[A]["gasto"] == 160 and t[A]["valor"] == 420 and t[B]["gasto"] == 10
    assert datos.rango("hf", [A]) == {"filas": 2, "desde": "2026-10-01", "hasta": "2026-10-02"}
    assert len(datos.cuenta_por_dia("hf", [A, B], "2026-10-01", "2026-10-02")) == 3


def test_anuncios_campanas_y_conjuntos_con_nombres(base_temporal):
    datos.guardar_objetos("hf", A, [
        {"nivel": "campana", "objeto_id": "c1", "nombre": "Otoño", "estado": "ACTIVE", "objetivo": "OUTCOME_SALES",
         "presupuesto_diario": 500.0},
        {"nivel": "conjunto", "objeto_id": "s1", "padre_id": "c1", "campaign_id": "c1", "nombre": "Mujeres",
         "estado": "ACTIVE", "aprendizaje": "FAIL"},
        {"nivel": "anuncio", "objeto_id": "a1", "padre_id": "s1", "campaign_id": "c1", "nombre": "Video 1",
         "estado": "ACTIVE", "miniatura_url": "https://x/1.jpg"}])
    datos.reemplazar_anuncio_dias("hf", A, "2026-10-01", "2026-10-02",
                                  [_ad("2026-10-01", "a1", 30, 90), _ad("2026-10-02", "a1", 20, 0, compras=0),
                                   _ad("2026-10-02", "a2", 5, 0, compras=0)])
    camp = datos.totales_por_campana("hf", [A], "2026-10-01", "2026-10-02")
    assert camp[0]["campaign_id"] == "c1" and camp[0]["nombre"] == "Otoño" and camp[0]["gasto"] == 55
    conj = datos.totales_por_conjunto("hf", [A], "2026-10-01", "2026-10-02")
    assert conj[0]["aprendizaje"] == "FAIL" and conj[0]["campana"] == "Otoño"
    ads = _ads("hf", [A], "2026-10-01", "2026-10-02")
    assert ads["a1"]["pedidos"] == 1 and ads["a1"]["ingresos"] == 90 and ads["a1"]["anuncio"] == "Video 1"
    assert ads["a1"]["dias_con_gasto"] == 2 and ads["a1"]["canal"] == "meta"
    assert ads["a2"]["anuncio"] is None
    assert datos.activos("hf", [A])[A] == {"campana": 1, "conjunto": 1, "anuncio": 1, "aprendizaje_limitado": 1}


def test_anuncio_trae_estado_miniatura_y_nombres_del_arbol(base_temporal):
    datos.guardar_objetos("hf", A, [
        {"nivel": "campana", "objeto_id": "c1", "nombre": "Otoño"},
        {"nivel": "conjunto", "objeto_id": "s1", "campaign_id": "c1", "nombre": "Mujeres"},
        {"nivel": "anuncio", "objeto_id": "a1", "padre_id": "s1", "campaign_id": "c1", "nombre": "Video 1",
         "estado": "PAUSED", "miniatura_url": "https://x/1.jpg"}])
    datos.reemplazar_anuncio_dias("hf", A, "2026-10-01", "2026-10-02",
                                  [_ad("2026-10-01", "a1", 30, 90), _ad("2026-10-02", "a2", 5, 0)])
    ads = _ads("hf", [A])
    a1, a2 = ads["a1"], ads["a2"]
    assert (a1["estado"], a1["miniatura_url"], a1["campana"], a1["conjunto"]) == \
        ("PAUSED", "https://x/1.jpg", "Otoño", "Mujeres")
    assert a1["ad_account_id"] == A and a1["campaign_id"] == "c1" and a1["adset_id"] == "s1"
    assert (a1["primera_fecha"], a1["ultima_fecha"]) == ("2026-10-01", "2026-10-01")
    # Sin fila en meta_objeto: todo lo del árbol es None, pero el anuncio sale con sus números.
    assert (a2["estado"], a2["miniatura_url"], a2["anuncio"]) == (None, None, None)
    assert a2["gasto"] == 5 and a2["campana"] == "Otoño" and a2["conjunto"] == "Mujeres"
    # Las claves que espera triple_whale.evaluacion.metricas, con sus tipos.
    for k in ("gasto", "ingresos", "pedidos"):
        assert isinstance(a1[k], float)
    for k in ("impresiones", "clics", "clics_salida", "thruplays", "vistas_3s", "p100", "dias_con_gasto"):
        assert isinstance(a1[k], int)
    from triple_whale import evaluacion
    assert evaluacion.metricas(a1)["roas"] == 3.0


def test_nombre_none_no_pisa_y_marcar_sin_estado(base_temporal):
    datos.guardar_objetos("hf", A, [{"nivel": "anuncio", "objeto_id": "a1", "nombre": "Video 1", "estado": "ACTIVE"}])
    datos.guardar_objetos("hf", A, [{"nivel": "anuncio", "objeto_id": "a1", "nombre": None, "estado": "PAUSED"}])
    datos.guardar_objetos("hf", A, [{"nivel": "anuncio", "objeto_id": "a9", "nombre": "Viejo", "estado": "ACTIVE"}])
    assert datos.marcar_sin_estado("hf", A, "anuncio", {"a1"}) == 1
    assert _ads("hf", [A]) == {}   # sin días no hay filas de anuncio
    datos.reemplazar_anuncio_dias("hf", A, "2026-10-01", "2026-10-01",
                                  [_ad("2026-10-01", "a1", 10, 0), _ad("2026-10-01", "a9", 4, 0)])
    ads = _ads("hf", [A])
    assert ads["a1"]["anuncio"] == "Video 1" and ads["a1"]["estado"] == "PAUSED"
    assert ads["a9"]["anuncio"] == "Viejo" and ads["a9"]["estado"] is None


def test_marcar_sin_estado_solo_toca_su_nivel_cuenta_y_proyecto(base_temporal):
    datos.guardar_objetos("hf", A, [{"nivel": "campana", "objeto_id": "c1", "nombre": "C", "estado": "ACTIVE"},
                                    {"nivel": "anuncio", "objeto_id": "a1", "nombre": "A", "estado": "ACTIVE"}])
    datos.guardar_objetos("hf", B, [{"nivel": "anuncio", "objeto_id": "b1", "nombre": "B", "estado": "ACTIVE"}])
    datos.guardar_objetos("otro", A, [{"nivel": "anuncio", "objeto_id": "o1", "nombre": "O", "estado": "ACTIVE"}])
    assert datos.marcar_sin_estado("hf", A, "anuncio", set()) == 1
    assert datos.marcar_sin_estado("hf", A, "anuncio", set()) == 0   # ya estaba sin estado
    assert datos.activos("hf", [A, B]) == {A: {"campana": 1, "conjunto": 0, "anuncio": 0, "aprendizaje_limitado": 0},
                                           B: {"campana": 0, "conjunto": 0, "anuncio": 1, "aprendizaje_limitado": 0}}
    assert datos.activos("otro", [A])[A]["anuncio"] == 1


def test_marcar_sin_estado_con_miles_de_ids(base_temporal):
    datos.guardar_objetos("hf", A, [{"nivel": "anuncio", "objeto_id": f"a{i}", "nombre": str(i), "estado": "ACTIVE"}
                                    for i in range(1200)])
    vistos = {f"a{i}" for i in range(0, 1200, 2)}
    assert datos.marcar_sin_estado("hf", A, "anuncio", vistos) == 600
    assert datos.activos("hf", [A])[A]["anuncio"] == 600


def test_objeto_solo_con_nombre_conserva_lo_guardado(base_temporal):
    datos.guardar_objetos("hf", A, [
        {"nivel": "conjunto", "objeto_id": "s1", "padre_id": "c1", "campaign_id": "c1", "nombre": "Mujeres",
         "estado": "ACTIVE", "aprendizaje": "FAIL", "presupuesto_diario": 300.0},
        {"nivel": "anuncio", "objeto_id": "a1", "nombre": "Video 1", "estado": "ACTIVE",
         "miniatura_url": "https://x/1.jpg"}])
    # Lo que llega de los insights: solo nivel, id, padre, campaña y nombre (sin «estado»).
    n = datos.guardar_objetos("hf", A, [
        {"nivel": "conjunto", "objeto_id": "s1", "campaign_id": "c1", "nombre": "Mujeres 25-34"},
        {"nivel": "anuncio", "objeto_id": "a1", "padre_id": "s1", "campaign_id": "c1", "nombre": None},
        {"nivel": "anuncio", "objeto_id": "a2", "padre_id": "s1", "campaign_id": "c1", "nombre": "Nuevo"}])
    assert n == 3
    with db.conectar() as con:
        o = {r.objeto_id: r for r in con.execute(sa.select(db.meta_objeto))}
    assert (o["s1"].nombre, o["s1"].estado, o["s1"].aprendizaje, o["s1"].presupuesto_diario, o["s1"].padre_id) == \
        ("Mujeres 25-34", "ACTIVE", "FAIL", 300.0, "c1")
    assert (o["a1"].nombre, o["a1"].estado, o["a1"].miniatura_url, o["a1"].padre_id) == \
        ("Video 1", "ACTIVE", "https://x/1.jpg", "s1")
    assert (o["a2"].nombre, o["a2"].estado, o["a2"].extra) == ("Nuevo", None, {})
    assert datos.activos("hf", [A])[A] == {"campana": 0, "conjunto": 1, "anuncio": 1, "aprendizaje_limitado": 1}


def test_alcance_borrar_y_purgar(base_temporal):
    datos.guardar_alcance("hf", A, [{"nivel": "cuenta", "objeto_id": A, "ventana": 30, "alcance": 9000,
                                     "frecuencia": 2.5}])
    datos.guardar_alcance("hf", A, [{"nivel": "cuenta", "objeto_id": A, "ventana": 30, "alcance": 9500,
                                     "frecuencia": 2.6}])
    assert datos.alcance("hf", [A], 30) == {A: {"alcance": 9500, "frecuencia": 2.6}}
    datos.reemplazar_anuncio_dias("hf", A, "2026-06-01", "2026-10-01",
                                  [_ad("2026-06-01", "a1", 1, 0), _ad("2026-10-01", "a1", 1, 0)])
    assert datos.purgar_anuncios("2026-07-01") == 1
    datos.borrar_cuenta("hf", A)
    assert datos.alcance("hf", [A], 30) == {} and datos.totales_por_anuncio("hf", [A], "2026-01-01", "2026-12-31") == []


def test_alcance_por_ventana_y_nivel(base_temporal):
    datos.guardar_alcance("hf", A, [
        {"nivel": "cuenta", "objeto_id": A, "ventana": 7, "alcance": 100, "frecuencia": 1.1},
        {"nivel": "cuenta", "objeto_id": A, "ventana": 30, "alcance": 300, "frecuencia": 1.3},
        {"nivel": "campana", "objeto_id": "c1", "ventana": 30, "alcance": 50, "frecuencia": None}])
    datos.guardar_alcance("hf", B, [{"nivel": "cuenta", "objeto_id": B, "ventana": 30, "alcance": 7,
                                     "frecuencia": 1.0}])
    assert datos.alcance("hf", [A, B], 30) == {A: {"alcance": 300, "frecuencia": 1.3},
                                               B: {"alcance": 7, "frecuencia": 1.0}}
    assert datos.alcance("hf", [A], 7) == {A: {"alcance": 100, "frecuencia": 1.1}}
    assert datos.alcance("hf", [A], 30, nivel="campana") == {"c1": {"alcance": 50, "frecuencia": None}}
    assert datos.alcance("hf", [], 30) == {}


def test_reemplazar_ignora_fechas_fuera_del_rango_y_cuenta_lo_escrito(base_temporal):
    n = datos.reemplazar_cuenta_dias("hf", A, "2026-10-01", "2026-10-02", [
        _dia("2026-09-30", 1, 0), _dia("2026-10-01", 2, 0), _dia("2026-10-02", 3, 0), _dia("2026-10-03", 4, 0)])
    assert n == 2
    assert datos.rango("hf", [A]) == {"filas": 2, "desde": "2026-10-01", "hasta": "2026-10-02"}
    # Reescribir el mismo tramo con otras cifras no duplica filas ni toca los días de afuera.
    datos.reemplazar_cuenta_dias("hf", A, "2026-10-03", "2026-10-03", [_dia("2026-10-03", 9, 0)])
    n = datos.reemplazar_cuenta_dias("hf", A, "2026-10-01", "2026-10-02", [_dia("2026-10-01", 20, 0)])
    assert n == 1
    t = datos.totales_por_cuenta("hf", [A], "2026-10-01", "2026-10-03")
    assert t[A]["gasto"] == 29 and t[A]["dias"] == 2


def test_reemplazar_anuncios_no_duplica_ni_pisa_otra_cuenta_ni_otro_proyecto(base_temporal):
    datos.reemplazar_anuncio_dias("hf", A, "2026-10-01", "2026-10-02",
                                  [_ad("2026-10-01", "a1", 1, 0), _ad("2026-10-02", "a1", 2, 0)])
    datos.reemplazar_anuncio_dias("hf", B, "2026-10-01", "2026-10-02", [_ad("2026-10-01", "b1", 3, 0)])
    datos.reemplazar_anuncio_dias("otro", A, "2026-10-01", "2026-10-02", [_ad("2026-10-01", "a1", 100, 0)])
    # El mismo anuncio y día dos veces en la misma tanda (paginado de Meta con solape): gana el último.
    n = datos.reemplazar_anuncio_dias("hf", A, "2026-10-01", "2026-10-01",
                                      [_ad("2026-10-01", "a1", 5, 0), _ad("2026-10-01", "a1", 6, 0)])
    assert n == 1
    assert _ads("hf", [A])["a1"]["gasto"] == 8            # 6 (reescrito) + 2 (día de afuera)
    assert _ads("hf", [B])["b1"]["gasto"] == 3
    assert _ads("otro", [A])["a1"]["gasto"] == 100
    assert _ads("hf", [B]).get("a1") is None


def test_borrar_cuenta_borra_las_cuatro_copias_solo_de_esa_cuenta_y_proyecto(base_temporal):
    for cliente, act in (("hf", A), ("hf", B), ("otro", A)):
        datos.reemplazar_cuenta_dias(cliente, act, "2026-10-01", "2026-10-01", [_dia("2026-10-01", 1, 0)])
        datos.reemplazar_anuncio_dias(cliente, act, "2026-10-01", "2026-10-01", [_ad("2026-10-01", "a1" + act, 1, 0)])
        datos.guardar_objetos(cliente, act, [{"nivel": "anuncio", "objeto_id": "a1" + act, "nombre": "x",
                                              "estado": "ACTIVE"}])
        datos.guardar_alcance(cliente, act, [{"nivel": "cuenta", "objeto_id": act, "ventana": 30, "alcance": 1,
                                              "frecuencia": 1.0}])
    assert datos.borrar_cuenta("hf", A) is None
    with db.conectar() as con:
        def n(tabla, **f):
            q = sa.select(sa.func.count()).select_from(tabla)
            for k, v in f.items():
                q = q.where(getattr(tabla.c, k) == v)
            return con.execute(q).scalar()
        for tabla in (db.meta_cuenta_dia, db.meta_anuncio_dia, db.meta_objeto, db.meta_alcance):
            assert n(tabla, cliente="hf", ad_account_id=A) == 0, tabla.name
            assert n(tabla, cliente="hf", ad_account_id=B) == 1, tabla.name
            assert n(tabla, cliente="otro", ad_account_id=A) == 1, tabla.name


def test_lecturas_con_cuentas_vacias_no_consultan(base_temporal):
    consultas = _contar_consultas()
    assert datos.rango("hf", []) == {"filas": 0, "desde": None, "hasta": None}
    assert datos.cuenta_por_dia("hf", [], "2026-01-01", "2026-12-31") == []
    assert datos.totales_por_cuenta("hf", [], "2026-01-01", "2026-12-31") == {}
    assert datos.totales_por_campana("hf", [], "2026-01-01", "2026-12-31") == []
    assert datos.totales_por_conjunto("hf", [], "2026-01-01", "2026-12-31") == []
    assert datos.totales_por_anuncio("hf", [], "2026-01-01", "2026-12-31") == []
    assert datos.alcance("hf", [], 30) == {}
    assert datos.activos("hf", []) == {}
    assert consultas == []


def _contar_consultas():
    """Lista que se llena con cada SQL que corre el motor desde aquí."""
    from sqlalchemy import event
    capturadas = []

    def _al_ejecutar(conn, cursor, statement, parameters, context, executemany):
        capturadas.append((statement, parameters))
    event.listen(db.engine(), "before_cursor_execute", _al_ejecutar)
    return capturadas


def test_cada_lectura_es_una_consulta_y_usa_el_indice_de_cuenta_y_fecha(base_temporal):
    datos.guardar_objetos("hf", A, [{"nivel": "anuncio", "objeto_id": "a1", "nombre": "V", "estado": "ACTIVE"}])
    datos.reemplazar_cuenta_dias("hf", A, "2026-10-01", "2026-10-01", [_dia("2026-10-01", 1, 0)])
    datos.reemplazar_anuncio_dias("hf", A, "2026-10-01", "2026-10-01", [_ad("2026-10-01", "a1", 1, 0)])
    datos.guardar_alcance("hf", A, [{"nivel": "cuenta", "objeto_id": A, "ventana": 30, "alcance": 1, "frecuencia": 1.0}])
    capturadas = _contar_consultas()
    lecturas = [
        lambda: datos.rango("hf", [A, B]),
        lambda: datos.cuenta_por_dia("hf", [A, B], "2026-10-01", "2026-10-31"),
        lambda: datos.totales_por_cuenta("hf", [A, B], "2026-10-01", "2026-10-31"),
        lambda: datos.totales_por_campana("hf", [A, B], "2026-10-01", "2026-10-31"),
        lambda: datos.totales_por_conjunto("hf", [A, B], "2026-10-01", "2026-10-31"),
        lambda: datos.totales_por_anuncio("hf", [A, B], "2026-10-01", "2026-10-31"),
        lambda: datos.alcance("hf", [A, B], 30),
        lambda: datos.activos("hf", [A, B]),
    ]
    for leer in lecturas:
        capturadas.clear()
        leer()
        selects = [c for c in capturadas if c[0].lstrip().upper().startswith("SELECT")]
        assert len(selects) == 1, (len(selects), selects)
        # Lo que filtra por proyecto + cuentas + fecha usa un índice (nunca recorre la tabla entera).
        with db.conectar() as con:
            plan = " | ".join(str(r[3]) for r in con.exec_driver_sql("EXPLAIN QUERY PLAN " + selects[0][0],
                                                                      selects[0][1]))
        assert "SCAN meta_anuncio_dia" not in plan and "SCAN meta_cuenta_dia" not in plan, plan
        if "FROM meta_anuncio_dia" in selects[0][0]:
            assert "ix_meta_anuncio_dia_cuenta_fecha" in plan, plan
