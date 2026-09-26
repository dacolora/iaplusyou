"""
Duraciones del pipeline de Flow Plus (spec 2026-09-25 §6 y §7.2; spec del
cliente §2.2-§2.3). Puro: sin base ni red. Un clip dura el techo de lo
hablado más el aire de cada momento, con mínimo MIN_CLIP; uno que pasa de
MAX_CLIP no se recorta aquí: lo marca la validación.
"""
import math

MIN_CLIP, MAX_CLIP = 5, 15
SEGUNDO_FINAL = 1.0


def palabras(texto):
    return len(str(texto or "").split())


def seg_hablados(texto, wps):
    return palabras(texto) / float(wps)


def textos_efectivos(lectura, hook="original"):
    """{n: texto} de todas las líneas, con la línea 1 cambiada por el hook elegido."""
    textos = {int(l["n"]): l["texto"] for l in lectura.get("lineas", [])}
    if hook and hook != "original":
        h = next((x for x in lectura.get("hooks", []) if x["id"] == hook), None)
        if h is None:
            raise ValueError(f"hook desconocido: {hook}")
        textos[1] = h["texto"]
    return textos


def conservadas(textos, quitadas=()):
    fuera = {int(n) for n in quitadas}
    return [(n, textos[n]) for n in sorted(textos) if n not in fuera]


def estimado_previo(lineas, wps, aire_por_linea):
    """Guía para el recorte antes de que exista el plan: lo hablado, un aire por línea y el cuadro final."""
    if not lineas:
        return 0.0
    return round(sum(seg_hablados(t, wps) for _, t in lineas) + aire_por_linea * len(lineas) + SEGUNDO_FINAL, 1)


def bloques_quitados(textos, quitadas):
    """Textos de las corridas contiguas quitadas, en el orden del guion."""
    fuera = sorted({int(n) for n in quitadas if int(n) in textos})
    bloques, actual, previo = [], [], None
    for n in fuera:
        if previo is not None and n != previo + 1:
            bloques.append(" ".join(actual))
            actual = []
        actual.append(textos[n])
        previo = n
    if actual:
        bloques.append(" ".join(actual))
    return bloques


def calcular_clip(momentos, textos, wps):
    tramos = []
    for m in momentos:
        dice = [int(n) for n in (m.get("dice") or [])]
        partes = [textos.get(n, "") for n in dice]
        texto = " ".join(p for p in partes if p)
        tramos.append((dice, partes, texto, seg_hablados(texto, wps) + float(m.get("aire") or 0)))
    total = sum(t[3] for t in tramos)
    duracion = max(MIN_CLIP, math.ceil(round(total, 6)))
    bordes, acc = [0.0], 0.0
    for t in tramos:
        acc += t[3]
        bordes.append(round(acc, 1))
    bordes[-1] = float(duracion)
    salida = [{"t_ini": bordes[i], "t_fin": bordes[i + 1], "dice": dice, "textos": partes, "texto": texto,
               "visual": str(m.get("visual") or "")}
              for i, ((dice, partes, texto, _), m) in enumerate(zip(tramos, momentos))]
    return {"duracion": duracion, "palabras": sum(palabras(t[2]) for t in tramos), "momentos": salida}
