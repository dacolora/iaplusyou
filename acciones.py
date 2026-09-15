"""
Acciones del motor (Bloque 4): lo que el decisor recomienda sobre una pieza o
un país — pausar, escalar, derivar, rescatar, activar, archivar — pasa por
aquí. Dos puertas:

- `pedir(...)`: consulta el modo del experimento (modos.resolver) y el tope de
  gasto; o ejecuta la acción, o la deja como propuesta pendiente para el
  humano. En ambos casos escribe un evento.
- `ejecutar(...)`: hace la acción de verdad (Meta vía lanzador, producción vía
  derivaciones). Es idempotente sobre `experimento_pieza.extra`
  (`derivado`, `rescatado_en_escalon`, `archivado`): repetir una acción cara
  no vuelve a gastar. La marca se escribe apenas la parte que gasta
  (producción) quedó planificada, antes de la parte barata y reintentable
  (pausar en Meta), así un fallo de Meta no provoca doble producción.

Nada se activa solo: la única vía es `ejecutar(..., "activar", ...)`, que en
los modos manual/semi solo llega tras aprobar la propuesta.
"""
import cola
import creative_flow
import decisor
import derivaciones
import experimentos
import lanzador
import modos
import propuestas
import proyectos

# Acciones que pueden aumentar el gasto: chequean el tope antes de ejecutarse.
_ACCIONES_CON_GASTO = ("escalar", "activar", "derivar")


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


def _pausar_si_activa(cliente, pz):
    """Pausa en Meta solo si hay anuncio y no está ya pausada (pausar_pieza
    exige meta_ad_id)."""
    if pz.get("meta_ad_id") and pz.get("estado") != "pausado":
        lanzador.pausar_pieza(cliente, pz["id"])


def _cadena_conceptos(cliente, cf_id, maximo=5):
    """La sesión de la pieza y, hacia arriba, de las que fue regenerada
    (`derivado_de`): archivar un concepto que perdió sus 3 escalones archiva
    toda la cadena, no solo la última regeneración. Tope de `maximo` saltos
    por si hubiera un ciclo en los datos."""
    if not cf_id:
        return []
    sesiones = creative_flow.cargar(cliente)
    cadena = []
    while cf_id and cf_id not in cadena and len(cadena) < maximo:
        cadena.append(cf_id)
        cf_id = (sesiones.get(cf_id) or {}).get("derivado_de")
    return cadena


def reglas_de(cliente, ex):
    return decisor.reglas_efectivas(proyectos.reglas_defecto(cliente), ex.get("reglas"))


def tope_alcanzado(ex):
    """Aproximación del chequeo de tope: con el gasto acumulado ya en el tope
    total no se abre ninguna acción que gaste más."""
    tope = float(ex.get("tope_total") or 0)
    return tope > 0 and float(ex.get("gasto_acumulado") or 0) >= tope


def ejecutar(cliente, experimento_id, accion, payload):
    """Ejecuta la acción y devuelve un mensaje corto (en español) de lo que
    pasó. Lanza ValueError si la acción no existe o faltan datos."""
    payload = payload or {}
    ex = _experimento(cliente, experimento_id)
    motivo = payload.get("motivo") or ""

    if accion == "pausar":
        pz = _pieza(ex, payload["ep_id"])
        lanzador.pausar_pieza(cliente, pz["id"])
        return f"Pausada {pz['nombre']} ({pz['pais']})."

    if accion == "escalar":
        pais = payload["pais"]
        reglas = reglas_de(cliente, ex)
        nuevo = lanzador.escalar_pais(cliente, experimento_id, pais, reglas["escalar_pct_dia"], reglas["escalar_tope_dia"])
        return f"Presupuesto de {pais} escalado a {nuevo:g} {ex.get('moneda') or ''} por día."

    if accion == "derivar":
        pz = _pieza(ex, payload["ep_id"])
        if (pz.get("extra") or {}).get("derivado"):
            return f"{pz['nombre']} ya derivada: no se vuelve a producir."
        hijo = derivaciones.planificar(cliente, experimento_id, "derivar", payload)
        experimentos.marcar_pieza(cliente, pz["id"], derivado=True)
        return f"Derivación planificada a partir de {pz['nombre']} (experimento hijo {hijo})."

    if accion == "rescatar":
        pz = _pieza(ex, payload["ep_id"])
        extra = pz.get("extra") or {}
        escalon_actual = int(pz.get("escalon_rescate") or 0)
        marcado = extra.get("rescatado_en_escalon")
        # A lo sumo un rescate por escalón. `planificar` sube
        # `escalon_rescate` de la pieza y acá se marca ese mismo número, así
        # que "ya marcado en el escalón actual (o más alto)" significa que el
        # rescate de este escalón ya se planificó: no se vuelve a producir ni
        # a gastar; solo se asegura la pausa (por si falló la primera vez).
        if marcado is not None and marcado >= escalon_actual:
            _pausar_si_activa(cliente, pz)
            return f"{pz['nombre']} ya rescatada (escalón {marcado}); pieza pausada."
        derivaciones.planificar(cliente, experimento_id, "rescatar", payload)
        # Marcar ANTES de pausar: si Meta falla al pausar, la marca ya existe
        # y una re-ejecución (reintento de la propuesta) no vuelve a
        # planificar — solo reintenta la pausa. El escalón es el que
        # planificar dejó en la pieza (al menos el siguiente al que había).
        pz_post = _pieza(_experimento(cliente, experimento_id), pz["id"])
        escalon = max(int(pz_post.get("escalon_rescate") or 0), escalon_actual + 1)
        experimentos.marcar_pieza(cliente, pz["id"], rescatado_en_escalon=escalon)
        _pausar_si_activa(cliente, pz)
        return f"Rescate planificado para {pz['nombre']} (escalón {escalon}); la pieza queda pausada."

    if accion == "activar":
        ep_ids = list(payload.get("ep_ids") or ([payload["ep_id"]] if payload.get("ep_id") else []))
        if not ep_ids:
            raise ValueError("No hay piezas para activar.")
        if ex["estado"] not in ("pausado", "corriendo", "decidido"):
            raise ValueError("El experimento todavía no está en Meta.")
        if ex["estado"] == "pausado":
            lanzador.cambiar_estado(cliente, experimento_id, "ACTIVE")
        for ep_id in ep_ids:
            lanzador.activar_pieza(cliente, ep_id)
        return f"Activadas {len(ep_ids)} pieza(s)."

    if accion == "archivar":
        pz = _pieza(ex, payload["ep_id"])
        if (pz.get("extra") or {}).get("archivado"):
            return f"{pz['nombre']} ya archivada."
        _pausar_si_activa(cliente, pz)
        for cf_id in _cadena_conceptos(cliente, payload.get("cf_id")):
            creative_flow.archivar_concepto(cliente, cf_id, motivo)
        experimentos.marcar_pieza(cliente, pz["id"], archivado=True)
        return f"Archivado el concepto de {pz['nombre']}: {motivo or 'sin motivo'}."

    raise ValueError(f"Acción desconocida: {accion!r}.")


def pedir(cliente, experimento_id, accion, payload, motivo):
    """Puerta del decisor. Devuelve ("ejecutada", mensaje) o
    ("propuesta", mensaje) según el modo del experimento y el tope; en ambos
    casos queda un evento (tipo `accion` o `propuesta`)."""
    payload = dict(payload or {})
    payload.setdefault("motivo", motivo)
    ex = _experimento(cliente, experimento_id)
    puerta = modos.resolver(ex["modo"], accion)
    motivo_prop = motivo
    if accion in _ACCIONES_CON_GASTO and tope_alcanzado(ex):
        puerta = "propuesta"
        motivo_prop = f"tope alcanzado ({ex.get('gasto_acumulado'):g} de {ex.get('tope_total'):g} {ex.get('moneda') or ''}); {motivo}".strip()
    ep_id = payload.get("ep_id")
    datos = {"accion": accion, "payload": payload, "modo": ex["modo"]}

    if puerta == "ejecutar":
        try:
            mensaje = ejecutar(cliente, experimento_id, accion, payload)
        except Exception as error:
            experimentos.registrar_evento(cliente, experimento_id, "error",
                                          cola.sin_token(str(error)), datos=datos, ep_id=ep_id)
            raise
        experimentos.registrar_evento(cliente, experimento_id, "accion",
                                      f"{mensaje} Motivo: {motivo}.", datos=datos, ep_id=ep_id)
        return "ejecutada", mensaje

    pid = propuestas.crear(cliente, experimento_id, accion, payload, motivo_prop)
    mensaje = f"Propuesta pendiente: {accion} ({motivo_prop})."
    experimentos.registrar_evento(cliente, experimento_id, "propuesta", mensaje,
                                  datos={**datos, "propuesta_id": pid}, ep_id=ep_id)
    return "propuesta", mensaje
