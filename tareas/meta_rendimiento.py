"""Tareas del worker para el rendimiento de Meta (spec 2026-10-08 meta rendimiento §6).

  meta_rend_sincronizar        -> f"{cliente}__meta_rend__{act}"  (max_intentos=2: leer de Meta no cobra).
                                  Una por CUENTA; el payload lleva `cliente` y `ad_account_id`.
  meta_rend_sincronizar_todas  -> periódica (worker.PERIODICAS, 3 h): encola la de cada cuenta de cada proyecto
  meta_rend_limpiar            -> periódica diaria: borra los días de anuncio de más de 95 días

Un error de Meta (o cualquier otro) deja ESA cuenta en estado `error` con el motivo en palabras y sin token, y sube
para que la cola reintente; las demás cuentas del proyecto no se enteran. Si Meta pidió esperar (límite de uso) pasa
lo mismo: el reintento o la siguiente periódica sigue donde se quedó, porque la copia inicial se reanuda."""
import logging
from datetime import date, timedelta

from flask_babel import gettext

import cola
import meta_conexion
import trabajos
from meta_rendimiento import cuentas, datos, graph, sync
from tareas import al_interrumpir, registrar

log = logging.getLogger("creatv.tareas.meta_rendimiento")

TIPO_SYNC = "meta_rend_sincronizar"
TIPO_TODAS = "meta_rend_sincronizar_todas"
TIPO_LIMPIAR = "meta_rend_limpiar"
# Los nombres son los que emite `sync.sincronizar` por `on_etapa` (así la barra mueve su rango); los pesos suman 100.
ETAPAS_SYNC = [(sync.ETAPA_CUENTA, 5), (sync.ETAPA_OBJETOS, 15), (sync.ETAPA_METRICAS, 70), (sync.ETAPA_ALCANCE, 10)]
MAX_INTENTOS_SYNC = 2
# Mayor = antes (cola.reclamar ordena por prioridad descendente; 5 es lo normal y los lotes de sprint van con 3).
# Los límites de uso de Meta se comparten entre las cuentas de un usuario y una copia inicial puede tardar minutos
# en el único hilo general del worker: que Crear, los experimentos y Triple Whale pasen primero.
PRIORIDAD_SYNC = 2
DIAS_ANUNCIO_GUARDADOS = 95


def job_id_sync(cliente, act):
    return f"{cliente}__meta_rend__{act}"


def encolar_sync(cliente, act=None):
    """Encola la copia de esa cuenta, o la de todas las del proyecto si no se dice cuál. Devuelve cuántas quedaron
    en cola (0: ya había una viva, o la cuenta no está en el proyecto)."""
    quiero = cuentas.normalizar_id(act) if act is not None else None
    lista = [a for a in cuentas.ids(cliente) if quiero is None or a == quiero]
    return sum(1 for a in lista if trabajos.encolar(
        job_id_sync(cliente, a), TIPO_SYNC, {"cliente": cliente, "ad_account_id": a}, cliente=cliente,
        duracion_estimada=180, etapas=ETAPAS_SYNC, max_intentos=MAX_INTENTOS_SYNC, prioridad=PRIORIDAD_SYNC))


def syncs_en_curso(cliente):
    """Los job ids de las copias del proyecto que están en cola o corriendo (una consulta): las barras del panel."""
    return sorted(cola.job_ids_vivos(cliente, TIPO_SYNC))


def _mensaje_error(e, token):
    """El motivo que se guarda en la cuenta y se muestra: sin token y de 500 caracteres como mucho. De un error de
    Meta (`ErrorGraph`) va su texto, que ya viene traducido; de cualquier otra excepción solo su tipo, porque su
    `str` (una `requests` con la URL) puede traer el token."""
    if isinstance(e, graph.ErrorGraph):
        texto = str(e) or type(e).__name__
    else:
        texto = gettext("No se pudo copiar la cuenta de Meta (%(tipo)s).", tipo=type(e).__name__)
    if token:
        texto = texto.replace(token, "***")
    return cola.recortar(cola.sin_token(texto), 500)


@registrar(TIPO_SYNC)
def meta_rend_sincronizar(tarea):
    p = tarea["payload"]
    cliente, act = p["cliente"], p["ad_account_id"]
    ya_no_esta = gettext("Esa cuenta de Meta ya no está en el proyecto.")
    if not cuentas.cuenta(cliente, act):
        return ya_no_esta
    token = (meta_conexion.cargar(cliente) or {}).get("token")
    if not token:
        # Reintentar no arregla una conexión que falta: se avisa en la cuenta y la tarea termina.
        mensaje = gettext("Meta no está conectado en este proyecto: conéctalo en Configuración › Conexiones.")
        cuentas.actualizar(cliente, act, estado="error", error=mensaje)
        return mensaje
    job_id = tarea.get("job_id") or job_id_sync(cliente, act)

    def etapa(nombre, progreso=None):
        trabajos.reportar(job_id, etapa=nombre, progreso=progreso)

    try:
        r = sync.sincronizar(cliente, act, token, on_etapa=etapa)
    except Exception as e:  # noqa: BLE001 — cualquier fallo deja la cuenta en error y la cola reintenta
        mensaje = _mensaje_error(e, token)
        cuentas.actualizar(cliente, act, estado="error", error=mensaje)
        # `from None`: el traceback del worker no arrastra la excepción original (su texto puede traer la URL).
        raise RuntimeError(mensaje) from None
    if r.get("omitida"):
        return ya_no_esta
    nombre = (cuentas.cuenta(cliente, act) or {}).get("nombre") or act
    return gettext("Listo (%(cuenta)s): %(dias)s día(s) de la cuenta y %(filas)s fila(s) de anuncios, del %(desde)s al %(hasta)s.",
                   cuenta=nombre, dias=r["dias_cuenta"], filas=r["filas_anuncio"], desde=r["desde"], hasta=r["hasta"])


@al_interrumpir(TIPO_SYNC)
def _sync_interrumpida(tarea, mensaje):
    """Un reinicio mató la copia sin reintentos que darle: la cuenta no se queda «copiando» para siempre."""
    p = tarea.get("payload") or {}
    if not (p.get("cliente") and p.get("ad_account_id")):
        return
    c = cuentas.cuenta(p["cliente"], p["ad_account_id"])
    if c and c["estado"] == "copiando":
        cuentas.actualizar(p["cliente"], p["ad_account_id"], estado="error",
                           error=cola.recortar(cola.sin_token(str(mensaje)), 500))


@registrar(TIPO_TODAS)
def meta_rend_sincronizar_todas(tarea):
    n = sum(encolar_sync(cliente, act) for cliente, act in cuentas.todas())
    return gettext("%(n)s copia(s) de Meta en cola", n=n)


@registrar(TIPO_LIMPIAR)
def meta_rend_limpiar(tarea):
    n = datos.purgar_anuncios((date.today() - timedelta(days=DIAS_ANUNCIO_GUARDADOS)).isoformat())
    return gettext("%(n)s fila(s) viejas de anuncios de Meta borradas", n=n)
