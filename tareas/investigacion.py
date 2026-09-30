"""
Tareas de la investigación automática del nicho (spec Parte 3 §1, §9) y el
motor que encadena los pasos.

  nicho_inv_consultas   -> Claude convierte el tema en 2–4 búsquedas (max_intentos=2)
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
import logging

from flask_babel import gettext

import cola
import gastos
import idiomas
import trabajos
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


def _gasto_claude(cliente, eid, tarea, paso, entrada, salida, detalle):
    """Registra la llamada a Claude (tipo `investigacion`) y devuelve su costo."""
    if entrada + salida <= 0:
        return 0.0
    usd = inv.costo_claude(entrada, salida)
    gastos.registrar_seguro(cliente, "investigacion", usd, f"investigacion:{eid}:{paso}{ref_sufijo(tarea)}", detalle=detalle,
                            proveedor="anthropic", extra={"tokens_entrada": entrada, "tokens_salida": salida, "modelo": avatares.modelo_actual()})
    return usd


def _gasto_apify(cliente, eid, tarea, paso, fuente, tarifa, nota=""):
    """Ítems crudos × precio del actor (aprox.), con las corridas para rastrear el cobro. Devuelve el costo."""
    n = int(getattr(fuente, "resultados", 0) or 0)
    if n <= 0:
        return 0.0
    usd = plataformas.usd(n, tarifa["usd_por_resultado"])
    corridas = [c.get("run_id") for c in (getattr(fuente, "corridas", None) or []) if c.get("run_id")]
    gastos.registrar_seguro(cliente, "recoleccion", usd, f"recoleccion:{eid}:{paso}{ref_sufijo(tarea)}",
                            detalle=f"Apify {tarifa['nombre']}: {n} resultado(s) aprox." + (f" — {nota}" if nota else ""),
                            proveedor="apify", extra={"actor": tarifa["actor"], "resultados": n, "usd_por_resultado": tarifa["usd_por_resultado"],
                                                      "corridas": corridas})
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
                        gettext("intento fallido"))
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
    rechaza un job vivo). Devuelve el paso encolado o None."""
    from tareas import nicho as tareas_nicho      # tareas.nicho importa este módulo: import perezoso
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
                             duracion_estimada=60, etapas=ETAPAS_CONSULTAS, max_intentos=2)
            return paso
        if paso.startswith("buscar:"):
            trabajos.encolar(datos.job_id_inv(cliente, estudio_id, paso), "nicho_inv_buscar", {**base, "plataforma": paso.split(":", 1)[1]},
                             cliente=cliente, duracion_estimada=300, etapas=ETAPAS_BUSCAR, max_intentos=1)
            return paso
        if paso == "seleccionar":
            if not (i.get("plataformas") or []):
                # Solo redes, sin ninguna plataforma buscada: no hay productos que
                # juzgar -- ni un solo dato pagado a Claude por nada (Ruling 16).
                _marcar(cliente, estudio_id, paso, "vacio", aviso=N_("sin plataformas"))
                continue
            trabajos.encolar(datos.job_id_inv(cliente, estudio_id, paso), "nicho_inv_seleccionar", base, cliente=cliente,
                             duracion_estimada=60, etapas=ETAPAS_SELECCION, max_intentos=2)
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
            ok = tareas_nicho.encolar_recolectar(cliente, estudio_id, plat, params, investigacion=True)
            if _propio_o_choque(cliente, estudio_id, job_id, ok, "investigacion"):
                return paso
            return None
        if paso.startswith("redes:"):
            red = paso.split(":", 1)[1]
            if fuentes_registro.llaves_faltantes(red):
                _marcar(cliente, estudio_id, paso, "saltado", nuevos=0, aviso=N_("sin llave"))
                continue
            job_id = datos.job_id_recolectar(cliente, estudio_id, red)
            ok = tareas_nicho.encolar_recolectar(cliente, estudio_id, red, inv.params_redes(red, i), investigacion=True)
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
        ok = tareas_nicho.encolar_generar(cliente, estudio_id, auto=True, tope_usd=tope)
        if _propio_o_choque(cliente, estudio_id, job_id, ok, "auto"):
            return paso
        return None
    return None


# ------------------------------------------------------------- tareas ---

@registrar("nicho_inv_consultas")
def ejecutar_consultas(tarea):
    p = tarea["payload"]
    cliente, eid = p["cliente"], int(p["estudio_id"])
    est, i = _activa(cliente, eid)
    if est is None:
        return gettext("La investigación no está activa.")
    if ((i.get("pasos") or {}).get("consultas") or {}).get("estado") == "hecho":
        # Reintento (p. ej. avanzar() reventó DESPUÉS de guardar las consultas):
        # ya están pagadas y guardadas -- no se vuelve a llamar a Claude (I3).
        avanzar(cliente, eid)
        return gettext("Consultas: %(consultas)s", consultas=", ".join(i.get("consultas") or []))
    if not (est.get("tema") or "").strip():
        _detener(cliente, eid, N_("sin tema"))
        return gettext("El estudio no tiene tema.")
    job = tarea.get("job_id") or datos.job_id_inv(cliente, eid, "consultas")
    cola.reportar(job, etapa=N_("Consultas"))
    _marcar(cliente, eid, "consultas", "en_curso")
    try:
        consultas, entrada, salida = inv.consultas_con_claude(est, i.get("pais") or est.get("pais") or "CO")
    except Exception as e:
        _fallo_claude(cliente, eid, tarea, "consultas", e, lambda m: gettext("Claude no pudo escribir las consultas: %(e)s", e=m))
        raise
    usd = _gasto_claude(cliente, eid, tarea, _ref_intento("consultas", tarea), entrada, salida, gettext("%(n)s consultas", n=len(consultas)))

    def _fn(x):
        previo = float(((x.get("pasos") or {}).get("consultas") or {}).get("usd") or 0)
        return inv.marcar_paso({**x, "consultas": consultas}, "consultas", "hecho", usd=round(previo + usd, 4), aviso="")
    datos.actualizar_investigacion(cliente, eid, _fn)
    avanzar(cliente, eid)
    return gettext("Consultas: %(consultas)s", consultas=", ".join(consultas))


@registrar("nicho_inv_buscar")
def ejecutar_buscar(tarea):
    p = tarea["payload"]
    cliente, eid, plat = p["cliente"], int(p["estudio_id"]), p["plataforma"]
    est, i = _activa(cliente, eid)
    if est is None:
        return gettext("La investigación no está activa.")
    paso = f"buscar:{plat}"
    consultas = [c for c in (i.get("consultas") or []) if c]
    if not consultas:
        _detener(cliente, eid, N_("sin consultas"))
        return gettext("No hay consultas para buscar.")
    topes = {**inv.TOPES_DEFECTO, **(i.get("topes") or {})}
    pais = i.get("pais") or est.get("pais") or ""
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
        _marcar_acumulando(cliente, eid, paso, "error", usd, productos=len(productos), nuevos=guardado["nuevos"], aviso=mensaje)
        avanzar(cliente, eid)                                   # una plataforma caída no frena a las demás
        raise
    usd = _gasto_apify(cliente, eid, tarea, paso, fuente, fuente.tarifa_busqueda())
    _marcar_acumulando(cliente, eid, paso, "hecho" if productos else "vacio", usd, productos=len(productos), nuevos=guardado["nuevos"],
                       aviso=getattr(fuente, "aviso", "") or "")
    avanzar(cliente, eid)
    return gettext("%(n)s producto(s) de %(plataforma)s (%(nuevos)s nuevos)", n=len(productos), plataforma=plataformas.nombre(plat), nuevos=guardado["nuevos"])


@registrar("nicho_inv_seleccionar")
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
        datos.marcar_relevancia(cliente, eid, decisiones)
    else:
        usd = 0.0                                                # nada sin juzgar: no se llama a Claude (I3)
    todos = datos.productos_nicho(cliente, eid)
    relevantes = [x for x in todos if x.get("relevante")]
    elegidos = inv.elegir(todos, {x["id"]: {"relevante": True} for x in relevantes}, topes["productos_elegidos"])

    def _fn(x):
        previo = float(((x.get("pasos") or {}).get("seleccionar") or {}).get("usd") or 0)
        nuevo = inv.marcar_paso({**x, "elegidos": elegidos}, "seleccionar", "hecho", usd=round(previo + usd, 4), relevantes=len(relevantes),
                                elegidos_n=sum(len(v) for v in elegidos.values()), aviso="")
        return inv.detener(nuevo, N_("no se encontraron productos del nicho")) if not elegidos else nuevo
    datos.actualizar_investigacion(cliente, eid, _fn)
    if not elegidos:
        return gettext("Ningún producto encontrado es del nicho.")
    avanzar(cliente, eid)
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
