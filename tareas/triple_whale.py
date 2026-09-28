"""Tareas del worker para Triple Whale (spec 2026-09-28 §4 y §6).

  tw_sincronizar        -> f"{cliente}__tw_sync"     (max_intentos=2; gratis:
                           la API de Triple Whale no cobra por llamada)
  tw_sincronizar_todas  -> periódica (worker.PERIODICAS, 2 h): encola la de
                           cada proyecto conectado
  tw_evaluar            -> f"{cliente}__tw_evaluar"  (max_intentos=1: paga a
                           Claude; el gasto real se registra como tipo
                           `evaluacion`, también si la respuesta no sirvió)

Un error de Triple Whale (llave revocada, tienda, red) deja la conexión en
`estado="error"` con el motivo sin token y sube para que la cola reintente.
"""
import logging

from flask_babel import gettext

import cifrado
import cola
import gastos
import idiomas
import proyectos
import trabajos
import triple_whale
import triple_whale_tiendas
from nicho.avatares import costo_real
from tareas import al_interrumpir, ref_sufijo, registrar
from triple_whale import analisis, avisos, datos, sync

log = logging.getLogger("creatv.tareas.triple_whale")

TIPO_SYNC = "tw_sincronizar"
TIPO_TODAS = "tw_sincronizar_todas"
TIPO_EVALUAR = "tw_evaluar"
ETAPAS_SYNC = [("Trayendo métricas", 100)]
ETAPAS_EVALUAR = [("Buscando miniaturas", 10), ("Sacando fotogramas", 15), ("Analizando con Claude", 75)]
MAX_INTENTOS_SYNC = 2


def job_id_sync(cliente):
    return f"{cliente}__tw_sync"


def job_id_evaluar(cliente):
    return f"{cliente}__tw_evaluar"


def encolar_sync(cliente):
    """True si quedó en cola (False: ya había una viva)."""
    return trabajos.encolar(job_id_sync(cliente), TIPO_SYNC, {"cliente": cliente}, cliente=cliente,
                            duracion_estimada=90, etapas=ETAPAS_SYNC, max_intentos=MAX_INTENTOS_SYNC)


def encolar_evaluacion(cliente, evaluacion_id):
    """max_intentos=1: paga a Claude. False si ya había una viva."""
    return trabajos.encolar(job_id_evaluar(cliente), TIPO_EVALUAR, {"cliente": cliente, "evaluacion_id": evaluacion_id},
                            cliente=cliente, duracion_estimada=120, etapas=ETAPAS_EVALUAR, max_intentos=1)


def evaluacion_en_curso(cliente):
    return trabajos.en_curso(job_id_evaluar(cliente))


def _sin_llave(cliente, texto):
    """Ningún mensaje nuestro lleva la llave, pero uno de un proveedor podría
    repetirla: se tacha su valor exacto antes de guardarlo o mostrarlo."""
    try:
        llave = triple_whale_tiendas.obtener_llave(cliente)
    except Exception:  # noqa: BLE001 — sin llave legible no hay nada que tachar
        llave = None
    return texto.replace(llave, "***") if llave and len(llave) >= 6 else texto


@registrar(TIPO_SYNC)
def tw_sincronizar(tarea):
    cliente = tarea["payload"]["cliente"]
    job_id = tarea.get("job_id") or job_id_sync(cliente)
    if not triple_whale_tiendas.obtener(cliente):
        return gettext("Triple Whale ya no está conectado en este proyecto.")

    def progreso(i, n, desde, hasta):
        trabajos.reportar(job_id, etapa="Trayendo métricas", progreso=i * 100.0 / max(1, n),
                          detalle=f"{desde} → {hasta}")

    try:
        r = sync.sincronizar(cliente, on_progreso=progreso)
    except (triple_whale.ErrorTripleWhale, cifrado.ErrorCifrado) as e:
        mensaje = cola.recortar(_sin_llave(cliente, cola.sin_token(str(e) or type(e).__name__)), 500)
        triple_whale_tiendas.actualizar(cliente, estado="error", error=mensaje)
        raise triple_whale.ErrorTripleWhale(mensaje) from None
    texto = gettext("Listo: %(n)s anuncio(s) y %(dias)s día(s) de la tienda, del %(desde)s al %(hasta)s.",
                    n=r["anuncios"], dias=r["dias_tienda"], desde=r["desde"], hasta=r["hasta"])
    if r["fallos"]:
        texto += " " + gettext("Sin %(partes)s: Triple Whale no aceptó esa consulta.",
                               partes=", ".join(sorted(r["fallos"])))
    # Lo que cambió desde la copia anterior (nuevos ganadores, fatiga,
    # perdedores, sin ventas) sale por correo; un fallo aquí no tumba la copia.
    try:
        c = avisos.revisar_y_avisar(cliente)
    except Exception as e:  # noqa: BLE001
        log.warning("avisos de Triple Whale de %s: %s", cliente, type(e).__name__)
        c = None
    if c and c.get("avisado"):
        texto += " " + gettext("Aviso enviado: %(g)s ganador(es) nuevo(s), %(c)s cansándose, %(p)s perdedor(es) nuevo(s).",
                               g=len(c["ganadores"]), c=len(c["cansados"]), p=len(c["perdedores"]))
    return texto


@registrar(TIPO_TODAS)
def tw_sincronizar_todas(tarea):
    n = sum(1 for cliente in triple_whale_tiendas.conectados() if encolar_sync(cliente))
    return f"{n} sincronización(es) de Triple Whale en cola"


@registrar(TIPO_EVALUAR)
def tw_evaluar(tarea):
    p = tarea["payload"]
    cliente, eid = p["cliente"], int(p["evaluacion_id"])
    job_id = tarea.get("job_id") or job_id_evaluar(cliente)
    fila = datos.evaluacion(cliente, eid)
    if fila is None:
        return gettext("Esa evaluación ya no existe.")
    datos.actualizar_evaluacion(eid, estado="analizando", tarea_id=tarea.get("id"), error=None)
    anuncios = list(fila["anuncios"] or [])
    extra = dict(fila["extra"] or {})
    trabajos.reportar(job_id, etapa="Buscando miniaturas", detalle=gettext("%(n)s anuncio(s)", n=len(anuncios)))
    medios = analisis.medios_meta(cliente, anuncios)
    # Las piezas hechas en Creatv tienen su video y su miniatura en R2: la
    # miniatura sirve tal cual y Claude recibe los fotogramas del video.
    creatv = datos.piezas_creatv(cliente, [a["ad_id"] for a in anuncios if a.get("canal") == triple_whale.CANAL_META])
    for a in anuncios:
        pieza = creatv.get(a["ad_id"])
        if not pieza:
            continue
        imagen = pieza.get("url_video") if pieza.get("tipo") == "imagen" else pieza.get("url_miniatura")
        medio = medios.setdefault(a["ad_id"], {"imagen": None, "titulo": "", "texto": "", "tipo": pieza.get("tipo")})
        if imagen:
            medio.update(imagen=imagen, imagen_origen=imagen)
        medio["origen"] = "creatv"
    medios = analisis.copiar_miniaturas(cliente, eid, anuncios, medios)
    trabajos.reportar(job_id, etapa="Sacando fotogramas")
    bloques, temporales = analisis.visuales(cliente, anuncios, medios, creatv)
    productos = datos.top_productos(cliente, fila["desde"], fila["hasta"], limite=analisis.MAX_PRODUCTOS)
    trabajos.reportar(job_id, etapa="Analizando con Claude")
    contexto = {"desde": fila["desde"], "hasta": fila["hasta"], "moneda": fila["moneda"],
                "modelo": extra.get("modelo"), "ventana": extra.get("ventana"),
                "benchmarks": extra.get("benchmarks") or {}, "meta_roas": extra.get("meta_roas")}
    referencia = f"tw_eval:{eid}{ref_sufijo(tarea)}"
    try:
        resultado, entrada, salida = analisis.analizar(proyectos.nombre_visible(cliente), contexto, anuncios,
                                                       medios, idiomas.de_proyecto(cliente), bloques=bloques,
                                                       productos=productos)
    except Exception as e:
        entrada = int(getattr(e, "tokens_entrada", 0) or 0)
        salida = int(getattr(e, "tokens_salida", 0) or 0)
        usd = costo_real(entrada, salida) if (entrada or salida) else 0.0
        if usd:
            gastos.registrar_seguro(cliente, "evaluacion", usd, referencia, proveedor="anthropic",
                                    detalle="sin resultado usable")
        mensaje = analisis.texto_error(e)
        datos.actualizar_evaluacion(eid, estado="error", error=mensaje, usd=usd)
        raise RuntimeError(mensaje) from None
    finally:
        analisis.borrar_temporales(temporales)
    usd = costo_real(entrada, salida)
    gastos.registrar_seguro(cliente, "evaluacion", usd, referencia, proveedor="anthropic",
                            detalle=f"{len(anuncios)} anuncio(s) de Triple Whale")
    for a in anuncios:
        medio = medios.get(a["ad_id"])
        if medio:
            a["medio"] = medio
        if a["ad_id"] in bloques:
            a["visual"] = bloques[a["ad_id"]]["clase"]
    extra["productos"] = productos
    datos.actualizar_evaluacion(eid, estado="lista", resultado=resultado, usd=usd, anuncios=anuncios, error=None,
                                extra=extra)
    return gettext("Evaluación lista: %(n)s idea(s) de anuncios nuevos.", n=len(resultado["ideas"]))


@al_interrumpir(TIPO_EVALUAR)
def _evaluar_interrumpida(tarea, mensaje):
    p = tarea.get("payload") or {}
    if p.get("cliente") and p.get("evaluacion_id"):
        fila = datos.evaluacion(p["cliente"], int(p["evaluacion_id"]))
        if fila and fila["estado"] in ("en_cola", "analizando"):
            datos.actualizar_evaluacion(int(p["evaluacion_id"]), estado="error",
                                        error=cola.recortar(cola.sin_token(str(mensaje)), 500))
