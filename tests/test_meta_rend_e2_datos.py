"""Datos de Meta rendimiento E2 (spec E2 §4 y §8): los desgloses se reemplazan por (cuenta, ventana, dimensión) en
una transacción, el gasto por conjunto sale de UNA consulta agregada, las evaluaciones (pagadas) se filtran por
proyecto y quitar una cuenta borra sus desgloses pero nunca una evaluación."""
import sqlalchemy as sa
import pytest

import db
from meta_rendimiento import datos

A, B = "act_1", "act_2"


def _seg(clave, gasto, valor=0.0, compras=0, **k):
    return dict(clave=clave, gasto=gasto, impresiones=1000, clics=40, clics_salida=25, compras=compras, valor=valor,
                **k)


def _por_clave(filas):
    return {(f["ad_account_id"], f["dimension"], f["clave"]): f for f in filas}


# ---------------------------------------------------------------- desgloses ---

def test_reemplazar_desgloses_escribe_y_lee_con_tipos(base_temporal):
    n = datos.reemplazar_desgloses("hf", A, 30, "edad_genero",
                                   [_seg("25-34|female", 120.5, 360, 3), _seg("35-44|male", 80, 0, 0)])
    assert n == 2
    filas = datos.desgloses("hf", [A], 30)
    assert len(filas) == 2
    f = _por_clave(filas)[(A, "edad_genero", "25-34|female")]
    assert f["gasto"] == 120.5 and f["valor"] == 360 and f["compras"] == 3
    assert isinstance(f["impresiones"], int) and isinstance(f["clics"], int) and isinstance(f["clics_salida"], int)
    assert isinstance(f["gasto"], float) and isinstance(f["compras"], float)
    assert f["calculado_en"]
    # Más gasto primero dentro de la dimensión.
    assert [x["clave"] for x in filas] == ["25-34|female", "35-44|male"]


def test_reemplazar_desgloses_es_idempotente_y_pisa_solo_esa_combinacion(base_temporal):
    datos.reemplazar_desgloses("hf", A, 30, "pais", [_seg("NO", 100), _seg("SE", 50)])
    datos.reemplazar_desgloses("hf", A, 30, "dispositivo", [_seg("mobile_app", 70)])
    datos.reemplazar_desgloses("hf", A, 7, "pais", [_seg("NO", 10)])
    datos.reemplazar_desgloses("hf", B, 30, "pais", [_seg("NO", 5)])
    # Otra vez la misma combinación: queda solo lo nuevo (SE desaparece, NO se actualiza), no se duplica.
    datos.reemplazar_desgloses("hf", A, 30, "pais", [_seg("NO", 111)])
    datos.reemplazar_desgloses("hf", A, 30, "pais", [_seg("NO", 111)])
    por = _por_clave(datos.desgloses("hf", [A, B], 30))
    assert set(por) == {(A, "pais", "NO"), (A, "dispositivo", "mobile_app"), (B, "pais", "NO")}
    assert por[(A, "pais", "NO")]["gasto"] == 111
    # Las otras combinaciones no se tocaron: otra ventana, otra dimensión, otra cuenta.
    assert por[(A, "dispositivo", "mobile_app")]["gasto"] == 70 and por[(B, "pais", "NO")]["gasto"] == 5
    assert _por_clave(datos.desgloses("hf", [A], 7))[(A, "pais", "NO")]["gasto"] == 10


def test_reemplazar_desgloses_con_lista_vacia_borra_la_combinacion(base_temporal):
    datos.reemplazar_desgloses("hf", A, 30, "pais", [_seg("NO", 100)])
    assert datos.reemplazar_desgloses("hf", A, 30, "pais", []) == 0
    assert datos.desgloses("hf", [A], 30) == []


def test_reemplazar_desgloses_ignora_filas_sin_clave_y_repite_la_ultima(base_temporal):
    n = datos.reemplazar_desgloses("hf", A, 30, "pais", [
        _seg("NO", 1), _seg("NO", 2), dict(gasto=9), dict(clave="", gasto=9), dict(clave=None, gasto=9)])
    assert n == 1
    assert [(f["clave"], f["gasto"]) for f in datos.desgloses("hf", [A], 30)] == [("NO", 2)]


def test_reemplazar_desgloses_rechaza_ventana_o_dimension_invalidas(base_temporal):
    with pytest.raises(ValueError):
        datos.reemplazar_desgloses("hf", A, 14, "pais", [_seg("NO", 1)])
    with pytest.raises(ValueError):
        datos.reemplazar_desgloses("hf", A, 30, "color_favorito", [_seg("NO", 1)])
    assert datos.desgloses("hf", [A], 30) == []


def test_desgloses_aislan_por_proyecto_cuenta_y_ventana(base_temporal):
    datos.reemplazar_desgloses("hf", A, 30, "pais", [_seg("NO", 100)])
    datos.reemplazar_desgloses("otro", A, 30, "pais", [_seg("NO", 999)])
    datos.reemplazar_desgloses("hf", B, 30, "pais", [_seg("SE", 5)])
    datos.reemplazar_desgloses("hf", A, 7, "pais", [_seg("NO", 7)])
    assert [(f["ad_account_id"], f["clave"], f["gasto"]) for f in datos.desgloses("hf", [A], 30)] == [(A, "NO", 100)]
    assert {f["ad_account_id"] for f in datos.desgloses("hf", [A, B], 30)} == {A, B}
    assert [f["gasto"] for f in datos.desgloses("otro", [A], 30)] == [999]
    assert datos.desgloses("hf", [A], 7)[0]["gasto"] == 7
    assert datos.desgloses("hf", [], 30) == []                # sin cuentas, ni toca la base
    assert datos.desgloses("nadie", [A], 30) == []


def test_desgloses_es_una_sola_consulta(base_temporal):
    for act in (A, B, "act_3"):
        for dim in datos.DIMENSIONES:
            datos.reemplazar_desgloses("hf", act, 30, dim, [_seg("x", 1), _seg("y", 2)])
    consultas = []

    @sa.event.listens_for(db.engine(), "before_cursor_execute")
    def _cuenta(conn, cursor, statement, params, context, executemany):
        consultas.append(statement)

    try:
        assert len(datos.desgloses("hf", [A, B, "act_3"], 30)) == 24
    finally:
        sa.event.remove(db.engine(), "before_cursor_execute", _cuenta)
    assert len(consultas) == 1


def test_borrar_cuenta_borra_sus_desgloses_y_no_los_de_otras(base_temporal):
    datos.reemplazar_desgloses("hf", A, 30, "pais", [_seg("NO", 1)])
    datos.reemplazar_desgloses("hf", A, 7, "pais", [_seg("NO", 1)])
    datos.reemplazar_desgloses("hf", B, 30, "pais", [_seg("NO", 2)])
    datos.reemplazar_desgloses("otro", A, 30, "pais", [_seg("NO", 3)])
    datos.borrar_cuenta("hf", A)
    assert datos.desgloses("hf", [A], 30) == [] and datos.desgloses("hf", [A], 7) == []
    assert [f["gasto"] for f in datos.desgloses("hf", [B], 30)] == [2]
    assert [f["gasto"] for f in datos.desgloses("otro", [A], 30)] == [3]


def test_borrar_cuenta_no_borra_las_evaluaciones(base_temporal):
    eid = datos.crear_evaluacion("hf", [A], "2026-09-10", "2026-10-09", "SEK", [{"ref": "a1"}], [], "ana")
    datos.borrar_cuenta("hf", A)
    assert datos.evaluacion("hf", eid) is not None


# ----------------------------------------------------------- gasto por conjunto ---

def _ad(fecha, ad, adset, gasto, valor=0, compras=0, campaign="c1"):
    return dict(fecha=fecha, campaign_id=campaign, adset_id=adset, ad_id=ad, gasto=gasto, impresiones=100,
                clics=5, clics_salida=2, compras=compras, valor=valor, vistas_3s=0, thruplays=0,
                p25=0, p50=0, p75=0, p100=0)


def test_gasto_por_conjunto_suma_por_conjunto_en_el_rango(base_temporal):
    datos.reemplazar_anuncio_dias("hf", A, "2026-10-01", "2026-10-08", [
        _ad("2026-10-01", "a1", "s1", 10, 30, 1), _ad("2026-10-02", "a1", "s1", 20, 40, 2),
        _ad("2026-10-02", "a2", "s1", 5, 0, 0), _ad("2026-10-02", "a3", "s2", 7, 14, 1),
        _ad("2026-10-08", "a3", "s2", 100, 0, 0)])
    datos.reemplazar_anuncio_dias("hf", B, "2026-10-02", "2026-10-02", [_ad("2026-10-02", "b1", "s9", 3, 6, 1)])
    datos.reemplazar_anuncio_dias("otro", A, "2026-10-02", "2026-10-02", [_ad("2026-10-02", "x1", "s1", 999)])
    r = datos.gasto_por_conjunto("hf", [A, B], "2026-10-01", "2026-10-07")
    assert set(r) == {"s1", "s2", "s9"}
    assert r["s1"] == {"gasto": 35.0, "compras": 3.0, "valor": 70.0}
    assert r["s2"] == {"gasto": 7.0, "compras": 1.0, "valor": 14.0}
    assert r["s9"]["gasto"] == 3
    # Solo la cuenta pedida, y un rango que incluye el último día suma el gasto de ese día.
    assert set(datos.gasto_por_conjunto("hf", [B], "2026-10-01", "2026-10-07")) == {"s9"}
    assert datos.gasto_por_conjunto("hf", [A], "2026-10-01", "2026-10-08")["s2"]["gasto"] == 107
    assert datos.gasto_por_conjunto("hf", [], "2026-10-01", "2026-10-07") == {}


def test_gasto_por_conjunto_ignora_anuncios_sin_conjunto_y_es_una_consulta(base_temporal):
    datos.reemplazar_anuncio_dias("hf", A, "2026-10-01", "2026-10-02", [
        _ad("2026-10-01", "a1", "s1", 10), _ad("2026-10-01", "a2", None, 50), _ad("2026-10-02", "a3", "s2", 4)])
    consultas = []

    @sa.event.listens_for(db.engine(), "before_cursor_execute")
    def _cuenta(conn, cursor, statement, params, context, executemany):
        consultas.append(statement)

    try:
        r = datos.gasto_por_conjunto("hf", [A], "2026-10-01", "2026-10-02")
    finally:
        sa.event.remove(db.engine(), "before_cursor_execute", _cuenta)
    assert r == {"s1": {"gasto": 10.0, "compras": 0.0, "valor": 0.0}, "s2": {"gasto": 4.0, "compras": 0.0, "valor": 0.0}}
    assert len(consultas) == 1


# ------------------------------------------------------------- evaluaciones ---

MUESTRA = [{"ref": "a1", "ad_id": "111", "ad_account_id": A}, {"ref": "a2", "ad_id": "222", "ad_account_id": B}]
RECOS = [{"id": "r1", "tipo": "perdedores_gastando", "nivel": "alta"}]


def _crear(cliente="hf", **k):
    args = dict(cuentas=[A, B], desde="2026-09-10", hasta="2026-10-09", moneda="SEK", muestra=MUESTRA,
                recomendaciones=RECOS, pedido_por="ana")
    args.update(k)
    return datos.crear_evaluacion(cliente, args["cuentas"], args["desde"], args["hasta"], args["moneda"],
                                  args["muestra"], args["recomendaciones"], args["pedido_por"])


def test_crear_evaluacion_nace_en_cola_con_lo_que_se_pidio(base_temporal):
    eid = _crear()
    assert isinstance(eid, int)
    e = datos.evaluacion("hf", eid)
    assert e["estado"] == "en_cola" and e["cliente"] == "hf" and e["pedido_por"] == "ana"
    assert e["cuentas"] == [A, B] and e["desde"] == "2026-09-10" and e["hasta"] == "2026-10-09"
    assert e["moneda"] == "SEK" and e["muestra"] == MUESTRA and e["recomendaciones"] == RECOS
    assert e["resultado"] == {} and e["usd"] == 0.0 and e["error"] is None and e["tarea_id"] is None
    assert e["extra"] == {} and e["creado_en"] and e["actualizado_en"]
    assert _crear() != eid                                       # cada pedido es otra fila


def test_actualizar_evaluacion_cambia_solo_lo_pedido(base_temporal):
    eid = _crear()
    antes = datos.evaluacion("hf", eid)
    assert datos.actualizar_evaluacion(eid, estado="analizando", tarea_id=77) is True
    e = datos.evaluacion("hf", eid)
    assert e["estado"] == "analizando" and e["tarea_id"] == 77
    assert e["muestra"] == MUESTRA and e["cuentas"] == [A, B] and e["creado_en"] == antes["creado_en"]
    assert datos.actualizar_evaluacion(eid, estado="lista", resultado={"resumen": "bien"}, usd=0.42,
                                       extra={"ideas_creadas": [0]}) is True
    e = datos.evaluacion("hf", eid)
    assert e["estado"] == "lista" and e["resultado"] == {"resumen": "bien"} and e["usd"] == 0.42
    assert e["extra"] == {"ideas_creadas": [0]}
    assert datos.actualizar_evaluacion(999999, estado="error") is False


def test_actualizar_evaluacion_valida_estado_y_no_toca_lo_inmutable(base_temporal):
    eid = _crear()
    with pytest.raises(ValueError):
        datos.actualizar_evaluacion(eid, estado="terminada")
    for campo in ("id", "cliente", "creado_en"):
        with pytest.raises(ValueError):
            datos.actualizar_evaluacion(eid, **{campo: "x"})
    assert datos.evaluacion("hf", eid)["estado"] == "en_cola"


def test_evaluacion_filtra_por_proyecto(base_temporal):
    eid = _crear("hf")
    assert datos.evaluacion("hf", eid)["id"] == eid
    assert datos.evaluacion("otro", eid) is None                 # el id existe, pero es de otro proyecto
    assert datos.evaluacion("hf", 999999) is None
    assert datos.borrar_evaluacion("otro", eid) is False
    assert datos.evaluacion("hf", eid) is not None


def test_evaluaciones_lista_las_mas_nuevas_primero_con_limite(base_temporal):
    ids = [_crear("hf") for _ in range(7)]
    otro = _crear("otro")
    lista = datos.evaluaciones("hf")                              # límite por omisión: 5
    assert [e["id"] for e in lista] == ids[::-1][:5]
    assert [e["id"] for e in datos.evaluaciones("hf", limite=2)] == ids[::-1][:2]
    assert [e["id"] for e in datos.evaluaciones("otro")] == [otro]
    assert datos.evaluaciones("nadie") == []
    assert {"resultado", "muestra", "estado", "cuentas"} <= set(lista[0])


def test_evaluaciones_es_una_sola_consulta(base_temporal):
    for _ in range(4):
        _crear("hf")
    consultas = []

    @sa.event.listens_for(db.engine(), "before_cursor_execute")
    def _cuenta(conn, cursor, statement, params, context, executemany):
        consultas.append(statement)

    try:
        assert len(datos.evaluaciones("hf")) == 4
    finally:
        sa.event.remove(db.engine(), "before_cursor_execute", _cuenta)
    assert len(consultas) == 1


def test_borrar_evaluacion_solo_la_del_proyecto(base_temporal):
    a, b = _crear("hf"), _crear("hf")
    assert datos.borrar_evaluacion("hf", a) is True
    assert datos.evaluacion("hf", a) is None and datos.evaluacion("hf", b) is not None
    assert datos.borrar_evaluacion("hf", a) is False


def test_un_id_de_evaluacion_borrado_no_se_reusa(base_temporal):
    """AUTOINCREMENT: la evaluación se paga y se enlaza (ideas -> Crear); un id borrado no vuelve a salir."""
    a = _crear()
    datos.borrar_evaluacion("hf", a)
    assert _crear() > a
