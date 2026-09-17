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
  producto_vincular     -> f"{cliente}__producto{pid}__vincular"  (max_intentos=1:
                           baja hasta 6 fotos y llama a Claude para la regla;
                           puede tardar minutos, por eso no va inline en la ruta)

Errores de tienda: un `ErrorConector` (o credenciales ilegibles / incompletas)
deja la tienda en `estado="rota"` con `error` mostrable y relanza, para que la
cola reintente con espera (una caída pasajera de la API se recupera sola). El
correo (`notificaciones.avisar(tipo="tienda")`) sale una sola vez, en el
último intento — no tres veces por el mismo token vencido. Una sync que
termina bien vuelve a `conectada` y limpia `error`.

MELI: si el conector renovó el token (`credenciales_actualizadas`), se guarda
SIEMPRE, incluso si la sync falló después — el refresh token es de un solo uso.

Tope de trabajo por corrida: crear un activo baja hasta 6 fotos y llama a
Claude, y el worker es de un solo hilo — una Shopify de 2 000 productos no
puede bloquearlo horas (ni al decisor de experimentos). Por eso una sync
liga como mucho `MAX_ACTIVOS_SYNC` productos sin activo por corrida (en
prueba → prioridad → nunca intentados; ver `importador.importar_lista`) y
una importación de archivo `MAX_ACTIVOS_IMPORTAR`; si quedaron pendientes
que nunca se intentaron, la misma tarea se vuelve a encolar para dentro de
`ESPERA_CONTINUACION` s (job_id alternando con el sufijo `__cont`, porque
el propio job_id sigue vivo mientras corre) hasta que no quede nada. Un
archivo importado solo se borra en la última corrida.
"""
import logging
import os
from datetime import datetime, timedelta

import sqlalchemy as sa

import atribucion
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
ETAPAS_VINCULAR = [("Bajando fotos", 60), ("Creando el activo", 40)]
CADA_SYNC_PRODUCTOS = 21600   # 6 h
CADA_SYNC_PEDIDOS = 7200      # 2 h
DIAS_PEDIDOS_INICIAL = 30
# Solape al pedir pedidos "desde la última sync": la tienda reporta la hora en
# su zona y `ultima_sync_pedidos` es hora local del servidor. Un día de más
# solo cuesta filas repetidas (guardar_pedidos es idempotente); uno de menos
# pierde ventas.
SOLAPE_PEDIDOS = timedelta(days=1)
MAX_INTENTOS_SYNC = 3
MAX_ACTIVOS_SYNC = 25
MAX_ACTIVOS_IMPORTAR = 50
ESPERA_CONTINUACION = 60
SUFIJO_CONTINUACION = "__cont"


def job_id_sync_productos(cliente, tienda_id):
    return f"{cliente}__tienda{tienda_id}__productos"


def job_id_sync_pedidos(cliente, tienda_id):
    return f"{cliente}__tienda{tienda_id}__pedidos"


def job_id_importar_archivo(cliente):
    return f"{cliente}__importar_archivo"


def job_id_importar_url(cliente):
    return f"{cliente}__importar_url"


def job_id_vincular(cliente, producto_id):
    return f"{cliente}__producto{producto_id}__vincular"


def job_id_continuacion(job_id):
    """El job_id de la corrida siguiente: alterna `<id>` ↔ `<id>__cont`. Una
    tarea no puede encolar su propio job_id (sigue `en_curso` hasta que
    termina), pero sí el otro de la pareja, que ya terminó."""
    if job_id.endswith(SUFIJO_CONTINUACION):
        return job_id[:-len(SUFIJO_CONTINUACION)]
    return job_id + SUFIJO_CONTINUACION


def _encolar_continuacion(tipo, payload, cliente, job_id, duracion_estimada):
    """Encola la corrida siguiente de una tarea que llegó a su tope.
    max_intentos=1: crea activos y llama a Claude. Devuelve True si quedó en cola."""
    cuando = (datetime.now() + timedelta(seconds=ESPERA_CONTINUACION)).isoformat(timespec="seconds")
    tid = cola.encolar(tipo, payload, cliente=cliente, job_id=job_id_continuacion(job_id),
                       duracion_estimada=duracion_estimada, etapas=ETAPAS_IMPORTAR, ejecutar_desde=cuando,
                       max_intentos=1)
    return tid is not None


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
    try:
        # Primera importación de esta fuente: vale la pena pedir descripciones.
        primera = not any(pr["fuente"] == tienda["tipo"]
                          for pr in tiendas.productos(cliente, incluir_archivados=True))
        con = _conector(cliente, tienda, cargar_descripciones=primera)
    except _ERRORES_TIENDA as error:
        mensaje = _marcar_rota(cliente, tienda, tarea, "productos", error)
        raise ErrorConector(mensaje) from error
    trabajos.reportar(job_id, etapa="Leyendo", detalle=_nombre(tienda))
    try:
        lista = con.listar_productos()
    except ErrorConector as error:
        # Solo un ErrorConector (credenciales/API) rompe la tienda; cualquier
        # otra excepción del conector al listar (p. ej. un parseo que lanza
        # ValueError) es un bug propio, no una tienda "rota", y sale tal cual
        # como error de la tarea.
        _guardar_credenciales(cliente, tienda, con)
        mensaje = _marcar_rota(cliente, tienda, tarea, "productos", error)
        raise ErrorConector(mensaje) from error
    _guardar_credenciales(cliente, tienda, con)

    resumen = importador.importar_lista(
        cliente, tienda["tipo"], lista, max_activos=MAX_ACTIVOS_SYNC,
        on_progreso=lambda etapa, detalle: trabajos.reportar(job_id, etapa=etapa, detalle=detalle))
    archivados = tiendas.archivar_faltantes(cliente, tienda["tipo"], [pr["fuente_id"] for pr in lista])
    tiendas.actualizar(cliente, tid, estado="conectada", error=None, ultima_sync_productos=db.ahora())
    texto = importador.resumen_texto(resumen)
    if archivados:
        texto += f" {archivados} archivado(s) por no estar ya en la tienda."
    if resumen.get("pendientes"):
        _encolar_continuacion("tienda_sync_productos", {"cliente": cliente, "tienda_id": tid}, cliente, job_id, 120)
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


@registrar("tienda_sync_pedidos")
def tienda_sync_pedidos(tarea):
    p = tarea["payload"]
    cliente, tid = p["cliente"], p["tienda_id"]
    tienda = tiendas.obtener(cliente, tid)
    if tienda is None:
        return "Esa tienda no existe."
    inicio = db.ahora()
    try:
        con = _conector(cliente, tienda)
    except _ERRORES_TIENDA as error:
        mensaje = _marcar_rota(cliente, tienda, tarea, "pedidos", error)
        raise ErrorConector(mensaje) from error
    if not getattr(con, "tiene_pedidos", False):
        return f"La tienda {_nombre(tienda)} no expone pedidos; no hay nada que sincronizar."
    try:
        pedidos = con.pedidos_desde(_desde_para_pedidos(tienda))
    except ErrorConector as error:
        # Igual que en tienda_sync_productos: solo un ErrorConector al pedir
        # los pedidos rompe la tienda; otra excepción sale como error de tarea.
        _guardar_credenciales(cliente, tienda, con)
        mensaje = _marcar_rota(cliente, tienda, tarea, "pedidos", error)
        raise ErrorConector(mensaje) from error
    _guardar_credenciales(cliente, tienda, con)

    nuevos = tiendas.guardar_pedidos(cliente, tid, pedidos)
    # Liga los pedidos con utm_content=<experimento_pieza.id> (o pieza.id en
    # links viejos) a su experimento_pieza; los
    # que no resuelven quedan en cola para la próxima sync.
    resueltos = atribucion.resolver_pendientes(cliente)
    # `inicio` (no "ahora"): un pedido creado mientras corría la sync entra en
    # la próxima ventana en vez de perderse.
    tiendas.actualizar(cliente, tid, estado="conectada", error=None, ultima_sync_pedidos=inicio)
    return f"{len(pedidos)} pedido(s) leído(s), {nuevos} nuevo(s), {resueltos} atribuido(s) a piezas."


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

    continua = False
    try:
        if url:
            resumen = importador.desde_url(cliente, url, on_progreso=avanzar, max_activos=MAX_ACTIVOS_IMPORTAR)
        else:
            if not p.get("ruta"):
                raise ErrorConector("La importación no trae archivo ni URL.")
            resumen = importador.desde_archivo(cliente, p["ruta"], p.get("nombre_archivo") or p["ruta"],
                                               on_progreso=avanzar, max_activos=MAX_ACTIVOS_IMPORTAR)
            if resumen.get("pendientes"):
                # La corrida siguiente vuelve a leer el mismo archivo (los ya
                # ligados solo se refrescan) y liga los siguientes 50.
                continua = _encolar_continuacion("catalogo_importar", dict(p), cliente, job_id, 120)
    finally:
        # El dashboard sube el archivo a clientes/<c>/importaciones/ solo para
        # esta tarea (`borrar_al_terminar`): se borra al terminar, salga bien o
        # mal (max_intentos=1: nadie lo va a releer), salvo que quede una
        # continuación en cola que lo necesita. Sin la bandera (una ruta
        # ajena, p. ej. un fixture) el archivo no se toca.
        if p.get("borrar_al_terminar") and p.get("ruta") and not continua:
            try:
                os.remove(p["ruta"])
            except OSError:
                pass
    if continua:
        guardados = int(resumen.get("nuevos") or 0) + int(resumen.get("actualizados") or 0)
        texto = (f"Importación en curso: {guardados} producto(s) guardado(s), "
                 f"{resumen.get('activos', 0)} activo(s) creado(s); el resto se completa solo en unos minutos.")
        errores = resumen.get("errores") or []
        if errores:
            texto += f" {len(errores)} aviso(s): " + "; ".join(errores[:3])
        return texto
    return "Importación lista: " + importador.resumen_texto(resumen)


# --- crear activo de un producto ---------------------------------------------

@registrar("producto_vincular")
def producto_vincular(tarea):
    """Payload {cliente, producto_id}: crea (o completa) el activo del
    catálogo del producto bajando sus fotos otra vez (`forzar_fotos=True`).
    Sin activo al final (producto sin fotos descargables) es un error de
    tarea: el mensaje en español de `importador` es lo que ve la persona."""
    p = tarea["payload"]
    cliente, pid = p["cliente"], int(p["producto_id"])
    job_id = tarea.get("job_id") or job_id_vincular(cliente, pid)
    prod = tiendas.producto(cliente, pid)
    if prod is None:
        raise ErrorConector("Ese producto ya no existe.")
    trabajos.reportar(job_id, etapa="Bajando fotos", detalle=prod.get("nombre") or f"producto {pid}")
    errores = []
    activo_id = importador.vincular_activo(cliente, pid, forzar_fotos=True, errores=errores)
    trabajos.reportar(job_id, etapa="Creando el activo")
    if not activo_id:
        raise ErrorConector("No pude crear el activo: "
                            + (" ".join(errores) or "el producto no tiene fotos descargables."))
    texto = f"Activo «{activo_id}» listo en el Catálogo."
    if errores:
        texto += " " + " ".join(errores)
    return texto


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


__all__ = ["ETAPAS_IMPORTAR", "ETAPAS_VINCULAR", "CADA_SYNC_PRODUCTOS", "CADA_SYNC_PEDIDOS", "MAX_INTENTOS_SYNC",
           "MAX_ACTIVOS_SYNC", "MAX_ACTIVOS_IMPORTAR", "ESPERA_CONTINUACION",
           "tienda_sync_productos", "tienda_sync_pedidos", "catalogo_importar", "producto_vincular",
           "tienda_sync_productos_todas", "tienda_sync_pedidos_todas",
           "job_id_sync_productos", "job_id_sync_pedidos", "job_id_importar_archivo", "job_id_importar_url",
           "job_id_vincular", "job_id_continuacion"]
