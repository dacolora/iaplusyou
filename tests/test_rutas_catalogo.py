"""Rutas del catálogo por colores (spec 2026-09-28 §10–11): imágenes de
colores, subir/quitar fotos por color, colores, mover fotos, «crear con»,
vuelta a la ficha, galería y ficha como fragmentos."""
import io
import os

import pytest

from tests.test_rutas_productos import _activo_con_foto, _flashes, _foto, _producto, app  # noqa: F401

JPG = b"\xff\xd8\xff\xe0fake-jpg"


def _con_colores(app, pid="original", nombre="Original", colores=("Pink", "Beige"), generales=1, cliente="acme"):
    import catalogo_productos as cp
    base = app["tmp"] / "clientes" / cliente / "productos" / pid
    base.mkdir(parents=True, exist_ok=True)
    meta = cp.cargar_meta(cliente)
    meta[pid] = {"nombre": nombre, "descripcion": "slides", "tipo": "calzado", "zonas": ["pies"], "regla": "",
                 "variantes": {cp.id_desde_nombre(c): {"nombre": f"{nombre} — {c}", "descripcion": "", "fuente_id": None,
                                                       "url_compra": None, "disponible": True} for c in colores}}
    cp.guardar_meta(cliente, meta)
    for c in colores:
        d = base / cp.id_desde_nombre(c)
        d.mkdir(exist_ok=True)
        (d / "01.jpg").write_bytes(JPG)
    for i in range(generales):
        (base / f"0{i + 1}.jpg").write_bytes(JPG)
    return pid


def test_imagenes_de_colores_con_barra_en_el_id(app):
    _con_colores(app)
    c = app["c"]
    assert c.get("/cliente/acme/productos/original/pink/imagen?categoria=producto&w=320").status_code == 200
    assert c.get("/cliente/acme/productos/original/imagen?categoria=producto").status_code == 200   # el primer color
    assert c.get("/cliente/acme/productos/original/pink/imagen/01.jpg?categoria=producto").status_code == 200
    assert c.get("/cliente/acme/productos/original/imagen/01.jpg?categoria=producto&variante=pink").status_code == 200
    assert c.get("/cliente/acme/productos/original/imagen/01.jpg?categoria=producto").status_code == 200      # general
    assert c.get("/cliente/acme/productos/original/imagen/01.jpg?categoria=producto&variante=..").status_code == 404
    assert c.get("/cliente/acme/productos/nada/pink/imagen/01.jpg").status_code == 404


def test_la_pagina_del_proyecto_crea_una_fila_por_producto_no_por_color(app):
    import tiendas
    _con_colores(app)
    assert app["c"].get("/cliente/acme").status_code == 200
    filas = tiendas.productos("acme", incluir_archivados=True)
    assert [f["activo_catalogo_id"] for f in filas] == ["original"]


def test_subir_y_quitar_foto_de_un_color_vuelven_a_la_ficha(app):
    _con_colores(app)
    c = app["c"]
    r = c.post("/cliente/acme/productos/original/imagenes/subir",
               data={"categoria": "producto", "variante": "pink", "imagenes": [_foto("b.jpg")]}, content_type="multipart/form-data")
    assert r.status_code == 302 and r.headers["Location"].endswith("#catalogo?ficha=producto:original")
    assert sorted(os.listdir(app["tmp"] / "clientes" / "acme" / "productos" / "original" / "pink")) == ["01.jpg", "b.jpg"]
    r = c.post("/cliente/acme/productos/original/imagenes/01.jpg/eliminar", data={"categoria": "producto", "variante": "pink"})
    assert r.headers["Location"].endswith("#catalogo?ficha=producto:original")
    assert os.listdir(app["tmp"] / "clientes" / "acme" / "productos" / "original" / "pink") == ["b.jpg"]
    r = c.post("/cliente/acme/productos/original/imagenes/b.jpg/eliminar", data={"categoria": "producto", "variante": "pink"})
    assert any("única foto" in m for m in _flashes(c))


def test_subir_fotos_a_un_color_que_no_existe_no_escribe_nada(app):
    """Revisión final: un `variante` que no es un color de la meta creaba la
    subcarpeta y guardaba la foto donde ningún listado la ve."""
    _con_colores(app)
    c = app["c"]
    base = app["tmp"] / "clientes" / "acme" / "productos" / "original"
    antes = sorted(os.listdir(base))
    r = c.post("/cliente/acme/productos/original/imagenes/subir",
               data={"categoria": "producto", "variante": "rojo", "imagenes": [_foto("x.jpg")]}, content_type="multipart/form-data")
    assert r.status_code == 302 and r.headers["Location"].endswith("#catalogo?ficha=producto:original")
    assert any("Ese color no existe." in m for m in _flashes(c))
    assert sorted(os.listdir(base)) == antes and not (base / "rojo").exists()
    # un personaje no tiene colores
    import catalogo_productos as cp
    aid = cp.crear("acme", "Ana", categoria="personaje")
    c.post(f"/cliente/acme/productos/{aid}/imagenes/subir",
           data={"categoria": "personaje", "variante": "pink", "imagenes": [_foto("y.jpg")]}, content_type="multipart/form-data")
    assert os.listdir(cp.carpeta_de("acme", aid, "personaje")) == []


def test_actualizar_y_crear_vuelven_a_la_ficha(app):
    _con_colores(app)
    c = app["c"]
    r = c.post("/cliente/acme/productos/original/actualizar", data={"categoria": "producto", "nombre": "Original 2", "descripcion": "x",
                                                                    "precio": "34.95", "moneda": "EUR", "url_compra": "https://t/o"})
    assert r.headers["Location"].endswith("#catalogo?ficha=producto:original")
    import tiendas
    assert tiendas.por_activo("acme")["original"]["precio"] == 34.95
    r = c.post("/cliente/acme/productos/crear", data={"nombre": "Gorra", "descripcion": "", "categoria": "producto",
                                                      "volver": "catalogo", "imagenes": _foto()}, content_type="multipart/form-data")
    assert r.headers["Location"].endswith("#catalogo?ficha=producto:gorra")
    r = c.post("/cliente/acme/productos/gorra/eliminar", data={"categoria": "producto"})
    assert r.headers["Location"].endswith("#catalogo")


def test_agregar_color_con_fotos_y_conversion(app):
    import catalogo_productos as cp
    c = app["c"]
    _activo_con_foto("acme", "Cojín")
    r = c.post("/cliente/acme/productos/cojin/colores", data={"nombre": "Rojo", "imagenes": [_foto("r.jpg")]}, content_type="multipart/form-data")
    assert any("dime de qué color" in m for m in _flashes(c))
    r = c.post("/cliente/acme/productos/cojin/colores", data={"nombre": "Rojo", "convertir_actual": "Azul", "imagenes": [_foto("r.jpg")]},
               content_type="multipart/form-data")
    assert r.headers["Location"].endswith("#catalogo?ficha=producto:cojin")
    p = cp.encontrar_producto("acme", "cojin")
    assert [x["color_id"] for x in p["colores"]] == ["azul", "rojo"] and p["colores"][1]["imagenes"] == ["r.jpg"]
    r = c.post("/cliente/acme/productos/cojin/colores/azul/quitar")
    assert r.headers["Location"].endswith("#catalogo?ficha=producto:cojin") and cp.encontrar_producto("acme", "cojin")["n_colores"] == 1
    r = c.post("/cliente/acme/productos/cojin/colores/rojo/quitar")
    assert any("único color" in m for m in _flashes(c))


def test_mover_foto_general_a_un_color(app):
    import catalogo_productos as cp
    _con_colores(app, generales=1)
    r = app["c"].post("/cliente/acme/productos/original/fotos/01.jpg/mover", data={"variante": "beige"})
    assert r.headers["Location"].endswith("#catalogo?ficha=producto:original")
    p = cp.encontrar_producto("acme", "original")
    assert p["fotos_generales"] == [] and p["colores"][1]["imagenes"] == ["01.jpg", "01_2.jpg"]
    app["c"].post("/cliente/acme/productos/original/fotos/nada.jpg/mover", data={"variante": "beige"})
    assert any("No encontré esa imagen" in m for m in _flashes(app["c"]))


def test_fotos_con_espacios_en_el_nombre_se_ven_se_borran_y_se_mueven(app):
    """Revisión final: las fotos de happyflops ya comprometidas se llaman
    «HOriginal - Beige_5.png»; `secure_filename` las volvía
    «HOriginal_-_Beige_5.png» y la ficha daba 404. Ahora se sirve el nombre
    tal cual si es una imagen de ESA carpeta; cualquier otra cosa, 404."""
    from urllib.parse import quote
    _con_colores(app, generales=0)
    base = app["tmp"] / "clientes" / "acme" / "productos" / "original"
    (base / "pink" / "HOriginal - Beige_5.png").write_bytes(JPG)
    (base / "pink" / "notas.txt").write_bytes(b"no es foto")
    (base / "HOriginal - Ambiente 1.png").write_bytes(JPG)
    c = app["c"]
    con_espacios = quote("HOriginal - Beige_5.png")
    assert c.get(f"/cliente/acme/productos/original/pink/imagen/{con_espacios}?categoria=producto").status_code == 200
    assert c.get(f"/cliente/acme/productos/original/imagen/{con_espacios}?categoria=producto&variante=pink&w=320").status_code == 200
    assert c.get(f"/cliente/acme/productos/original/imagen/{quote('HOriginal - Ambiente 1.png')}?categoria=producto").status_code == 200
    ficha = c.get("/cliente/acme/catalogo/producto/original/ficha").data.decode()
    assert "HOriginal%20-%20Beige_5.png" in ficha                     # la ficha la pide con su nombre real
    for malo in ("..", "..%2Fx", quote("../pink/01.jpg"), "notas.txt", quote("HOriginal_-_Beige_5.png")):
        assert c.get(f"/cliente/acme/productos/original/pink/imagen/{malo}?categoria=producto").status_code == 404, malo
    # borrar y mover aceptan el mismo nombre
    r = c.post(f"/cliente/acme/productos/original/imagenes/{con_espacios}/eliminar", data={"categoria": "producto", "variante": "pink"})
    assert r.status_code == 302 and sorted(os.listdir(base / "pink")) == ["01.jpg", "notas.txt"]
    r = c.post(f"/cliente/acme/productos/original/fotos/{quote('HOriginal - Ambiente 1.png')}/mover", data={"variante": "beige"})
    assert r.status_code == 302 and sorted(os.listdir(base / "beige")) == ["01.jpg", "HOriginal - Ambiente 1.png"]


def test_crear_con_deja_el_color_marcado_para_crear(app):
    _con_colores(app)
    c = app["c"]
    r = c.post("/cliente/acme/catalogo/producto/original/crear-con", data={"variante": "beige"})
    assert r.status_code == 302 and r.headers["Location"].endswith("#creativeflowplus")
    with c.session_transaction() as s:
        assert s["fp_prefill"] == {"cliente": "acme", "productos_catalogo": ["producto:original/beige"]}
    r = c.post("/cliente/acme/catalogo/producto/original/crear-con", data={})
    with c.session_transaction() as s:
        assert s["fp_prefill"] == {"cliente": "acme", "productos_catalogo": ["producto:original/pink"]}
    html = c.get("/cliente/acme").data.decode()
    assert '"productos_catalogo": ["producto:original/pink"]' in html      # el prefill llega al JS de Crear
    c.post("/cliente/acme/catalogo/producto/nada/crear-con", data={})
    assert any("no tiene fotos" in m for m in _flashes(c))


def test_selector_de_crear_agrupa_los_colores_por_producto(app):
    """El selector de Crear (diálogo «Del catálogo») agrupa los colores de un
    mismo producto bajo un encabezado en vez de listarlos sueltos (spec
    2026-09-28 §10.5); un producto plano sigue con su tile de siempre."""
    _con_colores(app)
    _activo_con_foto("acme", "Cojín")
    html = app["c"].get("/cliente/acme").data.decode()
    dialogo = html.split('id="fp-catalogo"', 1)[1].split("</dialog>", 1)[0]
    # La franja entre el primer "producto-grupo" y el siguiente (o el fin del
    # diálogo si no hay otro): más robusto que depender de la indentación exacta.
    resto = dialogo.split('class="producto-grupo"', 1)[1]
    grupo = resto.split('class="producto-grupo"', 1)[0]
    assert "Original" in grupo and "2 colores" in grupo
    assert 'value="producto:original/pink"' in grupo and 'value="producto:original/beige"' in grupo
    assert 'data-nombre="original original — pink"' in grupo and "<span>Pink</span>" in grupo
    assert 'value="producto:cojin"' in dialogo and 'class="producto-grupo"' not in dialogo.split('value="producto:cojin"', 1)[0].rsplit("<label", 1)[1]
    # «Crear con este producto» marca los colores desde la misma precarga de Crear (_prefill_para).
    assert "prefill.productos_catalogo.forEach" in html and "input[name=productos_catalogo][value=" in html


def test_prod_rutas_vuelven_a_la_ficha_si_la_fila_tiene_activo(app):
    import tiendas
    pid = _producto(nombre="Cojín Azul")
    r = app["c"].post(f"/cliente/acme/productos/{pid}/archivar")
    assert r.headers["Location"].endswith("#catalogo")                  # sin activo: la galería
    tiendas.marcar_producto("acme", pid, archivado=False)
    _activo_con_foto("acme", "Cojín Azul", "cojin_azul")
    tiendas.marcar_producto("acme", pid, activo_catalogo_id="cojin_azul")
    r = app["c"].post(f"/cliente/acme/productos/{pid}/pruebas", data={"texto": "Dura 3 inviernos", "fuente": "ficha"})
    assert r.headers["Location"].endswith("#catalogo?ficha=producto:cojin_azul")


def test_grid_de_productos_con_tarjetas_filtros_y_filas_sin_fotos(app):
    import tiendas
    _con_colores(app)                                                       # Original: 2 colores
    pid_ok = _producto(nombre="Cojín Azul")                                  # importada con activo
    _activo_con_foto("acme", "Cojín Azul", "cojin_azul")
    tiendas.marcar_producto("acme", pid_ok, activo_catalogo_id="cojin_azul", en_prueba=True, prioridad=40)
    _producto(nombre="Espejo redondo")                                      # importada sin activo
    pid_arch = _producto(nombre="Lámpara")
    tiendas.marcar_producto("acme", pid_arch, archivado=True)
    c = app["c"]
    r = c.get("/cliente/acme/catalogo/grid?cat=producto")
    assert r.status_code == 200
    html = r.data.decode()
    assert 'data-n-todos="3"' in html and 'data-n-en_prueba="1"' in html and 'data-n-sin_fotos="1"' in html and 'data-n-archivados="1"' in html
    assert html.index('id="producto-cojin_azul"') < html.index('id="producto-original"') < html.index('id="producto-fila-')
    cojin = html.split('id="producto-cojin_azul"', 1)[1].split("</article>", 1)[0]
    assert "89.900 COP" in cojin and "en prueba" in cojin and "CSV/Excel" in cojin and 'data-abrir-ficha="producto:cojin_azul"' in cojin
    orig = html.split('id="producto-original"', 1)[1].split("</article>", 1)[0]
    assert "2 colores" in orig and "sin precio" in orig and "sin URL" in orig and orig.count("cat-color-punto") == 2
    assert "/productos/original/pink/imagen?" in orig
    espejo = html.split('id="producto-fila-', 1)[1].split("</article>", 1)[0]
    assert "Sin fotos" in espejo and "Subir fotos" in espejo and "Crear activo desde las fotos de la tienda" in espejo and "Archivar" in espejo
    assert "Lámpara" not in html
    html = c.get("/cliente/acme/catalogo/grid?cat=producto&filtro=archivados").data.decode()
    assert "Lámpara" in html and "Recuperar" in html and 'data-archivado="1"' in html and "Cojín" not in html
    html = c.get("/cliente/acme/catalogo/grid?cat=producto&filtro=en_prueba").data.decode()
    assert "cojin_azul" in html and "producto-original" not in html
    html = c.get("/cliente/acme/catalogo/grid?cat=producto&q=beige").data.decode()
    assert "producto-original" in html and "cojin_azul" not in html          # busca también por color
    html = c.get("/cliente/acme/catalogo/grid?cat=producto&q=zzz").data.decode()
    assert "Nada coincide" in html
    assert 'data-abrir-detalle="cat-traer"' in c.get("/cliente/acme/catalogo/grid?cat=entorno").data.decode() or "Todavía no hay entornos" in c.get("/cliente/acme/catalogo/grid?cat=entorno").data.decode()


def test_grid_pagina_de_60_en_60(app, monkeypatch):
    import catalogo_vista
    monkeypatch.setattr(catalogo_vista, "POR_PAGINA", 2)
    for n in ("A", "B", "C"):
        _activo_con_foto("acme", f"Prod {n}")
    html = app["c"].get("/cliente/acme/catalogo/grid?cat=producto&orden=nombre").data.decode()
    assert 'id="producto-prod_a"' in html and 'id="producto-prod_c"' not in html and 'data-cat-mas="2"' in html
    html = app["c"].get("/cliente/acme/catalogo/grid?cat=producto&orden=nombre&pagina=2").data.decode()
    assert 'id="producto-prod_c"' in html and "data-cat-mas" not in html


def test_ficha_de_producto_con_colores(app):
    import tiendas
    _con_colores(app, generales=1)
    c = app["c"]
    r = c.get("/cliente/acme/catalogo/producto/original/beige/ficha")
    assert r.status_code == 200
    html = r.data.decode()
    assert 'data-color="pink"' in html and 'data-color="beige"' in html and 'aria-selected="true"' in html.split('data-color="beige"', 1)[1][:80]
    assert 'data-color-fotos="pink" hidden' in html and 'data-color-fotos="beige"' in html
    assert "Subir fotos a este color" in html and "Quitar color" in html and "+ Color" in html and "¿De qué color son" not in html
    assert "Fotos de ambiente" in html and "Asignar a color" in html and "/fotos/01.jpg/mover" in html
    assert 'name="precio"' in html and 'name="url_compra"' in html and "Cuántas promesas parecidas vio ya tu cliente" in html
    assert "Lo que Claude necesita" in html and "Pruebas del producto" in html
    assert "Crear con este producto" in html and '<option value="beige" selected' in html and "Crear experimento" in html
    assert "Dónde se usó" in html and 'data-accion="/cliente/acme/productos/original/eliminar"' in html
    assert tiendas.por_activo("acme")["original"]["fuente"] == "manual"          # la ficha asegura la fila
    assert "&lt;script&gt;" not in html and "<script" not in html                  # el fragmento no trae scripts


def test_ficha_de_producto_plano_personaje_y_404(app):
    _activo_con_foto("acme", "Cojín")
    c = app["c"]
    html = c.get("/cliente/acme/catalogo/producto/cojin/ficha").data.decode()
    assert "Fotos de referencia" in html and "¿De qué color son las fotos actuales?" in html and 'value="Cojín"' in html
    assert "Fotos de ambiente" not in html
    import catalogo_productos as cp
    aid = cp.crear("acme", "Ana", categoria="personaje")
    with open(os.path.join(cp.carpeta_de("acme", aid, "personaje"), "cara.jpg"), "wb") as f:
        f.write(JPG)
    html = c.get("/cliente/acme/catalogo/personaje/ana/ficha").data.decode()
    assert "cara.jpg" in html and 'name="precio"' not in html and "+ Color" not in html and "Eliminar" in html
    assert c.get("/cliente/acme/catalogo/producto/nada/ficha").status_code == 404
    assert c.get("/cliente/acme/catalogo/producto/../etc/ficha").status_code == 404


def test_la_pestana_trae_el_js_del_panel_y_el_css(app):
    html = app["c"].get("/cliente/acme").data.decode()
    for pieza in ("function abrirFicha(", "function cargarGrid(", "[data-poll-job]", "window.iniciarManiquis",
                  "history.replaceState(null, '', '#catalogo'", "addEventListener('hashchange'"):
        assert pieza in html, pieza
    import os
    css = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "style.css"), encoding="utf-8").read()
    i = css.index("Catálogo: galería y ficha")
    assert i > css.index("Base visual común")
    bloque = css[i:]
    for clase in (".cat-tarjetas", ".cat-tarjeta", ".cat-color-punto", ".cat-colores-tira", ".cat-color-ficha", ".cat-panel-lateral",
                  "@media (max-width: 640px)"):
        assert clase in bloque, clase


def test_el_select_asignar_a_color_ocupa_el_ancho_de_su_foto():
    """Revisión final (prueba real, T17): «Asignar a color…» se cortaba a 92 px.
    La celda de una foto de ambiente es más ancha, la foto la llena y el select
    ocupa todo el ancho de su celda."""
    import os
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    css = open(os.path.join(raiz, "static", "style.css"), encoding="utf-8").read()
    bloque = css[css.index("Catálogo: galería y ficha"):]
    celda = bloque.split(".cat-foto-general {", 1)[1].split("}", 1)[0]
    assert "width: 8.5rem" in celda
    foto = bloque.split(".cat-foto-general img {", 1)[1].split("}", 1)[0]
    assert "width: 100%" in foto and "aspect-ratio: 1 / 1" in foto
    select = bloque.split(".cat-foto-general .cat-form-mover select {", 1)[1].split("}", 1)[0]
    assert "width: 100%" in select and "92px" not in select


def test_cerrar_la_ficha_o_cambiar_de_pestana_no_pierde_lo_escrito(app):
    """Ruling I-7: Escape, el fondo y la ✕ preguntan si la ficha tiene campos
    sin guardar (data-sucio, base.html); salir de la pestaña con cambios solo
    OCULTA el panel (sin vaciarlo) y vuelve al regresar a Catálogo; con el
    modal de eliminar abierto, Escape cierra solo el modal."""
    html = app["c"].get("/cliente/acme").data.decode()
    tab = html.split('id="tab-catalogo"', 1)[1].split('id="tab-settings"', 1)[0]
    for pieza in ("Tienes cambios sin guardar en esta ficha",
                  "function fichaSucia() { return !!cuerpo.querySelector('[data-sucio]'); }",
                  "function pedirCerrar()", "if (fichaSucia() && !confirm(MSG_SIN_GUARDAR)) return;",
                  "fondo.addEventListener('click', pedirCerrar);",
                  "if (ev.target.closest('[data-panel-cerrar]')) { pedirCerrar(); return; }",
                  "function salirDeCatalogo()", "if (fichaSucia()) ocultar(); else cerrar();",
                  "function volverACatalogo()", "setTimeout(volverACatalogo, 0)",
                  "var modalEliminar = document.getElementById('modal-eliminar-producto');",
                  "if (modalEliminar && !modalEliminar.hidden) return;"):
        assert pieza in tab, pieza
    # ocultar() no vacía el panel: solo cerrar() lo hace
    ocultar = tab.split("function ocultar()", 1)[1].split("\n", 1)[0]
    assert "innerHTML" not in ocultar and "fichaActual" not in ocultar
    # el hashchange fuera de #catalogo y el clic en otra pestaña ya no cierran a ciegas
    assert "if (!panel.hidden) cerrar();" not in tab


def test_grid_y_ficha_leen_crear_y_experimentos_una_vez(app, monkeypatch):
    """Fix round 1 (revisión de Task 11): _usos_por_producto y
    _experimentos_por_activo no deben releer creative_flow.cargar/
    experimentos.cargar por cada helper — una sola lectura de cada una por
    request, aunque el request pida galería + usos + experimentos."""
    import dashboard
    _con_colores(app)
    contadores = {"cf": 0, "exp": 0}
    cf_real = dashboard.creative_flow.cargar
    exp_real = dashboard.experimentos.cargar

    def cf_contado(cliente):
        contadores["cf"] += 1
        return cf_real(cliente)

    def exp_contado(cliente):
        contadores["exp"] += 1
        return exp_real(cliente)

    monkeypatch.setattr(dashboard.creative_flow, "cargar", cf_contado)
    monkeypatch.setattr(dashboard.experimentos, "cargar", exp_contado)
    c = app["c"]
    # Como cualquier otro fragmento por fetch (tests/test_rutas_referentes.py):
    # X-Requested-With hace que _quiere_json() sea True y el chip de gasto del
    # sidebar (context processor global, ajeno a este fix) no recalcule el
    # tablero — si no, contaría una lectura de experimentos.cargar de más que
    # nada tiene que ver con _usos_por_producto/_experimentos_por_activo.
    fetch = {"X-Requested-With": "fetch"}
    assert c.get("/cliente/acme/catalogo/grid?cat=producto", headers=fetch).status_code == 200
    assert contadores == {"cf": 1, "exp": 1}
    contadores["cf"] = contadores["exp"] = 0
    assert c.get("/cliente/acme/catalogo/producto/original/ficha", headers=fetch).status_code == 200
    assert contadores == {"cf": 1, "exp": 1}


# --- «Traer de mi tienda»: Shopify sin llaves (Tarea 13) ---------------------

def test_traer_de_mi_tienda_conecta_shopify_publico_y_vuelve_al_catalogo(app):
    import tiendas
    from tests.test_rutas_productos import FalsoConector
    FalsoConector.resultado = {"ok": True, "nombre": "HappyFlops WW", "detalle": "Tienda pública leída: 19 productos, moneda EUR.",
                               "dominio": "www.happyflops.com"}
    r = app["c"].post("/cliente/acme/config/tienda/conectar",
                      data={"tipo": "shopify_publico", "dominio": "https://happyflops.com/es", "volver": "catalogo"})
    assert r.status_code == 302 and r.headers["Location"].endswith("#catalogo")
    (t,) = tiendas.listar("acme")
    assert t["tipo"] == "shopify_publico" and t["dominio"] == "www.happyflops.com" and t["nombre"] == "HappyFlops WW"
    assert FalsoConector.credenciales_vistas[-1] == {"dominio": "https://happyflops.com/es"}
    assert any(e["tipo"] == "tienda_sync_productos" for e in app["encolados"])
    assert any("HappyFlops WW" in m for m in _flashes(app["c"]))
    html = app["c"].get("/cliente/acme").data.decode()
    pestana = html.split('id="tab-catalogo"', 1)[1].split('id="tab-settings"', 1)[0]
    assert "Sincronizar ahora" in pestana and "HappyFlops WW" in pestana and 'name="dominio"' not in pestana
    r = app["c"].post("/cliente/acme/config/tienda/1/sincronizar", data={"volver": "catalogo"})
    assert r.headers["Location"].endswith("#catalogo")


def _falso_publico(monkeypatch):
    """`conectores.por_tipo` con un conector sin llaves de fuente «shopify»
    (el del fixture `app` sirve para todos los tipos y no tiene `fuente`)."""
    import conectores
    from tests.test_rutas_productos import FalsoConector

    class FalsoPublico(FalsoConector):
        tipo = "shopify_publico"
        fuente = "shopify"
        tiene_pedidos = False
    monkeypatch.setattr(conectores, "por_tipo", lambda tipo: FalsoPublico if tipo == "shopify_publico" else FalsoConector)


def test_conectar_admin_api_conserva_la_tienda_sin_llaves(app):
    """Ruling final-5 (revierte parte de la ronda de la Tarea 13): la tienda
    sin llaves es la fuente del catálogo — la Admin API no trae colores y lo
    congelaría —, así que conectar la Admin API NO la desconecta: quedan las
    dos, los productos no se tocan y la Admin API suma pedidos y atribución."""
    import tiendas
    from tests.test_rutas_productos import FalsoConector
    tiendas.conectar("acme", "shopify_publico", {"dominio": "www.acme.com"}, nombre="Acme", dominio="www.acme.com")
    pid = tiendas.upsert_producto("acme", "shopify", "p1", {"nombre": "Cojín"})
    FalsoConector.resultado = {"ok": True, "nombre": "Acme Store", "detalle": "ok"}
    app["c"].post("/cliente/acme/config/tienda/conectar", data={"tipo": "shopify", "dominio": "acme.myshopify.com", "token": "shpat_x"})
    assert sorted(t["tipo"] for t in tiendas.listar("acme")) == ["shopify", "shopify_publico"]
    assert tiendas.producto("acme", pid)["archivado"] is False
    assert [e["tipo"] for e in app["encolados"]] == ["tienda_sync_productos", "tienda_sync_pedidos"]
    assert any("El catálogo sigue llegando desde la conexión sin llaves; la Admin API agrega pedidos y atribución." in m
               for m in _flashes(app["c"]))


def test_la_tienda_sin_llaves_se_conecta_aunque_haya_admin_api(app, monkeypatch):
    import tiendas
    _falso_publico(monkeypatch)
    tiendas.conectar("acme", "shopify", {"dominio": "acme.myshopify.com", "token": "t"}, nombre="Acme Store", dominio="acme.myshopify.com")
    app["c"].post("/cliente/acme/config/tienda/conectar", data={"tipo": "shopify_publico", "dominio": "www.acme.com"})
    assert sorted(t["tipo"] for t in tiendas.listar("acme")) == ["shopify", "shopify_publico"]
    assert [e["tipo"] for e in app["encolados"]] == ["tienda_sync_productos"]
    assert not any("Admin API" in m and "ya está conectada" in m for m in _flashes(app["c"]))


def test_desconectar_una_de_dos_shopify_no_archiva_el_catalogo(app, monkeypatch):
    """Con la tienda sin llaves y la Admin API conectadas a la vez (misma
    fuente «shopify»), desconectar una no archiva los productos que la otra
    sigue trayendo; desconectar la última sí, como siempre."""
    import tiendas
    _falso_publico(monkeypatch)
    publica = tiendas.conectar("acme", "shopify_publico", {"dominio": "www.acme.com"}, nombre="Acme", dominio="www.acme.com")
    admin = tiendas.conectar("acme", "shopify", {"dominio": "acme.myshopify.com", "token": "t"}, nombre="Acme Store")
    pid = tiendas.upsert_producto("acme", "shopify", "p1", {"nombre": "Cojín"})
    app["c"].post(f"/cliente/acme/config/tienda/{admin}/desconectar")
    assert [t["tipo"] for t in tiendas.listar("acme")] == ["shopify_publico"]
    assert tiendas.producto("acme", pid)["archivado"] is False
    assert any("siguen activos" in m for m in _flashes(app["c"]))
    app["c"].post(f"/cliente/acme/config/tienda/{publica}/desconectar")
    assert tiendas.listar("acme") == [] and tiendas.producto("acme", pid)["archivado"] is True


def test_traer_de_mi_tienda_muestra_la_fecha_legible_y_el_error_de_una_tienda_rota(app):
    """Revisión final: la última sincronización se lee «2026-09-30 12:34» (sin
    la «T» del ISO) y, si la tienda sin llaves quedó «rota», se ve su error
    sin perder «Sincronizar ahora»."""
    import tiendas
    tid = tiendas.conectar("acme", "shopify_publico", {"dominio": "www.acme.com"}, nombre="Acme", dominio="www.acme.com")
    tiendas.actualizar("acme", tid, ultima_sync_productos="2026-09-30T12:34:56")

    def bloque():
        html = app["c"].get("/cliente/acme").data.decode()
        return html.split('id="cat-traer"', 1)[1].split("Importar CSV/Excel", 1)[0]

    b = bloque()
    assert "2026-09-30 12:34" in b and "2026-09-30T12:34" not in b and "tag-error" not in b
    tiendas.actualizar("acme", tid, estado="rota", error="la tienda www.acme.com limitó las peticiones (HTTP 429).")
    b = bloque()
    assert '<p class="tag-error">' in b and "limitó las peticiones (HTTP 429)." in b and "Sincronizar ahora" in b


def test_catalogo_ofrece_traer_de_mi_tienda_y_configuracion_el_tipo_sin_llaves(app):
    html = app["c"].get("/cliente/acme").data.decode()
    pestana = html.split('id="tab-catalogo"', 1)[1].split('id="tab-settings"', 1)[0]
    assert 'id="cat-traer"' in pestana and "Tu tienda Shopify (sin llaves)" in pestana and 'value="shopify_publico"' in pestana
    assert "Traer catálogo" in pestana and "Importar CSV/Excel" in pestana and "Importar desde URL" in pestana
    settings = html.split('id="tab-settings"', 1)[1]
    assert 'data-tienda-tipo="shopify_publico"' in settings and "Conectar Shopify (sin llaves)" in settings
    assert settings.index('data-tienda-tipo="shopify_publico"') < settings.index('data-tienda-tipo="shopify"')


# --- Tarea 15b: el buscador, el orden y los <select> de una sola acción no dejan "sin guardar" ---

def test_buscador_orden_y_selects_de_accion_no_quedan_sin_guardar(app):
    """base.html (marcarSucio, desde 6b76376) nunca marca "sucio" un buscador
    (type="search" o data-busqueda): perder lo escrito o elegido ahí no cuesta
    nada, así que no debe frenar una recarga automática al terminar un trabajo
    en segundo plano (recargarOAvisar). En el Catálogo eso aplica también al
    orden de la grilla (solo la reordena, ya cargada) y a los <select> que
    disparan una acción de un clic en vez de guardar una edición: "Asignar a
    color" (autoenvía con onchange="this.form.submit()") y el color de "Crear
    con este producto" (el clic solo abre Crear con ese color prellenado, no
    guarda nada aquí). Los <input type="file"> que autoenvían ya estaban
    exentos antes de esta tarea (base.html los descarta por type="file" antes
    de mirar data-busqueda), así que no necesitaron el atributo. El formulario
    "Datos" y "+ Color" sí editan de verdad — sus campos deben seguir
    marcando sucio, por eso no llevan data-busqueda."""
    _con_colores(app)                        # original: 2 colores con fotos + 1 foto general
    _producto(nombre="Espejo redondo")       # fila sin activo -> tarjeta "sin fotos" en la grilla
    c = app["c"]

    html = c.get("/cliente/acme").data.decode()
    tab = html.split('id="tab-catalogo"', 1)[1].split('id="tab-settings"', 1)[0]
    # El buscador ya queda exento por type="search" (no hace falta data-busqueda además).
    assert '<input type="search" class="cat-buscador"' in tab
    # El orden no guarda nada: solo reordena la grilla ya cargada.
    assert '<select class="cat-orden" data-cat-orden data-busqueda aria-label="Orden">' in tab

    grid = c.get("/cliente/acme/catalogo/grid?cat=producto").data.decode()
    # El <input type="file"> que autoenvía la fila "sin fotos" sigue tal cual: type="file" ya lo exime.
    assert '<input type="file" name="imagenes" accept=".jpg,.jpeg,.png,.webp" multiple onchange="this.form.submit()" hidden>' in grid

    ficha = c.get("/cliente/acme/catalogo/producto/original/ficha").data.decode()
    assert '<select name="variante" data-busqueda onchange="this.form.submit()" aria-label="Asignar a color">' in ficha
    assert '<select name="variante" data-busqueda aria-label="Color">' in ficha
    # "Datos" y "+ Color" son ediciones de verdad: sin data-busqueda, siguen marcando sucio.
    assert '<input type="text" name="nombre" value="Original" required>' in ficha
    assert 'Nombre del color<input type="text" name="nombre" placeholder="ej. Rosa" required>' in ficha
