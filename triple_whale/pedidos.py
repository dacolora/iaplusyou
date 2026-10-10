"""El pedido pagado de un análisis con IA: «Cómo mejorarlo» de un anuncio, «Analizar los N que más gastaron» y
«Evaluar con IA» (spec 2026-10-08 tarjetas §6.2 y §6.4, spec 2026-09-28 §8).

Por qué vive aquí (Rendimiento E2, tarea 2, 2026-10-10): la pestaña Rendimiento ofrece el mismo pedido para los
anuncios cuya fuente es Meta (cuentas sin tienda), desde otro blueprint. Para no copiarlo, su cuerpo salió TAL CUAL de
`triple_whale/rutas.py` (que lo sigue usando con el alcance de Triple Whale) con cada garantía y su comentario: el
precio del botón antes de cobrar y Cobros (`libro.exigir` antes de guardar nada), nunca pagar dos veces lo mismo (A1),
una fila sin tarea no bloquea el anuncio (A4), el lote cobra solo lo confirmado Y aún elegible (B6) y para en el primero
sin saldo. Lo único que cambió es la frontera: `usuario` llega explícito en vez de leerse de `session`, y los avisos
(`flash`) y las redirecciones se quedan en las rutas; aquí se devuelven textos (ya traducidos: se llama dentro de una
petición) y cuentas.

`alc` es el dict de `triple_whale.panel.alcance` (`config`, `tienda`, `tienda_id`, `dias`, `canal`, `ev`, `desde`,
`hasta`, `params`) o el de `pestana_rendimiento.alcance_meta.alcance` (la misma forma, más `fuente = "meta"`): desde
Rendimiento E2 (tarea 4) la galería única de la pestaña pide cada anuncio con el alcance de SU fuente. `alc_eval` es lo que guarda una evaluación: `{"ev", "desde", "hasta", "moneda", "extra"}`.
"""
import logging

from flask_babel import gettext

import gastos
import idiomas
import triple_whale
from cobros import SaldoInsuficiente, libro
from tareas import triple_whale as tareas_tw
from triple_whale import analisis, datos, mejorar, panel

log = logging.getLogger("creatv.triple_whale.pedidos")


def anuncio_del_alcance(alc, canal, ad_id):
    return next((x for x in alc["ev"]["anuncios"] if x["canal"] == canal and x["ad_id"] == ad_id), None)


def pedir_analisis(cliente, alc, a, usuario):
    """Crea la fila con la foto y encola la tarea (spec §6.2). (ok, mensaje). `usuario` queda como `pedido_por`."""
    if a["veredicto"] == "sin_datos":
        return False, gettext("Todavía tiene muy pocos datos: espera a que gaste más.")
    # «En curso» es la TAREA viva, no la fila: una fila en_cola/analizando cuya tarea ya no existe (murió antes de su
    # try, un reinicio) bloqueaba el anuncio para siempre (revisión final, A4).
    clave = (a["canal"], a["ad_id"])
    if tareas_tw.job_id_analisis(cliente, *clave) in tareas_tw.analisis_vivos(cliente):
        return False, gettext("Ese anuncio ya se está analizando.")
    filas = datos.analisis_de_anuncios(cliente, [clave]).get(clave, [])
    # Uno listo y fresco de ESTE alcance no se paga otra vez: una pestaña vieja (o la de 7 días después de pasar por
    # 30) todavía muestra el botón (revisión final, A1).
    if panel.elegir_analisis(a, filas, alc)["fresco"]:
        return False, gettext("Ese anuncio ya tiene un análisis con estos datos.")
    ev = alc["ev"]
    claves = [(a["canal"], a["ad_id"])] + [(b["canal"], b["ad_id"]) for b in ev["anuncios"]
                                           if b["veredicto"] == "ganador" and b["canal"] == a["canal"]]
    creativos = datos.creativos(cliente, claves)
    # Cobros (spec 2026-10-08-cobros §5): sin saldo no se guarda nada ni se encola; SaldoInsuficiente sube al
    # manejador común (402 al fetch de la tarjeta, aviso con «Recargar saldo» al formulario). `usd` es el COSTO, el
    # mismo del botón (`panel.precio_analisis`); la reserva la hace el encolado.
    usd = panel.precio_analisis(creativos.get(clave))["usd"]
    libro.exigir(cliente, usd)
    if any(f["estado"] in panel.EN_CURSO for f in filas):
        with idiomas.en_idioma(idiomas.de_proyecto(cliente)):        # lo que se guarda, en el idioma del proyecto
            interrumpido = gettext("Se interrumpió antes de terminar.")
        datos.cerrar_colgados(cliente, a["canal"], a["ad_id"], interrumpido)
    canal_info = next((c for c in ev["cuenta"]["canales"] if c["canal"] == a["canal"]), None)
    cuenta = {"benchmarks": ev.get("benchmarks_canal", {}).get(a["canal"]) or ev["benchmarks"],
              "meta_roas": ev["meta_roas"],
              "modelo": alc["config"].get("modelo_atribucion"), "ventana": alc["config"].get("ventana_atribucion"),
              "cpa_canal": (canal_info["gasto"] / canal_info["pedidos"]) if canal_info and canal_info["pedidos"] else None}
    if "creatv" not in a and a["canal"] == triple_whale.CANAL_META:
        a["creatv"] = datos.piezas_creatv(cliente, [a["ad_id"]]).get(a["ad_id"])
    # La fuente de los números va en la foto (Rendimiento E2): con "meta" la tarea trae el anuncio de Meta antes de
    # mirarlo, con la cuenta del anuncio; el alcance de Triple Whale no trae `fuente`.
    foto = mejorar.foto(a, creativos.get((a["canal"], a["ad_id"])), cuenta,
                        mejorar.ganadores_del_canal(ev, a, creativos),
                        fuente=alc.get("fuente", analisis.FUENTE_DEFECTO), ad_account_id=a.get("ad_account_id"))
    foto["alcance_canal"] = alc.get("canal")     # el filtro de canal del panel también es del alcance (revisión final, A3)
    # La moneda del anuncio si la trae (Meta: la de su cuenta); si no, la del alcance. Un alcance de Meta con cuentas en
    # monedas distintas no tiene una común (None) y el análisis guardaría None aunque el anuncio sí la sepa.
    aid = datos.crear_analisis(cliente, alc["tienda_id"], a["canal"], a["ad_id"], alc["desde"], alc["hasta"],
                               a.get("moneda") or alc["config"]["moneda"], foto, pedido_por=usuario)
    try:
        encolada = tareas_tw.encolar_analisis(cliente, aid, a["canal"], a["ad_id"], costo_estimado=usd)
    except Exception:                             # SaldoInsuficiente incluida: se borra la fila y sigue su camino
        datos.borrar_analisis(cliente, aid)       # sin tarea no hay quien la termine: una fila en_cola bloquearía el anuncio
        raise
    if not encolada:
        datos.borrar_analisis(cliente, aid)
        return False, gettext("Ese anuncio ya se está analizando.")
    return True, gettext("Analizando «%(nombre)s» con IA…", nombre=a["nombre"])


def claves_confirmadas(valores, tope=None):
    """[(canal, ad_id)] de los `clave=<canal>:<ad_id>` del formulario del lote: cada mitad validada con `id_valido`,
    lo mal formado se ignora, no se repite ninguna y se para en `tope` claves válidas (por defecto `panel.N_LOTE`).
    Un conjunto para lo ya visto: un formulario con miles de claves repetidas no cuesta cuadrático (revisión final,
    B6)."""
    tope = panel.N_LOTE if tope is None else tope
    claves, vistas = [], set()
    for v in valores:
        if len(claves) >= tope:
            break
        canal, dos_puntos, ad_id = str(v or "").partition(":")
        clave = (canal, ad_id)
        if dos_puntos and clave not in vistas and tareas_tw.id_valido(canal) and tareas_tw.id_valido(ad_id):
            vistas.add(clave)
            claves.append(clave)
    return claves


def pedir_lote(cliente, alc, claves, usuario, veredicto=""):
    """«Analizar los N que más gastaron» (spec §6.4): (encolados, fallos). `claves` son las que confirmó la persona
    (`claves_confirmadas` del formulario, que ya para en N_LOTE) y `veredicto` el filtro de la galería que las mostró:
    lo elegible se calcula con ese filtro, como cuando esto vivía en la ruta. Cobra solo confirmadas ∩ elegibles,
    nunca «los próximos N»: un segundo envío del mismo formulario no cobra nada (reglas 1 y 4).

    Sin saldo para el siguiente, para y re-lanza `SaldoInsuficiente` con `.lote = (encolados, fallos)`, para que quien
    llama diga cuántos sí salieron antes de que el manejador común diga el resto."""
    g = panel.galeria(cliente, alc["ev"], veredicto or "", alcance=alc)
    # Solo lo que se confirmó (el precio que vio la persona) Y que hoy se puede analizar; a lo sumo N_LOTE.
    elegibles = g["lote"]["elegibles"]
    claves = [k for k in claves if k in elegibles]
    n = fallos = 0
    for canal, ad_id in claves:
        a = anuncio_del_alcance(alc, canal, ad_id)
        if a is None:
            continue
        try:
            if pedir_analisis(cliente, alc, a, usuario)[0]:
                n += 1
        except SaldoInsuficiente as e:
            # Sin saldo para el siguiente (cobros §5.4): los ya encolados siguen con su reserva, los demás no se piden y
            # el manejador común dice el resto con «Recargar saldo».
            e.lote = (n, fallos)
            raise
        except Exception as e:  # noqa: BLE001 — una que falla no tumba las demás (cada una es su propia tarea pagada)
            fallos += 1
            log.warning("lote de análisis: %s/%s no se pudo encolar (%s)", canal, ad_id, type(e).__name__)
    return n, fallos


def pedir_evaluacion(cliente, alc_eval, usuario):
    """«Evaluar con IA» (spec 2026-09-28 §8): la muestra de `alc_eval["ev"]`, su precio, la fila con su `extra` y la
    tarea (`max_intentos=1`, un job_id por proyecto). (ok, mensaje): `ok` es True si se encoló, False si ya hay una
    en curso (aviso) y None si no hay anuncios con datos suficientes (nada que evaluar: la ruta lo avisa como error).
    Quien llama ya comprobó que no hay otra en curso (`tareas_tw.evaluacion_en_curso`); el encolado lo vuelve a mirar."""
    ev = alc_eval["ev"]
    muestra = analisis.muestra(ev)
    if not muestra:
        return None, gettext("Todavía no hay anuncios con datos suficientes para evaluar con IA.")
    # Cobros (spec 2026-10-08 §5): sin saldo no se crea la evaluación; el
    # manejador común responde. La reserva la hace el encolado.
    usd = gastos.estimar("evaluacion_tw", n=len(muestra))["usd"]
    libro.exigir(cliente, usd)
    eid = datos.crear_evaluacion(cliente, alc_eval["desde"], alc_eval["hasta"], alc_eval["moneda"], muestra,
                                 pedido_por=usuario)
    datos.actualizar_evaluacion(eid, extra=alc_eval["extra"])
    try:
        encolada = tareas_tw.encolar_evaluacion(cliente, eid, costo_estimado=usd)
    except SaldoInsuficiente:
        datos.borrar_evaluacion(cliente, eid)
        raise
    if not encolada:
        datos.borrar_evaluacion(cliente, eid)
        return False, gettext("Ya hay una evaluación con IA en curso.")
    return True, gettext("Evaluando %(n)s anuncio(s) con IA…", n=len(muestra))
