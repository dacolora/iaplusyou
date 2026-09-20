"""
Tareas del worker para Experimentos: lanzar (crea objetos en Meta, en pausa;
max_intentos=1 y hook de interrupción como meta_publicar), refrescar métricas
de un experimento, decidir (Bloque 4: el decisor dicta un veredicto por pieza
y pide la acción a acciones.pedir, que respeta el modo y el tope), y las
periódicas: refrescar todos los que corren, decidir todos los que corren y
hacer avanzar las derivaciones que están produciendo.

Bloque 7: un ganador, además de escalar y derivar, pide `publicar_organico`
(propuesta en manual/semi, sola en auto) — solo si el proyecto tiene algún
canal orgánico conectado y la pieza no tiene ya una publicación viva.
"""
import logging
from datetime import datetime

import sqlalchemy as sa

import acciones
import cola
import db
import decisor
import derivaciones
import experimentos
import lanzador
import notificaciones
import organico
import propuestas
import proyectos
import trabajos
from tareas import al_interrumpir, registrar

log = logging.getLogger("creatv.tareas.experimentos")


def job_id_lanzar(cliente, experimento_id):
    return f"{cliente}__exp{experimento_id}__lanzar"


def job_id_refrescar(cliente, experimento_id):
    return f"{cliente}__exp{experimento_id}__refrescar"


def job_id_decidir(cliente, experimento_id):
    return f"{cliente}__exp{experimento_id}__decidir"


@al_interrumpir("exp_lanzar")
def interrumpida(tarea, mensaje):
    p = tarea["payload"]
    ex = experimentos.obtener(p["cliente"], p["experimento_id"])
    if ex and ex["estado"] == "lanzando":
        experimentos.actualizar(p["cliente"], p["experimento_id"], estado="error", error=mensaje)


@registrar("exp_lanzar")
def exp_lanzar(tarea):
    p = tarea["payload"]
    job_id = tarea.get("job_id")
    return lanzador.lanzar(p["cliente"], p["experimento_id"],
                           on_etapa=lambda nombre: trabajos.reportar(job_id, etapa=nombre))


@registrar("exp_refrescar")
def exp_refrescar(tarea):
    p = tarea["payload"]
    n = lanzador.refrescar(p["cliente"], p["experimento_id"])
    return f"Métricas actualizadas ({n} anuncios)."


def _experimentos_en(estados):
    with db.conectar() as con:
        return con.execute(sa.select(db.experimento.c.id, db.experimento.c.cliente).where(
            db.experimento.c.legado.is_(False), db.experimento.c.estado.in_(tuple(estados)))).all()


@registrar("exp_refrescar_todos")
def exp_refrescar_todos(tarea):
    """Periódica (2 h): refresca métricas de los experimentos `corriendo` y
    también de los `decidido` — ahí los anuncios ganadores siguen entregando
    y el gasto acumulado tiene que seguir al día (tope)."""
    filas = _experimentos_en(("corriendo", "decidido"))
    for eid, cliente in filas:
        cola.encolar("exp_refrescar", {"cliente": cliente, "experimento_id": eid}, cliente=cliente,
                     job_id=job_id_refrescar(cliente, eid), duracion_estimada=30, max_intentos=2)
    return f"{len(filas)} experimentos en cola."


@registrar("exp_decidir_todos")
def exp_decidir_todos(tarea):
    """Periódica (1 h): encola exp_decidir para cada experimento `corriendo`."""
    filas = _experimentos_en(("corriendo",))
    for eid, cliente in filas:
        cola.encolar("exp_decidir", {"cliente": cliente, "experimento_id": eid}, cliente=cliente,
                     job_id=job_id_decidir(cliente, eid), duracion_estimada=30, max_intentos=2)
    return f"{len(filas)} experimentos en cola para decidir."


# --- exp_decidir -----------------------------------------------------------

def _fecha(texto):
    try:
        return datetime.fromisoformat(texto) if texto else None
    except (TypeError, ValueError):
        return None


def _horas_desde(texto, ahora):
    f = _fecha(texto)
    return max(0.0, (ahora - f).total_seconds() / 3600) if f else 0.0


def _horas_activo(pz, snaps, ahora):
    """Horas desde que la pieza se activó (extra.activado_en, lo escribe el
    lanzador); si no está, desde el primer snapshot con impresiones."""
    activado = (pz.get("extra") or {}).get("activado_en")
    if activado:
        return _horas_desde(activado, ahora)
    primero = _primer_snapshot_con_impresiones(snaps)
    return _horas_desde(primero.get("tomado_en"), ahora) if primero else 0.0


def _ranking(piezas_pais, atribucion):
    """Piezas del país con anuncio y métricas, ordenadas de mejor a peor: por
    CPC ascendente (sin CPC al final) o, con atribución y alguna compra, por
    ROAS descendente. Devuelve la lista ordenada de ep_id."""
    con_metricas = [p for p in piezas_pais if p.get("meta_ad_id") and p.get("metricas")]
    por_ventas = atribucion in ("pixel", "tienda") and any(
        int((p["metricas"] or {}).get("compras") or 0) > 0 for p in con_metricas)
    if por_ventas:
        clave = lambda p: -float((p["metricas"] or {}).get("roas") or 0)  # noqa: E731
    else:
        def clave(p):
            cpc = float((p["metricas"] or {}).get("cpc") or 0)
            return (1, 0.0) if cpc <= 0 else (0, cpc)
    return [p["id"] for p in sorted(con_metricas, key=clave)]


def _cf_id(pz):
    legado = pz.get("legado_id") or ""
    return legado.split("__")[0] if legado else None


def _pedir(cliente, eid, accion, payload, motivo, resultado):
    """acciones.pedir con captura: un fallo al ejecutar la acción queda como
    evento (lo escribe pedir) y no frena las demás piezas de la pasada. Como
    el veredicto ya quedó persistido y la pieza no se vuelve a evaluar, la
    acción fallida además se deja como propuesta pendiente — si no, se pierde
    sin que nada la reintente ni aparezca en el panel."""
    try:
        estado, mensaje = acciones.pedir(cliente, eid, accion, payload, motivo)
    except Exception as error:  # noqa: BLE001
        mensaje_error = cola.sin_token(str(error))
        resultado["errores"].append(f"{accion}: {mensaje_error}")
        propuestas.crear(cliente, eid, accion, payload, motivo=f"falló al ejecutar: {mensaje_error}")
        resultado["propuestas"].append(f"{accion} (falló al ejecutar, quedó pendiente de reintento): {mensaje_error}")
        return None
    if estado == "propuesta":
        resultado["propuestas"].append(mensaje)
    return estado


def _aplicar_veredicto(cliente, ex, pz, v, resultado):
    """Escribe el veredicto en la pieza + evento `veredicto`, y pide la acción
    que el decisor recomendó (todo gasto pasa por acciones.pedir)."""
    ep_id = pz["id"]
    experimentos.actualizar_pieza(cliente, ep_id, veredicto=v["veredicto"], veredicto_motivo=v["motivo"],
                                  veredicto_en=db.ahora())
    experimentos.registrar_evento(cliente, ex["id"], "veredicto",
                                  f"{pz['nombre']} ({pz['pais']}): {v['veredicto']} — {v['motivo']}",
                                  {"veredicto": v["veredicto"], "accion": v["accion"], "puerta": v["puerta"],
                                   "numeros": v["numeros"]}, ep_id=ep_id)
    resultado["veredictos"].append((pz, v))
    accion = v["accion"]
    if accion == "escalar_y_derivar":
        # "escalar" es una acción por país (sube el presupuesto del conjunto
        # en Meta), no por pieza: con varios ganadores del mismo país en una
        # misma pasada, solo el primero la pide — los demás solo derivan.
        if pz["pais"] in resultado["escalados"]:
            experimentos.registrar_evento(cliente, ex["id"], "escalado",
                                          f"{pz['nombre']} ({pz['pais']}): escalado ya pedido en esta pasada.",
                                          ep_id=ep_id)
        else:
            resultado["escalados"].add(pz["pais"])
            _pedir(cliente, ex["id"], "escalar", {"pais": pz["pais"], "ep_id": ep_id}, v["motivo"], resultado)
        _pedir(cliente, ex["id"], "derivar", {"ep_id": ep_id}, v["motivo"], resultado)
        resultado["ganadores"].append(pz)
        _pedir_publicacion_organica(cliente, ex, pz, v["motivo"], resultado)
    elif accion == "rescatar":
        # I-2 (spec §7): la pausa del perdedor es una acción aparte y sin
        # gasto — en semi/auto se ejecuta ya, en manual se propone. Así el
        # anuncio deja de gastar aunque el rescate espere aprobación.
        _pedir(cliente, ex["id"], "pausar", {"ep_id": ep_id}, v["motivo"], resultado)
        _pedir(cliente, ex["id"], "rescatar", {"ep_id": ep_id}, v["motivo"], resultado)
    elif accion == "archivar":
        _pedir(cliente, ex["id"], "pausar", {"ep_id": ep_id}, v["motivo"], resultado)
        _pedir(cliente, ex["id"], "archivar", {"ep_id": ep_id, "cf_id": _cf_id(pz), "motivo": v["motivo"]},
               v["motivo"], resultado)
    elif accion == "pausar":
        _pedir(cliente, ex["id"], "pausar", {"ep_id": ep_id}, v["motivo"], resultado)


def _canales_organicos(cliente):
    """Plataformas con canal orgánico disponible; [] si no se puede saber
    (meta.json ilegible, etc.): la pasada del decisor no se frena por eso."""
    try:
        return organico.disponibles(cliente)
    except Exception as error:  # noqa: BLE001
        log.warning("no pude leer los canales orgánicos de %s: %s", cliente, type(error).__name__)
        return []


def _pedir_publicacion_organica(cliente, ex, pz, motivo, resultado):
    """Bloque 7: la ganadora sale como contenido orgánico — propuesta en
    manual/semi (acciones.pedir la deja con el texto ya redactado), sola en
    auto. Solo con algún canal conectado y si la pieza no tiene ya una
    publicación viva en ninguno de ellos (ganador re-evaluado, o publicada
    a mano desde el panel)."""
    canales = _canales_organicos(cliente)
    if not canales or not pz.get("pieza_id") or not pz.get("url_video"):
        return
    vivas = {pub["plataforma"] for pub in organico.listar(cliente, pieza_id=pz["pieza_id"])
             if pub["estado"] in organico.ESTADOS_VIVOS}
    pendientes = [p for p in canales if p not in vivas]
    if not pendientes:
        return
    estado = _pedir(cliente, ex["id"], "publicar_organico", {"ep_id": pz["id"], "plataformas": pendientes},
                    motivo, resultado)
    if estado == "propuesta":
        resultado["organico_propuesto"].add(pz["id"])


def _rechazada_por_meta(cliente, ex, pz):
    """I-8: un anuncio DISAPPROVED/WITH_ISSUES no entrega; no se evalúa (a
    las 48 h con 0 impresiones sería 'perdedor' y se rescataría con crédito
    algo que nadie vio). Evento una sola vez (`extra.rechazo_avisado`)."""
    if pz.get("estado_meta") not in lanzador.ESTADOS_META_RECHAZO:
        return False
    if not (pz.get("extra") or {}).get("rechazo_avisado"):
        experimentos.registrar_evento(
            cliente, ex["id"], "rechazo_meta",
            f"{pz['nombre']} ({pz['pais']}): anuncio {pz['estado_meta']} en Meta, el decisor no la evalúa "
            f"hasta que se corrija o se reemplace.", {"estado_meta": pz["estado_meta"]}, ep_id=pz["id"])
        experimentos.marcar_pieza(cliente, pz["id"], rechazo_avisado=True)
    return True


def _primer_snapshot_con_impresiones(snaps):
    return next((s for s in snaps if int(s.get("impresiones") or 0) > 0), None)


def _dias_transcurridos(ex, snaps_por_pieza, ahora):
    """Días desde que el experimento se activó (`extra.activado_en`). Para
    experimentos activados antes de que existiera esa marca: desde el primer
    snapshot con impresiones de cualquiera de sus piezas (si no, 0 y la
    ventana de días nunca cierra — mejor que inventar una fecha)."""
    activado = (ex.get("extra") or {}).get("activado_en")
    if activado:
        return _horas_desde(activado, ahora) / 24
    primeros = [s["tomado_en"] for s in map(_primer_snapshot_con_impresiones, snaps_por_pieza.values()) if s]
    return _horas_desde(min(primeros), ahora) / 24 if primeros else 0.0


def _pausar_por_tope(cliente, ex):
    eid = ex["id"]
    texto = (f"Tope alcanzado: gasto {float(ex.get('gasto_acumulado') or 0):g} de "
             f"{float(ex.get('tope_total') or 0):g} {ex.get('moneda') or ''}. Se pausa el experimento.")
    try:
        lanzador.cambiar_estado(cliente, eid, "PAUSED")
    except Exception as error:  # noqa: BLE001
        experimentos.registrar_evento(cliente, eid, "error",
                                      f"No se pudo pausar por tope: {cola.sin_token(str(error))}")
        raise
    experimentos.registrar_evento(cliente, eid, "tope", texto)
    notificaciones.avisar(cliente, "tope", f"Tope alcanzado en «{ex['nombre']}»",
                          f"{texto}\n\nSi quieres seguir, sube el tope total y vuelve a activarlo desde el panel "
                          f"del experimento #{eid}.")
    return texto


def _avisar_resultado(cliente, ex, resultado):
    for pz in resultado["ganadores"]:
        v = next(v for p, v in resultado["veredictos"] if p["id"] == pz["id"])
        cuerpo = f"{v['motivo']}\n\nExperimento #{ex['id']}, país {pz['pais']}."
        if pz["id"] in resultado["organico_propuesto"]:
            cuerpo += ("\n\nAdemás quedó una propuesta para publicarla orgánica (Reels, Página, TikTok o Shorts, "
                       "según lo que tengas conectado) con el texto ya redactado: revísalo y apruébala en el panel.")
        notificaciones.avisar(cliente, "ganador", f"Ganador en «{ex['nombre']}»: {pz['nombre']} ({pz['pais']})", cuerpo)
    if resultado["propuestas"]:
        lineas = "\n".join(f"- {m}" for m in resultado["propuestas"])
        notificaciones.avisar(cliente, "propuesta",
                              f"{len(resultado['propuestas'])} propuesta(s) esperan tu aprobación en «{ex['nombre']}»",
                              f"El decisor dejó estas propuestas pendientes en el experimento #{ex['id']}:\n\n{lineas}\n\n"
                              f"Nada se ejecuta hasta que las apruebes en el panel.")


def _marcar_decidido(cliente, ex):
    """`decidido` cuando todas las piezas con anuncio tienen veredicto final,
    no hay ninguna propuesta pendiente (en semi/manual el rescate/escalada
    puede seguir esperando aprobación humana: marcar `decidido` ahora la
    dejaría inejecutable — lanzador.lanzar_piezas_nuevas/activar_pieza no
    aceptan ese estado), no queda ninguna pieza nueva a mitad de camino
    (`en_cola`/`publicando`, el anuncio todavía no existe en Meta) y no queda
    ninguna derivación produciendo. Relee el experimento (las acciones de
    esta pasada pudieron cambiar piezas y extra)."""
    ex = experimentos.obtener(cliente, ex["id"])
    if ex is None or ex["estado"] != "corriendo":
        return False
    if ex.get("propuestas_pendientes"):
        return False
    con_anuncio = [p for p in ex["piezas"] if p.get("meta_ad_id")]
    activas = [p for p in con_anuncio if p.get("estado") == "activo"]
    # Una pieza pausada a mano sin veredicto no bloquea: `decidido` es "todas
    # las piezas ACTIVAS tienen veredicto". Sin ninguna activa ni ninguna
    # con veredicto no hay nada decidido (experimento recién activado).
    if not con_anuncio or any((p.get("veredicto") or "pendiente") == "pendiente" for p in activas):
        return False
    if not any((p.get("veredicto") or "pendiente") != "pendiente" for p in con_anuncio):
        return False
    if any(p.get("estado") in ("en_cola", "publicando") for p in ex["piezas"]):
        return False
    if any(d.get("estado") == "produciendo" for d in ((ex.get("extra") or {}).get("derivaciones") or [])):
        return False
    experimentos.actualizar(cliente, ex["id"], estado="decidido")
    experimentos.registrar_evento(cliente, ex["id"], "estado",
                                  "Experimento decidido: todas las piezas activas tienen veredicto.")
    return True


@registrar("exp_decidir")
def exp_decidir(tarea):
    p = tarea["payload"]
    cliente, eid = p["cliente"], p["experimento_id"]
    ex = experimentos.obtener(cliente, eid)
    if ex is None:
        return "Ese experimento no existe."
    if ex["estado"] != "corriendo":
        return f"Experimento en estado {ex['estado']}: no se decide."
    if acciones.tope_alcanzado(ex):
        return _pausar_por_tope(cliente, ex)

    reglas = decisor.reglas_efectivas(proyectos.reglas_defecto(cliente), ex.get("reglas"))
    ahora = datetime.now()
    resultado = {"veredictos": [], "ganadores": [], "propuestas": [], "errores": [], "escalados": set(),
                 "organico_propuesto": set()}
    snaps_por_pieza = {}
    for pais in ex["paises"]:
        piezas_pais = [pz for pz in ex["piezas"] if pz["pais"] == pais["pais"]]
        orden = _ranking(piezas_pais, ex.get("atribucion"))
        for pz in piezas_pais:
            if not pz.get("meta_ad_id") or pz.get("estado") != "activo" or (pz.get("veredicto") or "pendiente") != "pendiente":
                continue
            if _rechazada_por_meta(cliente, ex, pz):
                continue
            snaps = snaps_por_pieza.setdefault(pz["id"], experimentos.snapshots(pz["id"]))
            dias_transcurridos = _dias_transcurridos(ex, snaps_por_pieza, ahora)
            ctx = {"horas_activo": _horas_activo(pz, snaps, ahora), "presupuesto_dia": pais.get("presupuesto_dia"),
                   "dias_experimento": ex.get("dias"), "dias_transcurridos": dias_transcurridos,
                   "escalon_rescate": pz.get("escalon_rescate") or 0, "atribucion": ex.get("atribucion"),
                   "posicion": (orden.index(pz["id"]) + 1) if pz["id"] in orden else None, "total_pais": len(orden),
                   "es_imagen": bool(pz.get("es_imagen"))}
            v = decisor.decidir(snaps, reglas, ctx)
            if v["veredicto"] == "pendiente":
                continue
            _aplicar_veredicto(cliente, ex, pz, v, resultado)

    _avisar_resultado(cliente, ex, resultado)
    decidido = _marcar_decidido(cliente, ex)
    partes = [f"{len(resultado['veredictos'])} veredicto(s)"]
    if resultado["ganadores"]:
        partes.append(f"{len(resultado['ganadores'])} ganador(es)")
    if resultado["propuestas"]:
        partes.append(f"{len(resultado['propuestas'])} propuesta(s) pendiente(s)")
    if resultado["errores"]:
        partes.append(f"{len(resultado['errores'])} acción(es) con error")
    if decidido:
        partes.append("experimento decidido")
    return ", ".join(partes) + "."


@registrar("exp_avanzar_todos")
def exp_avanzar_todos(tarea):
    """Periódica (10 min): una pasada de `derivaciones.avanzar` sobre cada
    experimento no legado con alguna derivación `produciendo`. Directo, sin
    una tarea por experimento (es barato: consultas y, a lo sumo, encolar).
    Un experimento que falle no frena a los demás: queda como evento."""
    with db.conectar() as con:
        filas = con.execute(sa.select(db.experimento.c.id, db.experimento.c.cliente, db.experimento.c.extra).where(
            db.experimento.c.legado.is_(False))).all()
    n = 0
    for eid, cliente, extra in filas:
        if not any(d.get("estado") == "produciendo" for d in ((extra or {}).get("derivaciones") or [])):
            continue
        n += 1
        try:
            derivaciones.avanzar(cliente, eid)
        except Exception as error:
            experimentos.registrar_evento(cliente, eid, "error",
                                          f"No se pudo avanzar la derivación: {cola.sin_token(str(error))}")
    return f"{n} experimentos con derivaciones en producción revisados."
