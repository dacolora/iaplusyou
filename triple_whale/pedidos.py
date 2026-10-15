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
from meta_rendimiento import cuentas as meta_cuentas
from tareas import triple_whale as tareas_tw
from triple_whale import analisis, datos, mejorar, panel

log = logging.getLogger("creatv.triple_whale.pedidos")


def anuncio_del_alcance(alc, canal, ad_id):
    return next((x for x in alc["ev"]["anuncios"] if x["canal"] == canal and x["ad_id"] == ad_id), None)


# Lo que puede moverse el precio visto al volver del navegador: el de siempre (G3, ganchos, swap).
TOLERANCIA_PRECIO = 0.005


def coincide(costo_visto, usd):
    """True si el costo que vio la persona (ya pasado de precio a costo UNA vez, en la ruta, con
    `gastos.costo_de_precio`) es el de ahora. Sin uno de los dos, no: nunca se cobra un precio que no se mostró."""
    return costo_visto is not None and usd is not None and abs(float(costo_visto) - float(usd)) <= TOLERANCIA_PRECIO


def costos_de(cliente, alc, claves):
    """{(canal, ad_id): costo o None} del botón «Cómo mejorarlo» de cada clave que está en el alcance (las demás no
    salen): la MISMA cuenta que la tarjeta y el cobro (`panel.precio_analisis`, con las filas de análisis para la
    duración de un anuncio de Meta, G2). Dos lecturas, crezcan o no las claves. La usa el lote para comparar el total
    que vio la persona (PND-236)."""
    claves = [tuple(k) for k in claves if anuncio_del_alcance(alc, *k) is not None]
    if not claves:
        return {}
    creativos = datos.creativos(cliente, claves)
    filas = datos.analisis_de_anuncios(cliente, claves)
    return {k: panel.precio_analisis(creativos.get(k), filas.get(k, []), alc.get("fuente"))["usd"] for k in claves}


def pedir_analisis(cliente, alc, a, usuario, *, costo_visto):
    """Crea la fila con la foto y encola la tarea (spec §6.2). (ok, mensaje). `usuario` queda como `pedido_por`.

    `costo_visto`: el precio que mostró el botón, ya pasado a costo en la ruta (`gastos.costo_de_precio`). Obligatorio
    y por nombre (PND-236, decisión del lote 1, 2026-10-13, como G3 en «Evaluar con IA»): si falta o no es el de ahora
    (una pestaña abierta antes de un cambio de tarifa, el video que trajo su duración), no se crea ni se reserva nada y
    el aviso dice el precio de ahora; la tarjeta que devuelve la ruta ya lo muestra."""
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
    # mismo del botón (`panel.precio_analisis`, con las filas ya leídas: para un anuncio de Meta, la duración que guardó
    # un análisis anterior, G2); la reserva la hace el encolado.
    precio = panel.precio_analisis(creativos.get(clave), filas, alc.get("fuente"))
    usd = precio["usd"]
    # Primero el precio que vio la persona (PND-236): después de lo que no cobra (sin datos, en curso, fresco), que dice
    # lo suyo, y antes de pedir saldo o guardar nada.
    if not coincide(costo_visto, usd):
        return False, gettext("El precio cambió (ahora: %(precio)s). Revisa y vuelve a confirmar.", precio=precio["texto"])
    libro.exigir(cliente, usd, tipo="evaluacion")      # `tipo`: lo incluido en un plan (main, planes 2026-10-10)
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
    # El periodo pedido (0 = «Desde el inicio»): la copia de anuncios de Meta guarda 90 días y su «Desde el inicio» corre
    # cada día, así que `panel.mismo_alcance` lo usa para la fuente Meta (B2 de la revisión final de Rendimiento E2).
    foto["alcance_dias"] = alc.get("dias")
    # La moneda del anuncio si la trae (Meta: la de su cuenta); si no, la del alcance. Un alcance de Meta con cuentas en
    # monedas distintas no tiene una común (None) y el análisis guardaría None aunque el anuncio sí la sepa.
    aid = datos.crear_analisis(cliente, alc["tienda_id"], a["canal"], a["ad_id"], alc["desde"], alc["hasta"],
                               a.get("moneda") or alc["config"]["moneda"], foto, pedido_por=usuario)
    if alc.get("fuente") == "meta" and meta_cuentas.dueno(a.get("ad_account_id")) != cliente:
        # PND-295 (2026-10-12): la cuenta se soltó mientras se pedía. Soltarla borra las filas de fuente Meta de esa
        # cuenta y DESPUÉS la cuenta (y barre otra vez, `cuentas.elegir`); una fila creada después de eso no la
        # alcanzaría ninguna suelta futura (solo borran las cuentas que sueltan). Se comprueba DESPUÉS de crearla y
        # ANTES de encolar: si la cuenta ya no es del proyecto, la fila se borra aquí y no se reserva ni se cobra nada.
        datos.borrar_analisis(cliente, aid)
        return False, gettext("Esa cuenta de Meta ya no está en el proyecto.")
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


def pedir_lote(cliente, alc, claves, usuario, veredicto="", *, costos_vistos):
    """«Analizar los N que más gastaron» (spec §6.4): (encolados, fallos). `claves` son las que confirmó la persona
    (`claves_confirmadas` del formulario, que ya para en N_LOTE) y `veredicto` el filtro de la galería que las mostró:
    lo elegible se calcula con ese filtro, como cuando esto vivía en la ruta. Cobra solo confirmadas ∩ elegibles,
    nunca «los próximos N»: un segundo envío del mismo formulario no cobra nada (reglas 1 y 4).

    `costos_vistos` = {(canal, ad_id): costo} de cada clave, que quien llama ya comparó con el total que vio la persona
    (`pestana_rendimiento.galeria.pedir_lote`, PND-236): cada análisis se pide con el suyo, así entre esa comparación y
    el cobro tampoco cambia nada sin mostrarse.

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
            if pedir_analisis(cliente, alc, a, usuario, costo_visto=costos_vistos.get((canal, ad_id)))[0]:
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


def _entero(valor):
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return None


def pedir_evaluacion(cliente, alc_eval, usuario, *, n_visto, precio_visto):
    """«Evaluar con IA» (spec 2026-09-28 §8): la muestra de `alc_eval["ev"]`, su precio, la fila con su `extra` y la
    tarea (`max_intentos=1`, un job_id por proyecto). (ok, mensaje): `ok` es True si se encoló, False si ya hay una
    en curso o si el botón mostró otra cosa (aviso) y None si no hay anuncios con datos suficientes (nada que evaluar:
    la ruta lo avisa como error). Quien llama ya comprobó que no hay otra en curso (`tareas_tw.evaluacion_en_curso`);
    el encolado lo vuelve a mirar.

    `n_visto` y `precio_visto`: lo que mandó el botón (cuántos anuncios mostró y el PRECIO que vio la persona, con el
    margen), tal cual llegó del formulario. Obligatorios: G3 (revisión final de Rendimiento E2, guardián de gasto,
    2026-10-10) adoptó aquí la guarda E2-R6 de la evaluación de Meta (`meta_rendimiento.rutas.evaluar`)."""
    ev = alc_eval["ev"]
    muestra = analisis.muestra(ev)
    if not muestra:
        return None, gettext("Todavía no hay anuncios con datos suficientes para evaluar con IA.")
    precio = analisis.estimado(cliente, muestra)        # la misma cuenta que el botón (con los fotogramas de Creatv)
    usd = precio["usd"]
    # Primero el precio, después el cobro (G3): si falta el número o el precio que vio la persona, o la muestra o el
    # precio (el margen) cambiaron desde que lo vio, no se crea ni se reserva nada y se dice el precio de ahora. El precio
    # vuelve a costo UNA vez (`gastos.costo_de_precio`), con la tolerancia de siempre.
    visto = gastos.costo_de_precio(precio_visto)
    if _entero(n_visto) != len(muestra) or visto is None or usd is None or abs(visto - usd) > 0.005:
        return False, gettext("Revisa el precio y vuelve a confirmar: ahora son %(n)s anuncio(s) por %(precio)s.",
                              n=len(muestra), precio=precio["texto"])
    # Cobros (spec 2026-10-08 §5): sin saldo no se crea la evaluación; el
    # manejador común responde. La reserva la hace el encolado.
    libro.exigir(cliente, usd, tipo="evaluacion")      # `tipo`: lo incluido en un plan (main, planes 2026-10-10)
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
