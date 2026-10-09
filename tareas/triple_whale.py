"""Tareas del worker para Triple Whale (spec 2026-09-28 §4 y §6; varias tiendas: 2026-10-08 §5).

  tw_sincronizar        -> f"{cliente}__tw_sync__{tienda_id}"  (max_intentos=2;
                           gratis: la API de Triple Whale no cobra por llamada).
                           Una por TIENDA; el payload lleva `cliente` y `tienda_id`
  tw_sincronizar_todas  -> periódica (worker.PERIODICAS, 2 h): encola la de
                           cada tienda conectada de cada proyecto
  tw_evaluar            -> f"{cliente}__tw_evaluar"  (max_intentos=1: paga a
                           Claude; el gasto real se registra como tipo
                           `evaluacion`, también si la respuesta no sirvió)
  tw_analizar_anuncio   -> f"{cliente}__tw_anuncio__{canal}__{ad_id}"  (max_intentos=1: paga Whisper (fal) y
                           Claude; «Cómo mejorarlo» de UN anuncio, spec 2026-10-08 tarjetas §6.2)
  tw_ganchos_preparar   -> f"{cliente}__tw_ganchos_{aid}_t{tanda}"  (max_intentos=1, prioridad 3; gratis: baja el
                           original y lanza una pieza de Crear por gancho, cada una la cobra flowplus_video)
  tw_ganchos_vigilar    -> periódica (worker.PERIODICAS, 60 s): mueve cada variante viva (spec 2026-10-09 §4.5)
  tw_gancho_armar       -> f"{cliente}__tw_gancho_{gid}_armar"  (max_intentos=2, prioridad 1; gratis: arma la
                           edición con el clip ya pagado y el original, y encola su render)

Un error de Triple Whale (llave revocada, tienda, red) deja ESA tienda en
`estado="error"` con el motivo sin token ni llave y sube para que la cola
reintente; las demás tiendas del proyecto no se enteran. Los avisos por correo
corren cuando termina la última copia del proyecto, no en cada una.
"""
import logging
import os
import re
import shutil
from datetime import datetime, timedelta

from flask_babel import gettext, ngettext

import cifrado
import cola
import creative_flow
import ediciones
import flowplus_lanzar
import gastos
import idiomas
import materiales
import proyectos
import trabajos
import triple_whale
import triple_whale_tiendas
from cobros import SaldoInsuficiente
from conectores import url as conector_url
from conectores.base import ErrorConector
from doctrina import aprendizajes as doctrina_aprendizajes
from final_edition import borrador, cortes, encuadre, insumos, mezcla
from final_edition import documento as documento_mod
from final_edition.motor import compilador
from nicho.avatares import costo_real
from storage import r2_uploader
from tareas import al_interrumpir, ref_sufijo, registrar
from tareas import edicion as tareas_edicion
from tareas.cadena import VIVOS_CREAR
from triple_whale import analisis, avisos, datos, ganchos, mejorar, paises, sync

log = logging.getLogger("creatv.tareas.triple_whale")

TIPO_SYNC = "tw_sincronizar"
TIPO_TODAS = "tw_sincronizar_todas"
TIPO_EVALUAR = "tw_evaluar"
ETAPAS_SYNC = [(idiomas.N_("Trayendo métricas"), 100)]
ETAPAS_EVALUAR = [(idiomas.N_("Buscando miniaturas"), 10), (idiomas.N_("Sacando fotogramas"), 15),
                  (idiomas.N_("Analizando con Claude"), 75)]
MAX_INTENTOS_SYNC = 2


def job_id_sync(cliente, tienda_id):
    return f"{cliente}__tw_sync__{tienda_id}"


def job_id_evaluar(cliente):
    return f"{cliente}__tw_evaluar"


def encolar_sync(cliente, tienda_id=None):
    """Encola la copia de esa tienda, o de todas las del proyecto si no se dice
    cuál. Devuelve cuántas quedaron en cola (0: ya había una viva, o la tienda
    no existe en el proyecto)."""
    if tienda_id is not None:
        ids = [t["id"] for t in triple_whale_tiendas.tiendas(cliente) if t["id"] == tienda_id]
    else:
        ids = [t["id"] for t in triple_whale_tiendas.tiendas(cliente)]
    return sum(1 for i in ids if trabajos.encolar(
        job_id_sync(cliente, i), TIPO_SYNC, {"cliente": cliente, "tienda_id": i}, cliente=cliente,
        duracion_estimada=90, etapas=ETAPAS_SYNC, max_intentos=MAX_INTENTOS_SYNC))


def syncs_en_curso(cliente):
    """Los job ids de las copias del proyecto que están en cola o corriendo
    (una consulta): las barras del panel y el aviso de «terminó la última»."""
    return sorted(cola.job_ids_vivos(cliente, TIPO_SYNC))


def encolar_evaluacion(cliente, evaluacion_id, costo_estimado=None):
    """max_intentos=1: paga a Claude. False si ya había una viva."""
    return trabajos.encolar(job_id_evaluar(cliente), TIPO_EVALUAR, {"cliente": cliente, "evaluacion_id": evaluacion_id},
                            cliente=cliente, duracion_estimada=120, etapas=ETAPAS_EVALUAR, max_intentos=1,
                            costo_estimado=costo_estimado)


def evaluacion_en_curso(cliente):
    return trabajos.en_curso(job_id_evaluar(cliente))


TIPO_ANALIZAR = "tw_analizar_anuncio"
ETAPAS_ANALIZAR = [(idiomas.N_("Bajando el video"), 15), (idiomas.N_("Escuchando la voz"), 15),
                   (idiomas.N_("Analizando con Claude"), 70)]
_RE_ID = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


def id_valido(valor):
    """Canal o ad_id que puede ir en una URL y en un job_id. `fullmatch`, no `match` con `$`: `$` deja pasar un salto
    de línea final y «p1%0A» tendría su propio job_id (un segundo análisis pagado del mismo anuncio)."""
    return bool(_RE_ID.fullmatch(str(valor or "")))


def job_id_analisis(cliente, canal, ad_id):
    return f"{cliente}__tw_anuncio__{canal}__{ad_id}"


def encolar_analisis(cliente, analisis_id, canal, ad_id, costo_estimado=None):
    """max_intentos=1: paga a fal y a Claude. False si ese anuncio ya tenía uno vivo, o si el canal o el ad_id no son
    válidos (la garantía de «uno por anuncio» no depende de que cada ruta valide antes). `costo_estimado` (USD del
    proveedor, sin margen): en un proyecto que cobra, `trabajos.encolar` exige y reserva ese precio (cobros §5.1)."""
    if not (id_valido(canal) and id_valido(ad_id)):
        return False
    return trabajos.encolar(job_id_analisis(cliente, canal, ad_id), TIPO_ANALIZAR,
                            {"cliente": cliente, "analisis_id": int(analisis_id)}, cliente=cliente,
                            duracion_estimada=90, etapas=ETAPAS_ANALIZAR, max_intentos=1,
                            costo_estimado=costo_estimado)


def analisis_vivos(cliente):
    """job_ids de los análisis por anuncio en cola o corriendo (una consulta, para las barras de la galería)."""
    return cola.job_ids_vivos(cliente, TIPO_ANALIZAR)


def _evaluacion_de_cuenta(cliente, tienda_id):
    """El `resultado` de la evaluación de cuenta lista más nueva del mismo alcance, o None."""
    for e in datos.evaluaciones(cliente, limite=5):
        if e["estado"] == "lista" and (e.get("extra") or {}).get("tienda_id") == tienda_id:
            return e.get("resultado") or None
    return None


@registrar(TIPO_ANALIZAR)
def tw_analizar_anuncio(tarea):
    p = tarea["payload"]
    cliente, aid = p["cliente"], int(p["analisis_id"])
    referencia = f"tw_anuncio:{aid}{ref_sufijo(tarea)}"
    medios = {"visual": None, "fotogramas": 0, "transcripcion": None, "copy": False}
    usd_voz, usd_claude, entrada, salida, temporales = 0.0, 0.0, 0, 0, []
    claude_anotado = False
    # Todo va dentro del try, también leer la fila (revisión final, A4): cualquier fallo (al leerla, al marcar
    # «analizando», al poner el precio o al guardar la lista) deja la fila en `error` con palabras, nunca colgada en
    # en_cola/analizando.
    try:
        fila = datos.analisis_anuncio(cliente, aid)
        if fila is None:
            return gettext("Ese análisis ya no existe.")
        job_id = tarea.get("job_id") or job_id_analisis(cliente, fila["canal"], fila["ad_id"])
        foto = fila["foto"] or {}
        medios["copy"] = bool((foto.get("creativo") or {}).get("copy"))
        datos.actualizar_analisis(aid, estado="analizando", tarea_id=tarea.get("id"), error=None)
        trabajos.reportar(job_id, etapa=idiomas.N_("Bajando el video"))
        vis, temporales = mejorar.visuales(foto)
        medios.update(visual=vis["clase"], fotogramas=vis["fotogramas"])
        voz = None
        if mejorar.tiene_voz(foto):
            trabajos.reportar(job_id, etapa=idiomas.N_("Escuchando la voz"))
            try:
                voz = mejorar.transcribir(foto)
            except Exception as e:  # noqa: BLE001 — sin voz, Claude juzga por lo demás
                log.info("sin voz para el análisis %s: %s", aid, type(e).__name__)
            if voz:
                usd_voz = float(voz.get("costo_usd") or 0)
                if usd_voz:
                    gastos.registrar_seguro(cliente, "transcripcion", usd_voz, f"{referencia}:voz", proveedor="fal",
                                            detalle=gettext("la voz de un anuncio de Triple Whale"))
                medios["transcripcion"] = (voz.get("texto") or "")[:mejorar.MAX_TRANSCRIPCION] or None
        trabajos.reportar(job_id, etapa=idiomas.N_("Analizando con Claude"))
        entradas = dict(voz=voz, evaluacion_cuenta=_evaluacion_de_cuenta(cliente, fila["tienda_id"]),
                        aprendizajes=doctrina_aprendizajes.texto_para_prompt(proyectos.aprendizajes(cliente)),
                        productos=datos.top_productos(cliente, fila["tienda_id"], fila["desde"], fila["hasta"],
                                                      limite=analisis.MAX_PRODUCTOS))
        marca = proyectos.nombre_visible(cliente)
        texto = mejorar.armar(marca, fila, **entradas)
        # Los segundos de los fotogramas y de la voz son datos citables, también su parte entera («el segundo 31»).
        resultado, entrada, salida = mejorar.analizar(texto, vis["bloques"], idiomas.de_proyecto(cliente),
                                                      verificable_extra=mejorar.segundos_verificables(vis["bloques"], voz),
                                                      duracion_s=(foto.get("creativo") or {}).get("duracion_s"),
                                                      # Las cifras se contrastan con los datos que se le dieron, no con
                                                      # los números de las instrucciones (revisión del 2026-10-09).
                                                      verificable=mejorar.datos_verificables(marca, fila, **entradas))
        if vis["clase"] != "fotogramas":
            # Spec 2026-10-09 §2: sin fotogramas del video (un anuncio de imagen, o nada) hay copy pero no ganchos,
            # aunque Claude los mande: el clip arranca en un fotograma que Claude tiene que haber visto.
            resultado["ganchos"] = []
        # El gasto de Claude se anota UNA vez, antes de la última escritura: si esa falla, el except no lo repite.
        usd_claude = costo_real(entrada, salida)
        gastos.registrar_seguro(cliente, "evaluacion", usd_claude, referencia, proveedor="anthropic",
                                detalle=gettext("un anuncio de Triple Whale"))
        claude_anotado = True
        datos.actualizar_analisis(aid, estado="lista", resultado=resultado, medios=medios, error=None,
                                  usd=round(usd_voz + usd_claude, 4))
    except Exception as e:
        if not claude_anotado:
            # Los tokens vienen de la excepción (AnalisisInvalido) o, si Claude sí contestó y falló el precio, de aquí.
            entrada = int(getattr(e, "tokens_entrada", entrada) or 0)
            salida = int(getattr(e, "tokens_salida", salida) or 0)
            try:
                usd_claude = costo_real(entrada, salida) if (entrada or salida) else 0.0
            except Exception:  # noqa: BLE001 — sin precio no se inventa uno; el error de la fila sigue siendo en palabras
                log.exception("sin precio para los tokens del análisis %s", aid)
                usd_claude = 0.0
            if usd_claude:      # pagado y sin entregar: en un proyecto que cobra no se le cobra (cobros §3)
                gastos.registrar_seguro(cliente, "evaluacion", usd_claude, referencia, proveedor="anthropic",
                                        detalle=gettext("sin resultado usable"), entregado=False)
        mensaje = mejorar.texto_error(e)
        try:
            datos.actualizar_analisis(aid, estado="error", error=mensaje, medios=medios,
                                      usd=round(usd_voz + usd_claude, 4))
        except Exception as e_fila:  # noqa: BLE001 — la tarea igual termina en error con su mensaje; la fila colgada
            # sin tarea viva ya no bloquea el anuncio (panel.elegir_analisis) y la ruta la cierra al pedir otro.
            log.warning("el análisis %s no se pudo dejar en error: %s", aid, type(e_fila).__name__)
        raise RuntimeError(mensaje) from None
    finally:
        analisis.borrar_temporales(temporales)
    return gettext("Análisis listo: %(frase)s", frase=resultado["frase"])


@al_interrumpir(TIPO_ANALIZAR)
def _analizar_interrumpido(tarea, mensaje):
    p = tarea.get("payload") or {}
    if p.get("cliente") and p.get("analisis_id"):
        fila = datos.analisis_anuncio(p["cliente"], int(p["analisis_id"]))
        if fila and fila["estado"] in ("en_cola", "analizando"):
            datos.actualizar_analisis(int(p["analisis_id"]), estado="error",
                                      error=cola.recortar(cola.sin_token(str(mensaje)), 500))


def _sin_llave(cliente, tienda_id, texto):
    """Ningún mensaje nuestro lleva la llave, pero uno de un proveedor podría
    repetirla: se tacha el valor exacto de la llave DE ESA TIENDA antes de
    guardarlo o mostrarlo."""
    return triple_whale_tiendas.sin_llave(cliente, tienda_id, texto)


def _nombre_tienda(cliente, tienda):
    """«Noruega», o el dominio si la tienda no tiene país."""
    if tienda.get("pais"):
        return paises.nombre_pais(tienda["pais"], idiomas.de_proyecto(cliente))
    return tienda["dominio"]


@registrar(TIPO_SYNC)
def tw_sincronizar(tarea):
    cliente, tienda_id = tarea["payload"]["cliente"], tarea["payload"].get("tienda_id")
    tienda = triple_whale_tiendas.tienda(cliente, tienda_id) if tienda_id is not None else None
    if not tienda:
        return gettext("Esa tienda de Triple Whale ya no está conectada.")
    job_id = tarea.get("job_id") or job_id_sync(cliente, tienda_id)

    def progreso(i, n, desde, hasta):
        trabajos.reportar(job_id, etapa=idiomas.N_("Trayendo métricas"), progreso=i * 100.0 / max(1, n),
                          detalle=f"{desde} → {hasta}")

    try:
        r = sync.sincronizar(cliente, tienda_id, on_progreso=progreso)
    except (triple_whale.ErrorTripleWhale, cifrado.ErrorCifrado) as e:
        mensaje = cola.recortar(_sin_llave(cliente, tienda_id, cola.sin_token(str(e) or type(e).__name__)), 500)
        triple_whale_tiendas.actualizar_tienda(cliente, tienda_id, estado="error", error=mensaje)
        raise triple_whale.ErrorTripleWhale(mensaje) from None
    texto = gettext("Listo (%(tienda)s): %(n)s anuncio(s) y %(dias)s día(s) de la tienda, del %(desde)s al %(hasta)s.",
                    tienda=_nombre_tienda(cliente, tienda), n=r["anuncios"], dias=r["dias_tienda"],
                    desde=r["desde"], hasta=r["hasta"])
    if r["fallos"]:
        texto += " " + gettext("Sin %(partes)s: Triple Whale no aceptó esa consulta.",
                               partes=", ".join(sorted(r["fallos"])))
    # Los avisos miran «Todas las tiendas»: solo corren cuando no queda otra
    # copia del proyecto en cola o en curso, así la última que termina avisa
    # una vez y con todo al día. Un fallo aquí no tumba la copia.
    if [j for j in syncs_en_curso(cliente) if j != job_id]:
        return texto
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
    n = sum(encolar_sync(cliente, tienda_id) for cliente, tienda_id in triple_whale_tiendas.conectadas())
    return gettext("%(n)s sincronización(es) de Triple Whale en cola", n=n)


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
    trabajos.reportar(job_id, etapa=idiomas.N_("Buscando miniaturas"), detalle=gettext("%(n)s anuncio(s)", n=len(anuncios)))
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
    trabajos.reportar(job_id, etapa=idiomas.N_("Sacando fotogramas"))
    bloques, temporales = analisis.visuales(cliente, anuncios, medios, creatv)
    productos = datos.top_productos(cliente, extra.get("tienda_id"), fila["desde"], fila["hasta"],
                                    limite=analisis.MAX_PRODUCTOS)
    trabajos.reportar(job_id, etapa=idiomas.N_("Analizando con Claude"))
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
                                    detalle=gettext("sin resultado usable"), entregado=False)
        mensaje = analisis.texto_error(e)
        datos.actualizar_evaluacion(eid, estado="error", error=mensaje, usd=usd)
        raise RuntimeError(mensaje) from None
    finally:
        analisis.borrar_temporales(temporales)
    usd = costo_real(entrada, salida)
    gastos.registrar_seguro(cliente, "evaluacion", usd, referencia, proveedor="anthropic",
                            detalle=gettext("%(n)s anuncio(s) de Triple Whale", n=len(anuncios)))
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


# ------------------------------------------------ ganchos nuevos (spec 2026-10-09 §4.4–§4.6) ---

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIPO_GANCHOS_PREPARAR = "tw_ganchos_preparar"
TIPO_GANCHOS_VIGILAR = "tw_ganchos_vigilar"
TIPO_GANCHO_ARMAR = "tw_gancho_armar"
# Como la cadena de escenas y los lotes de Sprints: una pieza suelta de Crear (5) siempre pasa adelante.
PRIORIDAD_GANCHOS = 3
# Una fila recién creada tiene unos milisegundos sin su trabajo en la cola (la ruta guarda el job_id después de
# crear la tanda; el vigilante mueve a «armando» antes de encolar): solo se da por cortada pasado esto sin cambios.
GRACIA_S = 120
ETAPAS_GANCHOS = [(idiomas.N_("Bajando el video"), 40), (idiomas.N_("Lanzando los clips"), 60)]
ETAPAS_ARMAR = [(idiomas.N_("Armando el video"), 100)]


def job_id_preparar(cliente, analisis_id, tanda):
    return f"{cliente}__tw_ganchos_{int(analisis_id)}_t{int(tanda)}"


def job_id_armar(cliente, gancho_id):
    return f"{cliente}__tw_gancho_{int(gancho_id)}_armar"


def encolar_preparar(cliente, analisis_id, tanda):
    """La preparación de una tanda. Gratis en sí: cada clip lo cobra su pieza de Crear. max_intentos=1: si se corta,
    el vigilante cierra la tanda y la persona la vuelve a pedir con su precio a la vista. False si ya estaba viva."""
    return trabajos.encolar(job_id_preparar(cliente, analisis_id, tanda), TIPO_GANCHOS_PREPARAR,
                            {"cliente": cliente, "analisis_id": int(analisis_id), "tanda": int(tanda)},
                            cliente=cliente, duracion_estimada=90, etapas=ETAPAS_GANCHOS, max_intentos=1,
                            prioridad=PRIORIDAD_GANCHOS)


def _texto_error(e, generico=ganchos.ERROR_PREPARAR):
    """El motivo en palabras, en el idioma del proyecto (el worker ya lo pone), sin rutas ni tokens: lo nuestro
    (`ganchos.GanchoError`, un msgid) traducido; una descarga que falla, en palabras; lo demás, `generico` (el msgid
    de la etapa: preparar o armar) con solo el tipo de la excepción."""
    if isinstance(e, ganchos.GanchoError):
        mensaje = str(e)
        return gettext(mensaje)
    if isinstance(e, ErrorConector):
        mensaje = ganchos.ERROR_BAJAR
        return gettext(mensaje)
    return gettext(generico, error=type(e).__name__)


def _fotograma_en(ruta, segundo, destino):
    """El cuadro del segundo `segundo` como JPG (`-ss` antes de `-i`: busca por el índice sin decodificar lo de
    antes). GanchoError si ffmpeg falla o no escribe nada (un segundo más allá del final)."""
    if os.path.exists(destino):
        os.remove(destino)
    try:
        cortes.ffmpeg(["-ss", f"{float(segundo):.3f}", "-i", ruta, "-frames:v", "1", "-q:v", "2", destino], timeout=120)
    except RuntimeError:
        raise ganchos.GanchoError(ganchos.ERROR_FOTOGRAMA) from None
    if not (os.path.isfile(destino) and os.path.getsize(destino) > 0):
        raise ganchos.GanchoError(ganchos.ERROR_FOTOGRAMA)
    return destino


def _bajar_original(foto, carpeta):
    """El video del anuncio a `carpeta/original.mp4` (spec §4.4.1): solo desde `mejorar._url_voz` (el mp4 de
    files.triplewhale.com o el video de R2 de una pieza de Creatv), con `conectores.url.descargar_archivo` (60 MB,
    solo video/*, SSRF en cada redirección), y ffmpeg solo lo abre si ffprobe dice mp4/mov."""
    url = mejorar._url_voz(foto or {})
    if not url:
        raise ganchos.GanchoError(ganchos.MOTIVO_SIN_VIDEO)
    os.makedirs(carpeta, exist_ok=True)
    ruta = os.path.join(carpeta, "original.mp4")
    try:
        conector_url.descargar_archivo(url, ruta)
    except ErrorConector:
        raise ganchos.GanchoError(ganchos.ERROR_BAJAR) from None
    if not mejorar.es_mp4(ruta):
        raise ganchos.GanchoError(ganchos.ERROR_NO_MP4)
    return ruta


def _medidas(ruta):
    """Duración y tamaño del video bajado (ffprobe, sin subir nada): {"duracion_ms", "ancho", "alto"}."""
    info = cortes.ffprobe_json(ruta)
    video = next((s for s in info.get("streams") or [] if s.get("codec_type") == "video"), {})
    ancho, alto = encuadre.medidas_visibles(video)
    return {"duracion_ms": borrador.ms(cortes.duracion(ruta)), "ancho": ancho or None, "alto": alto or None}


def _material_original(cliente, ruta, foto, medidas=None):
    """El original como material del editor (spec §4.4.2): gratis, deduplicado por hash, en «Medios» (origen
    triple_whale) y con su proxy en cola si aún no lo tiene. Si los mismos bytes ya habían entrado por otra vía (una
    subida del editor) sin sus medidas o sin `tiene_audio`, se completan: sin `tiene_audio` el gancho saldría mudo.
    `medidas`: las de `_medidas(ruta)` si quien llama ya las tomó (la preparación mide antes de subir nada)."""
    medidas = medidas or _medidas(ruta)
    tiene_audio = mezcla.tiene_audio(ruta)
    h = materiales.hash_archivo(ruta)
    mat = materiales.subir(cliente, ruta, f"clientes/{cliente}/materiales/{h}.mp4", "video/mp4", tipo="video",
                           origen="triple_whale", **medidas,
                           extra={"nombre": str(foto.get("nombre") or foto.get("ad_id") or "")[:120],
                                  "tiene_audio": tiene_audio, "local": ruta, "ad_id": foto.get("ad_id")})
    faltan = {k: v for k, v in medidas.items() if v and not mat.get(k)}
    if "tiene_audio" not in (mat.get("extra") or {}):
        faltan["extra"] = {"tiene_audio": tiene_audio}
    if faltan:
        mat = materiales.actualizar_ficha(cliente, mat["hash"], **faltan) or mat
    if not mat.get("url_proxy"):
        trabajos.encolar(insumos.job_id_proxy(cliente, mat["id"]), "edicion_proxy",
                         {"cliente": cliente, "material_id": mat["id"]}, cliente=cliente, duracion_estimada=120,
                         max_intentos=3, prioridad=1)
    return mat


def _con_duracion(cliente, mat, carpeta):
    """`mat` con su `duracion_ms` (el documento y `verificar_recortes` la necesitan). Si le falta, se mide su copia
    local (o la de R2: los materiales son nuestros) y se anota en la ficha. GanchoError(ERROR_DURACION) si no se puede."""
    if mat.get("duracion_ms"):
        return mat
    try:
        local = (mat.get("extra") or {}).get("local")
        if not (local and os.path.isfile(local)):
            local = materiales.descargar(mat, os.path.join(carpeta, f"m{int(mat['id'])}.mp4"))
        duracion_ms = borrador.ms(cortes.duracion(local))
    except Exception:  # noqa: BLE001 — el motivo va en palabras, sin la ruta ni el error crudo
        log.exception("ganchos: no se pudo medir el material %s", mat.get("id"))
        raise ganchos.GanchoError(ganchos.ERROR_DURACION) from None
    if duracion_ms <= 0:
        raise ganchos.GanchoError(ganchos.ERROR_DURACION)
    return materiales.actualizar_ficha(cliente, mat["hash"], duracion_ms=duracion_ms) or dict(mat, duracion_ms=duracion_ms)


def _lanzar_gancho(cliente, aid, g, foto, ruta, duracion_s, original, carpeta):
    """Una variante (spec §4.4.3): el fotograma de arranque a R2, la sesión de Crear del clip (como
    `tareas.cadena.lanzar_escena` con imagen de arranque: Kling O3 Pro imagen a video, 3 s, sin sonido) y su lugar en
    la cola. El cf_id se anota ANTES de lanzar: una corrida repetida nunca lanza dos veces la misma fila. Cada anotación
    es un `mover` de «preparando» a «preparando» (un CAS: `actualizar_gancho` no mira el estado): si el vigilante ya
    cerró la fila, no se crea ni se cobra nada. SaldoInsuficiente sube a quien llama. True si quedó en la cola."""
    gid = g["id"]
    # Ruling 5: sin la duración al analizar, `fotograma_s` llega sin acotar; aquí se acota contra el video medido.
    segundo = mejorar.segundo_fotograma(g["fotograma_s"], duracion_s)
    jpg = _fotograma_en(ruta, segundo, os.path.join(carpeta, f"g{gid}.jpg"))
    frame_url = r2_uploader.upload_image(jpg, f"clientes/{cliente}/triple_whale/ganchos/{gid}.jpg")
    if not datos.mover(gid, "preparando", "preparando", frame_url=frame_url):
        log.warning("ganchos: el gancho %s dejó de estar preparando antes de su clip", gid)
        return False
    accion = gettext("Gancho %(n)s · %(nombre)s", n=g["n"], nombre=foto.get("nombre") or foto.get("ad_id") or "")[:200]
    cf_id = creative_flow.crear(cliente, [], [], [], accion, ganchos.SEGUNDOS, "", "A", referencias_urls=[],
                                platforms=[])
    creative_flow.actualizar(cliente, cf_id, prompt_relleno=g["prompt"], prompt_fuente=g["prompt"], tipo="video",
                             modelo=ganchos.MODELO,
                             aspect_ratio=ganchos.aspecto_kling(original.get("ancho"), original.get("alto")),
                             con_sonido=False, sonido_texto="", musica_estilo="", calidad="final",
                             imagen_inicial=frame_url, elementos=[],
                             referencias=[{"tipo": "imagen", "url": frame_url, "frame_url": frame_url,
                                           "etiqueta": "@Imagen 1", "titulo": ganchos.codigo(gid)}],
                             tw_gancho={"gancho_id": gid, "analisis_id": aid, "original_hash": original["hash"]})
    # `vacios`: si otra corrida ya le anotó su clip a la fila, este no la pisa.
    if not datos.mover(gid, "preparando", "preparando", vacios=("cf_id",), cf_id=cf_id):
        creative_flow.eliminar(cliente, cf_id)      # sin lanzar: nada reservado ni cobrado
        log.warning("ganchos: el gancho %s dejó de estar preparando (o ya tenía su clip) antes de lanzarlo", gid)
        return False
    entry = creative_flow.cargar(cliente).get(cf_id)
    if not flowplus_lanzar.lanzar(cliente, cf_id, entry, prioridad=PRIORIDAD_GANCHOS):
        # Contrato de `lanzar`: False = ya había una tarea viva de esa sesión, un clip que se está pagando. Se sigue
        # como en `_clip_salio`: la fila va a «generando» y nunca a error (nada pagado se pierde).
        log.warning("ganchos: el clip %s del gancho %s ya estaba en la cola", cf_id, gid)
    if not datos.mover(gid, "preparando", "generando", job_id=flowplus_lanzar.job_id(cliente, cf_id)):
        log.warning("ganchos: el clip %s del gancho %s quedó en la cola pero la fila ya no estaba preparando",
                    cf_id, gid)
    return True


@registrar(TIPO_GANCHOS_PREPARAR)
def tw_ganchos_preparar(tarea):
    p = tarea["payload"]
    cliente, aid, tanda = p["cliente"], int(p["analisis_id"]), int(p["tanda"])
    job_id = tarea.get("job_id") or job_id_preparar(cliente, aid, tanda)
    pendientes = [g for g in datos.ganchos_de_analisis(cliente, aid)
                  if g["tanda"] == tanda and g["estado"] == "preparando" and not g["cf_id"]]
    if not pendientes:
        return gettext("No había ganchos que preparar.")
    carpeta = os.path.join(BASE_DIR, "salidas", cliente, "tw_ganchos", f"{aid}_t{tanda}")
    lanzados = 0
    try:
        foto = (datos.analisis_anuncio(cliente, aid) or {}).get("foto") or {}
        trabajos.reportar(job_id, etapa=idiomas.N_("Bajando el video"))
        ruta = _bajar_original(foto, carpeta)
        # Se mide antes de subir: un original corto no deja nada en R2 ni un proxy en la cola.
        medidas = _medidas(ruta)
        duracion_s = (medidas["duracion_ms"] or 0) / 1000
        if duracion_s < ganchos.MIN_ORIGINAL_S:
            raise ganchos.GanchoError(ganchos.MOTIVO_CORTO)
        original = _material_original(cliente, ruta, foto, medidas)
        trabajos.reportar(job_id, etapa=idiomas.N_("Lanzando los clips"))
        for i, g in enumerate(pendientes):
            try:
                if _lanzar_gancho(cliente, aid, g, foto, ruta, duracion_s, original, carpeta):
                    lanzados += 1
            except SaldoInsuficiente as e:
                # Cobros (spec §4.4.4): esa variante y las que faltan quedan en error con la frase; las ya lanzadas
                # siguen su camino con su reserva.
                frase = e.frase_proyecto()
                for resto in pendientes[i:]:
                    datos.mover(resto["id"], "preparando", "error", error=frase)
                break
    except Exception as e:
        log.exception("ganchos: no se pudo preparar la tanda %s del análisis %s", tanda, aid)
        mensaje = _texto_error(e)
        for g in datos.ganchos_de_analisis(cliente, aid):
            if g["tanda"] != tanda or g["estado"] != "preparando":
                continue
            if _clip_salio(cliente, g):
                # Spec §4.4.4: solo las filas sin clip pasan a error; la que ya lo tiene en la cola (pagado o
                # pagándose) sigue su camino con el vigilante.
                datos.mover(g["id"], "preparando", "generando", job_id=flowplus_lanzar.job_id(cliente, g["cf_id"]))
            else:
                datos.mover(g["id"], "preparando", "error", error=mensaje)
        raise RuntimeError(mensaje) from None
    finally:
        # El material ya guardó su copia en R2 (spec §4.4.4).
        shutil.rmtree(carpeta, ignore_errors=True)
    return ngettext("%(num)s gancho en camino.", "%(num)s ganchos en camino.", lanzados)


def _quieto(g, segundos=GRACIA_S):
    """¿La fila lleva al menos `segundos` sin cambiar?"""
    try:
        return datetime.fromisoformat(g["actualizado_en"]) <= datetime.now() - timedelta(seconds=segundos)
    except (TypeError, ValueError):
        return True


def _clip_salio(cliente, g, sesiones=None):
    """¿El clip de esta fila ya salió (pagado o pagándose)? Su tarea de Crear sigue viva en la cola o, con las
    `sesiones` del proyecto, su sesión ya tiene el video. Solo lee: nunca lanza ni cobra nada. Lo usan la preparación
    que falla y el vigilante, para que una fila con su clip en camino no se dé por perdida (nada pagado se pierde)."""
    if not g.get("cf_id"):
        return False
    if trabajos.en_curso(flowplus_lanzar.job_id(cliente, g["cf_id"])):
        return True
    return ((sesiones or {}).get(g["cf_id"]) or {}).get("estado") == "video_listo"


def vigilar_gancho(cliente, g, sesiones):
    """Un paso de una variante viva (spec §4.5). `sesiones` = `creative_flow.cargar(cliente)` (una lectura por
    proyecto). Seguro de llamar de más: `datos.mover` es un CAS y nada avanza dos veces."""
    estado, gid = g["estado"], g["id"]
    if estado == "generando":
        entry = sesiones.get(g["cf_id"]) if g["cf_id"] else None
        if entry is None:
            datos.mover(gid, "generando", "error", error=gettext("El clip de este gancho ya no está en Crear."))
        elif entry.get("estado") in VIVOS_CREAR:
            return
        elif entry.get("estado") == "video_listo":
            job = job_id_armar(cliente, gid)
            if datos.mover(gid, "generando", "armando", job_id=job):
                try:
                    trabajos.encolar(job, TIPO_GANCHO_ARMAR, {"cliente": cliente, "gancho_id": gid}, cliente=cliente,
                                     duracion_estimada=60, etapas=ETAPAS_ARMAR, max_intentos=2, prioridad=1)
                except Exception:  # noqa: BLE001 — sin tarea nadie la armaría: queda en error con su motivo
                    log.exception("ganchos: no se pudo encolar el armado del gancho %s", gid)
                    datos.mover(gid, "armando", "error", error=gettext("No se pudo poner el armado en la cola."))
        else:
            datos.mover(gid, "generando", "error", error=entry.get("error") or gettext("El clip no se pudo generar."))
    elif estado == "produciendo":
        final = creative_flow.final_por_legado(cliente, g["final_id"]) if g["final_id"] else None
        if final is None:
            datos.mover(gid, "produciendo", "error", error=gettext("La final de este gancho ya no existe."))
        elif final.get("estado") in ("listo", "degradada") and final.get("video_url"):
            datos.mover(gid, "produciendo", "lista", url_final=final["video_url"])
        elif final.get("estado") == "error":
            datos.mover(gid, "produciendo", "error", error=final.get("error") or gettext("No se pudo producir el video."))
    elif estado in ("preparando", "armando"):
        # Sin job_id no hay trabajo que esperar (y `en_curso(None)` buscaría tareas sin job_id).
        vivo = bool(g["job_id"]) and trabajos.en_curso(g["job_id"])
        if vivo or not _quieto(g):
            return
        if estado == "armando":
            mensaje = ganchos.ERROR_ARMADO_CORTADO
            datos.mover(gid, "armando", "error", error=gettext(mensaje))
        elif _clip_salio(cliente, g, sesiones):
            # La preparación murió entre lanzar este clip y mover la fila: el clip ya se está pagando, se sigue
            # como cualquier otro.
            datos.mover(gid, "preparando", "generando", job_id=flowplus_lanzar.job_id(cliente, g["cf_id"]))
        else:
            # Si el clip llegó a correr y falló, su sesión de Crear dice por qué; si no, la preparación se cortó.
            sesion = (sesiones.get(g["cf_id"]) if g["cf_id"] else None) or {}
            mensaje = ganchos.ERROR_PREPARACION_CORTADA
            error = sesion.get("error") if sesion.get("estado") == "error" else None
            datos.mover(gid, "preparando", "error", error=error or gettext(mensaje))


@registrar(TIPO_GANCHOS_VIGILAR)
def tw_ganchos_vigilar(tarea):
    por_cliente = {}
    for g in datos.ganchos_vivos():
        por_cliente.setdefault(g["cliente"], []).append(g)
    for cliente, filas in por_cliente.items():
        # Periódica: no tiene proyecto propio; lo que guarda va en el idioma de cada proyecto (spec §8).
        try:
            with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
                # Una lectura de las sesiones por proyecto, y solo si alguna fila la necesita.
                hace_falta = any(g["estado"] == "generando" or (g["estado"] == "preparando" and g["cf_id"])
                                 for g in filas)
                sesiones = creative_flow.cargar(cliente) if hace_falta else {}
                for g in filas:
                    try:
                        vigilar_gancho(cliente, g, sesiones)
                    except Exception:  # noqa: BLE001 — una variante rota no frena a las demás (como cadena_vigilar)
                        log.exception("ganchos: falló el vigilante en el gancho %s", g["id"])
        except Exception:  # noqa: BLE001 — un proyecto roto no frena a los demás; se reintenta en 60 s
            log.exception("ganchos: el vigilante no pudo con el proyecto %s", cliente)
    return None


def _ultimo_intento(tarea):
    return int(tarea.get("intentos") or 1) >= int(tarea.get("max_intentos") or 1)


def _edicion_previa(cliente, g, idioma, pais):
    """La edición que un intento anterior ya anotó en la fila (ruling del arreglo 2): (edición, ya_encolada), o
    (None, False) si no hay o ya no es de este clip. «Ya encolada» = su render está vivo en la cola, la edición quedó
    producida o la final del clip ya pasó por un render (lista, degradada o en error): entonces no se vuelve a producir.
    Solo lee."""
    if not g.get("edicion_id"):
        return None, False
    previa = ediciones.cargar(cliente, g["edicion_id"])
    if previa is None or previa.get("cf_id") != g["cf_id"]:
        return None, False
    final = creative_flow.final_por_legado(cliente, f"{g['cf_id']}__{idioma}_{pais}")
    encolada = (previa.get("estado") == "producida"
                or trabajos.en_curso(tareas_edicion.job_id_producir(cliente, previa["id"], idioma, pais))
                or (final or {}).get("estado") in ("listo", "degradada", "error"))
    return previa, bool(encolada)


def _anotar_produciendo(cliente, g, edicion_id, final_id, idioma, pais):
    """La fila pasa a «produciendo» con los ids de su render. Con el render ya en la cola nada sube: un reintento
    crearía otra edición y reiniciaría la final que ya se está produciendo."""
    try:
        if not datos.mover(g["id"], "armando", "produciendo", edicion_id=edicion_id, final_id=final_id,
                           job_id=tareas_edicion.job_id_producir(cliente, edicion_id, idioma, pais)):
            log.warning("ganchos: el gancho %s dejó de estar armando mientras se armaba", g["id"])
    except Exception:  # noqa: BLE001 — con el render en cola, nunca un segundo intento
        log.exception("ganchos: el render del gancho %s está en la cola pero no se pudo anotar en su fila", g["id"])


def _armar(cliente, g):
    """Spec §4.6: el material del clip, el del original (por su hash; si ya no está, se vuelve a bajar), el documento,
    la edición, la versión congelada y su render. Nada de esto cobra. La edición se anota en la fila apenas se crea:
    un reintento la reusa (le guarda el documento nuevo) en vez de dejar un borrador huérfano y crear otra, y si su
    render ya salió solo anota los ids y termina."""
    from final_edition import biblioteca, rutas_editor  # tardío: arrastran el blueprint del editor
    fila = datos.analisis_anuncio(cliente, g["analisis_id"]) or {}
    foto = fila.get("foto") or {}
    carpeta = os.path.join(BASE_DIR, "salidas", cliente, "tw_ganchos", f"g{g['id']}")
    try:
        clip = _con_duracion(cliente, biblioteca.materializar_pieza(cliente, g["cf_id"], os.path.join(carpeta, "clip")),
                             carpeta)
        h = ((creative_flow.cargar(cliente).get(g["cf_id"]) or {}).get("tw_gancho") or {}).get("original_hash")
        original = materiales.buscar_hash(cliente, h) if h else None
        if original is None:
            original = _material_original(cliente, _bajar_original(foto, carpeta), foto)
        original = _con_duracion(cliente, original, carpeta)
        tienda = triple_whale_tiendas.tienda(cliente, fila["tienda_id"]) if fila.get("tienda_id") else None
        idioma, pais = ganchos.destino((tienda or {}).get("pais"), proyectos.pais(cliente))
        doc = ganchos.documento_gancho(clip, original, g["texto"],
                                       ganchos.formato_cercano(original.get("ancho"), original.get("alto")),
                                       idioma, pais, analisis_id=g["analisis_id"], gancho_id=g["id"])
        # Los recortes se revisan ANTES de crear la edición: un documento que no se puede producir no deja un
        # borrador huérfano en Final edition (revisión de la tarea 5).
        compilador.verificar_recortes(documento_mod.resolver(doc, idioma, pais),
                                      {int(clip["id"]): int(clip["duracion_ms"]),
                                       int(original["id"]): int(original["duracion_ms"])})
        previa, encolada = _edicion_previa(cliente, g, idioma, pais)
        if encolada:
            # Un intento anterior ya encoló su render (y murió antes de anotarlo): ni otra edición ni otro render.
            _anotar_produciendo(cliente, g, previa["id"], f"{g['cf_id']}__{idioma}_{pais}", idioma, pais)
            return ganchos.codigo(g["id"])
        if previa is not None:
            ediciones.guardar(cliente, previa["id"], doc, previa["version_n"])
            ed = ediciones.cargar(cliente, previa["id"])
        else:
            # El nombre del anuncio se recorta, el código no: es lo que une la edición con su variante.
            sufijo = f" · {ganchos.codigo(g['id'])}"
            nombre = str(foto.get("nombre") or foto.get("ad_id") or "")[:120 - len(sufijo)] + sufijo
            ed = ediciones.crear(cliente, "video", nombre, doc, cf_id=g["cf_id"], creada_por="triple_whale")
            # Anotada apenas existe (CAS: la fila sigue «armando»): si algo falla antes del render, el reintento la reusa.
            if not datos.mover(g["id"], "armando", "armando", edicion_id=ed["id"]):
                log.warning("ganchos: el gancho %s dejó de estar armando; su edición %s no se produce", g["id"],
                            ed["id"])
                return ganchos.codigo(g["id"])
        version = ediciones.versionar(cliente, ed["id"], motivo="producir")
        [producida] = rutas_editor.encolar_producciones(cliente, ed["id"], ed, version, [f"{idioma}_{pais}"])
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)
    # Desde aquí el render ya está en la cola: se anotan los ids en la fila y se termina, sin subir nada.
    _anotar_produciendo(cliente, g, ed["id"], producida["final_id"], idioma, pais)
    return ganchos.codigo(g["id"])


@registrar(TIPO_GANCHO_ARMAR)
def tw_gancho_armar(tarea):
    p = tarea["payload"]
    cliente, gid = p["cliente"], int(p["gancho_id"])
    g = datos.gancho(cliente, gid)
    if not g or g["estado"] != "armando":
        return gettext("No había nada que armar.")
    try:
        codigo = _armar(cliente, g)
    except Exception as e:
        log.exception("ganchos: no se pudo armar el gancho %s", gid)
        mensaje = _texto_error(e, ganchos.ERROR_ARMAR)
        if _ultimo_intento(tarea):
            # Con max_intentos=2 el primer fallo deja la fila en «armando» y la cola vuelve a intentar desde el
            # principio (spec §4.6.5); el último deja el motivo en la fila.
            datos.mover(gid, "armando", "error", error=mensaje)
        raise RuntimeError(mensaje) from None
    return gettext("Gancho armado: produciendo %(codigo)s.", codigo=codigo)
