"""Relleno único de la tabla `gasto` con los cobros anteriores a su existencia
(2026-09-18): la tabla nació vacía y el panel de admin mostraba US$ 0 en todos
los proyectos aunque `pieza.costo_usd` y `swaps.json` sí tenían lo pagado.
`gastos.importar_historico` copia eso una vez, con la fecha original (para que
caiga en su mes) y con las mismas referencias que usan las tareas, de modo que
no duplica lo que una tarea ya registró y se puede correr las veces que sea."""
import pytest


@pytest.fixture()
def gastos(base_temporal):
    import gastos as g
    return g


def _pieza(db, cliente, tipo, legado_id, costo, estado="listo", creado_en="2026-09-03T11:17:25", modelo=None):
    import sqlalchemy as sa
    with db.conectar() as con:
        cid = con.execute(sa.insert(db.concepto).values(
            cliente=cliente, creado_en=creado_en, actualizado_en=creado_en, origen="manual",
            legado_id=legado_id, extra={})).inserted_primary_key[0]
        con.execute(sa.insert(db.pieza).values(
            cliente=cliente, creado_en=creado_en, actualizado_en=creado_en, concepto_id=cid,
            tipo=tipo, estado=estado, costo_usd=costo, legado_id=legado_id, modelo=modelo, capas={}, extra={}))


def _refs(gastos, cliente):
    return {f["referencia"]: f for f in gastos.historial(cliente)}


def test_importa_el_costo_de_las_piezas_listas_con_su_fecha(base_temporal, gastos):
    _pieza(base_temporal, "acme", "video", "cf_1", 1.3, creado_en="2026-09-03T11:17:25", modelo="wan3")
    _pieza(base_temporal, "acme", "final", "cf_1__es_CO", 0.07, estado="degradada", creado_en="2026-09-10T08:00:00")

    resumen = gastos.importar_historico("acme", swaps={})

    filas = _refs(gastos, "acme")
    assert set(filas) == {"video:cf_1", "final:cf_1__es_CO"}
    assert filas["video:cf_1"]["tipo"] == "video" and filas["video:cf_1"]["usd"] == 1.3
    assert filas["video:cf_1"]["creado_en"] == "2026-09-03T11:17:25"
    assert filas["final:cf_1__es_CO"]["tipo"] == "final" and filas["final:cf_1__es_CO"]["usd"] == 0.07
    assert resumen["piezas"] == 2 and resumen["swaps"] == 0 and resumen["usd"] == 1.37


def test_no_importa_piezas_en_curso_fallidas_ni_sin_costo(base_temporal, gastos):
    _pieza(base_temporal, "acme", "video", "cf_generando", 1.3, estado="generando")
    _pieza(base_temporal, "acme", "video", "cf_error", 1.3, estado="error")
    _pieza(base_temporal, "acme", "video", "cf_sin_costo", None)
    _pieza(base_temporal, "acme", "video", "cf_cero", 0.0)
    _pieza(base_temporal, "otro", "video", "cf_ajeno", 2.0)

    resumen = gastos.importar_historico("acme", swaps={})

    assert gastos.historial("acme") == []
    assert gastos.historial("otro") == []          # solo el proyecto pedido
    assert resumen == {"piezas": 0, "swaps": 0, "usd": 0.0}


def test_no_duplica_lo_que_la_tarea_ya_registro_y_es_idempotente(base_temporal, gastos):
    _pieza(base_temporal, "acme", "video", "cf_1", 1.3)
    _pieza(base_temporal, "acme", "video", "cf_2", 0.9)
    # cf_2 lo registró su tarea después del despliegue, con el sufijo por intento.
    gastos.registrar("acme", "video", 0.9, "video:cf_2:41", proveedor="wavespeed")

    gastos.importar_historico("acme", swaps={})
    gastos.importar_historico("acme", swaps={})

    assert sorted(_refs(gastos, "acme")) == ["video:cf_1", "video:cf_2:41"]


def test_importa_los_swaps_listos_del_json(base_temporal, gastos):
    swaps = {
        "swap_ok": {"estado": "listo", "usd": 0.094, "credits": 1.5, "proveedor": "higgsfield",
                    "tipo": "foto", "creado_en": "2026-08-29T20:22:18.997994"},
        "swap_fallido": {"estado": "error", "usd": 0.05, "proveedor": "higgsfield", "tipo": "foto",
                         "creado_en": "2026-09-02T10:00:00"},
        "swap_gratis": {"estado": "listo", "usd": 0, "proveedor": "nano_banana", "tipo": "foto",
                        "creado_en": "2026-09-02T10:00:00"},
    }

    resumen = gastos.importar_historico("acme", swaps=swaps)

    filas = _refs(gastos, "acme")
    assert set(filas) == {"swap:swap_ok"}
    f = filas["swap:swap_ok"]
    assert f["tipo"] == "swap" and f["usd"] == 0.094 and f["proveedor"] == "higgsfield"
    assert f["creado_en"] == "2026-08-29T20:22:18"
    assert resumen["swaps"] == 1 and resumen["usd"] == 0.094


def test_lo_importado_cae_en_el_mes_de_la_pieza(base_temporal, gastos):
    _pieza(base_temporal, "acme", "video", "cf_ago", 5.0, creado_en="2026-08-20T09:00:00")
    _pieza(base_temporal, "acme", "video", "cf_sep", 1.3, creado_en="2026-09-11T19:04:42")

    gastos.importar_historico("acme", swaps={})

    sept = gastos.resumen_mes("acme", ahora_iso="2026-09-19T00:00:00")
    assert sept["total"] == 1.3 and sept["n"] == 1
    assert gastos.por_proyecto_mes(["acme"], ahora_iso="2026-09-19T00:00:00") == {"acme": 1.3}
