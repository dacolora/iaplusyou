"""
Derivaciones (Bloque 4): producir piezas nuevas a partir de una pieza del
experimento y meterlas al experimento cuando estén listas.

- `derivar` (pieza ganadora): experimento hijo con N re-ediciones (variantes
  hook/estructura de la misma sesión) + M regeneraciones (sesiones nuevas
  con otro modelo y otro enfoque, que primero generan el clon y luego sus
  finales por país).
- `rescatar` (pieza perdedora): una sola pieza en el mismo experimento según
  el escalón (1 → re-edición hook, 2 → re-edición estructura, 3 →
  regeneración). La escalera es por concepto: la pieza rescatada nace con
  `escalon_rescate = n`, así que si también pierde el decisor pide el n+1
  y, agotados los 3, archivar (toda la cadena de sesiones).

La producción es asíncrona (worker): `planificar` deja la máquina de estados
en `experimento.extra["derivaciones"]` del experimento DESTINO, marca en la
pieza origen la bandera de idempotencia (`derivado` / `rescatado_en_escalon`)
y recién entonces intenta encolar (`avanzar`); si encolar falla queda un
evento `error` y la periódica lo retoma — nunca se vuelve a planificar (I-5).
`avanzar` (periódica `exp_avanzar_todos`, cada 10 min) es idempotente: mira
qué terminó, encola lo que falta y, cuando todo está listo, mete las piezas
al experimento y lanza sus anuncios. Nada se activa solo: la activación pasa
por `acciones.pedir("activar")` (puerta de modo). El id de cada derivación
(`d{n}`) se asigna dentro del RMW de `extra` (`_guardar`), así dos
planificaciones a la vez nunca comparten id (I-6). Las sesiones de tipo
`imagen` no se derivan ni rescatan (no hay video que cortar): ValueError.

Forma guardada (una entrada por derivación):
  {"id": "d1", "tipo": "derivar"|"rescatar", "origen_ep_id", "cf_id",
   "motivo", "escalon" (n del rescate; 0 en derivar),
   "estado": "produciendo"|"listo"|"error", "creado_en",
   "items": [{"clase": "reedicion"|"regeneracion", "variante": n|None,
              "variante_tipo": "hook"|"estructura"|None, "cf_id",
              "paises": [...], "idiomas": {pais: idioma},
              "estado": "produciendo_clon"|"produciendo_finales"|"listo"|"error",
              "finales": {"<idioma>_<pais>": legado_id}, "ep_ids": [...],
              "error": str|None}]}

Nota (cierre con fallo parcial): un item con varios países que falla en uno
después de haber agregado la pieza de otro deja esa pieza en el experimento
pero fuera de los `ep_ids` que se lanzan/activan (queda `en_cola`, sin
anuncio si el experimento ya está en Meta). Hoy no ocurre: `rescatar` es de
un solo país y `derivar` produce sobre un hijo `armando`, cuyo `lanzar`
toma todas las piezas `en_cola`.

`acciones` importa este módulo a nivel de módulo; acá se importan `acciones`
y `propuestas` de forma perezosa (solo en `_cerrar_si_lista`) para evitar el
ciclo.
"""
import cola
import creative_flow
import db
import decisor
import experimentos
import lanzador
import proyectos
import trabajos
from final_edition import ETAPAS_FINAL
from final_edition.tipos import PAISES
from flowplus_prompt import ORDEN_ENFOQUES as ENFOQUES
from providers import flowplus_modelos
from tareas import final_edition as tareas_fe
from tareas.flowplus import ETAPAS_CREATIVE_FLOW

TIPOS_VARIANTE = ("hook", "estructura")
_ESCALONES = {1: ("reedicion", "hook"), 2: ("reedicion", "estructura"), 3: ("regeneracion", None)}
_ESTADOS_FINAL_OK = ("listo", "degradada")
_PENDIENTES = ("produciendo_clon", "produciendo_finales")


# ------------------------------------------------------------ helpers ---

def _experimento(cliente, experimento_id):
    ex = experimentos.obtener(cliente, experimento_id)
    if ex is None:
        raise ValueError("Ese experimento no existe.")
    return ex


def _pieza(ex, ep_id):
    pz = next((p for p in ex["piezas"] if p["id"] == ep_id), None)
    if pz is None:
        raise ValueError("Esa pieza no está en el experimento.")
    return pz


def _cf_id_de(pz):
    """Sesión de Crear detrás de la pieza: para una final
    `cf_...__idioma_pais[__vN]`, para un clon el propio legado_id."""
    legado = pz.get("legado_id") or ""
    if not legado:
        raise ValueError("Esa pieza no viene de una sesión de Crear: no se puede derivar.")
    return legado.split("__")[0]


def _rechazar_imagen(cliente, cf_id):
    """Una sesión de imagen no tiene video que cortar: `producir` fallaría
    después de gastar el guion. Se rechaza antes de planificar nada."""
    sesion = creative_flow.cargar(cliente).get(cf_id) or {}
    if sesion.get("tipo") == "imagen":
        raise ValueError("Esa pieza viene de una sesión de imagen: no se puede derivar ni rescatar (no hay video).")


def _idiomas(pz, paises_ex, solo=None):
    """País destino -> idioma de la final a producir (I-7): el idioma que el
    experimento fijó para cada país (`ex["paises"][i]["idioma"]`); el país
    de origen de una final conserva el idioma de esa final. `solo` limita a
    esos países (rescatar: el de la pieza). Sin idioma en el experimento se
    cae al idioma base del país (clones viejos)."""
    idiomas = {p["pais"]: p.get("idioma") or (PAISES.get(p["pais"]) or {}).get("idioma", "es") for p in paises_ex}
    if solo is not None:
        idiomas = {p: idiomas.get(p) or (PAISES.get(p) or {}).get("idioma", "es") for p in solo}
    if pz.get("tipo") == "final" and pz.get("idioma") and pz.get("pais") in idiomas:
        idiomas[pz["pais"]] = pz["idioma"]
    return idiomas


def _siguiente_variante(cliente, cf_id, idiomas):
    """Primer número de variante libre en TODOS los destinos del item (una
    re-edición usa el mismo número en cada país)."""
    usadas = [f["variante"] or 0 for f in creative_flow.finales(cliente, cf_id)
              if f"{f['idioma']}_{f['pais']}" in {f"{i}_{p}" for p, i in idiomas.items()}]
    return (max(usadas) if usadas else 0) + 1


def _otro(lista, actual, k):
    """k-ésimo (desde 0, cíclico) de los elementos de `lista` DISTINTOS de
    `actual`: una regeneración nunca repite el modelo/enfoque del original y
    dos regeneraciones seguidas (k=0, 1, …) tampoco repiten entre sí mientras
    haya otros. Si `actual` es el único, se devuelve tal cual."""
    otros = [x for x in lista if x != actual]
    if not otros:
        return actual
    return otros[k % len(otros)]


def _item_reedicion(cf_id, variante, variante_tipo, idiomas):
    return {"clase": "reedicion", "variante": variante, "variante_tipo": variante_tipo, "cf_id": cf_id,
            "paises": list(idiomas), "idiomas": dict(idiomas), "estado": "produciendo_finales",
            "finales": {}, "ep_ids": [], "error": None}


def modelo_regeneracion(sesion, k):
    """Modelo de video que usaría la k-ésima regeneración (k >= 0) de
    `sesion` (dict con `modelo`, como lo guarda `creative_flow`): el mismo
    que elige `_item_regeneracion` (`_otro` sobre `flowplus_modelos.VIDEO`,
    nunca el modelo original). Expuesto para que `acciones._precio_estimado`
    valore cada regeneración con el modelo que de verdad se va a pagar, en
    vez del modelo de la pieza original (I1: sin esto el estimado podía
    quedar 2,5× por debajo del real)."""
    return _otro(flowplus_modelos.VIDEO, sesion.get("modelo") or flowplus_modelos.VIDEO_POR_DEFECTO, k)


def _item_regeneracion(cliente, cf_id, k, idiomas):
    """Sesión nueva (k-ésima regeneración, k >= 0) con otro modelo de video y
    otro enfoque que el original; el clon se genera en `avanzar`."""
    sesion = creative_flow.cargar(cliente).get(cf_id) or {}
    modelo = modelo_regeneracion(sesion, k)
    enfoque = _otro(ENFOQUES, sesion.get("enfoque") or ENFOQUES[0], k)
    nuevo = creative_flow.duplicar(cliente, cf_id, modelo=modelo, enfoque=enfoque)
    return {"clase": "regeneracion", "variante": None, "variante_tipo": None, "cf_id": nuevo,
            "paises": list(idiomas), "idiomas": dict(idiomas), "estado": "produciendo_clon",
            "finales": {}, "ep_ids": [], "error": None}


def _numero(d):
    try:
        return int(str(d.get("id") or "d0")[1:])
    except ValueError:
        return 0


def _guardar(cliente, experimento_id, derivacion):
    """Escribe la derivación en `extra.derivaciones` del experimento con un
    read-modify-write atómico (`experimentos.actualizar_extra`): no pisa
    `activado_en` ni lo que otra ruta haya escrito en `extra` entre medio.
    Una derivación sin `id` recibe `d{max existente + 1}` DENTRO del RMW
    (bajo el lock de escritura), así dos planificaciones concurrentes nunca
    comparten id ni se pisan (I-6). Devuelve el id."""
    def _poner(extra):
        lista = list(extra.get("derivaciones") or [])
        if not derivacion.get("id"):
            derivacion["id"] = f"d{max((_numero(d) for d in lista), default=0) + 1}"
        lista = [d for d in lista if d.get("id") != derivacion["id"]]
        lista.append(derivacion)
        extra["derivaciones"] = sorted(lista, key=_numero)
        return extra
    if experimentos.actualizar_extra(cliente, experimento_id, _poner) is None:
        raise ValueError("Ese experimento no existe.")
    return derivacion["id"]


def _nueva(cliente, experimento_id, tipo, pz, cf_id, motivo, items, escalon=0):
    """Guarda una derivación nueva en el experimento destino y la devuelve
    ya con su id (asignado en `_guardar`)."""
    d = {"id": None, "tipo": tipo, "origen_ep_id": pz["id"], "cf_id": cf_id,
         "motivo": motivo or "", "estado": "produciendo", "creado_en": db.ahora(), "escalon": escalon,
         "items": items}
    _guardar(cliente, experimento_id, d)
    return d


def _avanzar_sin_relanzar(cliente, experimento_id, d, ep_id):
    """Primer intento de encolar la producción recién planificada. Si falla
    (base, `crear_final`, `encolar`) NO se relanza: la derivación ya está
    guardada y la bandera de idempotencia ya está en la pieza, así que un
    reintento no debe volver a planificar; la periódica `exp_avanzar_todos`
    retoma lo que falte (I-5). Queda un evento `error` sin token."""
    try:
        avanzar(cliente, experimento_id)
    except Exception as error:  # noqa: BLE001
        experimentos.registrar_evento(
            cliente, experimento_id, "error",
            f"Derivación {d['id']}: no se pudo encolar la producción ({cola.sin_token(str(error))}); "
            f"la periódica lo reintenta.", datos={"derivacion": d["id"]}, ep_id=ep_id)


def _resumen_items(items):
    return ", ".join(
        (f"re-edición {i['variante_tipo']} v{i['variante']}" if i["clase"] == "reedicion"
         else f"regeneración {i['cf_id']}") for i in items)


# --------------------------------------------------------- planificar ---

def planificar(cliente, experimento_id, tipo, payload):
    """tipo ∈ ("derivar", "rescatar"). Deja la máquina de estados en el
    experimento destino, encola lo que ya se puede producir y devuelve el id
    del destino (hijo para derivar, el mismo para rescatar)."""
    payload = payload or {}
    ex = _experimento(cliente, experimento_id)
    pz = _pieza(ex, payload["ep_id"])
    motivo = payload.get("motivo") or ""
    if tipo == "derivar":
        return _planificar_derivar(cliente, ex, pz, motivo)
    if tipo == "rescatar":
        return _planificar_rescatar(cliente, ex, pz, motivo)
    raise ValueError(f"Tipo de derivación desconocido: {tipo!r}.")


def _planificar_derivar(cliente, ex, pz, motivo):
    cf_id = _cf_id_de(pz)
    _rechazar_imagen(cliente, cf_id)
    reglas = decisor.reglas_efectivas(proyectos.reglas_defecto(cliente), ex.get("reglas"))
    n_re, n_rg = int(reglas.get("n_reediciones") or 0), int(reglas.get("n_regeneraciones") or 0)
    if n_re + n_rg <= 0:
        raise ValueError("La regla no pide re-ediciones ni regeneraciones: no hay nada que derivar.")
    idiomas = _idiomas(pz, ex["paises"])
    # Items primero (duplicar puede fallar) y el hijo después: así no queda
    # un hijo huérfano sin derivación.
    items = []
    base = _siguiente_variante(cliente, cf_id, idiomas)
    for k in range(n_re):
        items.append(_item_reedicion(cf_id, base + k, TIPOS_VARIANTE[k % 2], idiomas))
    for k in range(n_rg):
        items.append(_item_regeneracion(cliente, cf_id, k, idiomas))
    hijo = experimentos.crear_hijo(cliente, ex["id"], f"{ex['nombre']} · derivado de {pz['nombre']}"[:200], pz["id"])
    d = _nueva(cliente, hijo, "derivar", pz, cf_id, motivo, items)
    # Bandera de idempotencia apenas la derivación está guardada y ANTES de
    # encolar: si encolar falla, un reintento no vuelve a planificar (I-5).
    experimentos.marcar_pieza(cliente, pz["id"], derivado=True)
    mensaje = f"Derivación {d['id']} a partir de {pz['nombre']}: {_resumen_items(items) or 'sin piezas'}."
    experimentos.registrar_evento(cliente, ex["id"], "derivacion", f"{mensaje} Experimento hijo {hijo}.",
                                  datos={"hijo": hijo, "derivacion": d["id"]}, ep_id=pz["id"])
    experimentos.registrar_evento(cliente, hijo, "derivacion", f"{mensaje} Motivo: {motivo or 'sin motivo'}.",
                                  datos={"padre": ex["id"], "derivacion": d["id"]})
    _avanzar_sin_relanzar(cliente, hijo, d, None)
    return hijo


def _planificar_rescatar(cliente, ex, pz, motivo):
    cf_id = _cf_id_de(pz)
    _rechazar_imagen(cliente, cf_id)
    escalon = int(pz.get("escalon_rescate") or 0) + 1
    if escalon not in _ESCALONES:
        raise ValueError(f"{pz['nombre']} ya agotó los {len(_ESCALONES)} escalones de rescate.")
    idiomas = _idiomas(pz, ex["paises"], solo=[pz["pais"]])
    clase, variante_tipo = _ESCALONES[escalon]
    if clase == "reedicion":
        item = _item_reedicion(cf_id, _siguiente_variante(cliente, cf_id, idiomas), variante_tipo, idiomas)
    else:
        item = _item_regeneracion(cliente, cf_id, 0, idiomas)
    experimentos.actualizar_pieza(cliente, pz["id"], escalon_rescate=escalon)
    d = _nueva(cliente, ex["id"], "rescatar", pz, cf_id, motivo, [item], escalon=escalon)
    # Bandera de idempotencia apenas la derivación está guardada y ANTES de
    # encolar (I-5): `acciones.ejecutar("rescatar")` la relee y no vuelve a
    # planificar este escalón aunque encolar haya fallado.
    experimentos.marcar_pieza(cliente, pz["id"], rescatado_en_escalon=escalon)
    experimentos.registrar_evento(
        cliente, ex["id"], "derivacion",
        f"Rescate {d['id']} de {pz['nombre']} (escalón {escalon}): {_resumen_items([item])}. Motivo: {motivo or 'sin motivo'}.",
        datos={"derivacion": d["id"], "escalon": escalon}, ep_id=pz["id"])
    _avanzar_sin_relanzar(cliente, ex["id"], d, pz["id"])
    return ex["id"]


# ------------------------------------------------------------ avanzar ---

def _encolar_clon(cliente, cf_id, tipo="video"):
    """Genera el clon de la sesión nueva (como `dashboard._lanzar_video_cf`,
    tarea según el `tipo` de la sesión): marca `video_generando` antes de
    encolar; no encola si ya hay una viva."""
    job_id = f"{cliente}__{cf_id}__creative_flow"
    if trabajos.en_curso(job_id):
        return False
    creative_flow.actualizar(cliente, cf_id, estado="video_generando")
    return trabajos.encolar(job_id, "flowplus_imagen" if tipo == "imagen" else "flowplus_video",
                            {"cliente": cliente, "cf_id": cf_id}, cliente=cliente,
                            duracion_estimada=60 if tipo == "imagen" else 180,
                            etapas=ETAPAS_CREATIVE_FLOW, max_intentos=1)


def _encolar_final(cliente, cf_id, idioma, pais, opciones):
    """Produce una final (como `dashboard.fe_producir`): fila en `generando`
    desde que se encola. Devuelve el legado_id de la final.

    Nunca reproduce una final que ya existe y no falló: cualquier final con
    ese legado es nuestra (las variantes son números nuevos y las
    regeneraciones son sesiones nuevas), así que si ya está `listo`/
    `degradada` o `generando` (o su tarea sigue viva) se devuelve el legado
    sin tocar nada — `crear_final` la reiniciaría y se pagaría dos veces si
    el estado en memoria de una pasada anterior no llegó a guardarse."""
    variante = opciones.get("variante")
    job_id = tareas_fe.job_id_final(cliente, cf_id, idioma, pais, variante=variante)
    legado = tareas_fe.legado_final(cf_id, idioma, pais, variante)
    if trabajos.en_curso(job_id):
        return legado
    existente = creative_flow.final_por_legado(cliente, legado)
    if existente is not None and existente.get("estado") != "error":
        return legado
    creative_flow.crear_final(cliente, cf_id, idioma, pais, variante=variante)
    trabajos.encolar(job_id, "final_producir",
                     {"cliente": cliente, "cf_id": cf_id, "idioma": idioma, "pais": pais, "opciones": dict(opciones)},
                     cliente=cliente, duracion_estimada=240, etapas=ETAPAS_FINAL, max_intentos=1)
    return legado


def _sesion(cliente, cf_id):
    return creative_flow.cargar(cliente).get(cf_id)


def _estado_final(cliente, legado):
    f = creative_flow.final_por_legado(cliente, legado)
    if f is None:
        return "error", f"la final {legado} ya no existe"
    return f["estado"], f.get("error")


def _opciones_de(item):
    if item["clase"] == "reedicion":
        return {"variante": item["variante"], "variante_tipo": item["variante_tipo"]}
    return {"variante": None}


def _fallar(cliente, experimento_id, d, item, motivo):
    motivo = cola.sin_token(str(motivo))
    item["estado"], item["error"] = "error", motivo
    experimentos.registrar_evento(cliente, experimento_id, "error",
                                  f"Derivación {d['id']}: falló {_resumen_items([item])}: {motivo}.",
                                  datos={"derivacion": d["id"], "cf_id": item["cf_id"]}, ep_id=d["origen_ep_id"])


def _avanzar_clon(cliente, experimento_id, d, item):
    s = _sesion(cliente, item["cf_id"])
    if s is None:
        _fallar(cliente, experimento_id, d, item, f"la sesión {item['cf_id']} ya no existe")
        return
    estado = s.get("estado")
    if estado == "video_listo":
        item["estado"] = "produciendo_finales"
        _avanzar_finales(cliente, experimento_id, d, item)
    elif estado == "error":
        _fallar(cliente, experimento_id, d, item, s.get("error") or "la generación del clon falló")
    elif estado != "video_generando":
        _encolar_clon(cliente, item["cf_id"], s.get("tipo") or "video")
    # video_generando: esperar.


def _heredar(cliente, d, ep_id):
    """La pieza nueva hereda la posición en la escalera del concepto: un
    rescate hecho en el escalón n deja la pieza en `escalon_rescate = n`
    (si vuelve a perder, el decisor pide el n+1 y, pasado el 3, archivar);
    una derivación (ganadora) arranca su propia escalera en 0. En ambos
    casos `extra.origen_ep_id` apunta a la pieza de la que salió."""
    if d["tipo"] == "rescatar":
        experimentos.actualizar_pieza(cliente, ep_id, escalon_rescate=int(d.get("escalon") or 0))
    experimentos.marcar_pieza(cliente, ep_id, origen_ep_id=d["origen_ep_id"])


def _avanzar_finales(cliente, experimento_id, d, item):
    """Encola las finales que falten, agrega al experimento las que terminaron
    y deja el item `listo` cuando todas están dentro."""
    opciones = _opciones_de(item)
    listas = set()
    for pais in item["paises"]:
        idioma = item["idiomas"][pais]
        clave = f"{idioma}_{pais}"
        if clave not in item["finales"]:
            item["finales"][clave] = _encolar_final(cliente, item["cf_id"], idioma, pais, opciones)
            continue
        estado, error = _estado_final(cliente, item["finales"][clave])
        if estado in _ESTADOS_FINAL_OK:
            ep_id = experimentos.agregar_pieza(cliente, experimento_id,
                                               creative_flow.pieza_id_por_legado(cliente, item["finales"][clave]), pais)
            if ep_id and ep_id not in item["ep_ids"]:
                _heredar(cliente, d, ep_id)
                item["ep_ids"].append(ep_id)
            listas.add(clave)
        elif estado == "error":
            _fallar(cliente, experimento_id, d, item, error or f"la final {clave} falló")
            return
        # generando: esperar.
    if len(listas) == len(item["paises"]):
        item["estado"] = "listo"


def _avanzar_item(cliente, experimento_id, d, item):
    if item["estado"] == "produciendo_clon":
        _avanzar_clon(cliente, experimento_id, d, item)
    elif item["estado"] == "produciendo_finales":
        _avanzar_finales(cliente, experimento_id, d, item)


def _lanzar_piezas(cliente, experimento_id):
    """Anuncios para las piezas nuevas: lanzamiento completo si el destino
    todavía está `armando` (queda `pausado`), o solo los anuncios nuevos si
    ya está en Meta."""
    ex = _experimento(cliente, experimento_id)
    if ex["estado"] == "armando":
        lanzador.lanzar(cliente, experimento_id)
    else:
        lanzador.lanzar_piezas_nuevas(cliente, experimento_id)


def _cerrar_si_lista(cliente, experimento_id, d):
    """Sin items pendientes: mete a Meta lo que se produjo, pide activarlo
    (puerta de modo) y cierra la derivación como `listo` (todo bien) o
    `error` (algún item falló; lo que sí salió entra igual)."""
    import acciones  # perezoso: acciones importa este módulo
    import propuestas
    if any(i["estado"] in _PENDIENTES for i in d["items"]):
        return
    ep_ids = sorted({ep for i in d["items"] if i["estado"] == "listo" for ep in i["ep_ids"]})
    con_error = [i for i in d["items"] if i["estado"] == "error"]
    if con_error and d["tipo"] == "rescatar":
        # La pieza origen quedó pausada y el decisor no vuelve a pedir ese
        # escalón: que la persona decida (reintentar el rescate o archivar).
        propuestas.crear(cliente, experimento_id, "rescatar", {"ep_id": d["origen_ep_id"]},
                         f"reintentar rescate: falló {'; '.join(i['error'] or 'sin detalle' for i in con_error)}")
    motivo = (f"derivación {d['id']} lista: {len(ep_ids)} pieza(s) nueva(s)"
              + (f", {len(con_error)} fallida(s)" if con_error else "")
              + (f"; {d['motivo']}" if d.get("motivo") else ""))
    if ep_ids:
        try:
            _lanzar_piezas(cliente, experimento_id)
            acciones.pedir(cliente, experimento_id, "activar", {"ep_ids": ep_ids}, motivo)
        except Exception as error:
            d["estado"] = "error"
            experimentos.registrar_evento(cliente, experimento_id, "error",
                                          f"Derivación {d['id']}: no se pudieron lanzar las piezas nuevas: {cola.sin_token(str(error))}",
                                          datos={"derivacion": d["id"], "ep_ids": ep_ids}, ep_id=d["origen_ep_id"])
            return
    d["estado"] = "error" if con_error else "listo"
    d["motivo_cierre"] = motivo
    experimentos.registrar_evento(
        cliente, experimento_id, "derivacion" if not con_error else "error",
        (f"Derivación {d['id']} lista: {len(ep_ids)} pieza(s) nueva(s) en el experimento." if not con_error
         else f"Derivación {d['id']} terminó con {len(con_error)} item(s) fallido(s); {len(ep_ids)} pieza(s) sí entraron."),
        datos={"derivacion": d["id"], "ep_ids": ep_ids}, ep_id=d["origen_ep_id"])


def avanzar(cliente, experimento_id):
    """Una pasada idempotente sobre las derivaciones `produciendo` del
    experimento. Devuelve un resumen: {"estado", "motivo", "derivaciones":
    [{"id", "estado"}]} — `estado` es el de la última derivación tocada
    ("produciendo"|"listo"|"error") o None si no había nada."""
    ex = _experimento(cliente, experimento_id)
    resumen = {"estado": None, "motivo": None, "derivaciones": []}
    for d in list((ex["extra"] or {}).get("derivaciones") or []):
        if d.get("estado") != "produciendo":
            continue
        for item in d["items"]:
            _avanzar_item(cliente, experimento_id, d, item)
            _guardar(cliente, experimento_id, d)  # persistir lo encolado apenas se encola
        _cerrar_si_lista(cliente, experimento_id, d)
        _guardar(cliente, experimento_id, d)
        resumen["estado"], resumen["motivo"] = d["estado"], d.get("motivo_cierre")
        resumen["derivaciones"].append({"id": d["id"], "estado": d["estado"]})
    return resumen
