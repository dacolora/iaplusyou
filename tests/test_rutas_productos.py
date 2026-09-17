"""Rutas de Productos y Configuración › Tienda / Pixel (Bloque 5, Task 6):
importar archivo/URL, marcar/archivar/vincular, «crear experimento desde
producto», conectar/sincronizar/desconectar tiendas, OAuth de MercadoLibre,
refrescar el Pixel y el render de las dos pestañas. Todo lo que sale a la red
(conectores, importador, Meta) o al worker (trabajos.encolar) va con fakes."""
import io
import os
import re

import pytest

from conectores import ErrorConector
from conectores.base import Conector
from tests.test_experimentos_db import PAISES


def _cliente_admin(dashboard):
    dashboard.app.config["TESTING"] = True
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "admin"; s["rol"] = "admin"; s["cliente"] = None
    return c


def _flashes(c):
    with c.session_transaction() as s:
        return [m for _cat, m in s.get("_flashes", [])]


class FalsoConector(Conector):
    """`probar()` devuelve lo que fije la clase entre tests, o lanza."""
    tipo = "shopify"
    tiene_pedidos = True
    soporta_utm = True
    resultado = {"ok": True, "nombre": "Acme Store", "detalle": "Conectado (moneda COP)."}
    error = None
    credenciales_vistas = []

    def __init__(self, credenciales, **kw):
        super().__init__(credenciales)
        FalsoConector.credenciales_vistas.append(dict(credenciales))

    def probar(self):
        if FalsoConector.error:
            raise FalsoConector.error
        return dict(FalsoConector.resultado)


@pytest.fixture()
def app(base_temporal, tmp_path, monkeypatch):
    import catalogo_productos
    import conectores
    import dashboard
    monkeypatch.setenv("FLASK_SECRET_KEY", "clave-de-prueba-larga-1234567890")
    monkeypatch.delenv("MELI_APP_ID", raising=False)
    monkeypatch.delenv("MELI_SECRET", raising=False)
    monkeypatch.setattr(dashboard, "_client_dir", lambda cliente: str(tmp_path / "clientes" / cliente))
    monkeypatch.setattr(catalogo_productos, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(dashboard.meta_conexion, "estado", lambda c: {"estado": "conectado", "verificado": True, "detalle": {}})
    monkeypatch.setattr(dashboard.meta_conexion, "estado_pixel",
                        lambda c, solo_cache=False: {"estado": "sin_pixel", "pixel_id": None, "nombre": None,
                                                     "ultimo_disparo": None, "detalle": "La cuenta no tiene Pixel."})
    encolados = []
    monkeypatch.setattr(dashboard.trabajos, "encolar",
                        lambda job_id, tipo, payload, **kw: (encolados.append({"job_id": job_id, "tipo": tipo, "payload": payload, **kw}), True)[1])
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: False)
    FalsoConector.error, FalsoConector.credenciales_vistas = None, []
    FalsoConector.resultado = {"ok": True, "nombre": "Acme Store", "detalle": "Conectado (moneda COP)."}
    monkeypatch.setattr(conectores, "por_tipo", lambda tipo: FalsoConector)
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard), "encolados": encolados, "tmp": tmp_path}


def _producto(cliente="acme", nombre="Cojín Azul", **datos):
    import tiendas
    base = {"nombre": nombre, "precio": 89900.0, "moneda": "COP", "url_compra": "https://tienda.test/cojin",
            "fotos": ["https://cdn.test/a.jpg"]}
    base.update(datos)
    return tiendas.upsert_producto(cliente, "csv", nombre.lower().replace(" ", "-"), base)


# --- importar --------------------------------------------------------------

def test_importar_archivo_guarda_y_encola_una_vez(app):
    c = app["c"]
    r = c.post("/cliente/acme/productos/importar/archivo",
               data={"archivo": (io.BytesIO(b"nombre;precio\nCojin;100\n"), "mi catalogo.csv")},
               content_type="multipart/form-data")
    assert r.status_code == 302 and "productos" in r.headers["Location"]
    carpeta = app["tmp"] / "clientes" / "acme" / "importaciones"
    archivos = os.listdir(carpeta)
    assert len(archivos) == 1 and archivos[0].endswith("_mi_catalogo.csv")
    assert re.match(r"^\d{8}_\d{6}_\d{6}_mi_catalogo\.csv$", archivos[0])   # <ts>_<micro>_<nombre>
    assert len(app["encolados"]) == 1
    t = app["encolados"][0]
    assert t["tipo"] == "catalogo_importar" and t["job_id"] == "acme__importar_archivo" and t["max_intentos"] == 1
    assert t["payload"]["ruta"] == str(carpeta / archivos[0]) and t["payload"]["nombre_archivo"] == "mi_catalogo.csv"
    assert t["payload"]["borrar_al_terminar"] is True and t["cliente"] == "acme"


def test_importar_archivo_rechaza_extension_y_tamano(app):
    c = app["c"]
    c.post("/cliente/acme/productos/importar/archivo",
           data={"archivo": (io.BytesIO(b"MZ..."), "virus.exe")}, content_type="multipart/form-data")
    c.post("/cliente/acme/productos/importar/archivo",
           data={"archivo": (io.BytesIO(b"x" * (5 * 1024 * 1024 + 1)), "grande.csv")}, content_type="multipart/form-data")
    c.post("/cliente/acme/productos/importar/archivo", data={}, content_type="multipart/form-data")
    assert app["encolados"] == []
    assert not (app["tmp"] / "clientes" / "acme" / "importaciones").exists()
    mensajes = _flashes(c)
    assert any(".csv o .xlsx" in m for m in mensajes) and any("5 MB" in m for m in mensajes)


def test_importar_archivo_dos_subidas_seguidas_no_se_pisan(app):
    c = app["c"]
    for _ in range(2):
        c.post("/cliente/acme/productos/importar/archivo",
               data={"archivo": (io.BytesIO(b"nombre\nX\n"), "c.csv")}, content_type="multipart/form-data")
    archivos = sorted(os.listdir(app["tmp"] / "clientes" / "acme" / "importaciones"))
    assert len(archivos) == 2 and len(set(archivos)) == 2
    assert sorted(t["payload"]["ruta"] for t in app["encolados"]) == [
        str(app["tmp"] / "clientes" / "acme" / "importaciones" / a) for a in archivos]


def test_importar_archivo_rechaza_por_content_length_antes_de_leer(app, monkeypatch):
    """Un POST muy grande se rechaza mirando Content-Length, sin parsear el
    multipart (no hay MAX_CONTENT_LENGTH global: personajes/marca suben videos)."""
    d = app["dashboard"]
    assert d.app.config.get("MAX_CONTENT_LENGTH") is None
    r = app["c"].post("/cliente/acme/productos/importar/archivo",
                      data={"archivo": (io.BytesIO(b"x" * (12 * 1024 * 1024)), "enorme.csv")},
                      content_type="multipart/form-data")
    assert r.status_code == 302 and app["encolados"] == []
    assert not (app["tmp"] / "clientes" / "acme" / "importaciones").exists()
    assert any("5 MB" in m for m in _flashes(app["c"]))


def test_importar_archivo_borra_si_ya_habia_una_en_curso(app, monkeypatch):
    monkeypatch.setattr(app["dashboard"].trabajos, "encolar", lambda *a, **kw: False)
    app["c"].post("/cliente/acme/productos/importar/archivo",
                  data={"archivo": (io.BytesIO(b"nombre\nX\n"), "c.csv")}, content_type="multipart/form-data")
    assert os.listdir(app["tmp"] / "clientes" / "acme" / "importaciones") == []
    assert any("en curso" in m for m in _flashes(app["c"]))


def test_importar_url_valida_http(app):
    c = app["c"]
    c.post("/cliente/acme/productos/importar/url", data={"url": "tienda.co/p"})
    assert app["encolados"] == []
    c.post("/cliente/acme/productos/importar/url", data={"url": "https://tienda.co/p"})
    t = app["encolados"][0]
    assert t["tipo"] == "catalogo_importar" and t["job_id"] == "acme__importar_url" and t["max_intentos"] == 1
    assert t["payload"] == {"cliente": "acme", "url": "https://tienda.co/p"}


# --- marcar / archivar / vincular / experimento ------------------------------

def test_marcar_actualiza_banderas_y_valida(app):
    import tiendas
    pid = _producto()
    c = app["c"]
    r = c.post(f"/cliente/acme/productos/{pid}/marcar",
               data={"en_prueba": "on", "prioridad": "70", "url_compra": "https://t.co/x", "precio": "120,5", "moneda": "mxn"})
    assert r.status_code == 302 and "productos" in r.headers["Location"]
    p = tiendas.producto("acme", pid)
    assert p["en_prueba"] is True and p["prioridad"] == 70 and p["url_compra"] == "https://t.co/x"
    assert p["precio"] == 120.5 and p["moneda"] == "MXN"
    # checkbox sin marcar = apagado; prioridad fuera de rango no toca nada
    c.post(f"/cliente/acme/productos/{pid}/marcar", data={"prioridad": "0"})
    assert tiendas.producto("acme", pid)["en_prueba"] is False
    c.post(f"/cliente/acme/productos/{pid}/marcar", data={"en_prueba": "on", "prioridad": "500"})
    c.post(f"/cliente/acme/productos/{pid}/marcar", data={"en_prueba": "on", "url_compra": "tienda.co"})
    c.post(f"/cliente/acme/productos/{pid}/marcar", data={"en_prueba": "on", "moneda": "pesos"})
    p = tiendas.producto("acme", pid)
    assert p["en_prueba"] is False and p["prioridad"] == 0 and p["moneda"] == "MXN"


def test_marcar_y_archivar_no_cruzan_clientes(app):
    import tiendas
    pid = _producto(cliente="otro")
    c = app["c"]
    r = c.post(f"/cliente/acme/productos/{pid}/marcar", data={"en_prueba": "on", "prioridad": "9"})
    assert r.status_code == 302
    r = c.post(f"/cliente/acme/productos/{pid}/archivar")
    assert r.status_code == 302
    p = tiendas.producto("otro", pid)
    assert p["en_prueba"] is False and p["prioridad"] == 0 and p["archivado"] is False
    assert all("No encontré" in m for m in _flashes(c))


def test_archivar_y_recuperar(app):
    """Archivar desde la pestaña es MANUAL (`extra.archivado_por`): una sync
    que traiga el producto no lo desarchiva. «Recuperar» limpia la marca."""
    import tiendas
    pid = _producto()
    c = app["c"]
    c.post(f"/cliente/acme/productos/{pid}/archivar")
    p = tiendas.producto("acme", pid)
    assert p["archivado"] is True and p["extra"]["archivado_por"] == "manual"
    tiendas.upsert_producto("acme", p["fuente"], p["fuente_id"], {"nombre": p["nombre"], "extra": {"handle": "h"}})
    assert tiendas.producto("acme", pid)["archivado"] is True
    c.post(f"/cliente/acme/productos/{pid}/archivar", data={"archivado": "0"})
    p = tiendas.producto("acme", pid)
    assert p["archivado"] is False and "archivado_por" not in p["extra"] and p["extra"]["handle"] == "h"


def test_vincular_encola_la_tarea_y_no_llama_al_importador(app, monkeypatch):
    """«Crear activo» baja fotos y llama a Claude: puede tardar minutos, así
    que la ruta solo encola `producto_vincular` (max_intentos=1)."""
    import importador
    pid = _producto()
    monkeypatch.setattr(importador, "vincular_activo",
                        lambda *a, **kw: pytest.fail("la ruta no debe vincular inline"))
    r = app["c"].post(f"/cliente/acme/productos/{pid}/vincular")
    assert r.status_code == 302 and "productos" in r.headers["Location"]
    assert len(app["encolados"]) == 1
    t = app["encolados"][0]
    assert t["tipo"] == "producto_vincular" and t["job_id"] == f"acme__producto{pid}__vincular"
    assert t["payload"] == {"cliente": "acme", "producto_id": pid} and t["max_intentos"] == 1
    assert t["cliente"] == "acme" and [e[0] for e in t["etapas"]] == ["Bajando fotos", "Creando el activo"]
    assert any("Creando el activo" in m and "Cojín Azul" in m for m in _flashes(app["c"]))
    # ya en curso: no se encola dos veces
    monkeypatch.setattr(app["dashboard"].trabajos, "encolar", lambda *a, **kw: False)
    app["c"].post(f"/cliente/acme/productos/{pid}/vincular")
    assert len(app["encolados"]) == 1 and any("espera" in m for m in _flashes(app["c"]))
    # cross-tenant: ni se encola
    monkeypatch.setattr(app["dashboard"].trabajos, "encolar",
                        lambda *a, **kw: pytest.fail("producto de otro cliente"))
    r = app["c"].post(f"/cliente/acme/productos/{_producto(cliente='otro')}/vincular")
    assert r.status_code == 302 and any("No encontré" in m for m in _flashes(app["c"]))


def test_render_fila_con_vincular_en_curso_pinta_barra(app, monkeypatch):
    """Con una tarea producto_vincular viva para esa fila, «Crear activo»
    queda deshabilitado y sale la barra con su job_id (una consulta a la cola)."""
    import cola
    pid = _producto(nombre="Cojín Azul")
    pid_otro = _producto(nombre="Espejo redondo")
    cola.encolar("producto_vincular", {"cliente": "acme", "producto_id": pid}, cliente="acme",
                 job_id=f"acme__producto{pid}__vincular", max_intentos=1)
    # una terminada no cuenta
    tid = cola.encolar("producto_vincular", {"cliente": "acme", "producto_id": pid_otro}, cliente="acme",
                       job_id=f"acme__producto{pid_otro}__vincular", max_intentos=1)
    cola.terminar(tid, "listo")
    html = app["c"].get("/cliente/acme").data.decode()
    assert f'id="trabajo-acme__producto{pid}__vincular"' in html and "Creando activo…" in html
    assert f"trabajo-acme__producto{pid_otro}__vincular" not in html
    assert html.count("Crear activo") == 1


def test_experimento_desde_producto_redirige_con_query(app):
    pid = _producto(nombre="Espejo redondo", url_compra="https://tienda.test/espejo")
    r = app["c"].post(f"/cliente/acme/productos/{pid}/experimento")
    assert r.status_code == 302
    loc = r.headers["Location"]
    assert "exp_nombre=Espejo+redondo" in loc and "exp_destino=https://tienda.test/espejo" in loc
    assert loc.endswith("#experimentos")
    r = app["c"].post(f"/cliente/acme/productos/{_producto(cliente='otro')}/experimento")
    assert "exp_nombre" not in r.headers["Location"] and r.headers["Location"].endswith("#productos")


# --- tiendas -----------------------------------------------------------------

def test_conectar_tienda_prueba_guarda_y_encola_sync(app):
    import tiendas
    c = app["c"]
    r = c.post("/cliente/acme/config/tienda/conectar",
               data={"tipo": "shopify", "dominio": "acme.myshopify.com", "token": "shpat_x"})
    assert r.status_code == 302 and "settings" in r.headers["Location"]
    assert FalsoConector.credenciales_vistas == [{"dominio": "acme.myshopify.com", "token": "shpat_x"}]
    lista = tiendas.listar("acme")
    assert len(lista) == 1 and lista[0]["tipo"] == "shopify" and lista[0]["nombre"] == "Acme Store"
    assert lista[0]["dominio"] == "acme.myshopify.com" and lista[0]["estado"] == "conectada"
    assert tiendas.credenciales("acme", lista[0]["id"]) == {"dominio": "acme.myshopify.com", "token": "shpat_x"}
    tipos = [(t["tipo"], t["max_intentos"]) for t in app["encolados"]]
    assert tipos == [("tienda_sync_productos", 3), ("tienda_sync_pedidos", 3)]
    assert app["encolados"][0]["job_id"] == f"acme__tienda{lista[0]['id']}__productos"
    assert app["encolados"][0]["payload"] == {"cliente": "acme", "tienda_id": lista[0]["id"]}


def test_conectar_woo_guarda_dominio_desde_url(app):
    import tiendas
    FalsoConector.resultado = {"ok": True, "nombre": "", "detalle": "ok"}
    app["c"].post("/cliente/acme/config/tienda/conectar",
                  data={"tipo": "woo", "url": "https://mitienda.com/", "ck": "ck_1", "cs": "cs_1"})
    t = tiendas.listar("acme")[0]
    assert t["tipo"] == "woo" and t["dominio"] == "mitienda.com" and t["nombre"] is None
    assert tiendas.credenciales("acme", t["id"]) == {"url": "https://mitienda.com/", "ck": "ck_1", "cs": "cs_1"}


def test_conectar_tienda_falla_no_guarda(app):
    import tiendas
    FalsoConector.error = ErrorConector("Shopify rechazó el token (401).")
    app["c"].post("/cliente/acme/config/tienda/conectar",
                  data={"tipo": "shopify", "dominio": "acme.myshopify.com", "token": "malo"})
    assert tiendas.listar("acme") == [] and app["encolados"] == []
    assert any("rechazó el token" in m for m in _flashes(app["c"]))
    FalsoConector.error = RuntimeError("boom access_token=abc123")
    app["c"].post("/cliente/acme/config/tienda/conectar",
                  data={"tipo": "shopify", "dominio": "acme.myshopify.com", "token": "malo"})
    assert tiendas.listar("acme") == []
    ultimo = _flashes(app["c"])[-1]
    assert "boom" in ultimo and "abc123" not in ultimo
    app["c"].post("/cliente/acme/config/tienda/conectar", data={"tipo": "meli"})
    assert tiendas.listar("acme") == []


def test_conectar_sin_secret_key_avisa_y_no_guarda(app, monkeypatch):
    import tiendas
    monkeypatch.delenv("FLASK_SECRET_KEY")
    app["c"].post("/cliente/acme/config/tienda/conectar",
                  data={"tipo": "shopify", "dominio": "acme.myshopify.com", "token": "shpat_x"})
    assert tiendas.listar("acme") == [] and FalsoConector.credenciales_vistas == []
    assert any("FLASK_SECRET_KEY" in m for m in _flashes(app["c"]))


def test_sincronizar_encola_dos_tareas_tambien_si_rota(app):
    import tiendas
    tid = tiendas.conectar("acme", "shopify", {"dominio": "d", "token": "t"}, nombre="Acme")
    tiendas.actualizar("acme", tid, estado="rota", error="token vencido")
    r = app["c"].post(f"/cliente/acme/config/tienda/{tid}/sincronizar")
    assert r.status_code == 302
    assert [t["tipo"] for t in app["encolados"]] == ["tienda_sync_productos", "tienda_sync_pedidos"]
    assert app["encolados"][1]["job_id"] == f"acme__tienda{tid}__pedidos"
    # de otro cliente: no existe para acme
    ajena = tiendas.conectar("otro", "shopify", {"dominio": "d", "token": "t"})
    app["c"].post(f"/cliente/acme/config/tienda/{ajena}/sincronizar")
    assert len(app["encolados"]) == 2


def test_desconectar_borra_tienda_y_archiva_productos(app):
    import tiendas
    tid = tiendas.conectar("acme", "shopify", {"dominio": "d", "token": "t"})
    pid = tiendas.upsert_producto("acme", "shopify", "p1", {"nombre": "Uno"})
    ajena = tiendas.conectar("otro", "shopify", {"dominio": "d", "token": "t"})
    app["c"].post(f"/cliente/acme/config/tienda/{ajena}/desconectar")
    assert tiendas.listar("otro") != []
    # con un pedido sincronizado: antes reventaba con IntegrityError (FK pedido.tienda_id)
    tiendas.guardar_pedidos("acme", tid, [{"fuente_id": "1001", "fecha": "2026-09-16T10:00:00", "total": 5.0,
                                           "moneda": "USD", "items": [], "utm_content": "7"}])
    r = app["c"].post(f"/cliente/acme/config/tienda/{tid}/desconectar")
    assert r.status_code == 302 and tiendas.listar("acme") == []
    assert tiendas.producto("acme", pid)["archivado"] is True
    assert [p["fuente_id"] for p in tiendas.pedidos_sin_resolver("acme")] == ["1001"]
    assert any("pedidos se conservan" in m for m in _flashes(app["c"]))


# --- MercadoLibre ------------------------------------------------------------

def test_meli_iniciar_sin_app_id_avisa(app):
    r = app["c"].get("/cliente/acme/config/tienda/meli/iniciar")
    assert r.status_code == 302 and "settings" in r.headers["Location"]
    msg = _flashes(app["c"])[-1]
    assert "MELI_APP_ID" in msg and "MELI_SECRET" in msg
    with app["c"].session_transaction() as s:
        assert "meli_oauth" not in s


def test_meli_oauth_completo(app, monkeypatch):
    import tiendas
    d = app["dashboard"]
    monkeypatch.setenv("MELI_APP_ID", "123")
    monkeypatch.setenv("MELI_SECRET", "s")
    c = app["c"]
    r = c.get("/cliente/acme/config/tienda/meli/iniciar")
    assert r.status_code == 302 and r.headers["Location"].startswith("https://auth.mercadolibre.com.co/authorization?")
    with c.session_transaction() as s:
        state = s["meli_oauth"]["state"]
        assert s["meli_oauth"]["cliente"] == "acme"
    assert f"state={state}" in r.headers["Location"] and "redirect_uri=http%3A%2F%2Flocalhost%2Fmeli%2Fcallback" in r.headers["Location"]

    # state ajeno: no se cambia el code ni se guarda nada
    llamadas = []
    monkeypatch.setattr(d.conector_meli, "cambiar_code",
                        lambda code, redirect_uri: (llamadas.append((code, redirect_uri)),
                                                    {"access_token": "a", "refresh_token": "r", "user_id": "9",
                                                     "nickname": "ACMECO", "site_id": "MCO"})[1])
    r = c.get(f"/meli/callback?code=abc&state=otro")
    assert r.status_code == 302 and llamadas == [] and tiendas.listar("acme") == []
    # el state es de un solo uso: hay que iniciar de nuevo
    c.get("/cliente/acme/config/tienda/meli/iniciar")
    with c.session_transaction() as s:
        state = s["meli_oauth"]["state"]
    r = c.get(f"/meli/callback?code=abc&state={state}")
    assert r.status_code == 302 and "settings" in r.headers["Location"]
    assert llamadas == [("abc", "http://localhost/meli/callback")]
    t = tiendas.listar("acme")[0]
    assert t["tipo"] == "meli" and t["nombre"] == "ACMECO"
    assert tiendas.credenciales("acme", t["id"])["refresh_token"] == "r"
    assert [x["tipo"] for x in app["encolados"]] == ["tienda_sync_productos", "tienda_sync_pedidos"]
    with c.session_transaction() as s:
        assert "meli_oauth" not in s


def test_meli_callback_sin_sesion_o_denegado(app, monkeypatch):
    import tiendas
    c = app["c"]
    r = c.get("/meli/callback?code=abc&state=x")
    assert r.status_code == 302 and r.headers["Location"].endswith("/")
    monkeypatch.setenv("MELI_APP_ID", "123")
    monkeypatch.setenv("MELI_SECRET", "s")
    c.get("/cliente/acme/config/tienda/meli/iniciar")
    with c.session_transaction() as s:
        state = s["meli_oauth"]["state"]
    r = c.get(f"/meli/callback?error=access_denied&error_description=cancelado&state={state}")
    assert "settings" in r.headers["Location"] and tiendas.listar("acme") == []
    assert any("cancelado" in m for m in _flashes(c))


# --- Pixel -------------------------------------------------------------------

def test_pixel_refrescar_invalida_y_consulta(app, monkeypatch):
    d = app["dashboard"]
    llamadas = []
    monkeypatch.setattr(d.meta_conexion, "invalidar_pixel", lambda c: llamadas.append(("invalidar", c)))
    monkeypatch.setattr(d.meta_conexion, "estado_pixel",
                        lambda c, solo_cache=False: (llamadas.append(("estado", c)), {"estado": "ok", "detalle": "x"})[1])
    r = app["c"].post("/cliente/acme/config/pixel/refrescar")
    assert r.status_code == 302 and "settings" in r.headers["Location"]
    assert llamadas == [("invalidar", "acme"), ("estado", "acme")]
    assert any("disparando" in m for m in _flashes(app["c"]))


# --- render ------------------------------------------------------------------

def test_render_pestana_productos(app, tmp_path):
    import catalogo_productos
    import tiendas
    pid_ok = _producto(nombre="Cojín Azul")
    _producto(nombre="Espejo redondo", en_prueba=True)
    tiendas.marcar_producto("acme", pid_ok, activo_catalogo_id="cojin_azul", en_prueba=True, prioridad=40)
    catalogo_productos.crear("acme", "Cojín Azul", categoria="producto", producto_id="cojin_azul")
    r = app["c"].get("/cliente/acme")
    assert r.status_code == 200
    html = r.data.decode()
    assert "Importar CSV/Excel" in html and "Importar desde URL" in html and "Conectar tienda" in html
    assert "Cojín Azul" in html and "Espejo redondo" in html
    assert "En prueba" in html and "listo para Crear" in html and "sin activo" in html and "Crear activo" in html
    assert "Mostrar archivados" in html and "Crear experimento" in html
    assert 'data-tab="productos"' in html and 'id="tab-productos"' in html


def test_render_productos_confirm_y_url_seguros(app):
    """El nombre con apóstrofo va en data-nombre (escapado como atributo), no
    dentro de un literal JS; y una url_compra que no es http(s) (CSV) no se
    vuelve enlace."""
    _producto(nombre="Cojín d'Or")
    _producto(nombre="Raro", url_compra="javascript:alert(1)")
    html = app["c"].get("/cliente/acme").data.decode()
    assert 'data-nombre="Cojín d&#39;Or"' in html
    assert "confirm('¿Archivar «Cojín" not in html and "confirm(\"¿Archivar" not in html
    assert 'href="javascript:' not in html and "javascript:alert(1)" in html
    assert 'href="https://tienda.test/cojin"' in html


def test_render_configuracion_tienda_y_pixel(app, monkeypatch):
    import tiendas
    d = app["dashboard"]
    tid = tiendas.conectar("acme", "shopify", {"dominio": "acme.myshopify.com", "token": "t"},
                           nombre="Acme Store", dominio="acme.myshopify.com")
    tiendas.actualizar("acme", tid, ultima_sync_productos="2026-09-16T10:00:00")
    monkeypatch.setattr(d.meta_conexion, "estado_pixel",
                        lambda c, solo_cache=False: {"estado": "ok", "pixel_id": "77", "nombre": "Pixel Acme",
                                                     "ultimo_disparo": "2026-09-16T09:00:00+0000", "detalle": "El Pixel disparó."})
    html = app["c"].get("/cliente/acme").data.decode()
    assert "Acme Store" in html and "acme.myshopify.com" in html and "2026-09-16T10:00" in html
    assert "Sincronizar" in html and "Desconectar" in html and "Conectar Shopify" in html and "Conectar WooCommerce" in html
    assert "MELI_APP_ID" in html          # sin app configurada: dice qué falta
    assert "Pixel activo" in html and "Pixel Acme" in html and "Volver a comprobar" in html
    assert "(sugerida)" in html           # selector de atribución en Nuevo experimento
    assert "Falta <code>FLASK_SECRET_KEY" not in html


def test_render_sin_cifrado_deshabilita_formularios(app, monkeypatch):
    monkeypatch.delenv("FLASK_SECRET_KEY")
    html = app["c"].get("/cliente/acme").data.decode()
    assert "Falta <code>FLASK_SECRET_KEY" in html


def test_render_pixel_sin_conexion(app, monkeypatch):
    d = app["dashboard"]
    monkeypatch.setattr(d.meta_conexion, "estado", lambda c: {"estado": "sin_conectar", "verificado": True, "detalle": {}})
    llamadas = []
    monkeypatch.setattr(d.meta_conexion, "estado_pixel", lambda c, solo_cache=False: llamadas.append(solo_cache))
    html = app["c"].get("/cliente/acme").data.decode()
    # sin Meta no se va a Graph: la única consulta es la de atribucion_sugerida, solo caché
    assert llamadas == [True] and "sin conexión" in html
    assert "Comprobar Pixel" not in html and "sin comprobar" not in html


def test_render_pixel_meta_conectado_sin_cache_muestra_sin_comprobar(app, monkeypatch):
    """La página del proyecto NUNCA va a Graph: con Meta conectado y caché
    vacío (estado_pixel(solo_cache=True) → None) muestra «sin comprobar» y
    el botón «Comprobar Pixel» (POST cfg_pixel_refrescar), que es el único
    que calcula."""
    d = app["dashboard"]
    llamadas = []
    monkeypatch.setattr(d.meta_conexion, "estado_pixel", lambda c, solo_cache=False: (llamadas.append(solo_cache), None)[1])
    html = app["c"].get("/cliente/acme").data.decode()
    assert llamadas == [True, True]      # ver_cliente + atribucion_sugerida, ambas solo caché
    assert "sin comprobar" in html and "Comprobar Pixel" in html
    assert "/cliente/acme/config/pixel/refrescar" in html
    assert "Volver a comprobar" not in html and "sin conexión" not in html
    assert "pulsa «Comprobar Pixel»" in html


def test_render_meli_configurado_sin_cifrado_avisa(app, monkeypatch):
    monkeypatch.setenv("MELI_APP_ID", "123")
    monkeypatch.delenv("FLASK_SECRET_KEY")
    html = app["c"].get("/cliente/acme").data.decode()
    inicio = html.index('data-tienda-panel="meli"')
    panel = html[inicio:html.index("</div>", inicio)]
    assert "FLASK_SECRET_KEY" in panel and "MELI_APP_ID</code> y" not in panel
    assert "/tienda/meli/iniciar" not in panel


def test_ver_cliente_contexto_productos(app, base_temporal, monkeypatch):
    """Estado en el loop: activo_ok por producto y «en N experimentos» contando
    experimentos con piezas hechas desde ese activo (productos_ids de Crear
    guarda NOMBRES). Se comprueba por el contexto que llega a la plantilla."""
    import catalogo_productos
    import creative_flow
    import experimentos as ex
    import tiendas
    d = app["dashboard"]
    pid = _producto(nombre="Cojín Azul")
    tiendas.marcar_producto("acme", pid, activo_catalogo_id="cojin_azul")
    catalogo_productos.crear("acme", "Cojín Azul", categoria="producto", producto_id="cojin_azul")
    pid_sin = _producto(nombre="Huérfano")
    tiendas.marcar_producto("acme", pid_sin, activo_catalogo_id="no_existe")
    cf = creative_flow.crear("acme", [], ["Cojín Azul"], [], "camina", 8, "alegre", "A")
    creative_flow.actualizar("acme", cf, estado="listo", video_url="https://r2/v.mp4")
    pieza = creative_flow.pieza_id_por_legado("acme", cf)
    e1 = ex.crear("acme", "Uno", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    e2 = ex.crear("acme", "Dos", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ex.crear("acme", "Vacío", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ex.agregar_pieza("acme", e1, pieza, "CO")
    ex.agregar_pieza("acme", e2, pieza, "CO")
    tiendas.conectar("acme", "shopify", {"dominio": "d", "token": "t"})
    job_sync = d.tareas_tiendas.job_id_sync_productos("acme", tiendas.listar("acme")[0]["id"])
    monkeypatch.setattr(d.trabajos, "en_curso", lambda jid: jid in (job_sync, "acme__importar_url"))
    llamadas_pixel = []
    monkeypatch.setattr(d.meta_conexion, "estado_pixel",
                        lambda c, solo_cache=False: (llamadas_pixel.append(solo_cache), {"estado": "sin_pixel"})[1])
    capturado = {}

    def _render(nombre, **ctx):
        capturado.update(ctx)
        return "ok"
    monkeypatch.setattr(d, "render_template", _render)
    assert app["c"].get("/cliente/acme").status_code == 200
    por_id = {p["id"]: p for p in capturado["productos_tienda"]}
    assert por_id[pid]["activo_ok"] is True and por_id[pid]["n_experimentos"] == 2
    assert por_id[pid_sin]["activo_ok"] is False and por_id[pid_sin]["n_experimentos"] == 0
    assert capturado["trabajos_prod"] == {"importar": {"job_id": "acme__importar_url"},
                                          "tiendas": {tiendas.listar("acme")[0]["id"]: {"job_id": job_sync}},
                                          "vincular": {}}
    assert capturado["atribucion_sugerida"] == "tienda" and capturado["cifrado_ok"] is True
    assert capturado["meli_configurado"] is False and capturado["estado_pixel"]["estado"] == "sin_pixel"
    assert capturado["meta_conectado"] is True
    assert llamadas_pixel == [True, True]   # ver_cliente y atribucion_sugerida: nunca a Graph
    assert capturado["pedidos_por_exp"] == {}
    assert "nombre" in capturado["columnas_csv"] and capturado["tipos_tienda"] == ("shopify", "woo", "meli")


def test_pedidos_por_experimento(app, base_temporal):
    import creative_flow
    import experimentos as ex
    import tiendas
    tid = tiendas.conectar("acme", "shopify", {"dominio": "d", "token": "t"})
    cf = creative_flow.crear("acme", [], [], [], "camina", 8, "alegre", "A")
    pieza = creative_flow.pieza_id_por_legado("acme", cf)
    eid = ex.crear("acme", "Uno", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP", atribucion="tienda")
    ex.agregar_pieza("acme", eid, pieza, "CO")
    ep_id = ex.piezas("acme", eid)[0]["id"]
    tiendas.guardar_pedidos("acme", tid, [
        {"fuente_id": "o1", "fecha": "2026-09-16T10:00:00", "total": 10.0, "moneda": "COP", "utm_content": str(ep_id)},
        {"fuente_id": "o2", "fecha": "2026-09-16T11:00:00", "total": 12.0, "moneda": "COP", "utm_content": str(ep_id)},
        {"fuente_id": "o3", "fecha": "2026-09-16T12:00:00", "total": 12.0, "moneda": "COP", "utm_content": None},
    ])
    assert tiendas.pedidos_por_experimento("acme") == {}
    for ped in tiendas.pedidos_sin_resolver("acme"):
        tiendas.resolver_pedido("acme", ped["id"], ep_id)
    assert tiendas.pedidos_por_experimento("acme") == {eid: 2}
    assert tiendas.pedidos_por_experimento("otro") == {}
    html = app["c"].get("/cliente/acme").data.decode()
    assert "ventas por tienda: 2 pedido(s)" in html and "atribución tienda" in html
