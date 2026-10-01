"""Quien busca la fila `producto` por un id de activo debe aceptar el id de un
color (`pid/color`) — spec 2026-09-28 §9."""
import os

import pytest


@pytest.fixture()
def catalogo(base_temporal, tmp_path, monkeypatch):
    import catalogo_productos
    import tiendas
    monkeypatch.setattr(catalogo_productos, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(catalogo_productos.idiomas, "de_proyecto", lambda cliente: "es")
    meta = {"original": {"nombre": "Original", "descripcion": "", "tipo": "calzado", "zonas": [], "regla": "",
                         "variantes": {"pink": {"nombre": "Original — Pink", "descripcion": "", "fuente_id": None,
                                                "url_compra": None, "disponible": True}}}}
    carpeta = tmp_path / "clientes" / "acme" / "productos" / "original" / "pink"
    carpeta.mkdir(parents=True)
    (carpeta / "01.jpg").write_bytes(b"\xff\xd8\xff\xe0fake")
    catalogo_productos.guardar_meta("acme", meta)
    pid = tiendas.upsert_producto("acme", "manual", "original", {"nombre": "Original", "precio": 34.95, "moneda": "EUR"})
    tiendas.marcar_producto("acme", pid, activo_catalogo_id="original")
    return {"pid": pid, "cp": catalogo_productos}


def test_sprints_y_final_edition_encuentran_la_fila_por_el_color(catalogo):
    from sprints import ideas
    import final_edition
    assert ideas._producto_fila("acme", "original/pink")["precio"] == 34.95
    assert final_edition._fila_producto("acme", "original/pink")["precio"] == 34.95
    assert ideas._producto_fila("acme", "nada") == {}


def test_productos_tienda_contexto_suma_experimentos_de_todos_los_colores(catalogo, monkeypatch):
    import dashboard
    monkeypatch.setattr(dashboard, "_experimentos_por_activo",
                        lambda cliente, experimentos_exp=None: {"original — pink": {1, 2}, "original": {2, 3}})
    (fila,) = dashboard._productos_tienda_contexto("acme", experimentos_exp=[])
    assert fila["activo_ok"] and fila["n_experimentos"] == 3


def test_experimentos_por_activo_devuelve_claves_en_minusculas(base_temporal, monkeypatch):
    import creative_flow
    import dashboard
    cf = creative_flow.crear("acme", [], ["Original — Pink"], [], "acción", 8, "tono", "A", legado_id="cf_20260928_000001_000001")
    monkeypatch.setattr(dashboard.experimentos, "cargar",
                        lambda cliente: [{"id": 7, "piezas": [{"legado_id": cf}]}])
    assert dashboard._experimentos_por_activo("acme") == {"original — pink": {7}}


def test_faltantes_del_producto_reune_ideas_de_un_color_y_sesiones_por_nombre(catalogo, monkeypatch):
    """Copia el armado de sprint + persona + campaña de tests/test_doctrina_pedidos.py
    (la misma función/fixture que ese archivo usa para probar faltantes) con
    `catalogo_id="original/pink"` y una pieza cuyo `extra.angulo.faltantes` traiga
    «¿Cuánto pesa?»; y una sesión de Crear con productos_ids=["Original — Pink"] cuyo
    `extra.angulo.faltantes` traiga «¿De qué material es?»."""
    import creative_flow
    import tiendas
    from doctrina import pedidos
    from sprints import datos as sprints_datos
    # --- sesión de Crear que nombra el color ---
    cf = creative_flow.crear("acme", [], ["Original — Pink"], [], "acción", 8, "tono", "A", legado_id="cf_20260928_000002_000002")
    creative_flow.actualizar("acme", cf, angulo={"faltantes": ["¿De qué material es?"]})
    fila = tiendas.producto("acme", catalogo["pid"])
    faltantes = pedidos.faltantes_del_producto("acme", fila)
    assert "¿De qué material es?" in faltantes
    # --- idea de una campaña cuyo catalogo_id es el COLOR (mismo armado que
    # tests/test_doctrina_pedidos.py::_producto_con_piezas, vía sprints.datos) ---
    persona_id = sprints_datos.crear_persona("acme", "Premium")
    sprint_id = sprints_datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31")
    campana_id = sprints_datos.agregar_campana("acme", sprint_id, persona_id, "original/pink")
    sprints_datos.crear_idea("acme", campana_id, "video", "Idea", "escena",
                             extra={"angulo": {"faltantes": ["¿Cuánto pesa?"]}})
    faltantes = pedidos.faltantes_del_producto("acme", fila)
    assert "¿Cuánto pesa?" in faltantes
