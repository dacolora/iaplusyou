"""Entrega 1: HTML acotado, fragmentos aislados y contratos de envío reales."""
import io

import pytest
import re
from tests.html_lote7 import HTML

from tests.conftest import JPG_VALIDO
from tests.test_rutas_productos import app, _activo_con_foto  # noqa: F401


class Arbol:
    """Consultas sobre el parser del repo; sin dependencias nuevas."""
    def __init__(self, nodo):
        self.nodo = nodo

    def __getitem__(self, clave):
        return self.nodo.attrs[clave]

    def get(self, clave):
        return self.nodo.attrs.get(clave)

    def has_attr(self, clave):
        return clave in self.nodo.attrs

    def get_text(self):
        return self.nodo.texto()

    def __str__(self):
        return self.get_text() + str(self.nodo.attrs) + ''.join(str(Arbol(h)) for h in self.nodo.hijos)

    def find_parent(self, tag):
        n = self.nodo.padre
        while n:
            if n.tag == tag:
                return Arbol(n)
            n = n.padre

    def select_one(self, selector):
        return next(iter(self.select(selector)), None)

    def select(self, selector):
        def coincide(n, parte):
            tag = re.match(r'^[a-zA-Z][\w-]*', parte)
            if tag and n.tag != tag[0]:
                return False
            for clase in re.findall(r'\.([\w-]+)', parte):
                if clase not in n.attrs.get('class', '').split():
                    return False
            ident = re.search(r'#([\w-]+)', parte)
            if ident and n.attrs.get('id') != ident[1]:
                return False
            for clave, valor in re.findall(r'\[([\w-]+)(?:="([^"]*)")?\]', parte):
                if clave not in n.attrs or (valor and n.attrs[clave] != valor):
                    return False
            return True
        partes = selector.split()
        def dentro(n):
            if not coincide(n, partes[-1]):
                return False
            ancestro = n.padre
            for parte in reversed(partes[:-1]):
                while ancestro and not coincide(ancestro, parte):
                    ancestro = ancestro.padre
                if not ancestro:
                    return False
                ancestro = ancestro.padre
            return True
        def nodos(n):
            for h in n.hijos:
                yield h
                yield from nodos(h)
        return [Arbol(n) for n in nodos(self.nodo) if dentro(n)]


FETCH = {"X-Requested-With": "fetch"}


@pytest.fixture()
def pagina(app, monkeypatch):
    d = app["dashboard"]
    monkeypatch.setattr(d.swaps_mod, "BASE_DIR", str(app["tmp"]))
    monkeypatch.setattr(d.proyectos, "BASE_DIR", str(app["tmp"]))
    monkeypatch.setattr(d.referencias_flowplus, "BASE_DIR", str(app["tmp"]))
    return app


def sopa(respuesta):
    assert respuesta.status_code == 200
    return Arbol(HTML(respuesta.get_data(as_text=True)).raiz)


def sembrar(pagina, n=50):
    import gastos
    d = pagina["dashboard"]
    _activo_con_foto("acme", "Propio", "propio")
    _activo_con_foto("otro", "Ajeno", "ajeno")
    for cliente in ("acme", "otro"):
        d.swaps_mod.guardar(cliente, {f"{cliente}_{i:03}": {
            "producto_id": "propio" if cliente == "acme" else "ajeno",
            "creado_en": f"2026-10-01T00:{i // 60:02}:{i % 60:02}",
            "estado": "listo", "resultado_url": f"https://r2/{cliente}/{i}.jpg",
            "foto_original_local": "original.jpg", "proveedor": "nano_banana", "tipo": "foto",
        } for i in range(n)})
        for i in range(n):
            gastos.registrar(cliente, "imagen", 1, f"{cliente}:gasto:{i:03}", detalle=f"{cliente} gasto {i:03}")


def test_catalogo_vacio_y_fragmento_aislado(pagina):
    sembrar(pagina, 1)
    html = sopa(pagina["c"].get("/cliente/acme"))
    for selector in ("plus", "clone"):
        grilla = html.select_one(f"#sel-{selector}-grilla")
        assert not grilla.select(".producto-opcion")
        assert grilla.get("data-url")
        assert grilla.find_parent("form") is not None
        frag = sopa(pagina["c"].get(grilla["data-url"], headers=FETCH))
        assert len(frag.select(".producto-opcion")) == 1
        assert "Ajeno" not in frag.get_text()
        assert not frag.select("script")
        assert all(i.get("loading") == "lazy" for i in frag.select("img"))


def test_precarga_se_conserva_en_fragmento_y_antes_de_abrir(pagina):
    sembrar(pagina, 1)
    c = pagina["c"]
    with c.session_transaction() as s:
        s["fp_prefill"] = {"cliente": "acme", "productos_catalogo": ["producto:propio"]}
    html = sopa(c.get("/cliente/acme"))
    assert html.select_one('#form-flowplus input[name="productos_catalogo"][value="producto:propio"][checked]')
    grilla = html.select_one("#sel-plus-grilla")
    frag = sopa(c.get(grilla["data-url"] + "&marcado=producto:propio", headers=FETCH))
    assert frag.select_one('input[value="producto:propio"][checked]')


def test_enviar_inputs_remotos_conserva_ambos_contratos(pagina, monkeypatch):
    import creative_flow
    sembrar(pagina, 1)
    d, c = pagina["dashboard"], pagina["c"]
    frag = sopa(c.get("/cliente/acme/catalogo/selector?sel=plus", headers=FETCH))
    entrada = frag.select_one("input")
    monkeypatch.setattr(d.r2_uploader, "upload_image", lambda *a, **k: "https://r2/propio.jpg")
    r = c.post("/cliente/acme/creative_flow/crear", data={entrada["name"]: entrada["value"],
        "accion_central": "Gira", "tipo": "video", "modelo": "wan3", "modo_prompt": "director", "bandeja_vista": "1"})
    assert r.status_code == 302
    pieza, = creative_flow.cargar("acme").values()
    assert pieza["referencias"][0]["producto"] == "Propio"
    frag = sopa(c.get("/cliente/acme/catalogo/selector?sel=clone", headers=FETCH))
    entrada = frag.select_one("input")
    enviados = []
    monkeypatch.setattr(d, "_lanzar_swap", lambda cliente, archivo, producto, pid, *a: enviados.append((cliente, pid, producto["nombre"])) or True)
    r = c.post("/cliente/acme/swap/generar", data={entrada["name"]: entrada["value"], "foto": (io.BytesIO(JPG_VALIDO), "foto.jpg")})
    assert r.status_code == 302 and enviados == [("acme", "propio", "Propio")]


@pytest.mark.parametrize("ruta", ["catalogo/selector?sel=plus", "swaps/lista", "gasto/lista"])
def test_fragmentos_rechazan_otro_proyecto(pagina, ruta):
    with pagina["c"].session_transaction() as s:
        s.update(usuario="user_acme", rol="cliente", cliente="acme")
    assert pagina["c"].get(f"/cliente/acme/{ruta}", headers=FETCH).status_code == 200
    assert pagina["c"].get(f"/cliente/otro/{ruta}", headers=FETCH).status_code in (403, 404)


def test_swaps_24_siguientes_y_vivo_antiguo_arriba(pagina, monkeypatch):
    sembrar(pagina)
    d = pagina["dashboard"]
    monkeypatch.setattr(d.trabajos, "en_curso", lambda jid: jid == "acme__acme_000__swap")
    html = sopa(pagina["c"].get("/cliente/acme"))
    lista = html.select_one(".swaps-lista")
    assert len(lista.select(".swap-card")) == 24
    vivo = lista.select_one(".swap-card")
    assert vivo["id"] == "swap-acme_000" and vivo.has_attr("open")
    assert vivo.select_one('[data-poll-job="acme__acme_000__swap"]')
    mas = html.select_one('[data-lista-mas="swaps-historial"]')
    frag = sopa(pagina["c"].get(mas["data-url"], headers=FETCH))
    assert len(frag.select(".swap-card")) == 24 and not frag.select("script")
    assert not {s["id"] for s in lista.select(".swap-card")} & {s["id"] for s in frag.select(".swap-card")}
    assert "otro_" not in str(frag)
    ultima = sopa(pagina["c"].get(frag.select_one("[data-lista-mas]")["data-url"], headers=FETCH))
    assert len(ultima.select(".swap-card")) == 2 and not ultima.select("[data-lista-mas]")


@pytest.mark.parametrize("rol", ["admin", "cliente"])
def test_gasto_24_siguientes_total_csv_y_modo(pagina, rol):
    import gastos
    from cobros import libro
    libro.configurar("acme", cobrar=True, margen=1.5, usuario="admin")
    import db
    with db.conectar() as con:
        libro.acreditar(con, "acme", "ajuste", 1000000, "ajuste", detalle="Prueba")
    sembrar(pagina)
    c = pagina["c"]
    if rol == "cliente":
        with c.session_transaction() as s:
            s.update(usuario="user_acme", rol="cliente", cliente="acme")
    html = sopa(c.get("/cliente/acme"))
    assert len(html.select(".gasto-historial tbody tr")) == 24
    assert len(html.select_one(".gasto-historial tbody tr").select("td")) == (5 if rol == "admin" else 4)
    primera = html.select_one(".gasto-historial tbody tr").select("td")
    assert primera[3].get_text() == gastos.formatear(1 if rol == "admin" else 1.5)
    if rol == "admin":
        assert primera[4].get_text() == gastos.formatear(1.5)
    total = html.select_one('.gasto-total').select('td')
    assert total[1].get_text() == '50'
    assert total[2].get_text() == gastos.formatear(50 if rol == "admin" else 75)
    assert html.select_one('#gasto-desde-inicio strong').get_text() == gastos.formatear(50 if rol == 'admin' else 75)
    if rol == "admin":
        assert total[3].get_text() == gastos.formatear(75)
    assert gastos.resumen_total("acme")["total"] == 50
    csv = c.get("/cliente/acme/gasto/todo.csv").get_data(as_text=True)
    assert all(f"acme gasto {i:03}" in csv for i in range(50))
    assert "otro gasto" not in csv
    frag = sopa(c.get(html.select_one('[data-lista-mas="gasto-filas"]')["data-url"], headers=FETCH))
    filas = frag.select("tr")
    assert len(filas) == 24 and not frag.select("script")
    assert all(len(f.select("td")) == (5 if rol == "admin" else 4) for f in filas)
    for fila in filas:
        valores = fila.select('td')
        assert valores[3].get_text() == gastos.formatear(1 if rol == 'admin' else 1.5)
        if rol == 'admin':
            assert valores[4].get_text() == gastos.formatear(1.5)
        else:
            assert gastos.formatear(1) not in [td.get_text() for td in valores]
    assert not {f.get_text() for f in html.select(".gasto-historial tbody tr")} & {f.get_text() for f in filas}
    assert "otro gasto" not in frag.get_text()
    ultima = sopa(c.get(frag.select_one('[data-lista-mas]')["data-url"], headers=FETCH))
    assert len(ultima.select("tr")) == 2 and not ultima.select('[data-lista-mas]')


def test_pagina_sembrada_baja_de_600_kib(pagina):
    sembrar(pagina, 200)
    for i in range(119):
        _activo_con_foto("acme", f"Producto {i:03}", f"producto_{i:03}")
    respuesta = pagina["c"].get("/cliente/acme")
    assert respuesta.status_code == 200
    print(f"PAGINA_SEMBRADA_BYTES={len(respuesta.data)}; KiB={len(respuesta.data) / 1024:.2f}")
    assert len(respuesta.data) < 600 * 1024


def _node(datos):
    import json
    import subprocess
    r = subprocess.run(['node', 'tests/js/pagina_por_partes.cjs'], input=json.dumps(datos), text=True, capture_output=True)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.parametrize('sel', ['plus', 'clone'])
def test_js_catalogo_al_abrir_una_vez_reintento_filtro_y_precarga(pagina, sel):
    sembrar(pagina, 1)
    html = pagina['c'].get('/cliente/acme').get_data(as_text=True)
    scripts = re.findall(r'<script>(.*?)</script>', html, re.S)
    script = next(s for s in scripts if f'var id = "sel-{sel}"' in s)
    frag = pagina['c'].get(f'/cliente/acme/catalogo/selector?sel={sel}', headers=FETCH)
    assert frag.status_code == 200
    _node({'tipo': 'catalogo', 'sel': sel, 'valor': 'producto:propio' if sel == 'plus' else 'propio',
           'html': frag.get_data(as_text=True), 'script': script, 'reintentar': 'Reintentar'})


@pytest.mark.parametrize('tipo', ['swaps', 'gasto'])
def test_js_historial_delegado_reintento_y_sondeo(pagina, tipo):
    html = pagina['c'].get('/cliente/acme').get_data(as_text=True)
    inicio = html.index('    // Página por partes:')
    fin = html.index('    window.arrancarSondeos =', inicio)
    _node({'tipo': tipo, 'script': html[inicio:fin], 'reintentar': 'Reintentar'})


def test_contexto_no_enriquece_catalogo_oculto_ni_swaps_fuera_de_pagina(pagina, monkeypatch):
    sembrar(pagina)
    d = pagina['dashboard']
    def no_armar(*args, **kwargs):
        pytest.fail('se armó el catálogo oculto para ver_cliente')
    monkeypatch.setattr(d, '_productos_con_uso', no_armar)
    listar_original = d.catalogo_productos.listar
    listar_lecturas = []
    def listar_vigilado(*a, **kw):
        import inspect
        if inspect.currentframe().f_back.f_code.co_name == 'ver_cliente':
            no_armar()
        listar_lecturas.append(a)
        return listar_original(*a, **kw)
    monkeypatch.setattr(d.catalogo_productos, 'listar', listar_vigilado)
    original = d.catalogo_productos.encontrar
    lecturas = []
    monkeypatch.setattr(d.catalogo_productos, 'encontrar', lambda *a, **kw: lecturas.append(a) or original(*a, **kw))
    assert pagina['c'].get('/cliente/acme').status_code == 200
    assert len(lecturas) == 24
    # Lecturas vigentes: encontrar para swaps visibles y _personajes del compositor.
    assert listar_lecturas == [('acme', 'producto'), ('acme', 'personaje')]


def test_fragmento_agrupa_colores_excluye_archivados_y_conserva_precarga(pagina):
    from tests.test_rutas_catalogo import _con_colores
    import tiendas
    _con_colores(pagina)
    _con_colores(pagina, pid="cozy", nombre="Cozy", colores=("Gray",))
    # Ver_cliente mantiene el enlace comercial histórico sin armar tiles.
    pagina['c'].get('/cliente/acme')
    tiendas.archivar_activo('acme', 'original')
    c = pagina['c']
    for sel, campo, valor in [('plus', 'productos_catalogo', 'producto:cozy/gray'), ('clone', 'producto_id', 'cozy/gray')]:
        frag = sopa(c.get(f'/cliente/acme/catalogo/selector?sel={sel}', headers=FETCH))
        assert frag.select_one(f'input[name="{campo}"][value="{valor}"]')
        assert not frag.select_one('input[value="producto:original/pink"]')
        assert not frag.select_one('input[value="original/pink"]')
    frag = sopa(c.get('/cliente/acme/catalogo/selector?sel=plus&marcado=producto:original/pink', headers=FETCH))
    assert frag.select_one('input[value="producto:original/pink"][checked]')
    grupo = next(g for g in frag.select('.producto-grupo') if g.select_one('input[value="producto:original/pink"]'))
    assert 'Original' in grupo.get_text() and '2 colores' in grupo.get_text()
    assert grupo.select_one('input[value="producto:original/beige"]')


def test_ningun_swap_vivo_queda_detras_de_ver_mas(pagina, monkeypatch):
    sembrar(pagina, 50)
    d = pagina['dashboard']
    vivos = {f'acme__acme_{i:03}__swap' for i in range(26)}
    monkeypatch.setattr(d.trabajos, 'en_curso', lambda jid: jid in vivos)
    html = sopa(pagina['c'].get('/cliente/acme'))
    lista = html.select_one('#swaps-historial')
    assert {n['data-poll-job'] for n in lista.select('[data-poll-job]')} == vivos
    frag = sopa(pagina['c'].get(html.select_one('[data-lista-mas="swaps-historial"]')['data-url'], headers=FETCH))
    assert len(frag.select('.swap-card')) == 24
    assert not {n['id'] for n in lista.select('.swap-card')} & {n['id'] for n in frag.select('.swap-card')}


def _arbol_json(nodo):
    return {'tag': nodo.tag, 'attrs': nodo.attrs, 'texto': ''.join(nodo.textos),
            'hijos': [_arbol_json(h) for h in nodo.hijos]}


def _node_arreglos(datos):
    import json
    import subprocess
    r = subprocess.run(['node', 'tests/js/pagina_arreglos.cjs'], input=json.dumps(datos), text=True, capture_output=True)
    assert r.returncode == 0, r.stdout + r.stderr


def _shell(pagina, sel):
    html = pagina['c'].get('/cliente/acme').get_data(as_text=True)
    if sel in ('historial', 'gasto'):
        inicio = html.index('    // Página por partes:')
        script = html[inicio:html.index('    window.arrancarSondeos =', inicio)]
    else:
        script = next(s for s in re.findall(r'<script>(.*?)</script>', html, re.S) if f'var id = "sel-{sel}"' in s)
    return {'pagina': _arbol_json(HTML(html).raiz), 'script': script}


def test_swap_con_archivo_sin_abrir_no_envia(pagina):
    sembrar(pagina, 1)
    frag = pagina['c'].get('/cliente/acme/catalogo/selector?sel=clone', headers=FETCH)
    _node_arreglos({'tipo': 'envio', **_shell(pagina, 'clone'), 'fragmento': _arbol_json(HTML(frag.get_data(as_text=True)).raiz)})


def test_swaps_ver_mas_siempre_despues_de_ultima_tarjeta_en_dom(pagina):
    sembrar(pagina, 74)
    fragmentos = [_arbol_json(HTML(pagina['c'].get(f'/cliente/acme/swaps/lista?desde={n}', headers=FETCH).get_data(as_text=True)).raiz)
                  for n in (24, 48, 72)]
    _node_arreglos({'tipo': 'orden', **_shell(pagina, 'historial'), 'fragmentos': fragmentos})


@pytest.mark.parametrize('sel', ['clone', 'plus', 'historial', 'gasto'])
@pytest.mark.parametrize('respuesta', ['403', 'login'])
def test_js_sesion_vencida_ofrece_entrar_sin_reintento(pagina, sel, respuesta):
    sembrar(pagina, 50)
    _node_arreglos({'tipo': 'sesion', 'sel': sel, 'respuesta': respuesta, **_shell(pagina, sel)})


def test_gasto_fallo_cobrado_conserva_historial_sin_columna(pagina, monkeypatch):
    from cobros import libro
    libro.configurar('acme', cobrar=True, margen=1.5, usuario='admin')
    sembrar(pagina)
    def fallar(*a, **k):
        raise RuntimeError('lectura de prueba')
    monkeypatch.setattr(pagina['dashboard'].vista_cobros, 'cobrado_por_gasto', fallar)
    html = sopa(pagina['c'].get('/cliente/acme'))
    filas = html.select('.gasto-historial tbody tr')
    assert len(filas) == 24
    assert all(len(f.select('td')) == 4 for f in filas)
    frag = sopa(pagina['c'].get('/cliente/acme/gasto/lista?desde=24', headers=FETCH))
    assert len(frag.select('tr')) == 24
    assert all(len(f.select('td')) == 4 for f in frag.select('tr'))


def test_contadores_selector_igual_que_main_con_colores(pagina):
    from tests.test_rutas_catalogo import _con_colores
    import catalogo_productos as cp
    import tiendas
    _con_colores(pagina, colores=('Pink', 'Beige', 'Blue'))
    _con_colores(pagina, pid='archivado', colores=('Gray', 'Black'))
    # Se enlaza la fila comercial como en main antes de archivar.
    pagina['c'].get('/cliente/acme')
    tiendas.archivar_activo('acme', 'archivado')
    # El conteo anterior sale de los activos, no de las filas comerciales.
    cantidades_main = {cid: len(cp.sin_archivados(cp.listar('acme', cid), tiendas.activos_archivados('acme')))
                       if cid == 'producto' else len(cp.listar('acme', cid)) for cid in cp.CATEGORIAS}
    assert cantidades_main['producto'] == 3
    html = sopa(pagina['c'].get('/cliente/acme'))
    assert re.findall(r'\d+', html.select_one('#sel-clone-resumen').get_text()) == [str(cantidades_main['producto'])]
    assert re.findall(r'\d+', html.select_one('#fp-abrir-catalogo small').get_text()) == [str(sum(cantidades_main.values()))]



@pytest.mark.parametrize('marcado', ['producto:archivado/gray', 'producto:archivado'])
def test_contadores_con_precarga_de_un_archivado_cuentan_como_main(pagina, marcado):
    """Main contaba lo que la precarga conserva (`sin_archivados(..., conservar=...)`): un producto archivado
    marcado por «Crear con este producto» sigue contando con sus colores (re-revisión, 2026-10-10)."""
    from tests.test_rutas_catalogo import _con_colores
    import catalogo_productos as cp
    import tiendas
    _con_colores(pagina, colores=('Pink', 'Beige', 'Blue'))
    _con_colores(pagina, pid='archivado', colores=('Gray', 'Black'))
    pagina['c'].get('/cliente/acme')
    tiendas.archivar_activo('acme', 'archivado')
    conservar = [marcado.split(':', 1)[1]]
    cantidades_main = {cid: len(cp.sin_archivados(cp.listar('acme', cid), tiendas.activos_archivados('acme'), conservar=conservar))
                       if cid == 'producto' else len(cp.listar('acme', cid)) for cid in cp.CATEGORIAS}
    assert cantidades_main['producto'] == 5
    with pagina['c'].session_transaction() as s:
        s['fp_prefill'] = {'cliente': 'acme', 'productos_catalogo': [marcado]}
    html = sopa(pagina['c'].get('/cliente/acme'))
    assert re.findall(r'\d+', html.select_one('#sel-clone-resumen').get_text()) == [str(cantidades_main['producto'])]
    assert re.findall(r'\d+', html.select_one('#fp-abrir-catalogo small').get_text()) == [str(sum(cantidades_main.values()))]


def _gasto_variado(pagina, rol):
    import db
    import gastos
    from cobros import libro
    libro.configurar('acme', cobrar=True, margen=1.5, usuario='admin')
    with db.conectar() as con:
        libro.acreditar(con, 'acme', 'ajuste', 1000000, 'ajuste', detalle='Prueba')
    sembrar(pagina)
    costos = {f'acme:gasto:{i:03}': (i + 1) / 10 for i in range(50)}
    for referencia, costo in costos.items():
        gastos.registrar('acme', 'imagen', costo, referencia)
    if rol == 'cliente':
        with pagina['c'].session_transaction() as s:
            s.update(usuario='user_acme', rol='cliente', cliente='acme')
    return costos


@pytest.mark.parametrize('rol', ['admin', 'cliente'])
def test_gasto_pagina_dos_valores_por_fila(pagina, rol):
    import gastos
    from cobros import libro
    costos = _gasto_variado(pagina, rol)
    frag = sopa(pagina['c'].get('/cliente/acme/gasto/lista?desde=24', headers=FETCH))
    assert len(frag.select('tr')) == 24
    for fila in frag.select('tr'):
        celdas = fila.select('td')
        costo = costos[celdas[2]['title']]
        cobrado = libro.precio_milesimas(costo, 1.5) / 1000
        assert celdas[3].get_text() == gastos.formatear(costo if rol == 'admin' else cobrado)
        if rol == 'admin':
            assert celdas[4].get_text() == gastos.formatear(cobrado)
        else:
            assert len(celdas) == 4
            assert gastos.formatear(costo) not in [c.get_text() for c in celdas]


@pytest.mark.parametrize('rol', ['admin', 'cliente'])
def test_gasto_total_grande_incluye_todas_las_paginas(pagina, rol):
    import gastos
    from cobros import libro
    costos = _gasto_variado(pagina, rol)
    esperado = sum(costos.values()) if rol == 'admin' else sum(libro.precio_milesimas(c, 1.5) / 1000 for c in costos.values())
    html = sopa(pagina['c'].get('/cliente/acme'))
    assert html.select_one('#gasto-desde-inicio strong').get_text() == gastos.formatear(esperado)


# Entrega 2: el código se sirve aparte; la página conserva solo sus valores.
SCRIPTS_CREAR = [
    ('crear-compositor', '// Tipo (video/imagen), modelo elegido y costo'),
    ('crear-flowplus', "var raiz = document.getElementById('gp')"),
    ('crear-audios', "var raiz = document.getElementById('au')"),
    ('crear-guiones', "var panel = document.getElementById('gpg-panel')"),
]


def _config_crear(html, archivo):
    import json
    patron = r'<script type="application/json" id="' + archivo + r'-datos">(.*?)</script>'
    m = re.search(patron, html, re.S)
    assert m, f'Falta el JSON de {archivo}'
    return json.loads(m[1])


def test_entrega2_compositor_sin_defer_en_su_lugar(pagina):
    respuesta = pagina['c'].get('/cliente/acme')
    html = respuesta.get_data(as_text=True)
    nodo = next(n for n in sopa(respuesta).select('script')
                if (n.get('src') or '').startswith('/static/crear-compositor.js?'))
    assert not nodo.has_attr('defer'), 'El compositor debe registrar las guardas al terminar su sección'
    assert not nodo.has_attr('async')
    script = html.index('<script src="' + nodo['src'] + '"')
    formulario = html.index('id="form-flowplus"')
    assert formulario < html.index('</form>', formulario) < script
    assert html.index('id="crear-compositor-datos"') < script
    assert html.index('function formatearUSD(') < script
    # Guiones, chat, Audios y el selector de modos aparecen después del compositor.
    for dependencia in ('/static/crear-guiones.js?', '/static/crear-flowplus.js?',
                        '/static/crear-audios.js?', "var KEY = 'crear-modo-"):
        assert script < html.index(dependencia), dependencia


@pytest.mark.parametrize('cliente', ['acme', 'otro'])
@pytest.mark.parametrize('campo,endpoint', [('urlBandeja', 'fp_bandeja'),
                                          ('urlDescribir', 'fp_describir'),
                                          ('urlVaciar', 'fp_vaciar_referencias')])
def test_entrega2_urls_json_del_proyecto(pagina, cliente, campo, endpoint):
    from flask import url_for
    respuesta = pagina['c'].get(f'/cliente/{cliente}')
    sopa(respuesta)
    datos = _config_crear(respuesta.get_data(as_text=True), 'crear-compositor')['datos']
    with pagina['dashboard'].app.test_request_context():
        esperado = url_for(endpoint, cliente=cliente)
    assert datos[campo] == esperado


def _sesion_cliente_con_margen(pagina):
    from cobros import libro
    libro.configurar('acme', usuario='admin', cobrar=True, margen=1.5)
    with pagina['c'].session_transaction() as s:
        s.update(usuario='user_acme', rol='cliente', cliente='acme')


def test_entrega2_tarifa_musica_json_es_precio_para_cliente(pagina):
    import gastos
    _sesion_cliente_con_margen(pagina)
    costo = gastos.costo_musica_estimada('generada')
    assert costo > 0
    respuesta = pagina['c'].get('/cliente/acme')
    sopa(respuesta)
    datos = _config_crear(respuesta.get_data(as_text=True), 'crear-compositor')['datos']
    assert datos['tarifaMusica'] == pytest.approx(costo * 1.5)
    assert datos['tarifaMusica'] != costo


@pytest.mark.parametrize('campo,clave', [('preciosClon', 'precios_clon'),
                                       ('preciosDisenar', 'precios_disenar')])
def test_entrega2_tablas_voces_json_sin_cruzarse(pagina, monkeypatch, campo, clave):
    _sesion_cliente_con_margen(pagina)
    d = pagina['dashboard']
    original = d._contexto_mis_voces
    contextos = {}
    def capturar(cliente):
        contexto = original(cliente)
        contextos[cliente] = contexto
        return contexto
    monkeypatch.setattr(d, '_contexto_mis_voces', capturar)
    respuesta = pagina['c'].get('/cliente/acme')
    sopa(respuesta)
    contexto = contextos['acme']
    assert contexto['precios_clon'] != contexto['precios_disenar']
    datos = _config_crear(respuesta.get_data(as_text=True), 'crear-audios')['datos']
    assert datos[campo] == contexto[clave]


@pytest.mark.parametrize('archivo,firma', SCRIPTS_CREAR)
def test_entrega2_cuerpo_fuera_del_html_y_estatico_versionado(pagina, archivo, firma):
    from pathlib import Path
    from urllib.parse import urlparse, parse_qs
    html = pagina['c'].get('/cliente/acme').get_data(as_text=True)
    assert firma not in html, f'Sigue inline: {archivo}'
    url = f'/static/{archivo}.js?v={int(Path("static", archivo + ".js").stat().st_mtime)}'
    nodo = next((n for n in sopa(pagina['c'].get('/cliente/acme')).select('script') if n.get('src') == url), None)
    assert nodo and nodo.has_attr('defer')
    assert parse_qs(urlparse(nodo['src']).query)['v']
    respuesta = pagina['c'].get(nodo['src'])
    assert respuesta.status_code == 200
    assert firma in respuesta.get_data(as_text=True)
    assert 'immutable' in respuesta.headers['Cache-Control']
    assert 'max-age=31536000' in respuesta.headers['Cache-Control']


@pytest.mark.parametrize('archivo,firma', SCRIPTS_CREAR)
def test_entrega2_node_check(archivo, firma):
    import subprocess
    r = subprocess.run(['node', '--check', f'static/{archivo}.js'], text=True, capture_output=True)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.parametrize('archivo,firma', SCRIPTS_CREAR)
def test_entrega2_textos_de_pagina_traducidos_y_usados(pagina, monkeypatch, archivo, firma):
    from pathlib import Path
    import idiomas
    from tests.i18n_util import _SCRIPT_TOKEN, _con_marca
    valores = {}
    for idioma in ('es', 'en'):
        monkeypatch.setattr(idiomas, 'de_usuario', lambda *a, idioma=idioma: idioma)
        html = pagina['c'].get('/cliente/acme').get_data(as_text=True)
        valores[idioma] = _config_crear(html, archivo)['textos']
    assert valores['es'] and valores['es'].keys() == valores['en'].keys()
    assert valores['es'] != valores['en'], 'El objeto no cambió de idioma'
    # Símbolos y nombres compartidos no tienen traducción; las frases con español sí cambian.
    for clave, texto in valores['es'].items():
        if _con_marca(texto):
            assert valores['en'][clave] != texto, f'{archivo}.{clave} no cambió de idioma'
    js = Path('static', archivo + '.js').read_text()
    assert '{{' not in js and '{%' not in js
    literales = [t for t in _SCRIPT_TOKEN.findall(js) if t[0] in ("'", '"', '`') and _con_marca(t)]
    assert not literales, literales
    claves_usadas = set(re.findall(r'\bT\.(\w+)', js))
    assert claves_usadas == set(valores['es']), 'Textos perdidos o sin objeto de la página'


@pytest.mark.parametrize('origen', ['producto', 'reusar'])
def test_entrega2_precarga_llega_al_compositor(pagina, monkeypatch, origen):
    import creative_flow
    sembrar(pagina, 1)
    d, c = pagina['dashboard'], pagina['c']
    if origen == 'producto':
        r = c.post('/cliente/acme/catalogo/producto/propio/crear-con')
        # El contrato de la ruta se comprueba además abajo con su selección.
        assert r.status_code == 302
    else:
        r = c.post('/cliente/acme/creative_flow/crear', data={'accion_central': 'Girando', 'modelo': 'wan3', 'duracion_objetivo': '10', 'tipo': 'video', 'modo_prompt': 'director', 'bandeja_vista': '1'})
        assert r.status_code == 302
        cf, = creative_flow.cargar('acme')
        r = c.post(f'/cliente/acme/flowplus/reusar/{cf}')
        assert r.status_code == 302
    html = c.get('/cliente/acme').get_data(as_text=True)
    prefill = _config_crear(html, 'crear-compositor')['datos']['prefill']
    assert prefill
    if origen == 'producto':
        assert prefill['productos_catalogo'] == ['producto:propio']
    else:
        assert prefill['texto'] == 'Girando' and prefill['modelo'] == 'wan3' and prefill['duracion'] == 10
    _ejecutar_crear(html)


def _ejecutar_crear(html, hash='#referencias', guardado=None):
    import json
    import subprocess
    from pathlib import Path
    arbol = HTML(html).raiz
    def serializar(n):
        return {'tag': n.tag, 'attrs': n.attrs, 'textos': n.textos, 'hijos': [serializar(h) for h in n.hijos]}
    nodos_scripts = Arbol(arbol).select('script')
    scripts = [{'archivo': nombre, 'codigo': Path('static', nombre + '.js').read_text(),
                'defer': next(n for n in nodos_scripts
                              if (n.get('src') or '').startswith('/static/' + nombre + '.js?')).has_attr('defer')}
               for nombre in ('crear-compositor', 'crear-guiones', 'crear-flowplus', 'crear-audios')]
    modo = (hash[1:].split('?')[0] if hash != '#creativeflowplus' else guardado) or 'referencias'
    modos = next(s for s in re.findall(r'<script>(.*?)</script>', html, re.S) if "var KEY = 'crear-modo-" in s)
    formato = next(s for s in re.findall(r'<script>(.*?)</script>', html, re.S) if 'function formatearUSD(' in s)
    scripts.insert(0, {'archivo': 'formatearUSD-inline', 'codigo': formato, 'defer': False})
    r = subprocess.run(['node', 'tests/js/crear_estaticos.cjs'], text=True, capture_output=True,
                       input=json.dumps({'dom': serializar(arbol), 'scripts': scripts, 'modos': modos,
                                         'hash': hash, 'modo': modo, 'guardado': guardado}))
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.parametrize('idioma', ['es', 'en'])
@pytest.mark.parametrize('hash,guardado', [('#flowplus', None), ('#creativeflowplus', 'flowplus'),
                                          ('#referencias', 'flowplus'), ('#audios', None)])
def test_entrega2_inicializacion_defer_y_eventos_en_node(pagina, monkeypatch, hash, guardado, idioma):
    import idiomas
    monkeypatch.setattr(idiomas, 'de_usuario', lambda *a: idioma)
    _ejecutar_crear(pagina['c'].get('/cliente/acme').get_data(as_text=True), hash, guardado)
