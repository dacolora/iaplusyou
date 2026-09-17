"""
Tareas del worker para tiendas conectadas (Bloque 5): sincronizar productos
y pedidos de una tienda, importar un catálogo desde archivo/URL, y las dos
periódicas que encolan las syncs.

Ids de trabajo (los mismos que usa el dashboard para encolar y consultar):
  tienda_sync_productos -> f"{cliente}__tienda{tid}__productos"   (max_intentos=3)
  tienda_sync_pedidos   -> f"{cliente}__tienda{tid}__pedidos"     (max_intentos=3)
  catalogo_importar     -> f"{cliente}__importar_archivo" / f"{cliente}__importar_url"
                           (max_intentos=1: crea activos y llama a Claude por
                           cada uno — un reintento a ciegas duplicaría trabajo)

Errores de tienda: un `ErrorConector` (o credenciales ilegibles / incompletas)
deja la tienda en `estado="rota"` con `error` mostrable y relanza, para que la
cola reintente con espera (una caída pasajera de la API se recupera sola). El
correo (`notificaciones.avisar(tipo="tienda")`) sale una sola vez, en el
último intento — no tres veces por el mismo token vencido. Una sync que
termina bien vuelve a `conectada` y limpia `error`.

MELI: si el conector renovó el token (`credenciales_actualizadas`), se guarda
SIEMPRE, incluso si la sync falló después — el refresh token es de un solo uso.
"""
import logging
from datetime import datetime, timedelta

import sqlalchemy as sa

import cifrado
import cola
import conectores
import db
import importador
import notificaciones
import tiendas
import trabajos
from conectores import ErrorConector
from tareas import registrar

log = logging.getLogger("creatv.tareas.tiendas")

ETAPAS_IMPORTAR = [("Leyendo", 20), ("Guardando productos", 30), ("Creando activos", 50)]
CADA_SYNC_PRODUCTOS = 21600   # 6 h
CADA_SYNC_PEDIDOS = 7200      # 2 h
DIAS_PEDIDOS_INICIAL = 30
# Solape al pedir pedidos "desde la última sync": la tienda reporta la hora en
# su zona y `ultima_sync_pedidos` es hora local del servidor. Un día de más
# solo cuesta filas repetidas (guardar_pedidos es idempotente); uno de menos
# pierde ventas.
SOLAPE_PEDIDOS = timedelta(days=1)
MAX_INTENTOS_SYNC = 3


def job_id_sync_productos(cliente, tienda_id):
    return f"{cliente}__tienda{tienda_id}__productos"


def job_id_sync_pedidos(cliente, tienda_id):
    return f"{cliente}__tienda{tienda_id}__pedidos"


def job_id_importar_archivo(cliente):
    return f"{cliente}__importar_archivo"


def job_id_importar_url(cliente):
    return f"{cliente}__importar_url"


# --- helpers ---------------------------------------------------------------

_ERRORES_TIENDA = (ErrorConector, cifrado.ErrorCifrado, ValueError)


def _conector(cliente, tienda, cargar_descripciones=False):
    creds = tiendas.credenciales(cliente, tienda["id"])
    if not creds:
        raise ErrorConector("La tienda no tiene credenciales guardadas. Vuelve a conectarla.")
    cls = conectores.por_tipo(tienda["tipo"])
    if tienda["tipo"] == "meli":
        # Solo MELI cobra la descripción aparte (una llamada por ítem).
        return cls(creds, cargar_descripciones=cargar_descripciones)
    return cls(creds)


def _guardar_credenciales(cliente, tienda, con):
    nuevas = getattr(con, "credenciales_actualizadas", None)
    if nuevas:
        tiendas.conectar(cliente, tienda["tipo"], nuevas, nombre=tienda.get("nombre"), dominio=tienda.get("dominio"))
        log.info("tienda %s/%s: credenciales renovadas guardadas", cliente, tienda["id"])


def _ultimo_intento(tarea):
    intentos = int(tarea.get("intentos") or 0)
    maximo = int(tarea.get("max_intentos") or 0)
    return intentos >= maximo


def _marcar_rota(cliente, tienda, tarea, que, error):
    mensaje = cola.sin_token(getattr(error, "usuario", None) or str(error))
    tiendas.actualizar(cliente, tienda["id"], estado="rota", error=mensaje)
    if _ultimo_intento(tarea):
        nombre = tienda.get("nombre") or tienda.get("dominio") or tienda.get("tipo")
        notificaciones.avisar(
            cliente, "tienda", f"La tienda «{nombre}» dejó de sincronizar",
            f"No se pudieron sincronizar los {que} de la tienda {nombre} ({tienda.get('tipo')}):\n\n{mensaje}\n\n"
            f"Revisa la conexión desde el panel de Tiendas y vuelve a sincronizar.")
    return mensaje


def _nombre(tienda):
    return tienda.get("nombre") or tienda.get("dominio") or f"tienda {tienda['id']}"


# --- sync productos ----------------------------------------------------------

@registrar("tienda_sync_productos")
def tienda_sync_productos(tarea):
    """Baja el catálogo de la tienda, lo guarda/actualiza (importador),
    liga activos, archiva lo que ya no está y marca `ultima_sync_productos`."""
    p = tarea["payload"]
    cliente, tid = p["cliente"], p["tienda_id"]
    job_id = tarea.get("job_id") or job_id_sync_productos(cliente, tid)
    tienda = tiendas.obtener(cliente, tid)
    if tienda is None:
        return "Esa tienda no existe."
    con = None
    try:
        # Primera importación de esta fuente: vale la pena pedir descripciones.
        primera = not any(pr["fuente"] == tienda["tipo"]
                          for pr in tiendas.productos(cliente, incluir_archivados=True))
        con = _conector(cliente, tienda, cargar_descripciones=primera)
        trabajos.reportar(job_id, etapa="Leyendo", detalle=_nombre(tienda))
        lista = con.listar_productos()
    except _ERRORES_TIENDA as error:
        if con is not None:
            _guardar_credenciales(cliente, tienda, con)
        mensaje = _marcar_rota(cliente, tienda, tarea, "productos", error)
        raise ErrorConector(mensaje) from error
    _guardar_credenciales(cliente, tienda, con)

    resumen = importador.importar_lista(
        cliente, tienda["tipo"], lista,
        on_progreso=lambda etapa, detalle: trabajos.reportar(job_id, etapa=etapa, detalle=detalle))
    archivados = tiendas.archivar_faltantes(cliente, tienda["tipo"], [pr["fuente_id"] for pr in lista])
    tiendas.actualizar(cliente, tid, estado="conectada", error=None, ultima_sync_productos=db.ahora())
    texto = importador.resumen_texto(resumen)
    if archivados:
        texto += f" {archivados} archivado(s) por no estar ya en la tienda."
    return texto


# --- sync pedidos ------------------------------------------------------------

def _desde_para_pedidos(tienda):
    ultima = tienda.get("ultima_sync_pedidos")
    if ultima:
        try:
            return (datetime.fromisoformat(ultima) - SOLAPE_PEDIDOS).isoformat(timespec="seconds")
        except ValueError:
            pass
    return (datetime.now() - timedelta(days=DIAS_PEDIDOS_INICIAL)).isoformat(timespec="seconds")


def _resolver_atribucion(cliente):
    """atribucion.resolver_pendientes (Task 5). Si el módulo todavía no
    existe, se salta: los pedidos quedan guardados con su utm_content y
    `tiendas.pedidos_sin_resolver` los entrega cuando el atribuidor llegue."""
    try:
        import atribucion  # noqa: PLC0415 — perezoso a propósito
    except ImportError:
        return None
    return atribucion.resolver_pendientes(cliente)


@registrar("tienda_sync_pedidos")
def tienda_sync_pedidos(tarea):
    p = tarea["payload"]
    cliente, tid = p["cliente"], p["tienda_id"]
    tienda = tiendas.obtener(cliente, tid)
    if tienda is None:
        return "Esa tienda no existe."
    con = None
    inicio = db.ahora()
    try:
        con = _conector(cliente, tienda)
        if not getattr(con, "tiene_pedidos", False):
            return f"La tienda {_nombre(tienda)} no expone pedidos; no hay nada que sincronizar."
        pedidos = con.pedidos_desde(_desde_para_pedidos(tienda))
    except _ERRORES_TIENDA as error:
        if con is not None:
            _guardar_credenciales(cliente, tienda, con)
        mensaje = _marcar_rota(cliente, tienda, tarea, "pedidos", error)
        raise ErrorConector(mensaje) from error
    _guardar_credenciales(cliente, tienda, con)

    nuevos = tiendas.guardar_pedidos(cliente, tid, pedidos)
    resueltos = _resolver_atribucion(cliente)
    # `inicio` (no "ahora"): un pedido creado mientras corría la sync entra en
    # la próxima ventana en vez de perderse.
    tiendas.actualizar(cliente, tid, estado="conectada", error=None, ultima_sync_pedidos=inicio)
    texto = f"{len(pedidos)} pedido(s) leído(s), {nuevos} nuevo(s)."
    if resueltos is not None:
        texto += f" {resueltos} atribuido(s) a piezas."
    return texto


# --- importar archivo / URL --------------------------------------------------

@registrar("catalogo_importar")
def catalogo_importar(tarea):
    """Payload {cliente, ruta, nombre_archivo} (CSV/Excel) o {cliente, url}.
    Etapas ETAPAS_IMPORTAR. Un ErrorConector (archivo ilegible, página sin
    producto) sale tal cual: es el mensaje que ve la persona."""
    p = tarea["payload"]
    cliente = p["cliente"]
    url = (p.get("url") or "").strip()
    job_id = tarea.get("job_id") or (job_id_importar_url(cliente) if url else job_id_importar_archivo(cliente))

    def avanzar(etapa, detalle=None):
        trabajos.reportar(job_id, etapa=etapa, detalle=detalle)

    if url:
        resumen = importador.desde_url(cliente, url, on_progreso=avanzar)
    else:
        if not p.get("ruta"):
            raise ErrorConector("La importación no trae archivo ni URL.")
        resumen = importador.desde_archivo(cliente, p["ruta"], p.get("nombre_archivo") or p["ruta"],
                                           on_progreso=avanzar)
    return "Importación lista: " + importador.resumen_texto(resumen)


# --- periódicas --------------------------------------------------------------

def _tiendas_conectadas(clientes=None):
    t = db.tienda
    condiciones = [t.c.estado == "conectada"]
    if clientes is not None:
        if not clientes:
            return []
        condiciones.append(t.c.cliente.in_(tuple(clientes)))
    with db.conectar() as con:
        return con.execute(sa.select(t.c.id, t.c.cliente, t.c.tipo).where(*condiciones).order_by(t.c.id)).all()


@registrar("tienda_sync_productos_todas")
def tienda_sync_productos_todas(tarea):
    """Periódica (6 h): una sync de productos por tienda `conectada`. Las
    `rota` no se tocan solas: la persona las reconecta o resincroniza a mano."""
    filas = _tiendas_conectadas()
    n = 0
    for tid, cliente, _tipo in filas:
        if cola.encolar("tienda_sync_productos", {"cliente": cliente, "tienda_id": tid}, cliente=cliente,
                        job_id=job_id_sync_productos(cliente, tid), duracion_estimada=120,
                        max_intentos=MAX_INTENTOS_SYNC):
            n += 1
    return f"{n} tienda(s) en cola para sincronizar productos."


def _clientes_con_atribucion_tienda():
    e = db.experimento
    with db.conectar() as con:
        filas = con.execute(sa.select(e.c.cliente).distinct().where(
            e.c.legado.is_(False), e.c.estado == "corriendo", e.c.atribucion == "tienda")).all()
    return sorted({f[0] for f in filas})


@registrar("tienda_sync_pedidos_todas")
def tienda_sync_pedidos_todas(tarea):
    """Periódica (2 h): pedidos solo para los clientes que tienen un
    experimento `corriendo` con atribución por tienda — a nadie más le sirve
    gastar cuota de la API en ventas."""
    clientes = _clientes_con_atribucion_tienda()
    n = 0
    for tid, cliente, tipo in _tiendas_conectadas(clientes):
        try:
            if not getattr(conectores.por_tipo(tipo), "tiene_pedidos", False):
                continue
        except ValueError:
            continue
        if cola.encolar("tienda_sync_pedidos", {"cliente": cliente, "tienda_id": tid}, cliente=cliente,
                        job_id=job_id_sync_pedidos(cliente, tid), duracion_estimada=60,
                        max_intentos=MAX_INTENTOS_SYNC):
            n += 1
    return f"{n} tienda(s) en cola para sincronizar pedidos."


__all__ = ["ETAPAS_IMPORTAR", "CADA_SYNC_PRODUCTOS", "CADA_SYNC_PEDIDOS", "MAX_INTENTOS_SYNC",
           "tienda_sync_productos", "tienda_sync_pedidos", "catalogo_importar",
           "tienda_sync_productos_todas", "tienda_sync_pedidos_todas",
           "job_id_sync_productos", "job_id_sync_pedidos", "job_id_importar_archivo", "job_id_importar_url"]
