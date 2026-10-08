"""
Tareas de la investigación automática del nicho (spec Parte 3 §1, §9) y el
motor que encadena los pasos.

  nicho_inv_consultas   -> Claude convierte el tema en búsquedas, hasta el tope aprobado (max_intentos=2)
  nicho_inv_buscar      -> el actor de búsqueda de UNA plataforma trae productos (max_intentos=1: cobra)
  nicho_inv_seleccionar -> Claude marca cuáles son del nicho y elige los de más reseñas (max_intentos=2)
  resenas:<plataforma>, redes:<red> y generar corren en tareas/nicho.py
  (`nicho_recolectar` con `investigacion: true`, `nicho_generar_avatares` con `auto: true`).

`avanzar(cliente, estudio_id)` lee `extra.investigacion`, toma el primer paso
pendiente del `orden` y lo encola con un job_id determinista; los pasos que
no necesitan tarea (reseñas sin productos elegidos, red sin llave) se anotan
y se sigue en el mismo llamado. Cada tarea termina llamando a `avanzar`.
Todo gasto se registra con el id de la tarea; Claude va por
`nicho.avatares._llamar` (modelo del proyecto).
"""
import contextvars
import functools
import logging

from flask_babel import gettext

import cola
import gastos
import idiomas
import trabajos
from cobros import SaldoInsuficiente
from idiomas import N_
from nicho import avatares, datos
from nicho import fuentes as fuentes_registro
from nicho import investigacion as inv
from nicho.fuentes import plataformas
from tareas import al_interrumpir, ref_sufijo, registrar

log = logging.getLogger(__name__)
ETAPAS_CONSULTAS = [(N_("Consultas"), 60)]
ETAPAS_BUSCAR = [(N_("Buscando"), 240), (N_("Guardando"), 10)]
ETAPAS_SELECCION = [(N_("Eligiendo productos"), 60)]
MAX_SALTOS = 12        # pasos sin tarea que `avanzar` puede cerrar en un solo llamado
NOTA_IDIOMA = N_("sin búsquedas en el idioma de la tienda: se usaron las del país")


def _ultimo_intento(tarea):
    return int(tarea.get("intentos") or 1) >= int(tarea.get("max_intentos") or 1)


def _marcar(cliente, eid, paso, estado, **kw):
    return datos.actualizar_investigacion(cliente, eid, lambda i: inv.marcar_paso(i, paso, estado, **kw))


def _detener(cliente, eid, motivo):
    return datos.actualizar_investigacion(cliente, eid, lambda i: inv.detener(i, motivo))


def _activa(cliente, eid):
    """(estudio, investigacion) si hay una investigación viva; (None, None) si no."""
    est = datos.estudio(cliente, eid)
    i = datos.investigacion(cliente, eid) if est else {}
    if not est or not i or i.get("estado") in ("lista", "detenida", "interrumpida"):
        return None, None
    return est, i


def _interrumpir(cliente, eid, e):
    """La cadena no puede seguir sola (no se encoló el siguiente paso, o una
    escritura se cayó después de pagar en el último intento): la investigación
    queda `interrumpida` con el error y «Reanudar» la retoma, en vez de quedar
    con un estado vivo y nada en la cola. Nunca lanza."""
    try:
        with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
            error = cola.recortar(cola.sin_token(e), 300)
        datos.actualizar_investigacion(
            cliente, eid, lambda i: i if (not i or i.get("estado") in ("lista", "detenida", "interrumpida"))
            else {**i, "estado": "interrumpida", "ultimo_error": error})
    except Exception:  # noqa: BLE001 — si hasta esto falla, queda en el log
        log.exception("No se pudo dejar interrumpida la investigación %s de %s", eid, cliente)


# El job_id de la tarea que cierra su paso y pide el siguiente (cobros, revisión
# final 2026-10-08): su reserva sigue viva mientras corre, pero ya está gastada;
# `_avanzar` la excluye del disponible (`libro.exigir(excluir_job=)`). Va en una
# ContextVar para no cambiar la firma de `avanzar`, que también llaman las rutas.
_EXCLUIR_JOB = contextvars.ContextVar("investigacion_excluir_job", default=None)


def _avanzar_seguro(cliente, eid, excluir_job=None):
    """`avanzar` después de cerrar un paso. Si revienta, la investigación queda
    interrumpida (con Reanudar) y la tarea que ya hizo su parte termina bien.
    `excluir_job`: el job_id de la tarea que llama (su reserva no cuenta)."""
    token = _EXCLUIR_JOB.set(excluir_job)
    try:
        return avanzar(cliente, eid)
    except Exception as e:  # noqa: BLE001
        log.exception("avanzar falló en la investigación %s de %s", eid, cliente)
        _interrumpir(cliente, eid, e)
        return None
    finally:
        _EXCLUIR_JOB.reset(token)


def red_de_la_cadena(paso_de):
    """Decorador de las tareas de la cadena. Si la tarea sale con error en su
    ÚLTIMO intento sin haber cerrado su paso (quedó pendiente o en curso), la
    investigación queda interrumpida (Reanudar) en vez de trabada con un estado
    vivo y nada en la cola (F2). Un paso que la tarea sí cerró (p. ej. `error`
    de una tienda caída, que ya siguió la cadena) no se toca. `paso_de(payload)`
    -> el paso de la cadena, o None si la tarea no es de la cadena."""
    def deco(fn):
        @functools.wraps(fn)
        def envuelta(tarea):
            try:
                return fn(tarea)
            except Exception as e:
                if _ultimo_intento(tarea):
                    try:
                        p = tarea.get("payload") or {}
                        paso = paso_de(p)
                        if paso:
                            cliente, eid = p["cliente"], int(p["estudio_id"])
                            estado_paso = (((datos.investigacion(cliente, eid).get("pasos") or {}).get(paso)) or {}).get("estado")
                            if estado_paso in (None, "pendiente", "en_curso"):
                                _interrumpir(cliente, eid, e)
                    except Exception:  # noqa: BLE001 — la red nunca tapa el error original
                        log.exception("La red de la cadena no pudo revisar la tarea %s", tarea.get("id"))
                raise
        return envuelta
    return deco


def _o_interrumpir(tarea, cliente, eid, fn):
    """Corre `fn` (las escrituras que siguen a un pago). Si revienta en el
    último intento, la investigación queda interrumpida antes de relanzar; con
    intentos por delante, el reintento del worker la retoma."""
    try:
        return fn()
    except Exception as e:
        if _ultimo_intento(tarea):
            _interrumpir(cliente, eid, e)
        raise


def _gasto_claude(cliente, eid, tarea, paso, entrada, salida, detalle, entregado=True):
    """Registra la llamada a Claude (tipo `investigacion`) y devuelve su costo.
    `entregado=False` para un intento fallido: el costo queda, al cliente no se
    le cobra (cobros §3.4)."""
    if entrada + salida <= 0:
        return 0.0
    usd = inv.costo_claude(entrada, salida)
    gastos.registrar_seguro(cliente, "investigacion", usd, f"investigacion:{eid}:{paso}{ref_sufijo(tarea)}", detalle=detalle,
                            proveedor="anthropic", entregado=entregado, extra={"tokens_entrada": entrada, "tokens_salida": salida, "modelo": avatares.modelo_actual()})
    return usd


def _gasto_apify(cliente, eid, tarea, paso, fuente, tarifa, nota=""):
    """Ítems crudos × precio del actor + el arranque de cada corrida lanzada
    (aprox.; una corrida con arranque cobra aunque no traiga nada), con las
    corridas para rastrear el cobro. Devuelve el costo."""
    n = int(getattr(fuente, "resultados", 0) or 0)
    corridas = [c.get("run_id") for c in (getattr(fuente, "corridas", None) or []) if c.get("run_id")]
    usd = plataformas.costo(n, len(corridas), tarifa)
    if usd <= 0:
        return 0.0
    detalle = gettext("Apify %(actor)s: %(n)s resultado(s) aprox.", actor=idiomas.traducir(tarifa["nombre"]), n=n)
    gastos.registrar_seguro(cliente, "recoleccion", usd, f"recoleccion:{eid}:{paso}{ref_sufijo(tarea)}",
                            detalle=detalle + (f" — {nota}" if nota else ""),
                            proveedor="apify", extra={"actor": tarifa["actor"], "resultados": n, "usd_por_resultado": tarifa["usd_por_resultado"],
                                                      "usd_por_corrida": tarifa.get("usd_por_corrida", 0), "corridas": corridas})
    return usd


def _ref_intento(paso, tarea):
    """Referencia del intento que sí pagó Claude: el primero usa `paso` tal
    cual (spec); del segundo en adelante, `paso:i<intento>` -- dos intentos de
    la MISMA tarea (uno falló, el otro pagó) no se pisan entre sí."""
    intentos = int(tarea.get("intentos") or 1)
    return paso if intentos <= 1 else f"{paso}:i{intentos}"


def _marcar_acumulando(cliente, eid, paso, estado, usd, **kw):
    """Como `_marcar`, pero el `usd` dado se SUMA al que ya tenía el paso: un
    paso que se retoma (interrumpido, reanudado) no pierde lo que ya había
    cobrado un intento anterior."""
    def _fn(i):
        previo = float(((i.get("pasos") or {}).get(paso) or {}).get("usd") or 0)
        return inv.marcar_paso(i, paso, estado, usd=round(previo + usd, 4), **kw)
    return datos.actualizar_investigacion(cliente, eid, _fn)


def _propio_o_choque(cliente, estudio_id, job_id, ok, bandera):
    """`encolar_recolectar`/`encolar_generar` devolvieron `ok`. Esos job_id se
    comparten con los botones manuales del panel ("recolectar esta fuente",
    "generar avatares"): si `ok` es False, el trabajo vivo con ese id puede
    ser el mismo paso de la cadena (su payload trae `bandera`: idempotente,
    la cadena sigue como si hubiera encolado) o un botón manual corriendo (la
    cadena no puede avanzar por encima de él: se interrumpe con un aviso
    claro en vez de fingir que encoló). Devuelve True si el llamador debe
    tratarlo como encolado con éxito."""
    if ok:
        return True
    fila = cola.consultar_por_job(job_id)
    if ((fila or {}).get("payload") or {}).get(bandera):
        return True
    with idiomas.en_idioma(idiomas.de_proyecto(cliente)):        # el hook no pasa por worker.ejecutar
        motivo = gettext("Otra tarea de este estudio está corriendo; reanuda la investigación cuando termine.")
    datos.actualizar_investigacion(cliente, estudio_id, lambda i: {**i, "estado": "interrumpida", "ultimo_error": motivo})
    return False


def _fallo_claude(cliente, eid, tarea, paso, e, motivo_de, ref=None):
    """Camino de fallo de consultas/seleccionar: gasto de lo cobrado, paso
    `pendiente` si queda intento, `error` + detenida si no. Devuelve el mensaje."""
    entrada, salida = int(getattr(e, "tokens_entrada", 0) or 0), int(getattr(e, "tokens_salida", 0) or 0)
    # Referencia propia por intento: el reintento usa la misma tarea (mismo :t<id>) y registrar_seguro
    # es idempotente por referencia; sin esto el cobro del intento bueno se perdería.
    usd = _gasto_claude(cliente, eid, tarea, f"{ref or paso}:fallido{int(tarea.get('intentos') or 1)}", entrada, salida,
                        gettext("intento fallido"), entregado=False)
    mensaje = cola.recortar(cola.sin_token(e), 300)

    def _fn(i):
        previo = float(((i.get("pasos") or {}).get(paso) or {}).get("usd") or 0)
        if _ultimo_intento(tarea):
            return inv.detener(inv.marcar_paso(i, paso, "error", usd=round(previo + usd, 4), aviso=mensaje), motivo_de(mensaje))
        return inv.marcar_paso(i, paso, "pendiente", usd=round(previo + usd, 4), aviso=mensaje)
    datos.actualizar_investigacion(cliente, eid, _fn)
    return mensaje


# ------------------------------------------------------------- avanzar ---

def avanzar(cliente, estudio_id):
    """Encola el siguiente paso pendiente (idempotente: `trabajos.encolar`
    rechaza un job vivo). Devuelve el paso encolado o None. Sin saldo (cobros,
    spec 2026-10-08 §5.4) la investigación queda detenida con la frase y nada
    se encola; «Reanudar» la retoma tras recargar. Corre en el worker (al
    cerrar cada paso) y en las rutas de iniciar y reanudar: nunca lanza por saldo."""
    try:
        return _avanzar(cliente, estudio_id)
    except SaldoInsuficiente as e:
        _detener(cliente, estudio_id, e.frase_proyecto())
        return None


def _costo_paso(est, i, paso, n_productos=None):
    """Costo del proveedor (USD, sin margen) del paso que se va a encolar, para
    que `trabajos.encolar` exija y reserve SU precio (cobros, revisión final
    2026-10-08: el total aprobado al iniciar no se reserva, y sin esto cada
    paso pedía solo una milésima y uno de varios dólares corría con centavos de
    saldo). El peor caso, con las mismas cuentas que el estimado aprobado
    (`inv.estimar`). None si no se puede calcular: basta con saldo positivo."""
    try:
        topes = {**inv.TOPES_DEFECTO, **(i.get("topes") or {})}
        pais = i.get("pais") or est.get("pais") or ""
        plat = i.get("plataformas") or []
        if paso in ("consultas", "seleccionar"):
            entrada, salida = inv._tokens_claude(len(plat), topes, len(inv.idiomas_necesarios(pais, plat)))
            return inv.costo_claude(entrada, salida)
        clave = paso.split(":", 1)[1] if ":" in paso else ""
        if paso.startswith("buscar:"):
            return plataformas.estimar_busqueda(clave, topes["consultas"], topes["productos_por_consulta"], pais)
        if paso.startswith("resenas:"):
            return plataformas.estimar_resenas(clave, n_productos or topes["productos_elegidos"],
                                               topes["resenas_por_producto"], pais)
        if paso == "generar":
            maximo = float(avatares.estimar_costo_maximo()["usd"])
            tope = round(float(i.get("aprobado_usd") or 0) - float(i.get("gastado_usd") or 0), 4)
            return min(maximo, tope) if tope > 0 else maximo
    except Exception as e:  # noqa: BLE001 — sin estimado no se inventa un precio
        log.warning("sin estimado del paso %s: %s", paso, type(e).__name__)
    return None


def _avanzar(cliente, estudio_id):
    from tareas import nicho as tareas_nicho      # tareas.nicho importa este módulo: import perezoso
    excluir = _EXCLUIR_JOB.get()
    for _ in range(MAX_SALTOS):
        est = datos.estudio(cliente, estudio_id)
        i = datos.investigacion(cliente, estudio_id) if est else {}
        paso = inv.siguiente_paso(i)
        if paso is None:
            return None
        if est.get("archivado"):
            _detener(cliente, estudio_id, N_("estudio archivado"))
            return None
        base = {"cliente": cliente, "estudio_id": int(estudio_id)}
        if paso == "consultas":
            trabajos.encolar(datos.job_id_inv(cliente, estudio_id, paso), "nicho_inv_consultas", base, cliente=cliente,
                             duracion_estimada=60, etapas=ETAPAS_CONSULTAS, max_intentos=2,
                             costo_estimado=_costo_paso(est, i, paso), excluir_job=excluir)
            return paso
        if paso.startswith("buscar:"):
            trabajos.encolar(datos.job_id_inv(cliente, estudio_id, paso), "nicho_inv_buscar", {**base, "plataforma": paso.split(":", 1)[1]},
                             cliente=cliente, duracion_estimada=300, etapas=ETAPAS_BUSCAR, max_intentos=1,
                             costo_estimado=_costo_paso(est, i, paso), excluir_job=excluir)
            return paso
        if paso == "seleccionar":
            if not (i.get("plataformas") or []):
                # Solo redes, sin ninguna plataforma buscada: no hay productos que
                # juzgar -- ni un solo dato pagado a Claude por nada (Ruling 16).
                _marcar(cliente, estudio_id, paso, "vacio", aviso=N_("sin plataformas"))
                continue
            trabajos.encolar(datos.job_id_inv(cliente, estudio_id, paso), "nicho_inv_seleccionar", base, cliente=cliente,
                             duracion_estimada=60, etapas=ETAPAS_SELECCION, max_intentos=2,
                             costo_estimado=_costo_paso(est, i, paso), excluir_job=excluir)
            return paso
        if paso.startswith("resenas:"):
            plat = paso.split(":", 1)[1]
            elegidos = (i.get("elegidos") or {}).get(plat) or []
            productos = [p for p in datos.productos_nicho(cliente, estudio_id, plataforma=plat, fuente_ids=elegidos) if not p["resenas_traidas"]]
            if not productos:
                _marcar(cliente, estudio_id, paso, "vacio", nuevos=0, aviso=N_("sin productos elegidos") if not elegidos else N_("reseñas ya traídas"))
                continue
            params = {"productos": [{"fuente_id": p["fuente_id"], "url": p["url"], "titulo": p["titulo"]} for p in productos],
                      "resenas_por_producto": int((i.get("topes") or {}).get("resenas_por_producto") or inv.TOPES_DEFECTO["resenas_por_producto"]),
                      "pais": i.get("pais") or est.get("pais") or ""}
            job_id = datos.job_id_recolectar(cliente, estudio_id, plat)
            ok = tareas_nicho.encolar_recolectar(cliente, estudio_id, plat, params, investigacion=True,
                                                 costo_estimado=_costo_paso(est, i, paso, len(productos)),
                                                 excluir_job=excluir)
            if _propio_o_choque(cliente, estudio_id, job_id, ok, "investigacion"):
                return paso
            return None
        if paso.startswith("redes:"):
            red = paso.split(":", 1)[1]
            if fuentes_registro.llaves_faltantes(red):
                _marcar(cliente, estudio_id, paso, "saltado", nuevos=0, aviso=N_("sin llave"))
                continue
            job_id = datos.job_id_recolectar(cliente, estudio_id, red)
            ok = tareas_nicho.encolar_recolectar(cliente, estudio_id, red, inv.params_redes(red, i), investigacion=True,
                                                 excluir_job=excluir)
            if _propio_o_choque(cliente, estudio_id, job_id, ok, "investigacion"):
                return paso
            return None
        # generar
        n = len(datos.comentarios_para_generar(cliente, estudio_id))
        if n < avatares.MIN_COMENTARIOS:
            _detener(cliente, estudio_id, gettext("solo hay %(n)s comentarios; hacen falta %(min)s para los avatares", n=n, min=avatares.MIN_COMENTARIOS))
            return None
        tope = round(float(i.get("aprobado_usd") or 0) - float(i.get("gastado_usd") or 0), 4)
        job_id = datos.job_id_generar(cliente, estudio_id)
        ok = tareas_nicho.encolar_generar(cliente, estudio_id, auto=True, tope_usd=tope,
                                          costo_estimado=_costo_paso(est, i, paso), excluir_job=excluir)
        if _propio_o_choque(cliente, estudio_id, job_id, ok, "auto"):
            return paso
        return None
    return None


# ------------------------------------------------------------- tareas ---

@registrar("nicho_inv_consultas")
@red_de_la_cadena(lambda p: "consultas")
def ejecutar_consultas(tarea):
    p = tarea["payload"]
    cliente, eid = p["cliente"], int(p["estudio_id"])
    est, i = _activa(cliente, eid)
    if est is None:
        return gettext("La investigación no está activa.")
    if ((i.get("pasos") or {}).get("consultas") or {}).get("estado") == "hecho":
        # Reintento (p. ej. avanzar() reventó DESPUÉS de guardar las consultas):
        # ya están pagadas y guardadas -- no se vuelve a llamar a Claude (I3).
        _avanzar_seguro(cliente, eid, excluir_job=tarea.get("job_id"))
        return gettext("Consultas: %(consultas)s", consultas=", ".join(i.get("consultas") or []))
    if not (est.get("tema") or "").strip():
        _detener(cliente, eid, N_("sin tema"))
        return gettext("El estudio no tiene tema.")
    topes = {**inv.TOPES_DEFECTO, **(i.get("topes") or {})}
    pais = i.get("pais") or est.get("pais") or "CO"
    job = tarea.get("job_id") or datos.job_id_inv(cliente, eid, "consultas")
    cola.reportar(job, etapa=N_("Consultas"))
    _marcar(cliente, eid, "consultas", "en_curso")
    try:
        # el tope aprobado viaja a Claude (F3); una lista por idioma de búsqueda, en UNA llamada (Parte 4 §2)
        idiomas_busqueda = inv.idiomas_necesarios(pais, i.get("plataformas") or [])
        por_idioma, entrada, salida = inv.consultas_por_idioma_con_claude(est, pais, topes["consultas"], idiomas_busqueda)
    except Exception as e:
        _fallo_claude(cliente, eid, tarea, "consultas", e, lambda m: gettext("Claude no pudo escribir las consultas: %(e)s", e=m))
        raise
    consultas = por_idioma[idiomas_busqueda[0]]
    usd = _gasto_claude(cliente, eid, tarea, _ref_intento("consultas", tarea), entrada, salida,
                        gettext("%(n)s consultas", n=sum(len(v) for v in por_idioma.values())))

    def _fn(x):
        previo = float(((x.get("pasos") or {}).get("consultas") or {}).get("usd") or 0)
        return inv.marcar_paso({**x, "consultas": consultas, "consultas_por_idioma": por_idioma}, "consultas", "hecho",
                               usd=round(previo + usd, 4), aviso="")
    _o_interrumpir(tarea, cliente, eid, lambda: datos.actualizar_investigacion(cliente, eid, _fn))
    _avanzar_seguro(cliente, eid, excluir_job=tarea.get("job_id"))
    return gettext("Consultas: %(consultas)s", consultas=", ".join(consultas))


@registrar("nicho_inv_buscar")
@red_de_la_cadena(lambda p: f"buscar:{p.get('plataforma')}")
def ejecutar_buscar(tarea):
    p = tarea["payload"]
    cliente, eid, plat = p["cliente"], int(p["estudio_id"]), p["plataforma"]
    est, i = _activa(cliente, eid)
    if est is None:
        return gettext("La investigación no está activa.")
    paso = f"buscar:{plat}"
    topes = {**inv.TOPES_DEFECTO, **(i.get("topes") or {})}
    pais = i.get("pais") or est.get("pais") or ""
    # Las búsquedas en el idioma de la tienda (Parte 4 §2: otro mercado, o AliExpress en inglés); si Claude no las
    # escribió, las del país y el paso lo avisa. Como máximo el tope aprobado: lo que el estimado cobró (F3).
    idioma = plataformas.idioma_busqueda(plat, pais)
    propias = [c for c in ((i.get("consultas_por_idioma") or {}).get(idioma) or []) if c]
    sin_propias = not propias and idioma != plataformas.idioma(pais)
    consultas = (propias or [c for c in (i.get("consultas") or []) if c])[:max(1, int(topes["consultas"]))]
    if not consultas:
        _detener(cliente, eid, N_("sin consultas"))
        return gettext("No hay consultas para buscar.")
    job = tarea.get("job_id") or datos.job_id_inv(cliente, eid, paso)

    def reportar(etapa, detalle=None):
        cola.reportar(job, etapa=etapa, detalle=detalle)

    _marcar(cliente, eid, paso, "en_curso")
    fuente = None
    productos, guardado = [], {"nuevos": 0, "actualizados": 0}
    try:
        fuente = fuentes_registro.por_tipo(plat)()               # adentro del try: si esto revienta, el paso igual cierra (R17)
        for prod in fuente.buscar(consultas, pais, topes["productos_por_consulta"], reportar):
            productos.append(prod)
        reportar(N_("Guardando"))
        guardado = datos.guardar_productos_nicho(cliente, eid, plat, productos)
    except Exception as e:
        try:
            if productos:
                guardado = datos.guardar_productos_nicho(cliente, eid, plat, productos)      # lo leído nunca se pierde
        except Exception:  # noqa: BLE001 — si la base también falla, manda el error original
            log.exception("No se pudieron guardar los productos de %s", plat)
        usd = (_gasto_apify(cliente, eid, tarea, paso, fuente, fuente.tarifa_busqueda(), nota=gettext("intento fallido"))
               if fuente is not None else 0.0)                   # la fuente ni se construyó: nada que cobrar
        mensaje = cola.recortar(cola.sin_token(e), 300)
        try:
            _marcar_acumulando(cliente, eid, paso, "error", usd, productos=len(productos), nuevos=guardado["nuevos"], aviso=mensaje)
        except Exception:  # noqa: BLE001 — sin poder cerrar el paso, la cadena queda interrumpida (F2)
            log.exception("No se pudo cerrar el paso %s", paso)
            _interrumpir(cliente, eid, e)
            raise e
        _avanzar_seguro(cliente, eid, excluir_job=tarea.get("job_id"))                           # una plataforma caída no frena a las demás
        raise
    usd = _gasto_apify(cliente, eid, tarea, paso, fuente, fuente.tarifa_busqueda())
    _o_interrumpir(tarea, cliente, eid, lambda: _marcar_acumulando(cliente, eid, paso, "hecho" if productos else "vacio", usd,
                                                                   productos=len(productos), nuevos=guardado["nuevos"],
                                                                   aviso=getattr(fuente, "aviso", "") or (NOTA_IDIOMA if sin_propias else "")))
    _avanzar_seguro(cliente, eid, excluir_job=tarea.get("job_id"))
    return gettext("%(n)s producto(s) de %(plataforma)s (%(nuevos)s nuevos)", n=len(productos), plataforma=plataformas.nombre(plat), nuevos=guardado["nuevos"])


@registrar("nicho_inv_seleccionar")
@red_de_la_cadena(lambda p: "seleccionar")
def ejecutar_seleccionar(tarea):
    p = tarea["payload"]
    cliente, eid = p["cliente"], int(p["estudio_id"])
    est, i = _activa(cliente, eid)
    if est is None:
        return gettext("La investigación no está activa.")
    topes = {**inv.TOPES_DEFECTO, **(i.get("topes") or {})}
    job = tarea.get("job_id") or datos.job_id_inv(cliente, eid, "seleccionar")
    cola.reportar(job, etapa=N_("Eligiendo productos"))
    _marcar(cliente, eid, "seleccionar", "en_curso")
    pendientes = datos.productos_nicho(cliente, eid, solo_sin_juzgar=True)
    decisiones, entrada, salida = {}, 0, 0
    if pendientes:
        try:
            decisiones, entrada, salida = inv.seleccion_con_claude({**est, "pais": i.get("pais") or est.get("pais") or ""}, pendientes)
        except Exception as e:
            _fallo_claude(cliente, eid, tarea, "seleccionar", e, lambda m: gettext("Claude no pudo elegir los productos: %(e)s", e=m), ref="seleccion")
            raise
        # Se registra el gasto YA, apenas Claude respondió -- antes de cualquier otra
        # escritura (I3): si `marcar_relevancia` o lo que sigue revienta, lo pagado
        # igual quedó anotado.
        usd = _gasto_claude(cliente, eid, tarea, _ref_intento("seleccion", tarea), entrada, salida,
                            gettext("%(n)s productos juzgados", n=len(decisiones)))
    else:
        usd = 0.0                                                # nada sin juzgar: no se llama a Claude (I3)

    def _guardar():
        # Lo que sigue al pago: si revienta en el último intento, la cadena queda
        # interrumpida (Reanudar) en vez de trabada con el paso en curso (F2).
        if pendientes:
            datos.marcar_relevancia(cliente, eid, decisiones)
        todos = datos.productos_nicho(cliente, eid)
        relevantes = [x for x in todos if x.get("relevante")]
        elegidos = inv.elegir(todos, {x["id"]: {"relevante": True} for x in relevantes}, topes["productos_elegidos"])

        def _fn(x):
            previo = float(((x.get("pasos") or {}).get("seleccionar") or {}).get("usd") or 0)
            nuevo = inv.marcar_paso({**x, "elegidos": elegidos}, "seleccionar", "hecho", usd=round(previo + usd, 4), relevantes=len(relevantes),
                                    elegidos_n=sum(len(v) for v in elegidos.values()), aviso="")
            return inv.detener(nuevo, N_("no se encontraron productos del nicho")) if not elegidos else nuevo
        datos.actualizar_investigacion(cliente, eid, _fn)
        return relevantes, elegidos
    relevantes, elegidos = _o_interrumpir(tarea, cliente, eid, _guardar)
    if not elegidos:
        return gettext("Ningún producto encontrado es del nicho.")
    _avanzar_seguro(cliente, eid, excluir_job=tarea.get("job_id"))
    return gettext("%(r)s producto(s) del nicho; %(e)s elegido(s) para traer reseñas", r=len(relevantes), e=sum(len(v) for v in elegidos.values()))


def _hook(paso_de):
    def hook(tarea, mensaje):
        p = tarea["payload"]
        cliente, eid = p["cliente"], int(p["estudio_id"])
        with idiomas.en_idioma(idiomas.de_proyecto(cliente)):        # el hook no pasa por worker.ejecutar
            error = cola.recortar(cola.sin_token(mensaje), 300)
        datos.actualizar_investigacion(cliente, eid, lambda i: {**inv.marcar_paso(i, paso_de(p), "pendiente"), "estado": "interrumpida", "ultimo_error": error})
    return hook


interrumpida_consultas = al_interrumpir("nicho_inv_consultas")(_hook(lambda p: "consultas"))
interrumpida_buscar = al_interrumpir("nicho_inv_buscar")(_hook(lambda p: f"buscar:{p.get('plataforma')}"))
interrumpida_seleccionar = al_interrumpir("nicho_inv_seleccionar")(_hook(lambda p: "seleccionar"))
