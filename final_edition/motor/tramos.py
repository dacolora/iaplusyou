"""Partición del render por tramos (spec §2.2): cada `overlay` de ffmpeg
cuesta ~8 MB de RSS; por encima de PRESUPUESTO_OVERLAYS el documento se
renderiza por ventanas de tiempo y se concatena sin recodificar. Puro."""
from final_edition.documento import duracion_ms

PRESUPUESTO_OVERLAYS = 60
TRAMO_MIN_MS = 2000
_PISTAS_OVERLAY = ("superpuesto", "imagen", "texto")


def capas_overlay(doc):
    capas = []
    for p in doc.get("pistas") or []:
        if p["tipo"] not in _PISTAS_OVERLAY or p.get("oculta"):
            continue
        for c in p.get("clips") or []:
            capas.append({"inicio_ms": int(c["inicio_ms"]), "fin_ms": int(c["inicio_ms"]) + int(c["duracion_ms"]),
                          "pista_id": p["id"], "clip_id": c["id"]})
    if (doc.get("marca") or {}).get("marca_de_agua"):
        capas.append({"inicio_ms": 0, "fin_ms": duracion_ms(doc), "pista_id": "marca", "clip_id": "marca_de_agua"})
    return capas


def contar(doc, inicio_ms, fin_ms):
    return sum(1 for c in capas_overlay(doc) if c["inicio_ms"] < fin_ms and c["fin_ms"] > inicio_ms)


def _fronteras_seguras(doc, total):
    """Fines de clip de la pista principal, corridos al final de su
    transición si la hay (nunca se corta dentro de un xfade)."""
    principal = next((p for p in doc["pistas"] if p["tipo"] == "video"), None)
    puntos = set()
    for c in (principal or {}).get("clips") or []:
        fin = int(c["inicio_ms"]) + int(c["duracion_ms"])
        tr = c.get("transicion")
        if tr and tr.get("tipo", "corte") != "corte" and int(tr.get("duracion_ms", 0)) > 0:
            fin += int(tr["duracion_ms"])
        if 0 < fin < total:
            puntos.add(fin)
    return sorted(puntos)


def _intervalos_transicion(doc):
    """[(fin_A, fin_A + d)] de cada transición de la pista principal: el
    intervalo de salida que ocupa la cola de A mientras B ya empieza en su
    posición exacta. Cortar en ese rango pierde la transición."""
    principal = next((p for p in doc["pistas"] if p["tipo"] == "video"), None)
    intervalos = []
    for c in (principal or {}).get("clips") or []:
        fin = int(c["inicio_ms"]) + int(c["duracion_ms"])
        tr = c.get("transicion")
        if tr and tr.get("tipo", "corte") != "corte" and int(tr.get("duracion_ms", 0)) > 0:
            intervalos.append((fin, fin + int(tr["duracion_ms"])))
    return intervalos


def _fuera_de_transicion(punto, intervalos):
    """Corre `punto` al final de la transición que lo contiene, si la hay.
    En la práctica el punto empujado coincide con el fin del tramo, porque
    cada fin de transición es una frontera; el tramo se acepta entero."""
    for a, b in intervalos:
        if a <= punto < b:
            return b
    return punto


def _max_simultaneas(doc, inicio, fin):
    eventos = []
    for c in capas_overlay(doc):
        if c["inicio_ms"] < fin and c["fin_ms"] > inicio:
            eventos.append((max(c["inicio_ms"], inicio), 1)); eventos.append((min(c["fin_ms"], fin), -1))
    eventos.sort(key=lambda e: (e[0], e[1]))
    peor = actual = 0
    for _, delta in eventos:
        actual += delta; peor = max(peor, actual)
    return peor


def partir(doc, presupuesto=None):
    """Un tramo de ≤ TRAMO_MIN_MS, o uno que no se puede partir sin romper
    una transición, puede superar el presupuesto; el único error duro es
    superar el presupuesto en un mismo instante."""
    presupuesto = PRESUPUESTO_OVERLAYS if presupuesto is None else presupuesto
    total = duracion_ms(doc)
    if total <= 0 or contar(doc, 0, total) <= presupuesto:
        return [(0, max(total, 0))]
    if _max_simultaneas(doc, 0, total) > presupuesto:
        raise ValueError(f"Hay más de {presupuesto} capas en el mismo instante; quita algunas.")
    fronteras = _fronteras_seguras(doc, total)
    tramos, inicio = [], 0
    for f in fronteras + [total]:
        if f <= inicio:
            continue
        tramos.append((inicio, f)); inicio = f
    # Subdividir por tiempo los tramos que aún se pasan, sin partir una
    # transición: un candidato que caiga dentro se corre a su fin; si eso ya
    # no deja espacio para partir, el tramo se acepta entero (puede quedar
    # sobre presupuesto).
    intervalos = _intervalos_transicion(doc)
    listo = []
    for a, b in tramos:
        pendientes = [(a, b)]
        while pendientes:
            x, y = pendientes.pop(0)
            if contar(doc, x, y) <= presupuesto or y - x <= TRAMO_MIN_MS:
                listo.append((x, y)); continue
            medio = x + max(TRAMO_MIN_MS, (y - x) // 2)
            medio = min(medio, y - 1)
            medio = _fuera_de_transicion(medio, intervalos)
            if medio >= y:
                listo.append((x, y)); continue
            pendientes = [(x, medio), (medio, y)] + pendientes
    return listo
