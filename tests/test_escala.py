"""Escala (spec docs/superpowers/specs/2026-10-01-escala-y-monitoreo-design.md):
el pool de conexiones, las lecturas recordadas (catálogo por petición,
usuarios.json, Babel) y que las rutas de tarjetas no consulten por tarjeta.
Cada atajo tiene que devolver exactamente lo mismo que el camino largo."""
import os

import pytest
import sqlalchemy as sa
from sqlalchemy import event


# ------------------------------------------------------------------ pool ---

def test_pool_explicito_y_configurable(monkeypatch):
    import db
    assert db.opciones_pool("sqlite:///:memory:") == {}
    monkeypatch.delenv("CREATV_DB_POOL", raising=False)
    o = db.opciones_pool("sqlite:////tmp/x.db")
    assert o == {"pool_size": 10, "max_overflow": 10, "pool_timeout": 15}
    monkeypatch.setenv("CREATV_DB_POOL", "24")
    monkeypatch.setenv("CREATV_DB_POOL_EXTRA", "no-es-numero")
    o = db.opciones_pool("sqlite:////tmp/x.db")
    assert o["pool_size"] == 24 and o["max_overflow"] == 10
    # Otra base: además revisa y recicla las conexiones (el servidor corta las ociosas).
    o = db.opciones_pool("postgresql://u@h/db")
    assert o["pool_pre_ping"] is True and o["pool_recycle"] == 1800


def test_el_engine_usa_el_pool_y_los_pragmas(base_temporal):
    eng = base_temporal.engine()
    assert eng.pool.size() == 10
    with base_temporal.conectar() as con:
        assert con.execute(sa.text("PRAGMA temp_store")).scalar() == 2   # MEMORY
        assert con.execute(sa.text("PRAGMA journal_mode")).scalar() == "wal"


# --------------------------------------------------------------- idiomas ---

@pytest.mark.parametrize("idioma", ["es", "en"])
@pytest.mark.parametrize("valor, decimales", [(1250000, 0), (4000, 0), (12.345, 2), (0.015, 2), (-3.5, 1), (0, 2),
                                              (999.995, 2), (1234567.891, 3)])
def test_numero_igual_que_babel_con_el_codigo_como_texto(idioma, valor, decimales):
    """El Locale y el patrón ya analizados dan EXACTAMENTE lo mismo que
    pasarle a Babel el código y el patrón como texto (lo de antes)."""
    from babel.numbers import format_decimal
    import idiomas
    patron = "#,##0" + ("." + "0" * decimales if decimales else "")
    esperado = format_decimal(float(f"{float(valor):.{decimales}f}"), patron, locale=idioma)
    assert idiomas.numero(valor, decimales, idioma) == esperado


def test_gettext_rapido_sigue_el_idioma_y_force_locale():
    """El memo por petición del catálogo de traducciones no deja salir otro
    idioma: dentro de idiomas.en_idioma(...) se traduce en ese, y al salir
    vuelve el de la petición."""
    from flask import render_template_string
    import dashboard
    import idiomas
    plantilla = "{{ _('Peticiones') }}|{{ ngettext('%(num)d petición', '%(num)d peticiones', 2) }}"
    with dashboard.app.test_request_context("/", headers={"Cookie": "idioma=es"}):
        dashboard.app.preprocess_request()
        antes = render_template_string(plantilla)
        with idiomas.en_idioma("en"):
            dentro = render_template_string(plantilla)
        despues = render_template_string(plantilla)
    assert antes == despues == "Peticiones|2 peticiones"
    assert dentro == "Requests|2 requests"


# --------------------------------------------------------------- catálogo ---

@pytest.fixture()
def catalogo(tmp_path, monkeypatch):
    """Un producto con dos colores (dos fotos cada uno) en una carpeta temporal."""
    import catalogo_productos
    monkeypatch.setattr(catalogo_productos, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(catalogo_productos.idiomas, "de_proyecto", lambda cliente: "es")
    for color in ("negro", "rosa"):
        carpeta = tmp_path / "clientes" / "acme" / "productos" / "sandalia" / color
        carpeta.mkdir(parents=True)
        for k in range(2):
            (carpeta / f"{color}_{k}.jpg").write_bytes(b"x")
    catalogo_productos.guardar_meta("acme", {"sandalia": {"nombre": "Sandalia", "variantes": {
        "negro": {"nombre": "Sandalia Negra"}, "rosa": {"nombre": "Sandalia Rosa"}}}})
    return catalogo_productos


def _contar_lecturas(monkeypatch, cp):
    vueltas = {"n": 0}
    recorrer = cp._recorrer

    def contado(cliente, categoria):
        vueltas["n"] += 1
        return recorrer(cliente, categoria)
    monkeypatch.setattr(cp, "_recorrer", contado)
    return vueltas


def test_dentro_del_memo_las_busquedas_leen_el_disco_una_vez(catalogo, monkeypatch):
    cp = catalogo
    fuera = [cp.encontrar_por_id_o_nombre("acme", n, "producto") for n in ("Sandalia Rosa", "sandalia/negro", "Nada")]
    vueltas = _contar_lecturas(monkeypatch, cp)
    with cp.lecturas_memorizadas():
        dentro = [cp.encontrar_por_id_o_nombre("acme", n, "producto") for n in ("Sandalia Rosa", "sandalia/negro", "Nada")]
        dentro += [cp.encontrar("acme", "sandalia"), cp.encontrar_producto("acme", "sandalia/rosa")]
    assert dentro[:3] == fuera
    assert dentro[3]["id"] == "sandalia/negro" and dentro[4]["id"] == "sandalia"
    assert vueltas["n"] == 2     # listar y listar_productos, una vez cada uno
    # Fuera del memo cada búsqueda vuelve a leer (rutas que escriben, el worker).
    cp.encontrar("acme", "sandalia/rosa")
    cp.encontrar("acme", "sandalia/rosa")
    assert vueltas["n"] == 4


def test_lo_que_devuelve_el_memo_es_una_copia(catalogo):
    cp = catalogo
    with cp.lecturas_memorizadas():
        uno = cp.encontrar("acme", "sandalia/rosa")
        uno["nombre"] = "cambiado"
        uno["referencias"].append("otra.jpg")
        otro = cp.encontrar("acme", "sandalia/rosa")
        prod = cp.encontrar_producto("acme", "sandalia")
        prod["colores"][0]["nombre"] = "cambiado"
        assert cp.encontrar_producto("acme", "sandalia")["colores"][0]["nombre"] == "Sandalia Negra"
    assert otro["nombre"] == "Sandalia Rosa" and "otra.jpg" not in otro["referencias"]


def test_escribir_la_meta_olvida_lo_leido(catalogo):
    cp = catalogo
    with cp.lecturas_memorizadas():
        assert cp.encontrar_por_id_o_nombre("acme", "Sandalia Rosa", "producto")
        cp.modificar_meta("acme", "producto", lambda m: {**m, "sandalia": {**m["sandalia"], "variantes": {
            "negro": {"nombre": "Sandalia Negra"}, "rosa": {"nombre": "Sandalia Fucsia"}}}})
        assert cp.encontrar_por_id_o_nombre("acme", "Sandalia Fucsia", "producto")["id"] == "sandalia/rosa"


def test_una_prueba_que_sustituye_listar_tambien_cuenta_dentro_del_memo(catalogo, monkeypatch):
    cp = catalogo
    monkeypatch.setattr(cp, "listar", lambda cliente, categoria="producto": [
        {"id": "x", "producto_id": "x", "variante": None, "nombre": "Equis", "nombre_producto": "Equis"}])
    with cp.lecturas_memorizadas():
        assert cp.encontrar_por_id_o_nombre("acme", "Equis", "producto")["id"] == "x"
    assert cp.encontrar("acme", "x")["id"] == "x"


def test_fila_producto_lee_las_filas_una_vez_por_peticion(catalogo, monkeypatch):
    """final_edition._fila_producto (precio y url de cada tarjeta) cargaba TODAS
    las filas comerciales del proyecto por cada producto distinto."""
    import final_edition
    import tiendas
    lecturas = {"n": 0}

    def por_activo(cliente):
        lecturas["n"] += 1
        return {"sandalia": {"precio": 89900.0, "extra": {}}}
    monkeypatch.setattr(tiendas, "por_activo", por_activo)
    with catalogo.lecturas_memorizadas():
        filas = [final_edition._fila_producto("acme", a) for a in ("sandalia/negro", "sandalia/rosa", "otra")]
        filas[0]["precio"] = 1
        assert final_edition._fila_producto("acme", "sandalia")["precio"] == 89900.0
    assert lecturas["n"] == 1 and filas[1]["precio"] == 89900.0 and filas[2] == {}
    final_edition._fila_producto("acme", "sandalia")
    assert lecturas["n"] == 2          # fuera del memo, como siempre


def test_el_memo_no_sobrevive_a_la_ruta(catalogo):
    cp = catalogo

    @cp.con_lecturas_memorizadas
    def ruta():
        return getattr(cp._MEMO, "d", None) is not None
    assert ruta() is True
    assert getattr(cp._MEMO, "d", None) is None


# --------------------------------------------------------------- usuarios ---

def test_obtener_ve_cada_escritura_y_no_entrega_el_dict_recordado(usuarios_tmp):
    u = usuarios_tmp
    a = u.obtener("alguien")
    a["correo"] = "cambiado@x"
    assert u.obtener("alguien")["correo"] == "alguien@prueba.local"
    u.actualizar("alguien", correo="nuevo@prueba.local")
    assert u.obtener("alguien")["correo"] == "nuevo@prueba.local"
    sv = u.obtener("alguien")["session_version"]
    u.cambiar_password("alguien", "otra-clave-larga")
    assert u.obtener("alguien")["session_version"] == sv + 1
    assert "password_hash" not in u.obtener("alguien")


def test_obtener_lee_el_archivo_una_vez_mientras_no_cambia(usuarios_tmp, monkeypatch):
    u = usuarios_tmp
    u.obtener("admin")
    lecturas = {"n": 0}
    cargar = u.cargar

    def contado():
        lecturas["n"] += 1
        return cargar()
    monkeypatch.setattr(u, "cargar", contado)
    for _ in range(5):
        u.obtener("admin")
    assert lecturas["n"] == 0
    monkeypatch.setattr(u, "_MEMO_S", 0.0)     # vencido: vuelve a leer aunque no cambie
    u.obtener("admin")
    assert lecturas["n"] == 1


# ----------------------------------------------------------- Crear (tarjetas) ---

@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import proyectos
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    dashboard.app.config["TESTING"] = True
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "admin"; s["rol"] = "admin"; s["cliente"] = None
    return c


def _sembrar(n, desde=0):
    import creative_flow
    for i in range(desde, desde + n):
        cf = creative_flow.crear("acme", [], ["Producto que ya no está"], [], f"acción {i}", 8, "tono", "A",
                                 legado_id=f"cf_20260901_000000_{i:06d}")
        creative_flow.actualizar("acme", cf, estado="video_listo", tipo="video", video_url=f"https://r2/v/{cf}.mp4")


class _Consultas:
    def __enter__(self):
        self.n = 0

        def contar(*_a, **_k):
            self.n += 1
        self._f = contar
        event.listen(sa.engine.Engine, "before_cursor_execute", contar)
        return self

    def __exit__(self, *a):
        event.remove(sa.engine.Engine, "before_cursor_execute", self._f)


@pytest.mark.parametrize("url", ["/cliente/acme/crear/tarjetas?desde=0",
                                 "/cliente/acme/final/tarjetas?lista=elegir&desde=0",
                                 "/cliente/acme/final/tarjetas?lista=en_edicion&desde=0",
                                 "/cliente/acme/final/tarjetas?lista=finalizados&desde=0"])
def test_ver_mas_no_consulta_por_tarjeta(app, url):
    """«Ver más» de Crear y Final edition armaba TODOS los items consultando la
    cola una vez por tarjeta (1 077 consultas con 300 piezas): ahora una sola
    lectura de los trabajos vivos para toda la lista."""
    _sembrar(3)
    with _Consultas() as pocas:
        assert app.get(url).status_code == 200
    _sembrar(20, desde=3)
    with _Consultas() as muchas:
        assert app.get(url).status_code == 200
    assert muchas.n - pocas.n <= 4, (pocas.n, muchas.n)


def test_hijas_b_igual_que_mirar_una_por_una():
    import dashboard
    data = {"a": {}, "b": {"derivado_de": "a", "variante": "B"}, "c": {"derivado_de": "a", "variante": "A"},
            "d": {"derivado_de": "c", "variante": "B"}, "e": {"variante": "B"}}
    lento = {cf for cf in data if any(e.get("derivado_de") == cf and e.get("variante") == "B" for e in data.values())}
    assert dashboard._hijas_b(data) == lento == {"a", "c"}


# ------------------------------------------------------------- snapshots ---

def test_snapshots_de_igual_que_una_por_una(base_temporal):
    import experimentos
    eid = experimentos.crear("acme", "Prueba", [{"pais": "CO", "idioma": "es", "presupuesto_dia": 10}],
                             "OUTCOME_TRAFFIC", 7, 100, "https://x.test", "COP")
    eps = []
    for j in range(3):
        with base_temporal.conectar() as con:
            eps.append(con.execute(base_temporal.experimento_pieza.insert().values(
                cliente="acme", creado_en=base_temporal.ahora(), actualizado_en=base_temporal.ahora(),
                experimento_id=eid, pais="CO", estado="activo", extra={})).inserted_primary_key[0])
    for k, dia in enumerate(("2026-08-30", "2026-09-02", "2026-09-05", "2026-09-05")):
        for ep in eps[:2]:
            experimentos.snapshot(ep, {"gasto": 10 * (k + 1), "impresiones": 100 * (k + 1), "rechazo": f"m{k}"},
                                  tomado_en=f"{dia}T0{k}:00:00")
    for desde in ("2026-09-01T00:00:00", "2026-08-01T00:00:00", "2026-10-01T00:00:00"):
        lote = experimentos.snapshots_de(eps, desde)
        uno = {ep: experimentos.snapshots(ep, desde=desde) for ep in eps}
        assert lote == {ep: v for ep, v in uno.items() if v}, desde
    assert experimentos.snapshots_de([], "2026-09-01") == {}


# -------------------------------------------------------------------- R2 ---

@pytest.mark.parametrize("clave, inmutable", [
    ("clientes/a/finales/cf_1__es_CO__v12.mp4", True),
    ("clientes/a/finales/cf_1__es_CO__v12.png", True),
    ("clientes/a/materiales/voz_0123456789abcdef.mp3", True),
    ("clientes/a/materiales/locucion_0123456789abcdef.mp3", True),
    ("clientes/a/materiales/" + "ab" * 32 + ".wav", True),
    ("clientes/a/finales/cf_1__es_CO.mp4", False),           # la final sin versión se reescribe
    ("clientes/a/materiales/12_proxy.mp4", False),            # el proxy se rehace (PROXY_VERSION)
    ("clientes/a/videos/cf_1.mp4", False),                    # un video de Crear regenerado
    ("referentes/123.jpg", False),
])
def test_solo_las_claves_que_nunca_cambian_van_con_cache_de_un_ano(clave, inmutable):
    from storage import r2_uploader
    assert (r2_uploader.cache_control(clave) == r2_uploader.INMUTABLE) is inmutable


def test_upload_file_manda_cache_control_solo_a_las_inmutables(monkeypatch, tmp_path):
    from storage import r2_uploader
    llamadas = []

    class Cliente:
        def put_object(self, **kw):
            llamadas.append(kw)
    monkeypatch.setattr(r2_uploader, "_client", lambda: Cliente())
    monkeypatch.setenv("R2_BUCKET_NAME", "b")
    monkeypatch.setenv("R2_PUBLIC_BASE_URL", "https://media.test")
    archivo = tmp_path / "a.mp3"
    archivo.write_bytes(b"x")
    r2_uploader.upload_file(str(archivo), "clientes/a/materiales/voz_0123456789abcdef.mp3", "audio/mpeg")
    r2_uploader.upload_file(str(archivo), "clientes/a/videos/cf_1.mp4", "video/mp4")
    assert llamadas[0]["CacheControl"] == r2_uploader.INMUTABLE
    assert "CacheControl" not in llamadas[1]


def test_gunicorn_conf_un_proceso_y_sin_reciclar(monkeypatch):
    """deploy/gunicorn.conf.py: UN proceso (trabajos.iniciar vive en su
    memoria), nunca reciclar por número de peticiones y los hilos por variable."""
    import runpy
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    monkeypatch.setenv("GUNICORN_HILOS", "24")
    conf = runpy.run_path(os.path.join(raiz, "deploy", "gunicorn.conf.py"))
    assert conf["workers"] == 1 and conf["worker_class"] == "gthread" and conf["threads"] == 24
    assert conf["max_requests"] == 0 and conf["preload_app"] is False
