"""Pestaña Alertas en dashboard.py (spec docs/superpowers/specs/2026-09-20-alertas-design.md §5-§7 y §12):
caché de `alertas.calcular` por (proyecto, idioma) con el filtro por rol al leer, el context processor
`alertas_ctx` (toda página con <cliente>, nunca un parcial JSON ni la landing), las rutas descartar/restaurar,
la pestaña, la burbuja del sidebar, la navegación «Ir a …» con ancla y que cada ancla que usa alertas.py exista
en la página. Sin red."""
import os
import re

import pytest

import idiomas
from tests.test_rutas_experimentos import _resultados

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H64 = "a" * 64


@pytest.fixture()
def app(base_temporal, tmp_path, monkeypatch):
    import alertas
    import catalogo_productos
    import dashboard
    import estado as estado_mod
    import proyectos
    monkeypatch.setenv("FLASK_SECRET_KEY", "clave-de-prueba-larga-1234567890")
    monkeypatch.setattr(dashboard, "_client_dir", lambda cliente: str(tmp_path / "clientes" / cliente))
    for mod in (alertas, proyectos, estado_mod, catalogo_productos):
        monkeypatch.setattr(mod, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    (tmp_path / "clientes" / "otro").mkdir(parents=True)
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(dashboard.meta_conexion, "estado", lambda c: {"estado": "sin_conectar", "verificado": True, "detalle": {}})
    monkeypatch.setattr(dashboard.meta_conexion, "estado_pixel", lambda c, solo_cache=False: None)
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: False)
    return {"dashboard": dashboard, "alertas": alertas, "c": _sesion(dashboard, "admin", "admin", None), "tmp": tmp_path}


def _sesion(dashboard, usuario, rol, cliente):
    dashboard.app.config["TESTING"] = True
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = usuario; s["rol"] = rol; s["cliente"] = cliente
    return c


def _cliente_rol_cliente(app):
    return _sesion(app["dashboard"], "user_acme", "cliente", "acme")


def _fijas(app, monkeypatch, lista, llamadas=None):
    """Reemplaza el cálculo por una lista fija (copias nuevas en cada llamada) y vacía la caché."""
    def calcular(cliente, ahora_iso=None):
        if llamadas is not None:
            llamadas.append(cliente)
        return [dict(a) for a in lista]
    monkeypatch.setattr(app["alertas"], "calcular", calcular)
    app["dashboard"].invalidar_alertas()


def _alerta(app, clave, nivel="atencion", grupo="faltantes", titulo=None, detalle="Detalle de prueba.", **kw):
    al = app["alertas"]
    return al._alerta(clave, kw.pop("huella", al.huella(clave)), nivel, grupo, titulo or f"Título {clave}", detalle,
                      kw.pop("tab", "settings"), **kw)


def _flashes(c):
    with c.session_transaction() as s:
        return [m for _cat, m in s.get("_flashes", [])]


def _descartes():
    import db
    with db.conectar() as con:
        return [(f.cliente, f.clave, f.huella) for f in con.execute(db.alerta_descartada.select()).fetchall()]


def _html(c, url="/cliente/acme"):
    r = c.get(url)
    assert r.status_code == 200, r.status_code
    return r.get_data(as_text=True)


def _tab(html):
    """El panel de Alertas completo: tiene <section> por grupo, así que se corta en el panel siguiente."""
    ini = html.index('<section id="tab-alertas"')
    return html[ini:html.index('<section id="tab-', ini + 10)]


def _sidebar(html):
    ini = html.index('<aside class="sidebar"')
    return html[ini:html.index("</aside>", ini)]


# ---------- caché y context processor ----------

def test_contexto_alertas_cachea_60s_por_proyecto_e_idioma(app, monkeypatch):
    d = app["dashboard"]
    llamadas = []
    _fijas(app, monkeypatch, [], llamadas)
    reloj = {"t": 1000.0}
    monkeypatch.setattr(d.time, "monotonic", lambda: reloj["t"])
    assert d.ALERTAS_TTL_S == 60
    with d.app.test_request_context("/cliente/acme"):
        assert d._contexto_alertas("acme", "admin")["resumen"]["n"] == 0 and llamadas == ["acme"]
        reloj["t"] += 59
        d._contexto_alertas("acme", "cliente")
        assert llamadas == ["acme"]                       # dentro del TTL no recalcula, tampoco con otro rol
        d._contexto_alertas("otro", "admin")
        assert llamadas == ["acme", "otro"]               # por proyecto
        with idiomas.en_idioma("en"):
            d._contexto_alertas("acme", "admin")
        assert llamadas == ["acme", "otro", "acme"]       # y por idioma: los títulos salen traducidos al calcular
        reloj["t"] += 1
        d._contexto_alertas("acme", "admin")
        assert llamadas == ["acme", "otro", "acme", "acme"]   # pasados 60 s se recalcula
        d.invalidar_alertas("acme")
        d._contexto_alertas("acme", "admin"); d._contexto_alertas("otro", "admin")
        assert llamadas[-1] == "acme" and len(llamadas) == 5  # invalidar un proyecto no toca el otro
        d.invalidar_tablero()                             # invalidar el tablero también vacía las alertas
        d._contexto_alertas("otro", "admin")
        assert llamadas[-1] == "otro" and len(llamadas) == 6


def test_contexto_filtra_por_rol_al_leer_sin_recalcular(app, monkeypatch):
    d = app["dashboard"]
    llamadas = []
    _fijas(app, monkeypatch, [_alerta(app, "llave:r2", "bloquea", "puesta_a_punto", solo_admin=True),
                              _alerta(app, "proyecto:logo", "info")], llamadas)
    with d.app.test_request_context("/cliente/acme"):
        admin = d._contexto_alertas("acme", "admin")
        cliente = d._contexto_alertas("acme", "cliente")
    assert [a["clave"] for a in admin["visibles"]] == ["llave:r2", "proyecto:logo"]
    assert admin["resumen"] == {"n": 2, "bloquea": 1, "atencion": 0, "info": 1}
    assert [a["clave"] for a in cliente["visibles"]] == ["proyecto:logo"]
    assert cliente["resumen"] == {"n": 1, "bloquea": 0, "atencion": 0, "info": 1}
    assert llamadas == ["acme"]


def test_context_processor_expone_alertas_ctx_y_no_en_json_ni_landing(app, monkeypatch):
    from flask import session
    d = app["dashboard"]
    _fijas(app, monkeypatch, [_alerta(app, "proyecto:logo", "info")])
    with d.app.test_request_context("/cliente/acme"):
        session["usuario"] = "admin"; session["rol"] = "admin"
        assert d._alertas_sidebar()["alertas_ctx"]["resumen"] == {"n": 1, "bloquea": 0, "atencion": 0, "info": 1}
    with d.app.test_request_context("/cliente/acme", headers={"X-Requested-With": "fetch"}):
        session["usuario"] = "admin"; session["rol"] = "admin"
        assert d._alertas_sidebar() == {}                       # parcial por fetch
    with d.app.test_request_context("/cliente/acme", headers={"Accept": "application/json"}):
        session["usuario"] = "admin"; session["rol"] = "admin"
        assert d._alertas_sidebar() == {}                       # JSON
    with d.app.test_request_context("/cliente/acme"):
        assert d._alertas_sidebar() == {}                       # sin sesión
    with d.app.test_request_context("/l/acme"):
        session["usuario"] = "admin"; session["rol"] = "admin"
        assert d._alertas_sidebar() == {}                       # landing pública
    with d.app.test_request_context("/"):
        session["usuario"] = "admin"; session["rol"] = "admin"
        assert d._alertas_sidebar() == {}                       # sin <cliente> en la URL


def test_una_peticion_json_no_calcula_alertas(app, monkeypatch):
    llamadas = []
    _fijas(app, monkeypatch, [_alerta(app, "proyecto:logo", "info")], llamadas)
    r = app["c"].get("/cliente/acme", headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200 and llamadas == []
    assert "sidebar-burbuja" not in r.get_data(as_text=True)


def test_si_el_calculo_revienta_la_pagina_sale_sin_alertas(app, monkeypatch, capsys):
    def explota(cliente, ahora_iso=None):
        raise RuntimeError("token=SECRETO")
    monkeypatch.setattr(app["alertas"], "calcular", explota)
    app["dashboard"].invalidar_alertas()
    html = _html(app["c"])
    assert "SECRETO" not in html and "sidebar-burbuja" not in html
    assert "No se pudieron calcular las alertas" in _tab(html)
    # El Tablero se fundió en Experimentos (E2): su línea de alertas vive en «Necesita tu decisión» del fragmento de
    # resultados, que también sale sin alertas, con el aviso, y sin arrastrar el token del error.
    fragmento = _resultados(app["c"])
    assert "No se pudo calcular las alertas" in fragmento and "cr-alertas-linea" in fragmento
    assert "SECRETO" not in fragmento
    salida = capsys.readouterr().out
    assert "[aviso] Alertas de acme: RuntimeError" in salida and "SECRETO" not in salida


# ---------- rutas descartar / restaurar ----------

def test_descartar_y_restaurar(app, monkeypatch):
    d = app["dashboard"]
    llamadas = []
    a = _alerta(app, "proyecto:guia_marca", ancla="config-marca")
    _fijas(app, monkeypatch, [a], llamadas)
    c = app["c"]
    _html(c)
    assert len(llamadas) == 1
    r = c.post("/cliente/acme/alertas/descartar", data={"clave": a["clave"], "huella": a["huella"]})
    assert r.status_code == 302 and r.headers["Location"].endswith("/cliente/acme#alertas")
    assert _flashes(c) == ["Alerta descartada."]
    assert _descartes() == [("acme", "proyecto:guia_marca", a["huella"])]
    tab = _tab(_html(c))
    assert len(llamadas) == 2                               # descartar vació la caché
    assert 'id="alertas-faltantes"' not in tab and "Descartadas (1)" in tab and "Título proyecto:guia_marca" in tab
    r = c.post("/cliente/acme/alertas/restaurar", data={"clave": a["clave"]})
    assert r.status_code == 302 and r.headers["Location"].endswith("/cliente/acme#alertas")
    assert _flashes(c) == ["Alerta restaurada."]
    assert _descartes() == []
    tab = _tab(_html(c))
    assert len(llamadas) == 3                               # restaurar también
    assert 'id="alertas-faltantes"' in tab and "Descartadas (" not in tab


def test_descartar_invalida_la_cache_antes_de_redirigir(app, monkeypatch):
    """Descartar (y restaurar) vacía la caché antes de redirigir: la página siguiente se calcula con lo real y no con
    una lista de hace unos segundos. Aquí la caché caliente trae la alerta; tras descartarla la realidad cambia (una
    alerta nueva) y el redirect ya la muestra."""
    d = app["dashboard"]
    a = _alerta(app, "crear:prompt_listo", grupo="decision", tab="creativeflowplus")
    nueva = _alerta(app, "proyecto:logo", "info")
    _fijas(app, monkeypatch, [a])
    with d.app.test_request_context("/cliente/acme"):
        assert d._contexto_alertas("acme", "admin")["resumen"]["n"] == 1     # caché caliente, con la alerta
    monkeypatch.setattr(app["alertas"], "calcular", lambda cliente, ahora_iso=None: [dict(a), dict(nueva)])  # la realidad cambió
    r = app["c"].post("/cliente/acme/alertas/descartar", data={"clave": a["clave"], "huella": a["huella"]})
    assert r.status_code == 302
    tab = _tab(_html(app["c"]))
    assert "Descartadas (1)" in tab and "Título proyecto:logo" in tab        # la lista nueva, no la cacheada
    assert _descartes() == [("acme", "crear:prompt_listo", a["huella"])]


def test_descartar_una_alerta_que_la_cache_vieja_no_trae_no_guarda_nada_y_renueva_la_cache(app, monkeypatch):
    """La clave tiene que estar en el cálculo actual. Si la caché (que es de donde salió la página que la persona vio)
    ya no trae la alerta, nada se escribe: no hay descarte huérfano que `visibles` tenga que podar. El POST igual
    vacía la caché y la página siguiente se calcula con lo real."""
    d = app["dashboard"]
    a = _alerta(app, "crear:prompt_listo", grupo="decision", tab="creativeflowplus")
    _fijas(app, monkeypatch, [])
    with d.app.test_request_context("/cliente/acme"):
        assert d._contexto_alertas("acme", "admin")["resumen"]["n"] == 0     # caché caliente SIN la alerta
    monkeypatch.setattr(app["alertas"], "calcular", lambda cliente, ahora_iso=None: [dict(a)])  # la realidad cambió
    c = app["c"]
    r = c.post("/cliente/acme/alertas/descartar", data={"clave": a["clave"], "huella": a["huella"]})
    assert r.status_code == 302 and r.headers["Location"].endswith("/cliente/acme#alertas")
    assert _flashes(c) == ["Esa alerta ya no está."] and _descartes() == []
    tab = _tab(_html(c))
    assert 'id="alertas-decision"' in tab and "Descartadas (" not in tab      # ya sale la real, y sin descartar


@pytest.mark.parametrize("datos", [
    {"clave": "sin dos puntos", "huella": H64},
    {"clave": "llave:r2", "huella": "zz"},
    {"clave": "llave:r2\n", "huella": H64},                 # re.match con «$» dejaría pasar el salto de línea
    {"clave": "llave:r2", "huella": H64 + "\n"},
    {"clave": "llave:r2", "huella": "A" * 64},              # sha256 hex en minúsculas
    {"clave": "a" * 30 + ":" + "b" * 175, "huella": H64},   # calza con el patrón pero pasa de 200 caracteres
    {"clave": "llave:r2"},
    {},
])
def test_descartar_valida_clave_y_huella(app, monkeypatch, datos):
    _fijas(app, monkeypatch, [])
    assert app["c"].post("/cliente/acme/alertas/descartar", data=datos).status_code == 400
    assert _descartes() == []


@pytest.mark.parametrize("clave", ["<script>", "llave:r2\n", "", "a" * 30 + ":" + "b" * 175])
def test_restaurar_valida_la_clave(app, monkeypatch, clave):
    _fijas(app, monkeypatch, [])
    assert app["c"].post("/cliente/acme/alertas/restaurar", data={"clave": clave}).status_code == 400


def test_descartar_una_clave_valida_pero_inventada_redirige_sin_escribir(app, monkeypatch):
    """Seguridad (CWE-770): sin esta regla cualquiera con sesión llenaría `alerta_descartada` de claves que nunca
    existieron. La respuesta es un redirect normal (con un aviso neutro), no un error."""
    a = _alerta(app, "proyecto:guia_marca", ancla="config-marca")
    _fijas(app, monkeypatch, [a])
    c = app["c"]
    r = c.post("/cliente/acme/alertas/descartar", data={"clave": "llave:r2", "huella": H64})
    assert r.status_code == 302 and r.headers["Location"].endswith("/cliente/acme#alertas")
    assert _flashes(c) == ["Esa alerta ya no está."] and _descartes() == []
    for i in range(30):                                                       # y tampoco con muchas: ninguna fila
        assert c.post("/cliente/acme/alertas/descartar", data={"clave": f"inventada:x{i}", "huella": H64}).status_code == 302
    assert _descartes() == []


def test_descartar_una_alerta_real_si_escribe_entre_varias(app, monkeypatch):
    lista = [_alerta(app, "proyecto:guia_marca"), _alerta(app, "proyecto:logo", "info"),
             _alerta(app, "crear:prompt_listo", grupo="decision")]
    _fijas(app, monkeypatch, lista)
    c = app["c"]
    r = c.post("/cliente/acme/alertas/descartar", data={"clave": "proyecto:logo", "huella": lista[1]["huella"]})
    assert r.status_code == 302 and _flashes(c) == ["Alerta descartada."]
    assert _descartes() == [("acme", "proyecto:logo", lista[1]["huella"])]


def test_rutas_respetan_el_guard_por_cliente(app, monkeypatch):
    _fijas(app, monkeypatch, [])
    c = _cliente_rol_cliente(app)
    r = c.post("/cliente/otro/alertas/descartar", data={"clave": "llave:r2", "huella": H64})
    assert r.status_code == 302 and "/cliente/acme" in r.headers["Location"]
    r = c.post("/cliente/otro/alertas/restaurar", data={"clave": "llave:r2"})
    assert r.status_code == 302 and "/cliente/acme" in r.headers["Location"]
    assert _descartes() == []
    sin_sesion = app["dashboard"].app.test_client()
    r = sin_sesion.post("/cliente/acme/alertas/descartar", data={"clave": "llave:r2", "huella": H64})
    assert r.status_code == 302 and "/login" in r.headers["Location"] and _descartes() == []


def test_post_de_otro_sitio_se_rechaza(app, monkeypatch):
    _fijas(app, monkeypatch, [])
    r = app["c"].post("/cliente/acme/alertas/descartar", data={"clave": "llave:r2", "huella": H64},
                      headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    r = app["c"].post("/cliente/acme/alertas/restaurar", data={"clave": "llave:r2"},
                      headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    assert _descartes() == []


def _saldo(app):
    """Las dos alertas del saldo como las arma `_fuente_saldo`: MISMA huella, la del cliente está en su página."""
    al = app["alertas"]
    h = al.huella("2026-10-01T10:00:00")
    return [al._alerta("saldo:wavespeed", h, "bloquea", "puesta_a_punto", "La generación está en pausa", "d",
                       "creativeflowplus"),
            al._alerta("saldo:wavespeed_recarga", h, "bloquea", "puesta_a_punto", "WaveSpeed se quedó sin saldo", "d",
                       "creativeflowplus", solo_admin=True)]


@pytest.mark.parametrize("clave", ["saldo:wavespeed_recarga", "llave:wavespeed"])
def test_un_cliente_no_descarta_ni_restaura_una_alerta_solo_admin(app, monkeypatch, clave):
    """Los descartes son del proyecto: si un cliente pudiera descartar una alerta `solo_admin` (la huella del saldo
    de admin es la misma que la del suyo, que sí ve), se la escondería al admin. El servidor lo frena con 403 y no
    escribe nada; ocultar el botón no basta."""
    lista = _saldo(app) + [_alerta(app, "llave:wavespeed", "bloquea", "puesta_a_punto", solo_admin=True)]
    _fijas(app, monkeypatch, lista)
    huella = next(a["huella"] for a in lista if a["clave"] == clave)
    c = _cliente_rol_cliente(app)
    assert c.post("/cliente/acme/alertas/descartar", data={"clave": clave, "huella": huella}).status_code == 403
    assert _descartes() == []
    r = app["c"].post("/cliente/acme/alertas/descartar", data={"clave": clave, "huella": huella})
    assert r.status_code == 302 and _descartes() == [("acme", clave, huella)]     # el admin sí
    assert c.post("/cliente/acme/alertas/restaurar", data={"clave": clave}).status_code == 403
    assert _descartes() == [("acme", clave, huella)]
    assert app["c"].post("/cliente/acme/alertas/restaurar", data={"clave": clave}).status_code == 302
    assert _descartes() == []


def test_un_cliente_si_descarta_las_suyas(app, monkeypatch):
    lista = _saldo(app)
    _fijas(app, monkeypatch, lista)
    r = _cliente_rol_cliente(app).post("/cliente/acme/alertas/descartar",
                                       data={"clave": "saldo:wavespeed", "huella": lista[0]["huella"]})
    assert r.status_code == 302 and _descartes() == [("acme", "saldo:wavespeed", lista[0]["huella"])]


@pytest.mark.parametrize("clave, status", [("llave:r2", 403), ("worker:parado", 403), ("revision:tablero", 403),
                                           ("saldo:wavespeed_recarga", 403), ("proyecto:logo", 302)])
def test_una_clave_de_admin_que_ya_no_esta_decide_por_su_prefijo(app, monkeypatch, clave, status):
    """Una clave de admin que ya no está calculada se frena por su prefijo (403); una de cliente que ya no está pasa
    el guard y la ruta no guarda nada (302, «Esa alerta ya no está.»). En ningún caso queda una fila."""
    _fijas(app, monkeypatch, [])
    c = _cliente_rol_cliente(app)
    r = c.post("/cliente/acme/alertas/descartar", data={"clave": clave, "huella": H64})
    assert r.status_code == status
    assert _descartes() == []
    assert _flashes(c) == ([] if status == 403 else ["Esa alerta ya no está."])


def test_toda_alerta_solo_admin_de_las_fuentes_lleva_prefijo_de_admin(app, monkeypatch):
    """`PREFIJOS_SOLO_ADMIN` decide cuando la alerta ya no está calculada: tiene que cubrir toda alerta `solo_admin`
    que producen las fuentes de verdad (llaves, worker, recarga del saldo, una fuente caída), y ninguna otra."""
    import llaves
    import saldo
    al = app["alertas"]
    for s_ in llaves.SERVICIOS:
        for v in s_["variables"]:
            monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(saldo, "vigente", lambda p: {"proveedor": p, "nombre": "WaveSpeed", "desde": "2026-10-01T10:00:00",
                                                     "recarga": "https://wavespeed.ai/top-up"} if p == "wavespeed" else None)

    def rota(cliente, ahora):
        raise RuntimeError("x")
    monkeypatch.setattr(al, "FUENTES", al.FUENTES + [("rota", rota)])
    lista = al.calcular("acme")
    de_admin = [a["clave"] for a in lista if a["solo_admin"]]
    assert all(c.startswith(al.PREFIJOS_SOLO_ADMIN) for c in de_admin), de_admin
    assert not [a["clave"] for a in lista if not a["solo_admin"] and a["clave"].startswith(al.PREFIJOS_SOLO_ADMIN)]
    for prefijo in al.PREFIJOS_SOLO_ADMIN:
        assert any(c.startswith(prefijo) for c in de_admin), prefijo
        assert al.es_solo_admin(prefijo + ("x" if prefijo.endswith(":") else ""), [])
    assert not al.es_solo_admin("saldo:wavespeed", lista) and al.es_solo_admin("saldo:wavespeed_recarga", lista)


# ---------- la caché se vacía al escribir y cuando cambia el Tablero ----------

def test_una_escritura_que_sale_bien_vacia_la_cache(app, monkeypatch):
    llamadas = []
    _fijas(app, monkeypatch, [_alerta(app, "proyecto:logo", "info")], llamadas)
    c = app["c"]
    _html(c); _html(c)
    assert len(llamadas) == 1                                       # GET: la caché manda
    assert c.post("/cliente/acme/nombre", data={"nombre": "Acme 2"}).status_code == 302
    _html(c)
    assert len(llamadas) == 2                                       # un POST que salió bien la vació
    assert c.post("/cliente/acme/alertas/descartar", data={"clave": "x", "huella": H64}).status_code == 400
    _html(c)
    assert len(llamadas) == 2                                       # uno que falló, no


def test_un_post_sin_acceso_al_proyecto_no_vacia_su_cache(app, monkeypatch):
    llamadas = []
    _fijas(app, monkeypatch, [_alerta(app, "proyecto:logo", "info")], llamadas)
    c = app["c"]
    _html(c)
    assert len(llamadas) == 1
    ajeno = app["dashboard"].app.test_client()                      # sin sesión: el guard responde 302 al login
    assert ajeno.post("/cliente/acme/nombre", data={"nombre": "X"}).status_code == 302
    _html(c)
    assert len(llamadas) == 1                                       # la caché sigue caliente


def test_subir_un_logo_quita_su_alerta_enseguida(app, monkeypatch):
    """Con la caché caliente, «Sin logos oficiales» se va en la página siguiente a la subida, no a los 60 s."""
    import io
    from tests.conftest import JPG_VALIDO
    monkeypatch.setattr(app["dashboard"].r2_uploader, "upload_image", lambda ruta, key: f"https://r2/{key}")
    c = app["c"]
    assert "Sin logos oficiales" in _tab(_html(c))
    r = c.post("/cliente/acme/logos/subir", data={"imagen": (io.BytesIO(JPG_VALIDO), "logo.jpg")},
               content_type="multipart/form-data")
    assert r.status_code == 302
    assert "Sin logos oficiales" not in _tab(_html(c))


def test_invalidar_tras_escribir_nunca_tumba_la_respuesta(app, monkeypatch, capsys):
    d = app["dashboard"]
    _fijas(app, monkeypatch, [])

    def explota(cliente=None):
        raise RuntimeError("token=SECRETO")
    monkeypatch.setattr(d, "invalidar_alertas", explota)
    r = app["c"].post("/cliente/acme/nombre", data={"nombre": "Acme 2"})
    assert r.status_code == 302 and r.headers["Location"].endswith("#settings")
    salida = capsys.readouterr().out
    assert "[aviso] Alertas: no pude invalidar tras escribir: RuntimeError" in salida and "SECRETO" not in salida


def test_la_cache_se_renueva_cuando_cambia_la_clave_del_tablero(app, monkeypatch):
    """Lo que cambia el worker (un snapshot, una propuesta, una publicación) no pasa por una ruta: la caché de
    alertas lleva la misma clave del Tablero y se renueva en cuanto cambia, sin esperar el TTL."""
    d = app["dashboard"]
    llamadas, clave = [], {"v": (1,)}
    _fijas(app, monkeypatch, [], llamadas)
    monkeypatch.setattr(d, "_clave_tablero", lambda cliente: clave["v"])
    for _ in range(2):
        with d.app.test_request_context("/cliente/acme"):
            d._alertas_calculadas("acme")
    assert len(llamadas) == 1
    clave["v"] = (2,)
    with d.app.test_request_context("/cliente/acme"):
        d._alertas_calculadas("acme")
    assert len(llamadas) == 2


def test_la_clave_del_tablero_se_lee_una_vez_por_pagina(app, monkeypatch):
    """El Tablero y las alertas comparten `_clave_tablero` (7 consultas) dentro de la misma petición."""
    d = app["dashboard"]
    _fijas(app, monkeypatch, [])
    leidas = []
    original = d._clave_tablero
    monkeypatch.setattr(d, "_clave_tablero", lambda cliente: leidas.append(cliente) or original(cliente))
    _html(app["c"])
    assert leidas == ["acme"]
    from sprints import datos
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31")
    leidas.clear()
    _html(app["c"], f"/cliente/acme/sprints/{sid}")             # el chip del sidebar y la burbuja
    assert leidas == ["acme"]


def test_la_fecha_del_descarte_sale_en_el_idioma_de_quien_mira(app, monkeypatch):
    import db
    a = _alerta(app, "proyecto:logo", "info", "faltantes", "Sin logos oficiales")
    _fijas(app, monkeypatch, [a])
    monkeypatch.setattr(db, "ahora", lambda: "2026-10-02T10:00:00")
    app["alertas"].descartar("acme", a["clave"], a["huella"])
    assert "Descartada el 2 oct." in _tab(_html(app["c"]))
    idiomas.guardar_de_usuario("admin", "en")
    assert "Discarded on 2 Oct." in _tab(_html(app["c"]))


# ---------- pestaña ----------

def test_pestana_pinta_grupos_resumen_botones_y_descartar(app, monkeypatch):
    lista = [
        _alerta(app, "llave:wavespeed", "bloquea", "puesta_a_punto", "Falta la llave de WaveSpeed",
                ancla="llave-wavespeed", solo_admin=True),
        _alerta(app, "proyecto:guia_marca", "atencion", "faltantes", "El proyecto no tiene guía de marca", ancla="config-marca"),
        _alerta(app, "tablero:propuestas_pendientes:7", "atencion", "decision", "«X» tiene 2 propuestas del motor",
                tab="experimentos", url="#experimentos?exp=7", entidad=7),
        _alerta(app, "crear:error:cf_1", "atencion", "fallos", "Falló «Sandalia» en Crear", tab="creativeflowplus",
                ancla="cf-cf_1"),
        _alerta(app, "proyecto:logo", "info", "faltantes", "Sin logos oficiales", ancla="config-logos"),
    ]
    _fijas(app, monkeypatch, lista)
    html = _html(app["c"])
    tab = _tab(html)
    # Panel justo después de Experimentos (el primero; ahí se fundió el Tablero) y antes de Configuración (los tests de
    # Configuración recortan desde ahí).
    assert html.index('<section id="tab-experimentos"') < html.index('<section id="tab-alertas"') \
        < html.index('<section id="tab-triplewhale"') < html.index('<section id="tab-settings"')
    assert "<h2>Alertas</h2>" in tab and 'class="panel-cabecera-desc"' in tab
    assert "1 bloquea · 3 piden atención · 1 informativa" in tab
    pos = []
    for gid, nombre in (("puesta_a_punto", "Puesta a punto pendiente"), ("faltantes", "Faltantes del proyecto"),
                        ("decision", "Esperan tu decisión"), ("fallos", "Fallos y errores")):
        assert f'id="alertas-{gid}"' in tab and nombre in tab
        pos.append(tab.index(f'id="alertas-{gid}"'))
    assert pos == sorted(pos)
    assert tab.count('<li class="alerta alerta-bloquea">') == 1 and tab.count('<li class="alerta alerta-atencion">') == 3
    assert tab.count('<li class="alerta alerta-info">') == 1
    assert '<span class="alerta-nivel">bloquea</span>' in tab and '<span class="alerta-nivel">atención</span>' in tab
    assert "Falta la llave de WaveSpeed" in tab and "Detalle de prueba." in tab
    # «Ir a …»: pestaña + ancla, o la URL tal cual.
    assert 'href="#settings" data-ir-tab="settings" data-ancla="llave-wavespeed">Ir a Configuración →' in tab
    assert 'href="#experimentos?exp=7">Ir a Experimentos →' in tab
    assert 'href="#creativeflowplus" data-ir-tab="creativeflowplus" data-ancla="cf-cf_1">Ir a Crear →' in tab
    # Un form de descartar por alerta con su clave y su huella.
    assert tab.count('action="/cliente/acme/alertas/descartar"') == 5
    assert f'<input type="hidden" name="huella" value="{lista[0]["huella"]}">' in tab
    assert '<input type="hidden" name="clave" value="tablero:propuestas_pendientes:7">' in tab
    assert "Descartadas (" not in tab and "estado-vacio" not in tab
    assert "<script" not in tab                       # la navegación vive una sola vez en cliente.html


def test_pestana_vacia_y_descartadas_con_restaurar(app, monkeypatch):
    a = _alerta(app, "proyecto:logo", "info", "faltantes", "Sin logos oficiales", ancla="config-logos")
    _fijas(app, monkeypatch, [a])
    app["alertas"].descartar("acme", a["clave"], a["huella"])
    tab = _tab(_html(app["c"]))
    assert 'class="estado-vacio"' in tab and "Todo en orden" in tab and 'id="alertas-faltantes"' not in tab
    assert "Descartadas (1)" in tab and "Sin logos oficiales" in tab
    assert 'action="/cliente/acme/alertas/restaurar"' in tab and 'name="clave" value="proyecto:logo"' in tab
    assert "Restaurar" in tab
    _fijas(app, monkeypatch, [])
    tab = _tab(_html(app["c"]))
    assert "Todo en orden" in tab and "Descartadas (" not in tab


def test_el_detalle_se_pinta_como_texto(app, monkeypatch):
    """`saldo:wavespeed_recarga` lleva la URL de recarga dentro del detalle, sin `url`: se pinta escapado, nunca
    como HTML, y el «Ir a …» va a la pestaña."""
    a = _alerta(app, "saldo:wavespeed_recarga", "bloquea", "puesta_a_punto", "WaveSpeed se quedó sin saldo",
                detalle='Recarga en https://wavespeed.ai/top-up <b>ya</b>', tab="creativeflowplus", solo_admin=True)
    _fijas(app, monkeypatch, [a])
    tab = _tab(_html(app["c"]))
    assert "Recarga en https://wavespeed.ai/top-up &lt;b&gt;ya&lt;/b&gt;" in tab and "<b>ya</b>" not in tab
    assert 'href="https://wavespeed.ai' not in tab
    assert 'href="#creativeflowplus" data-ir-tab="creativeflowplus">Ir a Crear →' in tab


def test_un_cliente_no_ve_las_alertas_solo_admin(app, monkeypatch):
    _fijas(app, monkeypatch, [
        _alerta(app, "llave:wavespeed", "bloquea", "puesta_a_punto", "Falta la llave de WaveSpeed", solo_admin=True),
        _alerta(app, "worker:parado", "bloquea", "puesta_a_punto", "El worker no está corriendo", solo_admin=True),
        _alerta(app, "proyecto:logo", "info", "faltantes", "Sin logos oficiales"),
    ])
    html = _html(_cliente_rol_cliente(app))
    tab = _tab(html)
    assert "Falta la llave de WaveSpeed" not in html and "El worker no está corriendo" not in html
    assert "Sin logos oficiales" in tab and "1 informativa" in tab and 'name="clave" value="llave:' not in tab
    assert '<span class="sidebar-burbuja atencion"' in _sidebar(html)
    html = _html(app["c"])
    assert "Falta la llave de WaveSpeed" in _tab(html) and '<span class="sidebar-burbuja bloquea"' in _sidebar(html)


# ---------- sidebar ----------

def test_burbuja_del_sidebar_roja_ambar_u_oculta(app, monkeypatch):
    _fijas(app, monkeypatch, [_alerta(app, "llave:r2", "bloquea", "puesta_a_punto"), _alerta(app, "proyecto:logo", "info")])
    sb = _sidebar(_html(app["c"]))
    assert sb.index('data-tab="experimentos"') < sb.index('data-tab="alertas"') < sb.index('data-tab="triplewhale"')
    assert 'data-tab="tablero"' not in sb
    item = sb[sb.index('data-tab="alertas"'):sb.index('data-tab="triplewhale"')]
    assert re.search(r'<span class="sidebar-burbuja bloquea"[^>]*>2</span>', item)
    _fijas(app, monkeypatch, [_alerta(app, "proyecto:logo", "info")])
    sb = _sidebar(_html(app["c"]))
    assert re.search(r'<span class="sidebar-burbuja atencion"[^>]*>1</span>', sb) and "sidebar-burbuja bloquea" not in sb
    _fijas(app, monkeypatch, [_alerta(app, "proyecto:guia_marca", "atencion")])
    assert '<span class="sidebar-burbuja atencion"' in _sidebar(_html(app["c"]))
    _fijas(app, monkeypatch, [])
    html = _html(app["c"])
    assert "sidebar-burbuja" not in html and 'data-tab="alertas"' in html


def test_burbuja_tambien_en_una_pagina_de_sprints(app, monkeypatch):
    from sprints import datos
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31")
    _fijas(app, monkeypatch, [_alerta(app, "llave:r2", "bloquea", "puesta_a_punto")])
    html = _html(app["c"], f"/cliente/acme/sprints/{sid}")
    assert '<span class="sidebar-burbuja bloquea"' in _sidebar(html) and 'data-tab="alertas"' in html


# ---------- navegación y anclas ----------

def test_navegacion_con_ancla_vive_una_vez_en_cliente_html(app, monkeypatch):
    _fijas(app, monkeypatch, [])
    html = _html(app["c"])
    assert "alertas: document.getElementById('tab-alertas')" in html
    assert html.count("#tab-experimentos [data-ir-tab], #tab-alertas [data-ir-tab]") == 1
    assert "#tab-tablero" not in html
    assert "a.dataset.ancla" in html and "scrollIntoView" in html and "window.irAConfig(ancla)" in html
    experimentos = html[html.index('<section id="tab-experimentos"'):html.index('<section id="tab-alertas"')]
    # El script viejo del Tablero se fue: el panel de Experimentos solo trae JSON de textos y su archivo JS.
    scripts = re.findall(r"<script\b[^>]*>", experimentos)
    assert scripts and all('type="application/json"' in s or " src=" in s for s in scripts)


def _anclas_de_alertas():
    """(literales, prefijos de f-string) de cada `ancla=` de alertas.py."""
    with open(os.path.join(RAIZ, "alertas.py"), encoding="utf-8") as f:
        fuente = f.read()
    literales, prefijos = set(), set()
    encontradas = re.findall(r'ancla=(f?)"([^"]+)"', fuente)
    # Toda `ancla=` (menos el `ancla=None` de la firma de _alerta) tiene que calzar con el patrón: una forma nueva
    # (una variable, comillas simples) no puede colarse sin que esta prueba la mire.
    assert len(re.findall(r"\bancla=(?!None\b)", fuente)) == len(encontradas)
    for es_f, valor in encontradas:
        if es_f:
            prefijos.add(valor.split("{", 1)[0])
        else:
            literales.add(valor)
    return literales, prefijos


# Anclas que solo usan alertas `solo_admin` (worker parado): no existen en la página de un cliente.
SOLO_ADMIN = {"config-puesta-a-punto"}
# El apartado Saldo solo existe para un cliente cuyo proyecto cobra (lo comprueba tests/test_cobros_alertas.py).
SOLO_SI_COBRA = {"config-ap-saldo"}


def test_cada_ancla_de_alertas_existe_en_la_pagina(app, monkeypatch):
    """Una alerta con `ancla` hace scroll hasta ese id: si el id no existe, el botón «Ir a …» deja a la persona
    arriba de la pestaña sin saber dónde mirar. Cada ancla de alertas.py (literal o de f-string) tiene que estar en
    la página que ve quien recibe la alerta."""
    import creative_flow
    import llaves
    literales, prefijos = _anclas_de_alertas()
    assert {"config-cuenta", "config-marca", "config-logos", "config-tienda", "config-correo",
            "config-canales-organicos", "config-puesta-a-punto"} <= literales
    # Un prefijo nuevo necesita su comprobación aquí abajo.
    assert prefijos == {"llave-", "cf-"}, prefijos
    creative_flow.crear("acme", [], [], [], "Sandalia", 8, "", "A", legado_id="cf_ancla")
    _fijas(app, monkeypatch, [])
    admin = _html(app["c"])
    for ancla in literales:
        assert f'id="{ancla}"' in admin, ancla
    for s in llaves.SERVICIOS:
        if s["id"] != "meta":
            assert f'id="llave-{s["id"]}"' in admin, s["id"]
    assert 'id="cf-cf_ancla"' in admin
    cliente = _html(_cliente_rol_cliente(app))
    for ancla in literales - SOLO_ADMIN - SOLO_SI_COBRA:
        assert f'id="{ancla}"' in cliente, ancla
    assert 'id="cf-cf_ancla"' in cliente


def test_las_anclas_nuevas_estan_en_su_sitio(app, monkeypatch):
    _fijas(app, monkeypatch, [])
    html = _html(app["c"])
    assert re.search(r'<h2 id="config-marca"[^>]*>Identidad de marca</h2>', html)
    assert re.search(r'<h2 id="config-logos"[^>]*>Logos oficiales</h2>', html)


# ---------- rendimiento ----------

def test_en_frio_las_alertas_no_crecen_con_las_piezas(base_temporal, monkeypatch, tmp_path):
    """La pestaña Alertas se calcula en cada carga de página (con caché de 60 s). Con la caché fría, 12 piezas
    más no pueden costar más consultas que el tope de test_perf_pagina_proyecto (con la caché caliente lo vigila
    esa prueba)."""
    import dashboard
    import proyectos
    from tests.test_perf_pagina_proyecto import _Contador, _sembrar
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    c = _sesion(dashboard, "admin", "admin", None)
    _sembrar(3)
    dashboard.invalidar_tablero()
    with _Contador() as pocas:
        assert c.get("/cliente/acme").status_code == 200
    _sembrar(12, desde=3)
    dashboard.invalidar_tablero()
    with _Contador() as muchas:
        html = c.get("/cliente/acme").data.decode()
    assert 'id="tab-alertas"' in html
    assert muchas.total - pocas.total <= 6, (pocas.total, muchas.total)
