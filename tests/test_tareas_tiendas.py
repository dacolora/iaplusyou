"""Tareas del worker de tiendas (`tareas/tiendas.py`): sync de productos y
pedidos con un conector falso, importación de catálogo y las periódicas."""
import os

import pytest

from conectores import ErrorConector
from conectores.base import Conector, normalizar_pedido, normalizar_producto

PAISES = [{"pais": "CO", "idioma": "es", "presupuesto_dia": 20000.0}]


def _prod(fuente_id, nombre, fotos=("https://cdn.test/a.png",)):
    return normalizar_producto({"fuente_id": fuente_id, "nombre": nombre, "precio": 10, "moneda": "USD",
                                "url_compra": f"https://t/{fuente_id}", "fotos": list(fotos)})


class Falso(Conector):
    """Conector de prueba: lo que devuelve se fija por clase entre tests."""
    tipo = "shopify"
    tiene_pedidos = True
    soporta_utm = True
    productos = []
    pedidos = []
    error = None
    instancias = []
    nuevas_credenciales = None

    def __init__(self, credenciales, **kw):
        super().__init__(credenciales)
        self.kw = kw
        self.credenciales_actualizadas = None
        Falso.instancias.append(self)

    def _falla(self):
        if Falso.error:
            raise Falso.error

    def listar_productos(self):
        if Falso.nuevas_credenciales:
            self.credenciales_actualizadas = dict(Falso.nuevas_credenciales)
        self._falla()
        return list(Falso.productos)

    def pedidos_desde(self, fecha_iso):
        self.desde = fecha_iso
        self._falla()
        return list(Falso.pedidos)


@pytest.fixture()
def entorno(base_temporal, tmp_path, monkeypatch):
    import catalogo_productos
    import conectores
    import importador
    import notificaciones
    import tareas
    monkeypatch.setenv("FLASK_SECRET_KEY", "clave-de-prueba-larga-1234567890")
    monkeypatch.setattr(catalogo_productos, "BASE_DIR", str(tmp_path))
    Falso.productos, Falso.pedidos, Falso.error, Falso.instancias, Falso.nuevas_credenciales = [], [], None, [], None
    monkeypatch.setattr(conectores, "por_tipo", lambda tipo: Falso)

    class _R:
        status_code = 200
        headers = {"Content-Type": "image/png"}

        def iter_content(self, chunk_size=65536):
            yield b"\x89PNG" + b"\x00" * 16

        def close(self):
            pass
    monkeypatch.setattr(importador.requests, "get", lambda *a, **k: _R())
    monkeypatch.setattr(importador, "host_permitido", lambda u: True)
    monkeypatch.setattr(importador.generador_prompts, "regla_fidelidad", lambda *a: "Regla.")
    avisos = []
    monkeypatch.setattr(notificaciones, "avisar", lambda c, tipo, asunto, cuerpo: avisos.append((c, tipo, asunto, cuerpo)))
    tareas.cargar_todas()
    return {"avisos": avisos, "db": base_temporal}


def _tienda(cliente="acme", tipo="shopify", creds=None):
    import tiendas
    return tiendas.conectar(cliente, tipo, creds or {"token": "t1", "dominio": "acme.myshopify.com"},
                            nombre="Acme", dominio="acme.myshopify.com")


def test_registro_job_ids_y_periodicas():
    import tareas
    import worker
    import tareas.tiendas as tt
    tareas.cargar_todas()
    for tipo in ("tienda_sync_productos", "tienda_sync_pedidos", "catalogo_importar",
                 "tienda_sync_productos_todas", "tienda_sync_pedidos_todas"):
        assert tipo in tareas.REGISTRO
    assert tt.job_id_sync_productos("acme", 3) == "acme__tienda3__productos"
    assert tt.job_id_sync_pedidos("acme", 3) == "acme__tienda3__pedidos"
    assert tt.job_id_importar_archivo("acme") == "acme__importar_archivo"
    assert tt.job_id_importar_url("acme") == "acme__importar_url"
    assert ("tienda_sync_productos_todas", 21600) in worker.PERIODICAS
    assert ("tienda_sync_pedidos_todas", 7200) in worker.PERIODICAS
    assert [e[0] for e in tt.ETAPAS_IMPORTAR] == ["Leyendo", "Guardando productos", "Creando activos"]
    assert "tienda" in __import__("notificaciones").TIPOS


def test_sync_productos_importa_archiva_y_marca_sync(entorno):
    import tareas
    import tiendas
    tid = _tienda()
    tiendas.upsert_producto("acme", "shopify", "viejo", {"nombre": "Viejo"})
    Falso.productos = [_prod("p1", "Cojín Azul"), _prod("p2", "Tenis Runner")]
    msg = tareas.REGISTRO["tienda_sync_productos"]({"payload": {"cliente": "acme", "tienda_id": tid},
                                                   "job_id": "acme__tienda1__productos"})
    assert "2 producto(s) nuevo(s)" in msg and "1 archivado(s)" in msg
    prods = {p["fuente_id"]: p for p in tiendas.productos("acme", incluir_archivados=True)}
    assert prods["viejo"]["archivado"] is True
    assert prods["p1"]["archivado"] is False and prods["p1"]["activo_catalogo_id"] == "cojin_azul"
    assert prods["p2"]["activo_catalogo_id"] == "tenis_runner"
    t = tiendas.obtener("acme", tid)
    assert t["estado"] == "conectada" and t["error"] is None and t["ultima_sync_productos"]
    assert Falso.instancias[-1].credenciales["token"] == "t1"
    assert entorno["avisos"] == []


def test_sync_productos_meli_persiste_credenciales_renovadas(entorno):
    import tareas
    import tiendas
    tid = _tienda(tipo="meli", creds={"access_token": "a1", "refresh_token": "r1", "user_id": "7"})
    Falso.productos = [_prod("m1", "Manta")]
    Falso.nuevas_credenciales = {"access_token": "a2", "refresh_token": "r2", "user_id": "7", "expira_en": "2030-01-01T00:00:00"}
    tareas.REGISTRO["tienda_sync_productos"]({"payload": {"cliente": "acme", "tienda_id": tid}})
    assert tiendas.credenciales("acme", tid)["refresh_token"] == "r2"
    assert Falso.instancias[-1].kw == {"cargar_descripciones": True}   # primera importación
    t = tiendas.obtener("acme", tid)
    assert t["nombre"] == "Acme" and t["estado"] == "conectada"
    # segunda vez: ya hay productos de esa fuente, no se piden descripciones
    Falso.nuevas_credenciales = None
    tareas.REGISTRO["tienda_sync_productos"]({"payload": {"cliente": "acme", "tienda_id": tid}})
    assert Falso.instancias[-1].kw == {"cargar_descripciones": False}


def test_sync_productos_error_conector_marca_rota_y_avisa(entorno):
    import tareas
    import tiendas
    tid = _tienda()
    Falso.error = ErrorConector("Shopify rechazó el token. Vuelve a conectar la tienda.")
    Falso.nuevas_credenciales = {"token": "renovado"}
    with pytest.raises(ErrorConector) as ex:
        tareas.REGISTRO["tienda_sync_productos"]({"payload": {"cliente": "acme", "tienda_id": tid},
                                                 "intentos": 3, "max_intentos": 3})
    assert "rechazó el token" in str(ex.value)
    t = tiendas.obtener("acme", tid)
    assert t["estado"] == "rota" and "rechazó el token" in t["error"] and t["ultima_sync_productos"] is None
    assert len(entorno["avisos"]) == 1
    cliente, tipo, asunto, cuerpo = entorno["avisos"][0]
    assert cliente == "acme" and tipo == "tienda" and "Acme" in asunto and "rechazó el token" in cuerpo
    # las credenciales renovadas se guardaron aunque la sync fallara después
    assert tiendas.credenciales("acme", tid) == {"token": "renovado"}


def test_error_en_intento_intermedio_no_avisa_todavia(entorno):
    import tareas
    import tiendas
    tid = _tienda()
    Falso.error = ErrorConector("Se cayó la API.")
    with pytest.raises(ErrorConector):
        tareas.REGISTRO["tienda_sync_productos"]({"payload": {"cliente": "acme", "tienda_id": tid},
                                                 "intentos": 1, "max_intentos": 3})
    assert tiendas.obtener("acme", tid)["estado"] == "rota" and entorno["avisos"] == []
    # se recupera sola en el siguiente intento
    Falso.error = None
    Falso.productos = [_prod("p1", "Cojín")]
    tareas.REGISTRO["tienda_sync_productos"]({"payload": {"cliente": "acme", "tienda_id": tid}})
    t = tiendas.obtener("acme", tid)
    assert t["estado"] == "conectada" and t["error"] is None


def test_credenciales_ilegibles_marcan_rota(entorno, monkeypatch):
    import cifrado
    import tareas
    import tiendas
    tid = _tienda()

    def _rompe(*a, **k):
        raise cifrado.ErrorCifrado("¿cambió FLASK_SECRET_KEY?")
    monkeypatch.setattr(tiendas, "credenciales", _rompe)
    with pytest.raises(ErrorConector):
        tareas.REGISTRO["tienda_sync_productos"]({"payload": {"cliente": "acme", "tienda_id": tid}})
    assert "FLASK_SECRET_KEY" in tiendas.obtener("acme", tid)["error"]


def test_valueerror_al_listar_productos_no_marca_rota(entorno):
    """Un ValueError propio del conector (p. ej. un parseo raro) al listar no
    es un problema de la tienda: sale como error de la tarea tal cual, sin
    tocar `estado` ni avisar al cliente."""
    import tareas
    import tiendas
    tid = _tienda()
    Falso.error = ValueError("no se pudo parsear el precio")
    with pytest.raises(ValueError):
        tareas.REGISTRO["tienda_sync_productos"]({"payload": {"cliente": "acme", "tienda_id": tid},
                                                 "intentos": 3, "max_intentos": 3})
    assert tiendas.obtener("acme", tid)["estado"] == "conectada"
    assert entorno["avisos"] == []


def test_valueerror_al_listar_pedidos_no_marca_rota(entorno):
    import tareas
    import tiendas
    tid = _tienda()
    Falso.error = ValueError("no se pudo parsear la fecha")
    with pytest.raises(ValueError):
        tareas.REGISTRO["tienda_sync_pedidos"]({"payload": {"cliente": "acme", "tienda_id": tid},
                                              "intentos": 3, "max_intentos": 3})
    assert tiendas.obtener("acme", tid)["estado"] == "conectada"
    assert entorno["avisos"] == []


def test_sync_tienda_inexistente(entorno):
    import tareas
    assert "no existe" in tareas.REGISTRO["tienda_sync_productos"]({"payload": {"cliente": "acme", "tienda_id": 99}})
    assert "no existe" in tareas.REGISTRO["tienda_sync_pedidos"]({"payload": {"cliente": "acme", "tienda_id": 99}})


def test_sync_pedidos_guarda_y_resuelve_atribucion(entorno):
    """La sync liga los pedidos con utm_content=<experimento_pieza.id>
    (atribucion real, sin stub) y deja sin resolver los que traen un utm
    que no es un id."""
    import experimentos as ex
    import tareas
    import tiendas
    from tests.test_experimentos_db import _pieza
    tid = _tienda()
    pieza = _pieza(entorno["db"])
    eid = ex.crear("acme", "Cojín", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP", atribucion="tienda")
    ep_id = ex.agregar_pieza("acme", eid, pieza, "CO")
    Falso.pedidos = [normalizar_pedido({"fuente_id": "o1", "fecha": "2026-09-15T10:00:00Z", "total": 50,
                                        "moneda": "USD", "utm_content": str(ep_id)}),
                     normalizar_pedido({"fuente_id": "o2", "fecha": "2026-09-15T11:00:00Z", "total": 5,
                                        "moneda": "USD", "utm_content": "ep_1"})]
    msg = tareas.REGISTRO["tienda_sync_pedidos"]({"payload": {"cliente": "acme", "tienda_id": tid}})
    assert "2 pedido(s)" in msg and "2 nuevo(s)" in msg and "1 atribuido(s)" in msg
    pendientes = tiendas.pedidos_sin_resolver("acme")
    assert [p["fuente_id"] for p in pendientes] == ["o2"]
    assert tiendas.ventas_por_pieza("acme", ep_id, "2026-01-01T00:00:00") == {"compras": 1, "ingresos": 50.0, "monedas": ["USD"]}
    t = tiendas.obtener("acme", tid)
    assert t["ultima_sync_pedidos"] and t["estado"] == "conectada"
    # sin ultima_sync: 30 días atrás; con ella: un día de solape
    primera = Falso.instancias[0].desde
    assert primera < t["ultima_sync_pedidos"]
    msg = tareas.REGISTRO["tienda_sync_pedidos"]({"payload": {"cliente": "acme", "tienda_id": tid}})
    assert "0 nuevo(s)" in msg and "0 atribuido(s)" in msg   # resync: nada nuevo, o1 sigue ligado
    assert Falso.instancias[-1].desde < t["ultima_sync_pedidos"] and Falso.instancias[-1].desde > primera


def test_sync_pedidos_sin_utm_no_atribuye(entorno):
    import tareas
    import tiendas
    tid = _tienda()
    Falso.pedidos = [normalizar_pedido({"fuente_id": "o1", "fecha": "2026-09-15", "total": 5})]
    msg = tareas.REGISTRO["tienda_sync_pedidos"]({"payload": {"cliente": "acme", "tienda_id": tid}})
    assert "1 nuevo(s)" in msg and "0 atribuido(s)" in msg
    assert tiendas.pedidos_sin_resolver("acme") == []
    assert tiendas.obtener("acme", tid)["ultima_sync_pedidos"]


def test_sync_pedidos_error_marca_rota(entorno):
    import tareas
    import tiendas
    tid = _tienda()
    Falso.error = ErrorConector("Sin permiso read_orders.")
    with pytest.raises(ErrorConector):
        tareas.REGISTRO["tienda_sync_pedidos"]({"payload": {"cliente": "acme", "tienda_id": tid}})
    t = tiendas.obtener("acme", tid)
    assert t["estado"] == "rota" and "read_orders" in t["error"] and t["ultima_sync_pedidos"] is None
    assert entorno["avisos"][0][1] == "tienda"


def test_sync_pedidos_tienda_sin_pedidos(entorno, monkeypatch):
    import tareas
    tid = _tienda()
    monkeypatch.setattr(Falso, "tiene_pedidos", False)
    msg = tareas.REGISTRO["tienda_sync_pedidos"]({"payload": {"cliente": "acme", "tienda_id": tid}})
    assert "no expone pedidos" in msg


def test_periodica_productos_encola_solo_conectadas(entorno, monkeypatch):
    import cola
    import tareas
    import tiendas
    t1 = _tienda("acme")
    t2 = _tienda("otro")
    tiendas.actualizar("otro", t2, estado="rota", error="x")
    encolados = []
    monkeypatch.setattr(cola, "encolar", lambda tipo, payload, **kw: encolados.append((tipo, payload, kw)) or 1)
    msg = tareas.REGISTRO["tienda_sync_productos_todas"]({"payload": {}})
    assert "1 tienda(s)" in msg
    assert encolados == [("tienda_sync_productos", {"cliente": "acme", "tienda_id": t1},
                          {"cliente": "acme", "job_id": f"acme__tienda{t1}__productos", "duracion_estimada": 120,
                           "max_intentos": 3})]


def test_periodica_pedidos_solo_clientes_con_experimento_corriendo_y_atribucion_tienda(entorno, monkeypatch):
    import cola
    import experimentos as ex
    import tareas
    t_acme = _tienda("acme")
    _tienda("otro")
    _tienda("tercero")
    e1 = ex.crear("acme", "A", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ex.actualizar("acme", e1, estado="corriendo", atribucion="tienda")
    e2 = ex.crear("otro", "B", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ex.actualizar("otro", e2, estado="corriendo", atribucion="pixel")     # atribución por píxel: no
    e3 = ex.crear("tercero", "C", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ex.actualizar("tercero", e3, estado="pausado", atribucion="tienda")   # no corre: no
    encolados = []
    monkeypatch.setattr(cola, "encolar", lambda tipo, payload, **kw: encolados.append((tipo, payload, kw)) or 1)
    msg = tareas.REGISTRO["tienda_sync_pedidos_todas"]({"payload": {}})
    assert "1 tienda(s)" in msg
    assert [(e[0], e[1]) for e in encolados] == [("tienda_sync_pedidos", {"cliente": "acme", "tienda_id": t_acme})]
    assert encolados[0][2]["max_intentos"] == 3 and encolados[0][2]["job_id"] == f"acme__tienda{t_acme}__pedidos"
    # sin experimentos que califiquen no se encola nada
    ex.actualizar("acme", e1, estado="cerrado")
    encolados.clear()
    tareas.REGISTRO["tienda_sync_pedidos_todas"]({"payload": {}})
    assert encolados == []


def test_periodica_pedidos_salta_tiendas_sin_pedidos(entorno, monkeypatch):
    import cola
    import experimentos as ex
    import tareas
    _tienda("acme")
    e1 = ex.crear("acme", "A", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ex.actualizar("acme", e1, estado="corriendo", atribucion="tienda")
    monkeypatch.setattr(Falso, "tiene_pedidos", False)
    encolados = []
    monkeypatch.setattr(cola, "encolar", lambda tipo, payload, **kw: encolados.append(tipo) or 1)
    tareas.REGISTRO["tienda_sync_pedidos_todas"]({"payload": {}})
    assert encolados == []


def test_catalogo_importar_archivo_reporta_etapas_y_resume(entorno, monkeypatch):
    import tareas
    import tiendas
    import trabajos
    reportes = []
    monkeypatch.setattr(trabajos, "reportar", lambda job_id, **kw: reportes.append((job_id, kw)))
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "productos.csv")
    msg = tareas.REGISTRO["catalogo_importar"]({"payload": {"cliente": "acme", "ruta": ruta, "nombre_archivo": "productos.csv"},
                                               "job_id": "acme__importar_archivo"})
    assert msg.startswith("Importación lista: ") and "3 producto(s) nuevo(s)" in msg and "2 con activo" in msg
    assert "1 aviso(s)" in msg and "Repisa" in msg
    etapas = [kw["etapa"] for _, kw in reportes]
    assert etapas[0] == "Leyendo" and "Guardando productos" in etapas and "Creando activos" in etapas
    assert all(job_id == "acme__importar_archivo" for job_id, _ in reportes)
    assert len(tiendas.productos("acme")) == 3 and all(p["fuente"] == "csv" for p in tiendas.productos("acme"))


def test_catalogo_importar_url_y_errores(entorno, monkeypatch):
    import importador
    import tareas
    import trabajos
    monkeypatch.setattr(trabajos, "reportar", lambda job_id, **kw: None)
    monkeypatch.setattr(importador.conector_url, "leer", lambda url: _prod("u1", "Espejo web"))
    msg = tareas.REGISTRO["catalogo_importar"]({"payload": {"cliente": "acme", "url": "https://tienda.test/espejo"}})
    assert "1 producto(s) nuevo(s)" in msg and "1 con activo" in msg
    with pytest.raises(ErrorConector):
        tareas.REGISTRO["catalogo_importar"]({"payload": {"cliente": "acme"}})

    def _falla(url):
        raise ErrorConector("No encontré ningún producto en esa página.")
    monkeypatch.setattr(importador.conector_url, "leer", _falla)
    with pytest.raises(ErrorConector, match="ningún producto"):
        tareas.REGISTRO["catalogo_importar"]({"payload": {"cliente": "acme", "url": "https://tienda.test/x"}})
