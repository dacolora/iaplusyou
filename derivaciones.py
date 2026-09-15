"""
Derivaciones (Bloque 4): producir piezas nuevas a partir de una pieza del
experimento y meterlas al experimento cuando estén listas.

- `derivar` (pieza ganadora): experimento hijo con N re-ediciones (variantes
  hook/estructura de la misma sesión) + M regeneraciones (sesiones nuevas
  con otro modelo y otro enfoque, que primero generan el clon y luego sus
  finales por país).
- `rescatar` (pieza perdedora): una sola pieza en el mismo experimento según
  el escalón (1 → re-edición hook, 2 → re-edición estructura, 3 →
  regeneración).

La producción es asíncrona (worker): `planificar` deja la máquina de estados
en `experimento.extra["derivaciones"]` del experimento DESTINO y encola lo que
puede; `avanzar` (periódica `exp_avanzar_todos`, cada 10 min) es idempotente:
mira qué terminó, encola lo que falta y, cuando todo está listo, mete las
piezas al experimento y lanza sus anuncios. Nada se activa solo: la
activación pasa por `acciones.pedir("activar")` (puerta de modo).

Forma guardada (una entrada por derivación):
  {"id": "d1", "tipo": "derivar"|"rescatar", "origen_ep_id", "cf_id",
   "motivo", "estado": "produciendo"|"listo"|"error", "creado_en",
   "items": [{"clase": "reedicion"|"regeneracion", "variante": n|None,
              "variante_tipo": "hook"|"estructura"|None, "cf_id",
              "paises": [...], "idiomas": {pais: idioma},
              "estado": "produciendo_clon"|"produciendo_finales"|"listo"|"error",
              "finales": {"<idioma>_<pais>": legado_id}, "ep_ids": [...],
              "error": str|None}]}

`acciones` importa este módulo a nivel de módulo; acá se importa `acciones`
de forma perezosa (solo en `_cerrar_si_lista`) para evitar el ciclo.
"""
import creative_flow
import db
import decisor
import experimentos
import lanzador
import proyectos
import trabajos
from final_edition import ETAPAS_FINAL
from final_edition.tipos import PAISES
from providers import flowplus_modelos
from tareas import final_edition as tareas_fe
from tareas.flowplus import ETAPAS_CREATIVE_FLOW

ENFOQUES = ("producto", "persona", "unboxing")
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


def _idiomas(pz, paises):
    """País destino -> idioma de la final a producir: el de la final origen
    si la pieza es una final; si es un clon, el idioma base de cada país."""
    if pz.get("tipo") == "final" and pz.get("idioma"):
        return {p: pz["idioma"] for p in paises}
    return {p: (PAISES.get(p) or {}).get("idioma", "es") for p in paises}


def _siguiente_variante(cliente, cf_id, idiomas):
    """Primer número de variante libre en TODOS los destinos del item (una
    re-edición usa el mismo número en cada país)."""
    usadas = [f["variante"] or 0 for f in creative_flow.finales(cliente, cf_id)
              if f"{f['idioma']}_{f['pais']}" in {f"{i}_{p}" for p, i in idiomas.items()}]
    return (max(usadas) if usadas else 0) + 1


def _otro(lista, actual, desplazamiento):
    """Elemento `desplazamiento` posiciones después de `actual` en `lista`
    (cíclico) — así dos regeneraciones no repiten modelo/enfoque."""
    lista = list(lista)
    base = lista.index(actual) if actual in lista else 0
    return lista[(base + desplazamiento) % len(lista)]


def _item_reedicion(cf_id, variante, variante_tipo, idiomas):
    return {"clase": "reedicion", "variante": variante, "variante_tipo": variante_tipo, "cf_id": cf_id,
            "paises": list(idiomas), "idiomas": dict(idiomas), "estado": "produciendo_finales",
            "finales": {}, "ep_ids": [], "error": None}


def _item_regeneracion(cliente, cf_id, n, idiomas):
    """Sesión nueva (n-ésima regeneración, n >= 1) con otro modelo de video y
    otro enfoque que el original; el clon se genera en `avanzar`."""
    sesion = creative_flow.cargar(cliente).get(cf_id) or {}
    modelo = _otro(flowplus_modelos.VIDEO, sesion.get("modelo") or flowplus_modelos.VIDEO_POR_DEFECTO, n)
    enfoque = _otro(ENFOQUES, sesion.get("enfoque") or ENFOQUES[0], n)
    nuevo = creative_flow.duplicar(cliente, cf_id, modelo=modelo, enfoque=enfoque)
    return {"clase": "regeneracion", "variante": None, "variante_tipo": None, "cf_id": nuevo,
            "paises": list(idiomas), "idiomas": dict(idiomas), "estado": "produciendo_clon",
            "finales": {}, "ep_ids": [], "error": None}


def _guardar(cliente, experimento_id, derivacion):
    """Escribe la derivación en `extra.derivaciones` del experimento releyendo
    `extra` justo antes (actualizar reemplaza el dict completo)."""
    ex = _experimento(cliente, experimento_id)
    extra = dict(ex["extra"] or {})
    lista = [d for d in (extra.get("derivaciones") or []) if d.get("id") != derivacion["id"]]
    lista.append(derivacion)
    extra["derivaciones"] = sorted(lista, key=lambda d: int(d["id"][1:]))
    experimentos.actualizar(cliente, experimento_id, extra=extra)


def _nueva(cliente, experimento_id, tipo, pz, cf_id, motivo, items):
    existentes = (_experimento(cliente, experimento_id)["extra"] or {}).get("derivaciones") or []
    return {"id": f"d{len(existentes) + 1}", "tipo": tipo, "origen_ep_id": pz["id"], "cf_id": cf_id,
            "motivo": motivo or "", "estado": "produciendo", "creado_en": db.ahora(), "items": items}


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
    reglas = decisor.reglas_efectivas(proyectos.reglas_defecto(cliente), ex.get("reglas"))
    idiomas = _idiomas(pz, [p["pais"] for p in ex["paises"]])
    hijo = experimentos.crear_hijo(cliente, ex["id"], f"{ex['nombre']} · derivado de {pz['nombre']}", pz["id"])
    items = []
    base = _siguiente_variante(cliente, cf_id, idiomas)
    for k in range(int(reglas.get("n_reediciones") or 0)):
        items.append(_item_reedicion(cf_id, base + k, TIPOS_VARIANTE[k % 2], idiomas))
    for k in range(int(reglas.get("n_regeneraciones") or 0)):
        items.append(_item_regeneracion(cliente, cf_id, k + 1, idiomas))
    d = _nueva(cliente, hijo, "derivar", pz, cf_id, motivo, items)
    _guardar(cliente, hijo, d)
    mensaje = f"Derivación {d['id']} a partir de {pz['nombre']}: {_resumen_items(items) or 'sin piezas'}."
    experimentos.registrar_evento(cliente, ex["id"], "derivacion", f"{mensaje} Experimento hijo {hijo}.",
                                  datos={"hijo": hijo, "derivacion": d["id"]}, ep_id=pz["id"])
    experimentos.registrar_evento(cliente, hijo, "derivacion", f"{mensaje} Motivo: {motivo or 'sin motivo'}.",
                                  datos={"padre": ex["id"], "derivacion": d["id"]})
    avanzar(cliente, hijo)
    return hijo


def _planificar_rescatar(cliente, ex, pz, motivo):
    cf_id = _cf_id_de(pz)
    escalon = int(pz.get("escalon_rescate") or 0) + 1
    if escalon not in _ESCALONES:
        raise ValueError(f"{pz['nombre']} ya agotó los {len(_ESCALONES)} escalones de rescate.")
    idiomas = _idiomas(pz, [pz["pais"]])
    clase, variante_tipo = _ESCALONES[escalon]
    if clase == "reedicion":
        item = _item_reedicion(cf_id, _siguiente_variante(cliente, cf_id, idiomas), variante_tipo, idiomas)
    else:
        item = _item_regeneracion(cliente, cf_id, escalon, idiomas)
    experimentos.actualizar_pieza(cliente, pz["id"], escalon_rescate=escalon)
    d = _nueva(cliente, ex["id"], "rescatar", pz, cf_id, motivo, [item])
    _guardar(cliente, ex["id"], d)
    experimentos.registrar_evento(
        cliente, ex["id"], "derivacion",
        f"Rescate {d['id']} de {pz['nombre']} (escalón {escalon}): {_resumen_items([item])}. Motivo: {motivo or 'sin motivo'}.",
        datos={"derivacion": d["id"], "escalon": escalon}, ep_id=pz["id"])
    avanzar(cliente, ex["id"])
    return ex["id"]


# ------------------------------------------------------------ avanzar ---

def _encolar_clon(cliente, cf_id):
    """Genera el video de la sesión nueva (como `dashboard._lanzar_video_cf`):
    marca `video_generando` antes de encolar; no encola si ya hay una viva."""
    job_id = f"{cliente}__{cf_id}__creative_flow"
    if trabajos.en_curso(job_id):
        return False
    creative_flow.actualizar(cliente, cf_id, estado="video_generando")
    return trabajos.encolar(job_id, "flowplus_video", {"cliente": cliente, "cf_id": cf_id}, cliente=cliente,
                            duracion_estimada=180, etapas=ETAPAS_CREATIVE_FLOW, max_intentos=1)


def _encolar_final(cliente, cf_id, idioma, pais, opciones):
    """Produce una final (como `dashboard.fe_producir`): fila en `generando`
    desde que se encola. Devuelve el legado_id de la final."""
    variante = opciones.get("variante")
    job_id = tareas_fe.job_id_final(cliente, cf_id, idioma, pais, variante=variante)
    legado = tareas_fe._legado_final(cf_id, idioma, pais, variante)
    if trabajos.en_curso(job_id):
        return legado
    creative_flow.crear_final(cliente, cf_id, idioma, pais, variante=variante)
    trabajos.encolar(job_id, "final_producir",
                     {"cliente": cliente, "cf_id": cf_id, "idioma": idioma, "pais": pais, "opciones": dict(opciones)},
                     cliente=cliente, duracion_estimada=240, etapas=ETAPAS_FINAL, max_intentos=1)
    return legado


def _estado_sesion(cliente, cf_id):
    s = creative_flow.cargar(cliente).get(cf_id)
    if s is None:
        return "error", f"la sesión {cf_id} ya no existe"
    return s.get("estado"), s.get("error")


def _estado_final(cliente, legado):
    f = creative_flow.final_por_legado(cliente, legado)
    if f is None:
        return "error", f"la final {legado} ya no existe"
    return f["estado"], f.get("error")


def _opciones_de(item):
    if item["clase"] == "reedicion":
        return {"variante": item["variante"], "variante_tipo": item["variante_tipo"]}
    return {"variante": None}


def _fallar(cliente, experimento_id, item, motivo):
    item["estado"], item["error"] = "error", motivo
    experimentos.registrar_evento(cliente, experimento_id, "error",
                                  f"Falló {_resumen_items([item])}: {motivo}.", datos={"cf_id": item["cf_id"]})


def _avanzar_clon(cliente, experimento_id, item):
    estado, error = _estado_sesion(cliente, item["cf_id"])
    if estado == "video_listo":
        item["estado"] = "produciendo_finales"
        _avanzar_finales(cliente, experimento_id, item)
    elif estado == "error":
        _fallar(cliente, experimento_id, item, error or "la generación del clon falló")
    elif estado != "video_generando":
        _encolar_clon(cliente, item["cf_id"])
    # video_generando: esperar.


def _avanzar_finales(cliente, experimento_id, item):
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
                item["ep_ids"].append(ep_id)
            listas.add(clave)
        elif estado == "error":
            _fallar(cliente, experimento_id, item, error or f"la final {clave} falló")
            return
        # generando: esperar.
    if len(listas) == len(item["paises"]):
        item["estado"] = "listo"


def _avanzar_item(cliente, experimento_id, item):
    if item["estado"] == "produciendo_clon":
        _avanzar_clon(cliente, experimento_id, item)
    elif item["estado"] == "produciendo_finales":
        _avanzar_finales(cliente, experimento_id, item)


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
    if any(i["estado"] in _PENDIENTES for i in d["items"]):
        return
    ep_ids = sorted({ep for i in d["items"] if i["estado"] == "listo" for ep in i["ep_ids"]})
    con_error = [i for i in d["items"] if i["estado"] == "error"]
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
                                          f"Derivación {d['id']}: no se pudieron lanzar las piezas nuevas: {error}",
                                          datos={"derivacion": d["id"], "ep_ids": ep_ids})
            return
    d["estado"] = "error" if con_error else "listo"
    d["motivo_cierre"] = motivo
    experimentos.registrar_evento(
        cliente, experimento_id, "derivacion" if not con_error else "error",
        (f"Derivación {d['id']} lista: {len(ep_ids)} pieza(s) nueva(s) en el experimento." if not con_error
         else f"Derivación {d['id']} terminó con {len(con_error)} item(s) fallido(s); {len(ep_ids)} pieza(s) sí entraron."),
        datos={"derivacion": d["id"], "ep_ids": ep_ids})


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
            _avanzar_item(cliente, experimento_id, item)
        _cerrar_si_lista(cliente, experimento_id, d)
        _guardar(cliente, experimento_id, d)
        resumen["estado"], resumen["motivo"] = d["estado"], d.get("motivo_cierre")
        resumen["derivaciones"].append({"id": d["id"], "estado": d["estado"]})
    return resumen
