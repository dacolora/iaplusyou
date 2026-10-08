"""Auditoría de seguridad 2026-10-01: lo que se corrigió, para que no vuelva.
Barrera CSRF global, cabeceras de seguridad, estado de trabajos solo para el
dueño, tope de intentos de login, sesión limpia al entrar, tope de tamaño de
las peticiones, «Cambiar producto» sin XSS por subida, SSRF en los
descargadores y el Excel-bomba. Sin red."""
import io
import zipfile

import pytest
from PIL import Image

from tests.test_rutas_cuentas import _ana, _cliente_con_sesion, _flashes, _sesion, app  # noqa: F401 (fixture)


def _png(ancho=4, alto=4):
    buf = io.BytesIO()
    Image.new("RGB", (ancho, alto), (200, 10, 10)).save(buf, format="PNG")
    return buf.getvalue()


# --- CSRF: ningún POST de otro sitio, en ninguna ruta ---------------------------------------

@pytest.mark.parametrize("sitio, esperado", [
    (None, 401), ("same-origin", 401), ("none", 401), ("cross-site", 403), ("same-site", 403),
])
def test_login_rechaza_post_de_otro_sitio(app, sitio, esperado):
    """«Login CSRF»: un formulario de otro sitio no puede iniciar sesión con
    la cuenta del atacante en el navegador de la víctima."""
    c = app["dashboard"].app.test_client()
    headers = {} if sitio is None else {"Sec-Fetch-Site": sitio}
    r = c.post("/login", data={"usuario": "nadie", "password": "x"}, headers=headers)
    assert r.status_code == esperado


def test_post_de_otro_sitio_responde_json_a_fetch(app):
    c = _ana(app)
    r = c.post("/cliente/acme/logos/subir", headers={"Sec-Fetch-Site": "cross-site", "X-Requested-With": "fetch"})
    assert r.status_code == 403 and r.get_json()["ok"] is False


def test_get_no_pasa_por_la_barrera(app):
    c = app["dashboard"].app.test_client()
    assert c.get("/login", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 200


# --- Cabeceras -------------------------------------------------------------------------------

def test_cabeceras_de_seguridad(app, monkeypatch):
    d = app["dashboard"]
    c = d.app.test_client()
    r = c.get("/login")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert "microphone=(self)" in r.headers["Permissions-Policy"]
    assert "Strict-Transport-Security" not in r.headers           # http local: sin HSTS
    monkeypatch.setitem(d.app.config, "SESSION_COOKIE_SECURE", True)
    assert c.get("/login").headers["Strict-Transport-Security"].startswith("max-age=")


# --- Estado de trabajos: solo el dueño ------------------------------------------------------

def test_estado_de_trabajo_solo_para_quien_puede_entrar_al_proyecto(app, monkeypatch):
    d = app["dashboard"]
    import trabajos
    monkeypatch.setattr(trabajos, "dueno", lambda job_id: {"acme__x": "acme", "otro__y": "otro"}.get(job_id))
    monkeypatch.setattr(trabajos, "consultar", lambda job_id: {"estado": "error", "progreso": 100, "elapsed": 1,
                                                                "mensaje": "secreto", "etapa": None, "detalle": None,
                                                                "progreso_real": False})
    anonimo = d.app.test_client()
    assert anonimo.get("/trabajo/acme__x/estado").get_json()["estado"] == "desconocido"
    ana = _ana(app)                                  # rol cliente de "acme"
    assert ana.get("/trabajo/acme__x/estado").get_json()["mensaje"] == "secreto"
    r = ana.get("/trabajo/otro__y/estado").get_json()
    assert r["estado"] == "desconocido" and r["mensaje"] is None
    assert ana.get("/trabajo/sin_dueno/estado").get_json()["estado"] == "desconocido"
    admin = _cliente_con_sesion(app, "admin")
    assert admin.get("/trabajo/otro__y/estado").get_json()["mensaje"] == "secreto"


def test_dueno_de_un_trabajo_en_memoria_y_en_la_cola(base_temporal):
    import threading

    import trabajos
    listo = threading.Event()
    assert trabajos.iniciar("hilo_acme", lambda: listo.wait(5) and "ok", cliente="acme")
    assert trabajos.dueno("hilo_acme") == "acme"
    listo.set()
    assert trabajos.iniciar("hilo_sin_cliente", lambda: "ok")
    assert trabajos.dueno("hilo_sin_cliente") is None
    assert trabajos.encolar("cola_otro", "tipo_x", {}, cliente="otro")
    assert trabajos.dueno("cola_otro") == "otro"
    assert trabajos.dueno("no_existe") is None


# --- Login: tope de intentos, tiempo parejo, sesión limpia ----------------------------------

def test_login_frena_tras_muchos_intentos_fallidos(app, monkeypatch):
    d = app["dashboard"]
    monkeypatch.setattr(d.cuentas, "LOGIN_MAX_POR_USUARIO", 3)
    app["usuarios"].crear("ana", "secreta123", "cliente", cliente="acme", correo="ana@ejemplo.com")
    c = d.app.test_client()
    assert c.post("/login", data={"usuario": "ana", "password": "secreta123"}).status_code == 302  # el bueno no cuenta
    c = d.app.test_client()
    for _ in range(3):
        assert c.post("/login", data={"usuario": "ana", "password": "mala"}).status_code == 401
    r = c.post("/login", data={"usuario": "ana", "password": "secreta123"})
    assert r.status_code == 429 and "usuario" not in _sesion(c)


def test_login_de_usuario_inexistente_tambien_calcula_un_hash(app, monkeypatch):
    usuarios = app["usuarios"]
    llamadas = []
    original = usuarios.check_password_hash
    monkeypatch.setattr(usuarios, "check_password_hash", lambda h, p: llamadas.append(h) or original(h, p))
    assert usuarios.verificar("no-existe", "lo-que-sea") is None
    assert len(llamadas) == 1


def test_login_empieza_con_la_sesion_limpia(app):
    app["usuarios"].crear("ana", "secreta123", "cliente", cliente="acme", correo="ana@ejemplo.com")
    c = app["dashboard"].app.test_client()
    with c.session_transaction() as s:
        s["fp_prefill"] = {"cliente": "otro"}
        s["meta_oauth"] = {"state": "x", "cliente": "otro"}
    c.post("/login", data={"usuario": "ana", "password": "secreta123"})
    sesion = _sesion(c)
    assert sesion["usuario"] == "ana" and "fp_prefill" not in sesion and "meta_oauth" not in sesion


def test_sesion_con_otro_rol_o_proyecto_que_el_usuario_se_cierra(app):
    c = _ana(app)
    with c.session_transaction() as s:
        s["rol"] = "admin"                           # la cookie dice admin; usuarios.json, cliente
    r = c.get("/panel")
    assert r.status_code == 302 and "usuario" not in _sesion(c)


# --- Tamaño de las peticiones ---------------------------------------------------------------

def test_hay_tope_global_de_tamano(app, monkeypatch):
    d = app["dashboard"]
    assert d.app.config["MAX_CONTENT_LENGTH"] == d.MAX_BYTES_PETICION
    monkeypatch.setitem(d.app.config, "MAX_CONTENT_LENGTH", 1024)
    c = _ana(app)
    r = c.post("/cliente/acme/logos/subir", data={"imagen": (io.BytesIO(b"x" * 4096), "logo.png")},
               content_type="multipart/form-data")
    assert r.status_code == 302 and r.headers["Location"].endswith("/cliente/acme")
    assert any("pesa más de" in m for m in _flashes(c))
    r = c.post("/cliente/acme/logos/subir", data={"imagen": (io.BytesIO(b"x" * 4096), "logo.png")},
               content_type="multipart/form-data", headers={"X-Requested-With": "fetch"})
    assert r.status_code == 413 and r.get_json()["ok"] is False
    assert not (app["tmp"] / "clientes" / "acme" / "logos").exists()


# --- Subidas: el contenido manda, no la extensión -------------------------------------------

def test_foto_subida_invalida(app):
    from werkzeug.datastructures import FileStorage
    d = app["dashboard"]
    falsa = FileStorage(io.BytesIO(_png() + b"<script>alert(1)</script>"), filename="x.png")
    assert d._foto_subida_invalida(falsa) is None                           # PNG real (con basura detrás)
    assert d._foto_subida_invalida(FileStorage(io.BytesIO(b"<html>"), filename="x.png"))
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    assert d._foto_subida_invalida(FileStorage(io.BytesIO(svg), filename="x.webp"))


def test_logo_que_no_es_imagen_no_se_guarda(app, monkeypatch):
    d = app["dashboard"]
    subidos = []
    monkeypatch.setattr(d.r2_uploader, "upload_image", lambda local, clave: subidos.append(clave) or "https://r2.test/x")
    c = _ana(app)
    c.post("/cliente/acme/logos/subir", data={"imagen": (io.BytesIO(b"<html>hola</html>"), "logo.png")},
           content_type="multipart/form-data")
    assert subidos == []
    assert any("No pude leer la imagen" in m for m in _flashes(c))
    c.post("/cliente/acme/logos/subir", data={"imagen": (io.BytesIO(_png()), "logo.png")},
           content_type="multipart/form-data")
    assert subidos == ["clientes/acme/logos/logo.png"]


def test_cambiar_producto_rechaza_html_y_sirve_el_original_como_imagen(app, monkeypatch):
    d = app["dashboard"]
    monkeypatch.setattr(d.swaps_mod, "BASE_DIR", str(app["tmp"]))
    encolados = []
    monkeypatch.setattr(d.catalogo_productos, "encontrar", lambda cliente, pid: {"id": pid})
    monkeypatch.setattr(d.aspect_ratio_mod, "detectar_gemini", lambda ruta: "1:1")
    monkeypatch.setattr(d.trabajos, "encolar", lambda *a, **k: encolados.append(a) or True)
    c = _ana(app)
    html = _png() + b"<script>alert(document.cookie)</script>"
    c.post("/cliente/acme/swap/generar", data={"foto": (io.BytesIO(html), "x.html"), "producto_id": "p1"},
           content_type="multipart/form-data")
    assert encolados == []
    c.post("/cliente/acme/swap/generar", data={"foto": (io.BytesIO(b"no soy foto"), "x.png"), "producto_id": "p1"},
           content_type="multipart/form-data")
    assert encolados == []
    c.post("/cliente/acme/swap/generar", data={"foto": (io.BytesIO(_png()), "x.png"), "producto_id": "p1"},
           content_type="multipart/form-data")
    assert len(encolados) == 1
    swap_id = encolados[0][2]["swap_id"]
    r = c.get(f"/cliente/acme/swap/{swap_id}/original")
    assert r.status_code == 200 and r.mimetype == "image/png"
    assert r.headers["X-Content-Type-Options"] == "nosniff"


def test_cambiar_producto_tiene_tope_de_archivos(app, monkeypatch):
    d = app["dashboard"]
    encolados = []
    monkeypatch.setattr(d.catalogo_productos, "encontrar", lambda cliente, pid: {"id": pid})
    monkeypatch.setattr(d.trabajos, "encolar", lambda *a, **k: encolados.append(a) or True)
    c = _ana(app)
    fotos = [(io.BytesIO(_png()), f"f{i}.png") for i in range(d.MAX_SWAPS_POR_ENVIO + 1)]
    c.post("/cliente/acme/swap/generar", data={"foto": fotos, "producto_id": "p1"}, content_type="multipart/form-data")
    assert encolados == []


# --- SSRF -----------------------------------------------------------------------------------

@pytest.mark.parametrize("ip", ["100.64.0.1", "::ffff:127.0.0.1", "::ffff:10.0.0.1", "192.0.2.10"])
def test_host_permitido_rechaza_cgnat_y_ipv4_envuelta(monkeypatch, ip):
    from conectores import url as conector_url
    monkeypatch.setattr(conector_url.socket, "getaddrinfo", lambda host, *a, **kw: [(10, 1, 6, "", (ip, 0))])
    assert conector_url.host_permitido("http://ejemplo.test/x") is False


def test_abrir_no_sigue_una_redireccion_a_la_red_interna(monkeypatch):
    from conectores import url as conector_url
    from conectores.base import ErrorConector

    def dns(host, *a, **kw):
        return [(2, 1, 6, "", ("93.184.216.34" if host == "publico.test" else "169.254.169.254", 0))]

    class Redireccion:
        status_code = 302
        headers = {"Location": "http://metadata.test/latest/"}

        def close(self):
            pass
    pedidas = []
    monkeypatch.setattr(conector_url.socket, "getaddrinfo", dns)
    monkeypatch.setattr(conector_url.requests, "get", lambda url, **kw: pedidas.append(url) or Redireccion())
    with pytest.raises(ErrorConector):
        conector_url.abrir("http://publico.test/foto.jpg")
    assert pedidas == ["http://publico.test/foto.jpg"]


def test_link_de_referencia_no_baja_de_la_red_interna(monkeypatch, tmp_path):
    import referencias_link
    from conectores import url as conector_url
    assert referencias_link._es_trendtrack("https://app.trendtrack.io/share/ads/1")
    assert not referencias_link._es_trendtrack("http://169.254.169.254/latest/?trendtrack.io")
    monkeypatch.setattr(conector_url.socket, "getaddrinfo", lambda host, *a, **kw: [(2, 1, 6, "", ("10.0.0.7", 0))])
    monkeypatch.setattr(referencias_link, "_descargar_ytdlp", lambda *a: pytest.fail("no debió descargar"))
    with pytest.raises(referencias_link.LinkError):
        referencias_link.descargar("https://interno.test/video", str(tmp_path), "x")


def test_tienda_woo_no_llama_a_la_red_interna_ni_sigue_redirecciones(monkeypatch):
    from conectores import _http, woo
    from conectores import url as conector_url
    from conectores.base import ErrorConector

    class Sesion:
        def __init__(self, respuesta):
            self.respuesta, self.llamadas = respuesta, []

        def request(self, metodo, url, **kw):
            self.llamadas.append(kw)
            return self.respuesta

    class Respuesta:
        status_code = 301
        headers = {"Location": "http://169.254.169.254/"}
    monkeypatch.setattr(conector_url.socket, "getaddrinfo", lambda host, *a, **kw: [(2, 1, 6, "", ("10.1.2.3", 0))])
    s = Sesion(Respuesta())
    with pytest.raises(ErrorConector):
        _http.pedir_tienda(s, "GET", "https://tienda.test/wp-json/wc/v3/products")
    assert s.llamadas == []
    monkeypatch.setattr(conector_url.socket, "getaddrinfo", lambda host, *a, **kw: [(2, 1, 6, "", ("93.184.216.34", 0))])
    tienda = woo.Woo({"url": "https://tienda.test", "ck": "ck", "cs": "cs"})
    tienda._s = s
    with pytest.raises(ErrorConector) as ei:
        tienda._get("products")
    assert "169.254.169.254" in str(ei.value) and s.llamadas[0]["allow_redirects"] is False


def test_nueva_idea_visual_solo_acepta_un_personaje_del_proyecto(app, monkeypatch):
    d = app["dashboard"]
    monkeypatch.setattr(d, "_personajes", lambda cliente: [{"nombre": "p.png", "url": "https://r2.test/clientes/acme/personajes/p.png"}])
    monkeypatch.setattr(d.generador_prompts, "generar_conceptos_imagen", lambda *a, **k: pytest.fail("no debió generar"))
    c = _ana(app)
    r = c.post("/cliente/acme/idea/nueva_visual", data={"idea": "x", "image_url": "http://169.254.169.254/latest/"})
    assert r.status_code == 302


# --- Excel con bomba de descompresión -------------------------------------------------------

def test_xlsx_que_descomprime_demasiado_se_rechaza():
    from conectores.base import xlsx_demasiado_grande
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/sharedStrings.xml", b"A" * (2 * 1024 * 1024))
    datos = buf.getvalue()
    assert len(datos) < 50_000
    assert xlsx_demasiado_grande(datos, tope=1024 * 1024) is True
    assert xlsx_demasiado_grande(datos) is False
    assert xlsx_demasiado_grande(b"no es zip") is False


def test_registro_no_sirve_para_listar_usuarios_existentes(app):
    """Decir «ya existe ese usuario/correo» tiene tope por IP (20 por hora)."""
    app["usuarios"].crear("ana", "secreta123", "cliente", cliente="acme", correo="ana@ejemplo.com")
    for _ in range(20):
        app["cuentas"].limite_ok("alta:consulta:ip:5.6.7.8", maximo=20)
    r = app["dashboard"].app.test_client().post(
        "/proyectos/nuevo", data={"nombre": "X", "usuario": "ana", "correo": "otra@ejemplo.com", "password": "secreta123"},
        environ_base={"REMOTE_ADDR": "5.6.7.8"})
    assert r.status_code == 429 and "Ya existe" not in r.get_data(as_text=True)
