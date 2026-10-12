"""«Archivar» un producto entero desde su ficha (pedido de Daniel, 2026-10-01,
para los productos viejos hechos a mano de happyflops): TODAS sus filas
`producto` pasan a archivadas a mano con la marca `archivado_con_producto`;
la galería lo esconde (sigue en «Archivados») y los selectores de Crear,
Cambiar producto, Sprints, Nicho, Recrear y Flow Plus no lo ofrecen, salvo
donde ya estaba elegido. No se borra nada. «Desarchivar» devuelve solo las
filas que archivó él (y las que la sync había archivado), nunca un duplicado
archivado a mano por otra razón (migración 0025)."""
import pytest

from tests.test_rutas_catalogo import _con_colores
from tests.test_rutas_productos import _flashes, app  # noqa: F401
# El fixture de Sprints con otro nombre: su catálogo es una lista fija (espejo_led, division_bano).
from tests.test_rutas_sprints import app as sprints_app  # noqa: F401


# --- tiendas: el producto entero -------------------------------------------

def test_archivar_activo_archiva_todas_sus_filas_y_desarchivar_las_devuelve(base_temporal):
    import tiendas
    manual = tiendas.asegurar_manual("acme", "cojin", "Cojín")
    csv = tiendas.upsert_producto("acme", "csv", "sku-1", {"nombre": "Cojín", "precio": 1, "moneda": "COP"})
    tiendas.marcar_producto("acme", csv, activo_catalogo_id="cojin")
    otro = tiendas.asegurar_manual("acme", "manta", "Manta")
    assert tiendas.activos_archivados("acme") == set()

    assert tiendas.archivar_activo("acme", "cojin") == 2
    assert tiendas.activos_archivados("acme") == {"cojin"}
    filas = {f["id"]: f for f in tiendas.productos("acme", incluir_archivados=True)}
    assert filas[manual]["archivado"] and filas[csv]["archivado"] and not filas[otro]["archivado"]
    assert filas[csv]["extra"]["archivado_por"] == "manual" and filas[csv]["extra"]["archivado_con_producto"] is True

    # Es un archivado a mano: la sync de la tienda no lo deshace.
    tiendas.upsert_producto("acme", "csv", "sku-1", {"nombre": "Cojín", "precio": 2, "moneda": "COP"})
    assert tiendas.activos_archivados("acme") == {"cojin"}

    assert tiendas.archivar_activo("acme", "cojin", archivado=False) == 2
    assert tiendas.activos_archivados("acme") == set()
    fila = tiendas.producto("acme", csv)
    assert not fila["archivado"] and "archivado_por" not in fila["extra"] and "archivado_con_producto" not in fila["extra"]
    assert fila["precio"] == 2   # la sync sí actualizó sus datos mientras estuvo archivado


def test_desarchivar_no_revive_un_duplicado_archivado_a_mano_por_otra_razon(base_temporal):
    """La migración 0025 dejó filas duplicadas archivadas a mano apuntando al
    mismo producto: si «Desarchivar» las devolviera, cambiaría qué fila manda
    (precio y URL viejos)."""
    import tiendas
    viva = tiendas.asegurar_manual("acme", "cojin", "Cojín")
    dup = tiendas.upsert_producto("acme", "csv", "viejo", {"nombre": "Cojín viejo", "precio": 9, "moneda": "COP"})
    tiendas.marcar_producto("acme", dup, activo_catalogo_id="cojin", archivado=True)   # a mano, sin la marca
    assert tiendas.archivar_activo("acme", "cojin") == 1
    assert tiendas.archivar_activo("acme", "cojin", archivado=False) == 1
    assert not tiendas.producto("acme", viva)["archivado"] and tiendas.producto("acme", dup)["archivado"]
    assert tiendas.por_activo("acme")["cojin"]["id"] == viva


def test_archivar_toma_tambien_la_fila_que_la_sync_ya_habia_archivado(base_temporal):
    """La tienda dejó de listar el producto (la sync archivó su fila) y la
    persona lo archiva: si la tienda lo vuelve a listar, sigue archivado."""
    import tiendas
    fid = tiendas.upsert_producto("acme", "shopify", "gid-1", {"nombre": "Original", "precio": 1, "moneda": "USD"})
    tiendas.marcar_producto("acme", fid, activo_catalogo_id="original")
    assert tiendas.archivar_faltantes("acme", "shopify", set()) == 1
    assert tiendas.archivar_activo("acme", "original") == 1
    tiendas.upsert_producto("acme", "shopify", "gid-1", {"nombre": "Original", "precio": 1, "moneda": "USD"})
    assert tiendas.activos_archivados("acme") == {"original"}
    assert tiendas.archivar_activo("acme", "original", archivado=False) == 1
    assert tiendas.activos_archivados("acme") == set()


def test_desarchivar_sin_filas_marcadas_recupera_la_que_se_ve(base_temporal):
    """Todas sus filas archivadas a mano por otra razón: «Desarchivar» igual
    tiene que devolver el producto (la fila que la galería muestra)."""
    import tiendas
    a = tiendas.asegurar_manual("acme", "cojin", "Cojín")
    tiendas.marcar_producto("acme", a, archivado=True)
    assert tiendas.activos_archivados("acme") == {"cojin"}
    assert tiendas.archivar_activo("acme", "cojin", archivado=False) == 1
    assert tiendas.activos_archivados("acme") == set()


def test_recuperar_una_fila_suelta_quita_tambien_la_marca(base_temporal):
    """«Recuperar» de una fila (prod_archivar, archivado=0) deja la fila limpia."""
    import tiendas
    a = tiendas.asegurar_manual("acme", "cojin", "Cojín")
    tiendas.archivar_activo("acme", "cojin")
    tiendas.marcar_producto("acme", a, archivado=False)
    assert "archivado_con_producto" not in tiendas.producto("acme", a)["extra"]


def test_activos_archivados_con_una_fila_viva_el_producto_esta_vivo(base_temporal):
    import tiendas
    a = tiendas.asegurar_manual("acme", "cojin", "Cojín")
    b = tiendas.upsert_producto("acme", "csv", "sku", {"nombre": "Cojín", "precio": 1, "moneda": "COP"})
    tiendas.marcar_producto("acme", b, activo_catalogo_id="cojin", archivado=True)
    assert tiendas.activos_archivados("acme") == set()
    tiendas.marcar_producto("acme", a, archivado=True)
    assert tiendas.activos_archivados("acme") == {"cojin"}
    assert tiendas.activos_archivados("otro") == set()


# --- catalogo_productos.sin_archivados ---------------------------------------

def test_sin_archivados_quita_el_producto_y_sus_colores_salvo_lo_elegido():
    import catalogo_productos as cp
    entradas = [{"id": "original/pink"}, {"id": "original/beige"}, {"id": "cozy"}, {"id": "viejo"}]
    assert cp.sin_archivados(entradas, set()) == entradas
    assert [e["id"] for e in cp.sin_archivados(entradas, {"original", "viejo"})] == ["cozy"]
    assert [e["id"] for e in cp.sin_archivados(entradas, {"original", "viejo"}, conservar=["original/beige", None, ""])] \
        == ["original/pink", "original/beige", "cozy"]
    assert [e["id"] for e in cp.sin_archivados(entradas, {"viejo"}, conservar=["viejo"])] == [e["id"] for e in entradas]


# --- la ficha y la galería ----------------------------------------------------

URL = "/cliente/acme/catalogo/producto/{}/archivar"


def test_archivar_y_desarchivar_desde_la_ficha(app):
    import tiendas
    _con_colores(app)
    c = app["c"]
    archivar, desarchivar = 'name="archivado" value="1"', 'name="archivado" value="0"'
    ficha = c.get("/cliente/acme/catalogo/producto/original/ficha").get_data(as_text=True)
    assert URL.format("original") in ficha and archivar in ficha and desarchivar not in ficha

    r = c.post(URL.format("original"), data={"archivado": "1"})
    assert r.status_code == 302 and r.headers["Location"].endswith("#catalogo?ficha=producto:original")
    assert tiendas.activos_archivados("acme") == {"original"}
    assert any("Archivaste «Original»" in m for m in _flashes(c))
    ficha = c.get("/cliente/acme/catalogo/producto/original/ficha").get_data(as_text=True)
    assert desarchivar in ficha and "Desarchivar" in ficha and archivar not in ficha
    assert "Crear con este producto" not in ficha and "cat-ficha-archivado" in ficha

    r = c.post(URL.format("original"), data={"archivado": "0"})
    assert r.headers["Location"].endswith("#catalogo?ficha=producto:original")
    assert tiendas.activos_archivados("acme") == set()
    ficha = c.get("/cliente/acme/catalogo/producto/original/ficha").get_data(as_text=True)
    assert "Crear con este producto" in ficha and archivar in ficha and desarchivar not in ficha


def test_archivar_un_producto_que_no_existe_no_crea_nada(app):
    import tiendas
    r = app["c"].post(URL.format("nada"), data={"archivado": "1"})
    assert r.status_code == 302 and r.headers["Location"].endswith("#catalogo")
    assert tiendas.productos("acme", incluir_archivados=True) == []


def test_archivar_rechaza_un_post_de_otro_sitio(app):
    import tiendas
    _con_colores(app)
    r = app["c"].post(URL.format("original"), data={"archivado": "1"}, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    assert tiendas.activos_archivados("acme") == set()


def test_la_galeria_lo_esconde_y_lo_muestra_en_archivados(app):
    _con_colores(app)
    _con_colores(app, pid="cozy", nombre="Cozy", colores=("Gray",))
    c = app["c"]
    c.post(URL.format("original"), data={"archivado": "1"})
    todos = c.get("/cliente/acme/catalogo/grid?cat=producto").get_data(as_text=True)
    assert 'data-abrir-ficha="producto:cozy"' in todos and 'data-abrir-ficha="producto:original"' not in todos
    archivados = c.get("/cliente/acme/catalogo/grid?cat=producto&filtro=archivados").get_data(as_text=True)
    assert 'data-abrir-ficha="producto:original"' in archivados and 'data-abrir-ficha="producto:cozy"' not in archivados
    assert "prod-archivado" in archivados


# --- los selectores -------------------------------------------------------------

def test_crear_y_cambiar_producto_no_ofrecen_el_archivado(app):
    _con_colores(app)
    _con_colores(app, pid="cozy", nombre="Cozy", colores=("Gray",))
    c = app["c"]
    c.post(URL.format("original"), data={"archivado": "1"})
    html = c.get("/cliente/acme").get_data(as_text=True)
    # Desde la página por partes (PND-062, 2026-10-10) la grilla llega por fetch al abrir el selector.
    crear = c.get("/cliente/acme/catalogo/selector?sel=plus", headers={"X-Requested-With": "fetch"}).get_data(as_text=True)
    cambiar = c.get("/cliente/acme/catalogo/selector?sel=clone", headers={"X-Requested-With": "fetch"}).get_data(as_text=True)
    assert 'value="producto:cozy/gray"' in crear and 'value="producto:original/pink"' not in crear      # Crear
    assert 'name="producto_id" value="cozy/gray"' in cambiar and 'value="original/pink"' not in cambiar   # Cambiar producto
    assert 'data-n-cat="producto">1</span>' in html                                                  # la pestaña cuenta 1


def test_una_precarga_de_crear_conserva_el_producto_archivado(app):
    """«Editar y crear otra a partir de esta» de una pieza vieja: el producto
    archivado sigue marcado (si no estuviera en el selector se perdería en
    silencio)."""
    _con_colores(app)
    c = app["c"]
    c.post(URL.format("original"), data={"archivado": "1"})
    with c.session_transaction() as s:
        s["fp_prefill"] = {"cliente": "acme", "productos_catalogo": ["producto:original/pink"]}
    html = c.get("/cliente/acme").get_data(as_text=True)
    assert 'value="producto:original/pink"' in html


def test_el_panel_de_sprints_no_ofrece_el_archivado_salvo_el_de_la_campana(sprints_app):
    import tiendas
    from sprints import datos
    from tests.test_rutas_sprints import _base
    pid, tid = _base(datos)
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31")
    con_viejo = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 1, 0)
    con_otro = datos.agregar_campana("acme", sid, pid, "division_bano", tid, 1, 0)
    tiendas.asegurar_manual("acme", "espejo_led", "Espejo LED")
    tiendas.archivar_activo("acme", "espejo_led")
    c = sprints_app["c"]
    otro = c.get(f"/cliente/acme/sprints/{sid}/campanas/{con_otro}/panel").get_data(as_text=True)
    assert 'value="division_bano"' in otro and 'value="espejo_led"' not in otro
    viejo = c.get(f"/cliente/acme/sprints/{sid}/campanas/{con_viejo}/panel").get_data(as_text=True)
    assert 'value="espejo_led" selected' in viejo and "ya no está en el catálogo" not in viejo
    detalle = c.get(f"/cliente/acme/sprints/{sid}").get_data(as_text=True)
    assert '<option value="division_bano">' in detalle and '<option value="espejo_led">' not in detalle


def test_nicho_no_ofrece_el_archivado_salvo_el_del_estudio(app):
    import tiendas
    from nicho import rutas as nicho_rutas
    _con_colores(app)
    _con_colores(app, pid="cozy", nombre="Cozy", colores=("Gray",))
    tiendas.asegurar_manual("acme", "original", "Original")
    tiendas.archivar_activo("acme", "original")
    assert [p["id"] for p in nicho_rutas._productos("acme")] == ["cozy"]
    assert sorted(p["id"] for p in nicho_rutas._productos("acme", conservar=["original/pink"])) == ["cozy", "original"]


def test_recrear_no_ofrece_el_archivado_salvo_el_pedido(app):
    import tiendas
    from referentes import rutas as ref_rutas
    _con_colores(app)
    _con_colores(app, pid="cozy", nombre="Cozy", colores=("Gray",))
    tiendas.asegurar_manual("acme", "original", "Original")
    tiendas.archivar_activo("acme", "original")
    productos, producto = ref_rutas._producto_para("acme", {})
    assert [p["id"] for p in productos] == ["cozy/gray"] and producto["id"] == "cozy/gray"
    productos, producto = ref_rutas._producto_para("acme", {"producto_id": "original/pink"})
    assert "original/pink" in [p["id"] for p in productos] and producto["id"] == "original/pink"


def test_flow_plus_no_ofrece_el_archivado_salvo_el_que_usa_la_version(app):
    import tiendas
    from guiones import rutas_pipeline
    _con_colores(app)
    _con_colores(app, pid="cozy", nombre="Cozy", colores=("Gray",))
    tiendas.asegurar_manual("acme", "original", "Original")
    tiendas.archivar_activo("acme", "original")
    catalogo = rutas_pipeline._catalogo_para_elegir("acme", [])
    assert [a["id"] for a in catalogo["producto"]] == ["cozy/gray"]
    en_uso = [{"tipo": "producto", "activo_id": "original/beige"}, {"tipo": "personaje", "activo_id": "ana"}]
    catalogo = rutas_pipeline._catalogo_para_elegir("acme", en_uso)
    assert sorted(a["id"] for a in catalogo["producto"]) == ["cozy/gray", "original/beige", "original/pink"]


def test_sugerir_personas_no_le_cuenta_a_claude_el_archivado(app, monkeypatch):
    import tiendas
    from sprints import sugerencias
    _con_colores(app, pid="viejo", nombre="Pantufla Vieja", colores=("Gris",))
    _con_colores(app, pid="cozy", nombre="Cozy Nueva", colores=("Gray",))
    tiendas.asegurar_manual("acme", "viejo", "Pantufla Vieja")
    tiendas.archivar_activo("acme", "viejo")
    visto = {}

    def falso(contenido, **kw):
        visto["texto"] = contenido[0]["text"]
        raise RuntimeError("basta")
    monkeypatch.setattr(sugerencias.analisis, "_llamar", falso)
    with pytest.raises(RuntimeError):
        sugerencias.sugerir_personas("acme")
    assert "Cozy Nueva" in visto["texto"] and "Pantufla Vieja" not in visto["texto"]
