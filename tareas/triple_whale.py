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

Un error de Triple Whale (llave revocada, tienda, red) deja ESA tienda en
`estado="error"` con el motivo sin token ni llave y sube para que la cola
reintente; las demás tiendas del proyecto no se enteran. Los avisos por correo
corren cuando termina la última copia del proyecto, no en cada una.
"""
import logging
import re

from flask_babel import gettext

import cifrado
import cola
import gastos
import idiomas
import proyectos
import trabajos
import triple_whale
import triple_whale_tiendas
from doctrina import aprendizajes as doctrina_aprendizajes
from nicho.avatares import costo_real
from tareas import al_interrumpir, ref_sufijo, registrar
from triple_whale import analisis, avisos, datos, mejorar, paises, sync

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


def encolar_evaluacion(cliente, evaluacion_id):
    """max_intentos=1: paga a Claude. False si ya había una viva."""
    return trabajos.encolar(job_id_evaluar(cliente), TIPO_EVALUAR, {"cliente": cliente, "evaluacion_id": evaluacion_id},
                            cliente=cliente, duracion_estimada=120, etapas=ETAPAS_EVALUAR, max_intentos=1)


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


def encolar_analisis(cliente, analisis_id, canal, ad_id):
    """max_intentos=1: paga a fal y a Claude. False si ese anuncio ya tenía uno vivo, o si el canal o el ad_id no son
    válidos (la garantía de «uno por anuncio» no depende de que cada ruta valide antes)."""
    if not (id_valido(canal) and id_valido(ad_id)):
        return False
    return trabajos.encolar(job_id_analisis(cliente, canal, ad_id), TIPO_ANALIZAR,
                            {"cliente": cliente, "analisis_id": int(analisis_id)}, cliente=cliente,
                            duracion_estimada=90, etapas=ETAPAS_ANALIZAR, max_intentos=1)


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
        texto = mejorar.armar(proyectos.nombre_visible(cliente), fila, voz=voz,
                              evaluacion_cuenta=_evaluacion_de_cuenta(cliente, fila["tienda_id"]),
                              aprendizajes=doctrina_aprendizajes.texto_para_prompt(proyectos.aprendizajes(cliente)),
                              productos=datos.top_productos(cliente, fila["tienda_id"], fila["desde"], fila["hasta"],
                                                            limite=analisis.MAX_PRODUCTOS))
        # Los segundos de los fotogramas y de la voz son datos citables, también su parte entera («el segundo 31»).
        resultado, entrada, salida = mejorar.analizar(texto, vis["bloques"], idiomas.de_proyecto(cliente),
                                                      verificable_extra=mejorar.segundos_verificables(vis["bloques"], voz))
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
            if usd_claude:
                gastos.registrar_seguro(cliente, "evaluacion", usd_claude, referencia, proveedor="anthropic",
                                        detalle=gettext("sin resultado usable"))
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
                                    detalle=gettext("sin resultado usable"))
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
