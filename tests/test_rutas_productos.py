"""Rutas de productos (viven en Catálogo › Productos) y Configuración › Tienda
/ Pixel (Bloque 5, Task 6): importar archivo/URL, marcar/archivar/vincular,
«crear experimento desde producto», subir fotos a un importado, conectar/
sincronizar/desconectar tiendas, OAuth de MercadoLibre, refrescar el Pixel y
el render de Catálogo y Configuración. Todo lo que sale a la red (conectores,
importador, Meta) o al worker (trabajos.encolar) va con fakes."""
import io
import os
import re

import pytest

from conectores import ErrorConector
from conectores.base import Conector
from tests.conftest import JPG_VALIDO
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
    assert r.status_code == 302 and r.headers["Location"].endswith("#catalogo")
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
    multipart (el MAX_CONTENT_LENGTH global es el de un video, 256 MB:
    personajes/marca suben videos; esta ruta tiene su propio tope)."""
    d = app["dashboard"]
    assert d.app.config.get("MAX_CONTENT_LENGTH") == d.MAX_BYTES_PETICION > 12 * 1024 * 1024
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
    assert r.status_code == 302 and r.headers["Location"].endswith("#catalogo")
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
    assert r.status_code == 302 and r.headers["Location"].endswith("#catalogo")
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
    queda deshabilitado y sale la barra con su job_id (una consulta a la cola).
    Desde la Tarea 12 la tarjeta de la fila vive en el fragmento del grid, no
    en la página."""
    import cola
    pid = _producto(nombre="Cojín Azul")
    pid_otro = _producto(nombre="Espejo redondo")
    cola.encolar("producto_vincular", {"cliente": "acme", "producto_id": pid}, cliente="acme",
                 job_id=f"acme__producto{pid}__vincular", max_intentos=1)
    # una terminada no cuenta
    tid = cola.encolar("producto_vincular", {"cliente": "acme", "producto_id": pid_otro}, cliente="acme",
                       job_id=f"acme__producto{pid_otro}__vincular", max_intentos=1)
    cola.terminar(tid, "listo")
    grid = app["c"].get("/cliente/acme/catalogo/grid?cat=producto").data.decode()
    assert f'id="trabajo-acme__producto{pid}__vincular"' in grid and "Creando activo…" in grid
    assert f"trabajo-acme__producto{pid_otro}__vincular" not in grid
    assert grid.count("Crear activo") == 1


def test_experimento_desde_producto_redirige_con_query(app):
    pid = _producto(nombre="Espejo redondo", url_compra="https://tienda.test/espejo")
    r = app["c"].post(f"/cliente/acme/productos/{pid}/experimento")
    assert r.status_code == 302
    loc = r.headers["Location"]
    assert "exp_nombre=Espejo+redondo" in loc and "exp_destino=https://tienda.test/espejo" in loc
    # «Crear experimento» lleva a «Nuevo experimento» (E2: exp_nuevo), donde está la galería con el paso 3.
    assert loc.startswith("/cliente/acme/experimentos/nuevo?")
    r = app["c"].post(f"/cliente/acme/productos/{_producto(cliente='otro')}/experimento")
    assert "exp_nombre" not in r.headers["Location"] and r.headers["Location"].endswith("#catalogo")


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

def _activo_con_foto(cliente, nombre, producto_id=None):
    """Activo de categoría producto CON una foto en disco (sin foto no
    aparece en listar())."""
    import catalogo_productos
    aid = catalogo_productos.crear(cliente, nombre, categoria="producto", producto_id=producto_id)
    carpeta = catalogo_productos.carpeta_de(cliente, aid, "producto")
    with open(os.path.join(carpeta, "a.jpg"), "wb") as f:
        f.write(b"\xff\xd8\xff\xe0fake-jpg")
    return aid


def test_render_catalogo_en_la_pagina_y_lo_demas_en_el_grid(app):
    """La página trae la pestaña, sus filtros y los formularios; las tarjetas
    y los importados sin fotos llegan por el fragmento del grid."""
    import tiendas
    pid_ok = _producto(nombre="Cojín Azul")
    _producto(nombre="Espejo redondo", en_prueba=True)
    tiendas.marcar_producto("acme", pid_ok, activo_catalogo_id="cojin_azul", en_prueba=True, prioridad=40)
    _activo_con_foto("acme", "Cojín Azul", "cojin_azul")
    r = app["c"].get("/cliente/acme")
    assert r.status_code == 200
    html = r.data.decode()
    assert 'data-tab="productos"' not in html and 'id="tab-productos"' not in html
    assert 'data-tab="catalogo"' in html and 'id="tab-catalogo"' in html
    pestana = html.split('id="tab-catalogo"', 1)[1].split('id="tab-settings"', 1)[0]
    assert "Traer productos de" in pestana and "Importar CSV/Excel" in pestana and "Importar desde URL" in pestana
    assert 'data-cat-grid="producto"' in pestana and 'data-cat-filtro="sin_fotos"' in pestana and 'data-cat-filtro="archivados"' in pestana
    assert 'id="catalogo-panel"' in pestana and 'id="nuevo-producto"' in pestana and 'data-n-cat="producto">1<' in pestana
    assert 'id="producto-cojin_azul"' not in pestana                    # las tarjetas no van en la página
    nuevo = pestana.split('id="nuevo-moneda"', 1)[1].split("</select>", 1)[0]
    assert 'value="COP" selected' in nuevo and 'value="USD"' in nuevo
    assert "Adonde llega el anuncio" in pestana
    grid = app["c"].get("/cliente/acme/catalogo/grid?cat=producto").data.decode()
    assert 'id="producto-cojin_azul"' in grid and "Espejo redondo" in grid and "Subir fotos" in grid
    tarjeta = grid.split('id="producto-cojin_azul"', 1)[1].split("</article>", 1)[0]
    assert "89.900 COP" in tarjeta and "en prueba" in tarjeta and "CSV/Excel" in tarjeta
    ficha = app["c"].get("/cliente/acme/catalogo/producto/cojin_azul/ficha").data.decode()
    assert 'href="https://tienda.test/cojin"' in ficha and "prioridad 40" in ficha and "Sincronizado de CSV/Excel" in ficha
    assert "Crear experimento" in ficha and f"/productos/{pid_ok}/experimento" in ficha
    assert 'name="en_prueba"' in ficha and 'name="url_compra"' in ficha and 'name="precio"' in ficha


def test_render_activo_manual_recibe_fila_y_muestra_precio(app):
    import tiendas
    c = app["c"]
    _crear_activo(c, precio="25000", moneda="COP", url_compra="wa.me/573001234567", prioridad="5")
    _activo_con_foto("acme", "Viejo")
    assert tiendas.por_activo("acme").get("viejo") is None
    assert c.get("/cliente/acme").status_code == 200
    fila_vieja = tiendas.por_activo("acme")["viejo"]
    assert fila_vieja["fuente"] == "manual" and fila_vieja["nombre"] == "Viejo"
    grid = c.get("/cliente/acme/catalogo/grid?cat=producto").data.decode()
    tarjeta = grid.split('id="producto-cojin_azul"', 1)[1].split("</article>", 1)[0]
    assert "25.000 COP" in tarjeta and "sin URL" not in tarjeta and 'data-n-sin_fotos="0"' in grid
    vieja = grid.split('id="producto-viejo"', 1)[1].split("</article>", 1)[0]
    assert "sin precio" in vieja and "sin URL" in vieja
    ficha = c.get("/cliente/acme/catalogo/producto/cojin_azul/ficha").data.decode()
    assert 'href="https://wa.me/573001234567"' in ficha and "prioridad 5" in ficha and "Sincronizado de" not in ficha
    c.get("/cliente/acme")
    assert len(tiendas.productos("acme", incluir_archivados=True)) == 2


def test_render_importado_archivado_solo_en_su_filtro(app):
    import tiendas
    pid = _producto(nombre="Lámpara")
    tiendas.marcar_producto("acme", pid, archivado=True)
    grid = app["c"].get("/cliente/acme/catalogo/grid?cat=producto").data.decode()
    assert "Lámpara" not in grid and 'data-n-archivados="1"' in grid
    grid = app["c"].get("/cliente/acme/catalogo/grid?cat=producto&filtro=archivados").data.decode()
    assert "Lámpara" in grid and 'data-archivado="1"' in grid and "Recuperar" in grid


def test_render_banner_sincronizando_no_choca_con_la_barra_de_configuracion(app, monkeypatch):
    """Config › Conexiones pinta su propia barra para el mismo job_id
    (id="trabajo-<job>"); el aviso «Sincronizando» de Catálogo necesita un id
    propio (id="cat-sync-<job>", fix ronda 1 hallazgo 2) o getElementById solo
    encuentra la primera y la otra barra se queda sin sondeo (0% sin texto)."""
    import tiendas
    d = app["dashboard"]
    tid = tiendas.conectar("acme", "shopify", {"dominio": "acme.myshopify.com", "token": "t"})
    job = d.tareas_tiendas.job_id_sync_productos("acme", tid)
    monkeypatch.setattr(d.trabajos, "en_curso", lambda jid: jid == job)
    html = app["c"].get("/cliente/acme").data.decode()
    assert html.count(f'id="cat-sync-{job}"') == 1
    assert html.count(f'id="trabajo-{job}"') == 1


# --- subir fotos a un importado -----------------------------------------------

def test_fotos_subir_crea_activo_y_enlaza(app):
    import catalogo_productos
    import tiendas
    pid = _producto(nombre="Espejo redondo", descripcion="marco dorado")
    r = app["c"].post(f"/cliente/acme/productos/{pid}/fotos",
                      data={"imagenes": [_foto("a.jpg"), _foto("b.png")]}, content_type="multipart/form-data")
    assert r.status_code == 302 and r.headers["Location"].endswith("#catalogo?ficha=producto:espejo_redondo")
    p = tiendas.producto("acme", pid)
    assert p["activo_catalogo_id"] == "espejo_redondo"
    activo = catalogo_productos.encontrar("acme", "espejo_redondo", categoria="producto")
    assert activo and activo["nombre"] == "Espejo redondo" and activo["descripcion"] == "marco dorado"
    assert sorted(activo["imagenes"]) == ["a.jpg", "b.png"]
    assert any("2 foto(s)" in m for m in _flashes(app["c"]))
    # ya no aparece como fila sin fotos (tarjeta "producto-fila-..."); su
    # tarjeta de activo muestra lo comercial de la fila importada.
    grid = app["c"].get("/cliente/acme/catalogo/grid?cat=producto").data.decode()
    assert 'id="producto-fila-' not in grid
    tarjeta = grid.split('id="producto-espejo_redondo"', 1)[1].split("</article>", 1)[0]
    assert "89.900 COP" in tarjeta and "CSV/Excel" in tarjeta
    assert len(tiendas.productos("acme", incluir_archivados=True)) == 1


def test_fotos_subir_desambigua_id_ocupado(app):
    """Otro activo ya usa el id derivado del nombre: se crea `-2`, no se le
    pisan las fotos al primero."""
    import catalogo_productos
    import tiendas
    _activo_con_foto("acme", "Espejo redondo")
    pid = _producto(nombre="Espejo redondo")
    app["c"].post(f"/cliente/acme/productos/{pid}/fotos",
                  data={"imagenes": _foto()}, content_type="multipart/form-data")
    assert tiendas.producto("acme", pid)["activo_catalogo_id"] == "espejo_redondo-2"
    assert catalogo_productos.encontrar("acme", "espejo_redondo", categoria="producto")["imagenes"] == ["a.jpg"]


def test_fotos_subir_con_activo_existente_agrega_fotos_sin_duplicar(app):
    """Doble envío o página vieja: si la fila ya apunta a un activo que
    existe, las fotos van a ese activo y no se crea `-2`."""
    import catalogo_productos
    import tiendas
    pid = _producto(nombre="Espejo redondo")
    c = app["c"]
    c.post(f"/cliente/acme/productos/{pid}/fotos", data={"imagenes": _foto("a.jpg")}, content_type="multipart/form-data")
    c.post(f"/cliente/acme/productos/{pid}/fotos", data={"imagenes": _foto("b.jpg")}, content_type="multipart/form-data")
    assert tiendas.producto("acme", pid)["activo_catalogo_id"] == "espejo_redondo"
    assert not catalogo_productos.existe("acme", "espejo_redondo-2", "producto")
    assert sorted(catalogo_productos.encontrar("acme", "espejo_redondo", categoria="producto")["imagenes"]) == ["a.jpg", "b.jpg"]
    assert any("1 foto(s) añadida(s)" in m for m in _flashes(c))


def test_fotos_subir_valida(app):
    import catalogo_productos
    import tiendas
    pid = _producto(nombre="Taza")
    c = app["c"]
    r = c.post(f"/cliente/acme/productos/{pid}/fotos", data={}, content_type="multipart/form-data")
    assert r.status_code == 302 and any("ninguna foto" in m for m in _flashes(c))
    c.post(f"/cliente/acme/productos/{pid}/fotos",
           data={"imagenes": (io.BytesIO(b"x"), "malo.exe")}, content_type="multipart/form-data")
    assert tiendas.producto("acme", pid)["activo_catalogo_id"] is None
    assert not catalogo_productos.existe("acme", "taza", "producto")
    assert any("formato soportado" in m for m in _flashes(c))
    # cross-tenant
    r = c.post(f"/cliente/acme/productos/{_producto(cliente='otro')}/fotos",
               data={"imagenes": _foto()}, content_type="multipart/form-data")
    assert r.status_code == 302 and any("No encontré" in m for m in _flashes(c))


def test_render_productos_confirm_y_url_seguros(app):
    """El nombre con apóstrofo va en data-nombre (escapado como atributo, en
    la tarjeta del grid), no dentro de un literal JS — el mensaje se arma en
    el script de _tab_catalogo.html a partir de data-nombre, nunca con el
    nombre embebido; y una url_compra que no es http(s) nunca se vuelve href,
    ni en la tarjeta sin activo (el grid no la muestra) ni en el campo de la
    ficha de un activo (que sí la muestra, como valor, nunca como enlace)."""
    import tiendas
    _producto(nombre="Cojín d'Or")
    pid_raro = _producto(nombre="Raro", url_compra="javascript:alert(1)")
    tiendas.marcar_producto("acme", pid_raro, activo_catalogo_id="raro")
    _activo_con_foto("acme", "Raro", "raro")
    html = app["c"].get("/cliente/acme").data.decode()
    assert "confirm('¿Archivar «Cojín" not in html and "confirm(\"¿Archivar" not in html
    grid = app["c"].get("/cliente/acme/catalogo/grid?cat=producto").data.decode()
    assert 'data-nombre="Cojín d&#39;Or"' in grid
    assert 'href="javascript:' not in grid
    # El fragmento del grid no trae <script>: el nombre nunca puede acabar
    # dentro de un confirm(), esté o no escapado bien (fix ronda 1 hallazgo 3
    # — la comprobación en /cliente/acme ya no dice nada: ahí no hay tarjetas).
    assert "confirm(" not in grid
    ficha = app["c"].get("/cliente/acme/catalogo/producto/raro/ficha").data.decode()
    assert 'href="javascript:' not in ficha and "javascript:alert(1)" in ficha


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
    # El selector de atribución vive en «Nuevo experimento» (E2: su propia ruta, ya no la pestaña).
    assert "(sugerida)" in app["c"].get("/cliente/acme/experimentos/nuevo").data.decode()
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
    # Sin Meta no se va a Graph ni se calcula la atribución del fragmento.
    assert llamadas == [] and "sin conexión" in html
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
    assert llamadas == [True]           # ver_cliente: solo caché, sin el contexto del fragmento
    assert "sin comprobar" in html and "Comprobar Pixel" in html
    assert "/cliente/acme/config/pixel/refrescar" in html
    assert "Volver a comprobar" not in html and "sin conexión" not in html
    # La ayuda de la atribución sugerida («pulsa «Comprobar Pixel» en Configuración») va en «Nuevo experimento», que
    # tampoco va nunca a Graph: solo lee el caché del Pixel.
    llamadas.clear()
    nuevo = app["c"].get("/cliente/acme/experimentos/nuevo").data.decode()
    assert "pulsa «Comprobar Pixel»" in nuevo and llamadas and all(llamadas)


def test_render_meli_configurado_sin_cifrado_avisa(app, monkeypatch):
    monkeypatch.setenv("MELI_APP_ID", "123")
    monkeypatch.delenv("FLASK_SECRET_KEY")
    html = app["c"].get("/cliente/acme").data.decode()
    inicio = html.index('data-tienda-panel="meli"')
    panel = html[inicio:html.index("</div>", inicio)]
    assert "FLASK_SECRET_KEY" in panel and "MELI_APP_ID</code> y" not in panel
    assert "/tienda/meli/iniciar" not in panel


def test_ver_cliente_contexto_productos(app, base_temporal, monkeypatch):
    """Desde la Tarea 12 `productos_tienda` ya no llega al contexto de la
    página: activo_ok y n_experimentos por producto se comprueban aquí mismo
    a través de la galería y la ficha (siguen siendo _productos_tienda_contexto
    por debajo, dashboard.py:2861-2863 — el huérfano con activo_catalogo_id
    colgado se ve como tarjeta "fila", Cojín Azul cuenta sus 2 experimentos).
    Lo que sigue en el contexto de ver_cliente (trabajos_prod, cifrado,
    Pixel solo-caché) se comprueba por el contexto que llega a la plantilla.
    La atribución sugerida se comprueba en Nuevo experimento (PND-137)."""
    import creative_flow
    import experimentos as ex
    import tiendas
    d = app["dashboard"]
    c = app["c"]
    pid = _producto(nombre="Cojín Azul")
    tiendas.marcar_producto("acme", pid, activo_catalogo_id="cojin_azul")
    _activo_con_foto("acme", "Cojín Azul", "cojin_azul")  # con foto: se ve en la galería y en la ficha
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
    # activo_ok=False (huérfano, sin carpeta real en el catálogo): tarjeta
    # "fila", no la de un activo. activo_ok=True + 2 experimentos: la ficha
    # de Cojín Azul los cuenta (misma _experimentos_por_activo por debajo).
    grid = c.get("/cliente/acme/catalogo/grid?cat=producto").data.decode()
    assert f'id="producto-fila-{pid_sin}"' in grid and 'id="producto-cojin_azul"' in grid
    ficha = c.get("/cliente/acme/catalogo/producto/cojin_azul/ficha").data.decode()
    assert "Experimentos: 2" in ficha
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
    assert capturado["trabajos_prod"] == {"importar": {"job_id": "acme__importar_url"},
                                          "tiendas": {tiendas.listar("acme")[0]["id"]: {"job_id": job_sync}},
                                          "vincular": {}, "pedidos": {}}
    assert "atribucion_sugerida" not in capturado and capturado["cifrado_ok"] is True
    assert capturado["meli_configurado"] is False and capturado["estado_pixel"]["estado"] == "sin_pixel"
    assert capturado["meta_conectado"] is True
    assert llamadas_pixel == [True]        # ver_cliente: nunca a Graph
    assert "pedidos_por_exp" not in capturado
    assert "nombre" in capturado["columnas_csv"] and capturado["tipos_tienda"] == ("shopify_publico", "shopify", "woo", "meli")
    capturado.clear()
    llamadas_pixel.clear()
    assert c.get("/cliente/acme/experimentos/nuevo").status_code == 200
    assert capturado["atribucion_sugerida"] == "tienda"
    assert capturado["pedidos_por_exp"] == {}
    assert llamadas_pixel and all(llamadas_pixel)  # Nuevo también lee solo el caché.


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
    from tests.test_rutas_experimentos import _resultados
    html = _resultados(app["c"], exp=eid)   # E2: la gestión del experimento llega en el fragmento de resultados
    assert "ventas por tienda: 2 pedido(s)" in html and "atribución tienda" in html


# --- Catálogo: activo de categoría producto ⇄ fila producto (manual) --------

def _foto(nombre="a.jpg"):
    return (io.BytesIO(JPG_VALIDO), nombre)


def _crear_activo(c, nombre="Cojín Azul", categoria="producto", **extra):
    data = {"nombre": nombre, "descripcion": "suave", "categoria": categoria, "volver": "catalogo",
            "imagenes": _foto()}
    data.update(extra)
    return c.post("/cliente/acme/productos/crear", data=data, content_type="multipart/form-data")


def _fila_por_activo(activo_id, cliente="acme"):
    import tiendas
    return tiendas.por_activo(cliente).get(activo_id)


def test_crear_producto_con_precio_crea_fila_manual(app):
    import tiendas
    c = app["c"]
    r = _crear_activo(c, precio="89900,50", moneda="cop", url_compra="https://tienda.test/cojin",
                      en_prueba="on", prioridad="7")
    assert r.status_code == 302
    p = _fila_por_activo("cojin_azul")
    assert p is not None and p["fuente"] == "manual" and p["fuente_id"] == "cojin_azul"
    assert p["nombre"] == "Cojín Azul" and p["descripcion"] == "suave"
    assert p["precio"] == 89900.5 and p["moneda"] == "COP"
    assert p["url_compra"] == "https://tienda.test/cojin" and p["en_prueba"] is True and p["prioridad"] == 7
    assert len(tiendas.productos("acme", incluir_archivados=True)) == 1


def test_crear_producto_sin_campos_comerciales_usa_moneda_de_meta(app):
    _crear_activo(app["c"])
    p = _fila_por_activo("cojin_azul")
    assert p is not None and p["precio"] is None and p["moneda"] == "COP" and p["url_compra"] is None
    assert p["en_prueba"] is False and p["prioridad"] == 0


def test_crear_producto_sin_meta_usa_cop(app, monkeypatch):
    monkeypatch.setattr(app["dashboard"].meta_conexion, "cargar", lambda c: None)
    _crear_activo(app["c"], moneda="")
    assert _fila_por_activo("cojin_azul")["moneda"] == "COP"


def test_crear_producto_normaliza_wa_me(app):
    _crear_activo(app["c"], url_compra="wa.me/573001234567")
    assert _fila_por_activo("cojin_azul")["url_compra"] == "https://wa.me/573001234567"


def test_crear_producto_url_invalida_avisa_y_crea_igual(app):
    c = app["c"]
    _crear_activo(c, url_compra="tienda.test/cojin", precio="10")
    p = _fila_por_activo("cojin_azul")
    assert p is not None and p["url_compra"] is None and p["precio"] == 10.0
    assert any("URL de compra" in m for m in _flashes(c))


def test_crear_producto_precio_invalido_avisa_y_crea_igual(app):
    c = app["c"]
    _crear_activo(c, precio="abc", prioridad="500")
    p = _fila_por_activo("cojin_azul")
    assert p is not None and p["precio"] is None and p["prioridad"] == 0
    assert any("precio" in m.lower() or "prioridad" in m.lower() for m in _flashes(c))


def test_crear_personaje_no_crea_fila(app):
    import tiendas
    _crear_activo(app["c"], nombre="Laura", categoria="personaje", precio="10")
    assert tiendas.productos("acme", incluir_archivados=True) == []


def test_actualizar_producto_cambia_precio_y_nombre(app):
    c = app["c"]
    _crear_activo(c, precio="10", moneda="COP")
    pid = _fila_por_activo("cojin_azul")["id"]
    r = c.post("/cliente/acme/productos/cojin_azul/actualizar",
               data={"nombre": "Cojín Rojo", "descripcion": "nuevo", "categoria": "producto",
                     "precio": "25,5", "moneda": "usd", "url_compra": "wa.me/57300", "prioridad": "3"})
    assert r.status_code == 302
    p = _fila_por_activo("cojin_azul")
    assert p["id"] == pid and p["nombre"] == "Cojín Rojo" and p["descripcion"] == "nuevo"
    assert p["precio"] == 25.5 and p["moneda"] == "USD" and p["url_compra"] == "https://wa.me/57300"
    assert p["en_prueba"] is False and p["prioridad"] == 3


def test_actualizar_producto_crea_fila_si_no_existe(app):
    """Un activo anterior a esta versión no tiene fila: editarlo la crea."""
    import catalogo_productos
    c = app["c"]
    catalogo_productos.crear("acme", "Viejo", "d")
    assert _fila_por_activo("viejo") is None
    c.post("/cliente/acme/productos/viejo/actualizar",
           data={"nombre": "Viejo", "categoria": "producto", "precio": "5", "en_prueba": "on"})
    p = _fila_por_activo("viejo")
    assert p is not None and p["fuente"] == "manual" and p["precio"] == 5.0 and p["en_prueba"] is True


def test_actualizar_producto_url_invalida_avisa_y_conserva(app):
    c = app["c"]
    _crear_activo(c, url_compra="https://tienda.test/a")
    c.post("/cliente/acme/productos/cojin_azul/actualizar",
           data={"nombre": "Cojín Azul", "categoria": "producto", "url_compra": "ftp://nada"})
    assert _fila_por_activo("cojin_azul")["url_compra"] == "https://tienda.test/a"
    assert any("URL de compra" in m for m in _flashes(c))


def test_actualizar_personaje_no_crea_fila(app):
    import tiendas
    c = app["c"]
    _crear_activo(c, nombre="Laura", categoria="personaje")
    c.post("/cliente/acme/productos/laura/actualizar",
           data={"nombre": "Laura", "categoria": "personaje", "precio": "5"})
    assert tiendas.productos("acme", incluir_archivados=True) == []


def test_eliminar_producto_archiva_la_fila(app):
    import tiendas
    c = app["c"]
    _crear_activo(c, precio="10")
    pid = _fila_por_activo("cojin_azul")["id"]
    r = c.post("/cliente/acme/productos/cojin_azul/eliminar", data={"categoria": "producto"})
    assert r.status_code == 302
    p = tiendas.producto("acme", pid)
    assert p["archivado"] is True and p["extra"].get("archivado_por") == "manual"
    assert p["activo_catalogo_id"] == "cojin_azul"
    assert tiendas.productos("acme") == []


def test_eliminar_producto_sin_fila_no_falla(app):
    import catalogo_productos
    import tiendas
    c = app["c"]
    catalogo_productos.crear("acme", "Viejo", "d")
    r = c.post("/cliente/acme/productos/viejo/eliminar", data={"categoria": "producto"})
    assert r.status_code == 302 and tiendas.productos("acme", incluir_archivados=True) == []


def test_eliminar_personaje_no_toca_filas(app):
    import tiendas
    c = app["c"]
    _crear_activo(c, precio="10")
    _crear_activo(c, nombre="Laura", categoria="personaje")
    c.post("/cliente/acme/productos/laura/eliminar", data={"categoria": "personaje"})
    assert len(tiendas.productos("acme")) == 1


def test_actualizar_producto_guarda_la_sofisticacion_del_mercado(app):
    """Doctrina, bloque 2: «Cuántas promesas parecidas vio ya tu cliente»."""
    c = app["c"]
    _crear_activo(c, sofisticacion="3")
    assert _fila_por_activo("cojin_azul")["extra"]["sofisticacion"] == 3
    # un formulario sin el campo no borra lo elegido
    c.post("/cliente/acme/productos/cojin_azul/actualizar", data={"nombre": "Cojín Azul", "categoria": "producto"})
    assert _fila_por_activo("cojin_azul")["extra"]["sofisticacion"] == 3
    # «Que Claude lo decida» (vacío) o un valor raro lo borra
    c.post("/cliente/acme/productos/cojin_azul/actualizar",
           data={"nombre": "Cojín Azul", "categoria": "producto", "sofisticacion": ""})
    assert "sofisticacion" not in _fila_por_activo("cojin_azul")["extra"]
    c.post("/cliente/acme/productos/cojin_azul/actualizar",
           data={"nombre": "Cojín Azul", "categoria": "producto", "sofisticacion": "9"})
    assert "sofisticacion" not in _fila_por_activo("cojin_azul")["extra"]


def test_catalogo_muestra_el_selector_de_sofisticacion(app):
    """Desde la Tarea 12 la ficha es un fragmento propio (catalogo_ficha)."""
    c = app["c"]
    _crear_activo(c, sofisticacion="4")
    ficha = c.get("/cliente/acme/catalogo/producto/cojin_azul/ficha").data.decode()
    assert "Cuántas promesas parecidas vio ya tu cliente" in ficha
    assert 'value="4" selected' in ficha and "Que Claude lo decida" in ficha


def test_pruebas_del_producto_desde_catalogo(app):
    """Doctrina, bloque 2 (§5.4): agregar y borrar pruebas en la ficha del
    producto (fragmento propio desde la Tarea 12)."""
    c = app["c"]
    _crear_activo(c)
    pid = _fila_por_activo("cojin_azul")["id"]
    r = c.post(f"/cliente/acme/productos/{pid}/pruebas", data={"texto": "Relleno de 1.200 g", "fuente": "ficha"})
    assert r.status_code == 302 and r.headers["Location"].endswith("#catalogo?ficha=producto:cojin_azul")
    prueba = _fila_por_activo("cojin_azul")["extra"]["pruebas"][0]
    assert prueba["texto"] == "Relleno de 1.200 g"
    ficha = c.get("/cliente/acme/catalogo/producto/cojin_azul/ficha").data.decode()
    assert "Pruebas del producto" in ficha and "Relleno de 1.200 g" in ficha
    c.post(f"/cliente/acme/productos/{pid}/pruebas", data={"texto": "", "fuente": "ficha"})
    assert any("Escribe la prueba" in m for m in _flashes(c))
    c.post(f"/cliente/acme/productos/{pid}/pruebas/{prueba['id']}/borrar")
    assert "pruebas" not in _fila_por_activo("cojin_azul")["extra"]
    assert c.post("/cliente/acme/productos/9999/pruebas", data={"texto": "x", "fuente": "ficha"}).status_code == 302


def test_lo_que_claude_necesita_en_catalogo(app, monkeypatch):
    """Doctrina, bloque 2 (§5.3–5.4): actualizar encola con precio (solo si hay
    faltantes), responder deja una prueba, «No aplica» cierra el pedido. La
    ficha es un fragmento propio desde la Tarea 12."""
    from doctrina import pedidos, producto as dp
    c = app["c"]
    _crear_activo(c)
    pid = _fila_por_activo("cojin_azul")["id"]
    monkeypatch.setattr(pedidos, "faltantes_del_producto", lambda cliente, fila: [])
    c.post(f"/cliente/acme/productos/{pid}/pedidos/actualizar")
    assert app["encolados"] == [] and any("no ha pedido nada" in m for m in _flashes(c))
    monkeypatch.setattr(pedidos, "faltantes_del_producto", lambda cliente, fila: ["faltan comentarios"])
    c.post(f"/cliente/acme/productos/{pid}/pedidos/actualizar")
    t = app["encolados"][-1]
    assert t["tipo"] == "producto_pedidos" and t["payload"] == {"cliente": "acme", "producto_id": pid} and t["max_intentos"] == 1
    k1, k2 = [p["id"] for p in dp.reemplazar_abiertos("acme", pid, [{"texto": "Pega un comentario", "para_que": "prueba"},
                                                                     {"texto": "Dinos la garantía", "para_que": "cifra"}])]
    ficha = c.get("/cliente/acme/catalogo/producto/cojin_azul/ficha").data.decode()
    # El badge «N pedidos de Claude» era del resumen de _catalogo_lista.html
    # (Tarea 11 ya no lo trae en la tarjeta ni en la ficha nueva); el contenido
    # sigue: los dos pedidos abiertos se listan enteros dentro de la sección.
    assert "Lo que Claude necesita" in ficha and "Pega un comentario" in ficha and "Dinos la garantía" in ficha
    assert "Actualizar lo que Claude necesita (US$ 0,01 aprox.)" in ficha
    c.post(f"/cliente/acme/productos/{pid}/pedidos/{k1}/responder", data={"texto": "Súper suaves", "fuente": "comentarios"})
    assert _fila_por_activo("cojin_azul")["extra"]["pruebas"][0]["pedido_id"] == k1
    c.post(f"/cliente/acme/productos/{pid}/pedidos/{k2}/descartar")
    assert [p["estado"] for p in dp.pedidos(_fila_por_activo("cojin_azul"))] == ["respondido", "descartado"]
