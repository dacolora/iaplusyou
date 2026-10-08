"""Copias de Meta en la base (spec §4 y §6): reemplazar un tramo es idempotente,
las lecturas agregan en una consulta y quitar una cuenta borra sus copias."""
import re

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
    # El alcance son personas únicas: no se suma entre días. Por día sí se guarda y se lee; del período, alcance().
    assert "alcance" not in t[A] and "alcance" not in t[B]
    assert {d["alcance"] for d in datos.cuenta_por_dia("hf", [A], "2026-10-01", "2026-10-02")} == {800}


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


def test_marcar_sin_estado_solo_limpia_los_estados_pedidos(base_temporal):
    datos.guardar_objetos("hf", A, [
        {"nivel": "anuncio", "objeto_id": "act1", "nombre": "A", "estado": "ACTIVE"},
        {"nivel": "anuncio", "objeto_id": "act2", "nombre": "B", "estado": "DISAPPROVED"},
        {"nivel": "anuncio", "objeto_id": "pau", "nombre": "C", "estado": "PAUSED"},
        {"nivel": "anuncio", "objeto_id": "vis", "nombre": "D", "estado": "ACTIVE"}])
    # Los anuncios pausados no se listan en cada copia: no venir en el listado no los deja sin estado.
    n = datos.marcar_sin_estado("hf", A, "anuncio", {"vis"}, estados={"ACTIVE", "DISAPPROVED"})
    assert n == 2
    assert datos.activos("hf", [A])[A]["anuncio"] == 1   # solo «vis» sigue ACTIVE
    t = db.meta_objeto
    with db.conectar() as con:
        estados = dict(con.execute(sa.select(t.c.objeto_id, t.c.estado)).all())
    assert estados == {"act1": None, "act2": None, "pau": "PAUSED", "vis": "ACTIVE"}


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


def test_alcance_de_cada_proyecto_es_solo_suyo(base_temporal):
    datos.guardar_alcance("hf", A, [{"nivel": "cuenta", "objeto_id": A, "ventana": 30, "alcance": 111,
                                     "frecuencia": 1.1}])
    datos.guardar_alcance("otro", A, [{"nivel": "cuenta", "objeto_id": A, "ventana": 30, "alcance": 999,
                                       "frecuencia": 9.9}])
    assert datos.alcance("hf", [A], 30) == {A: {"alcance": 111, "frecuencia": 1.1}}
    assert datos.alcance("otro", [A], 30) == {A: {"alcance": 999, "frecuencia": 9.9}}
    # Reescribir el de un proyecto no toca el del otro.
    datos.guardar_alcance("hf", A, [{"nivel": "cuenta", "objeto_id": A, "ventana": 30, "alcance": 222,
                                     "frecuencia": 2.2}])
    assert datos.alcance("hf", [A], 30)[A]["alcance"] == 222
    assert datos.alcance("otro", [A], 30)[A]["alcance"] == 999


def test_nombres_y_estados_de_los_objetos_no_se_cruzan_entre_proyectos(base_temporal):
    """Dos proyectos con los MISMOS ids de campaña, conjunto y anuncio (el único es por proyecto + id): cada
    lectura trae solo los nombres y estados del suyo, una fila por objeto."""
    for cliente, sufijo, estado, apr in (("hf", "propio", "ACTIVE", "FAIL"), ("otro", "ajeno", "PAUSED", "SUCCESS")):
        datos.guardar_objetos(cliente, A, [
            {"nivel": "campana", "objeto_id": "c1", "nombre": f"Campaña {sufijo}", "estado": estado,
             "objetivo": "OUTCOME_SALES" if cliente == "hf" else "OUTCOME_LEADS"},
            {"nivel": "conjunto", "objeto_id": "s1", "campaign_id": "c1", "nombre": f"Conjunto {sufijo}",
             "estado": estado, "aprendizaje": apr},
            {"nivel": "anuncio", "objeto_id": "a1", "campaign_id": "c1", "nombre": f"Anuncio {sufijo}",
             "estado": estado, "miniatura_url": f"https://x/{sufijo}.jpg"}])
        datos.reemplazar_anuncio_dias(cliente, A, "2026-10-01", "2026-10-01", [_ad("2026-10-01", "a1", 10, 0)])
    for cliente, sufijo, estado in (("hf", "propio", "ACTIVE"), ("otro", "ajeno", "PAUSED")):
        ads = datos.totales_por_anuncio(cliente, [A], "2026-10-01", "2026-10-01")
        assert len(ads) == 1
        assert (ads[0]["anuncio"], ads[0]["conjunto"], ads[0]["campana"], ads[0]["estado"],
                ads[0]["miniatura_url"]) == (f"Anuncio {sufijo}", f"Conjunto {sufijo}", f"Campaña {sufijo}", estado,
                                             f"https://x/{sufijo}.jpg")
        conj = datos.totales_por_conjunto(cliente, [A], "2026-10-01", "2026-10-01")
        assert len(conj) == 1
        assert (conj[0]["nombre"], conj[0]["campana"], conj[0]["estado"]) == (f"Conjunto {sufijo}",
                                                                              f"Campaña {sufijo}", estado)
        camp = datos.totales_por_campana(cliente, [A], "2026-10-01", "2026-10-01")
        assert len(camp) == 1
        assert (camp[0]["nombre"], camp[0]["estado"], camp[0]["objetivo"]) == (
            f"Campaña {sufijo}", estado, "OUTCOME_SALES" if cliente == "hf" else "OUTCOME_LEADS")
        assert datos.activos(cliente, [A])[A]["anuncio"] == (1 if estado == "ACTIVE" else 0)


def test_dias_con_gasto_no_cuenta_los_dias_en_cero(base_temporal):
    datos.reemplazar_anuncio_dias("hf", A, "2026-10-01", "2026-10-03", [
        _ad("2026-10-01", "a1", 10, 0), _ad("2026-10-02", "a1", 0, 0, compras=0), _ad("2026-10-03", "a1", 5, 0)])
    a1 = _ads("hf", [A])["a1"]
    assert a1["dias_con_gasto"] == 2
    assert (a1["primera_fecha"], a1["ultima_fecha"]) == ("2026-10-01", "2026-10-03")


def test_un_dia_sin_conjunto_ni_campana_no_parte_el_anuncio_en_dos_filas(base_temporal):
    datos.guardar_objetos("hf", A, [
        {"nivel": "campana", "objeto_id": "c1", "nombre": "Otoño"},
        {"nivel": "conjunto", "objeto_id": "s1", "campaign_id": "c1", "nombre": "Mujeres"},
        {"nivel": "anuncio", "objeto_id": "a1", "nombre": "Video 1", "estado": "ACTIVE"}])
    sin_ids = _ad("2026-10-02", "a1", 20, 0)
    sin_ids.update(adset_id=None, campaign_id=None)
    datos.reemplazar_anuncio_dias("hf", A, "2026-10-01", "2026-10-02", [_ad("2026-10-01", "a1", 30, 90), sin_ids])
    ads = datos.totales_por_anuncio("hf", [A], "2026-10-01", "2026-10-02")
    assert len(ads) == 1
    a1 = ads[0]
    assert (a1["gasto"], a1["adset_id"], a1["campaign_id"], a1["conjunto"], a1["campana"], a1["dias_con_gasto"]) == \
        (50, "s1", "c1", "Mujeres", "Otoño", 2)


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
            # Búsqueda por índice con proyecto + cuenta por delante. Para campañas y conjuntos es el de
            # cuenta y fecha; el agregado por anuncio prefiere el único (cliente, cuenta, anuncio, fecha) porque
            # ya viene ordenado para agrupar y la fecha se filtra dentro del índice.
            assert re.search(r"SEARCH meta_anuncio_dia USING (COVERING )?INDEX \w+ \(cliente=\? AND ad_account_id=\?",
                             plan), plan
