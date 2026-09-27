"""El revisor de la pieza terminada (doctrina, bloque 3; spec
`docs/superpowers/specs/2026-09-27-doctrina-bloque-3-revisor-design.md`).

Dos capas sobre la lista de `textos/revisar.md`: `reglas(datos)` revisa lo
mecánico (puro, gratis, siempre igual) y `revisar(cliente, cf_id)` le pide a
Claude con visión los 12 puntos. Nada de esto bloquea ni reescribe: informa."""
import json

import doctrina

PUNTOS = (
    (1, "gancho", "Gancho", "gancho"),
    (2, "una_idea", "Una sola idea", "angulo"),
    (3, "reason_why", "El porqué", "base"),
    (4, "pruebas", "Pruebas", "base"),
    (5, "mecanismo", "Mecanismo", "angulo"),
    (6, "visuales", "Visuales", "video"),
    (7, "ojos", "Texto en pantalla", "video"),
    (8, "lado_brillante", "Lado brillante", "guion"),
    (9, "cierre", "Cierre", "guion"),
    (10, "marca", "Marca", "revisar"),
    (11, "aburrimiento", "Aburrimiento", "revisar"),
    (12, "mismo_mensaje", "Mismo mensaje", "angulo"),
)
PUNTO = {n: {"n": n, "clave": c, "titulo": t, "rebanada": r} for n, c, t, r in PUNTOS}
ESTADOS = ("pasa", "mejorar", "no_aplica")
MAX_FOTOGRAMAS = 8
MAX_DETALLE = 400


class ErrorRevision(RuntimeError):
    """La revisión no se pudo hacer o Claude no respondió algo usable.
    `tokens_entrada`/`tokens_salida` traen lo ya pagado (0 si no se llamó)."""
    def __init__(self, mensaje, tokens_entrada=0, tokens_salida=0):
        super().__init__(mensaje)
        self.tokens_entrada, self.tokens_salida = tokens_entrada, tokens_salida


def _palabras(texto):
    return len(str(texto or "").split())


def _norm(texto):
    return " ".join(str(texto or "").lower().split())


def _entero(valor):
    try:
        return int(valor)
    except (TypeError, ValueError, OverflowError):
        return None


def bloques_guion(guion):
    return [b for b in ((guion or {}).get("bloques") or []) if isinstance(b, dict)]


def textos_guion(guion):
    return [str(b[k]) for b in bloques_guion(guion) for k in ("texto_voz", "texto_pantalla") if b.get(k)]


def reglas(datos):
    """Revisión rápida: [{"n", "codigo", "texto", "donde"}] ordenada por punto.

    `datos` (lo arma `reunir`): `angulo` (dict o None), `sofisticacion_fija`
    (la del producto, manda si existe), `guion` (dict o None), `caption`
    (str), `idea` (dict o None: la idea del sprint) y `verificables` (el
    texto contra el que se verifican las cifras del caption). Sin ángulo, las
    reglas que lo necesitan no se evalúan."""
    avisos = []

    def aviso(n, codigo, texto, donde):
        avisos.append({"n": n, "codigo": codigo, "texto": texto, "donde": donde})

    a = datos.get("angulo") if isinstance(datos.get("angulo"), dict) else None
    if a:
        gancho = " ".join(str(a.get("gancho") or "").split())
        if gancho and _palabras(gancho) > doctrina.MAX_PALABRAS_GANCHO:
            aviso(1, "gancho_largo", f"El gancho tiene {_palabras(gancho)} palabras: con {doctrina.MAX_PALABRAS_GANCHO} "
                                     "o menos se lee en tres segundos.", "angulo")
        cons = doctrina.normalizar_consciencia(a.get("consciencia"))
        recomendados = doctrina.lead_por_consciencia(cons) if cons else ()
        lead = a.get("lead")
        if cons and lead in doctrina.LEADS and recomendados and lead not in recomendados:
            aviso(1, "arranque_consciencia",
                  f"El arranque «{doctrina.LEADS_NOMBRE[lead]}» no es de los recomendados para una audiencia "
                  f"{doctrina.CONSCIENCIAS_NOMBRE[cons]}: mejor "
                  + " o ".join(f"«{doctrina.LEADS_NOMBRE[x]}»" for x in recomendados) + ".", "angulo")
        _, errores = doctrina.validar_angulo(a)
        if "promesa_multiple" in errores:
            aviso(2, "promesa_multiple", "La promesa dice más de una cosa: una pieza vende una sola idea.", "angulo")
        fija = _entero(datos.get("sofisticacion_fija"))
        sof = fija if fija in doctrina.SOFISTICACIONES else _entero(a.get("sofisticacion"))
        if sof is not None and sof >= 3 and not str(a.get("mecanismo") or "").strip():
            aviso(5, "sin_mecanismo", f"El mercado ya vio promesas parecidas (sofisticación {sof}) y el ángulo no dice "
                                      "por qué funciona el producto (el mecanismo).", "angulo")
    caption = str(datos.get("caption") or "")
    for cifra in doctrina.verificar_cifras(caption, datos.get("verificables") or ""):
        aviso(4, "cifra_no_verificada", f"La cifra «{cifra}» del caption no está en los datos del producto ni en sus "
                                        "pruebas: si es real, agrégala como prueba del producto.", "caption")
    bloques = bloques_guion(datos.get("guion"))
    if bloques and bloques[-1].get("rol") != "cta":
        aviso(9, "sin_cta", "El guion no termina con una llamada a la acción.", "guion")
    idea = datos.get("idea") if isinstance(datos.get("idea"), dict) else None
    if a and idea and idea.get("gancho") and a.get("gancho") and _norm(idea["gancho"]) != _norm(a["gancho"]):
        aviso(12, "gancho_distinto", "El gancho de la idea del sprint no es el del ángulo: la pieza puede estar "
                                     "contando dos cosas distintas.", "idea")
    return sorted(avisos, key=lambda x: x["n"])


def tiempos(duracion):
    """Segundos de los fotogramas a revisar: 0,3 (el gancho), uno cada 3 s y
    el último cerca del final (el cierre); si pasan de `MAX_FOTOGRAMAS`, esos
    se reparten parejo de principio a fin."""
    d = _numero(duracion)
    if d is None or d <= 0.6:
        return [0.3]
    ts = [0.3]
    t = 3.0
    while t < d - 0.3:
        ts.append(t)
        t += 3.0
    if d - 0.3 - ts[-1] >= 1.5:
        ts.append(round(d - 0.3, 2))
    if len(ts) > MAX_FOTOGRAMAS:
        paso = (d - 0.6) / (MAX_FOTOGRAMAS - 1)
        ts = [round(0.3 + i * paso, 2) for i in range(MAX_FOTOGRAMAS)]
    return ts


def _numero(valor):
    try:
        v = float(valor)
    except (TypeError, ValueError, OverflowError):
        return None
    return v if v == v and v not in (float("inf"), float("-inf")) else None


def parsear_revision(texto):
    """{"puntos": [12 puntos en orden], "resumen"} desde la respuesta de
    Claude. Exige los 12 `n` una vez, estados válidos y detalle en «mejorar»;
    si no, `ErrorRevision` (sin tokens: los pone quien llamó)."""
    t = (texto or "").strip()
    ini, fin = t.find("{"), t.rfind("}")
    if ini < 0 or fin <= ini:
        raise ErrorRevision("Claude no devolvió JSON.")
    try:
        data = json.loads(t[ini:fin + 1])
    except ValueError as e:
        raise ErrorRevision(f"JSON inválido: {e}")
    crudos = data.get("puntos") if isinstance(data, dict) else None
    if not isinstance(crudos, list):
        raise ErrorRevision("El JSON no trae la lista «puntos».")
    puntos = {}
    for p in crudos:
        if not isinstance(p, dict):
            continue
        n = _entero(p.get("n"))
        if n not in PUNTO:
            continue
        if n in puntos:
            raise ErrorRevision(f"El punto {n} viene dos veces.")
        estado = p.get("estado")
        if estado not in ESTADOS:
            raise ErrorRevision(f"El punto {n} trae un estado que no existe: «{estado}».")
        detalle = " ".join(str(p.get("detalle") or "").split())[:MAX_DETALLE]
        if estado == "mejorar" and not detalle:
            raise ErrorRevision(f"El punto {n} dice «mejorar» sin decir qué.")
        puntos[n] = {"n": n, "estado": estado, "detalle": detalle,
                     "donde": " ".join(str(p.get("donde") or "").split())[:80]}
    faltan = [n for n in PUNTO if n not in puntos]
    if faltan:
        raise ErrorRevision("Faltan los puntos " + ", ".join(str(n) for n in faltan) + ".")
    resumen = " ".join(str(data.get("resumen") or "").split())[:300]
    return {"puntos": [puntos[n] for n in sorted(puntos)], "resumen": resumen}


def contar(rev):
    """Puntos «para mejorar» de una revisión guardada más los avisos de la
    foto de reglas que se guardó con ella; 0 si no hay revisión o falló."""
    if not isinstance(rev, dict) or rev.get("error"):
        return 0
    mejorar = sum(1 for p in rev.get("puntos") or [] if isinstance(p, dict) and p.get("estado") == "mejorar")
    return mejorar + sum(1 for x in rev.get("reglas") or [] if isinstance(x, dict))


def estado_revision(rev, video_url=None):
    """«sin_revisar», «vieja» (es de otro video), «error», «mejorar» o «bien».
    Con `video_url=None` no se mira si es vieja (una final se muestra con la
    revisión de su pieza de origen)."""
    if not isinstance(rev, dict) or not rev:
        return "sin_revisar"
    if video_url is not None and rev.get("video_url") != video_url:
        return "vieja"
    if rev.get("error"):
        return "error"
    return "mejorar" if contar(rev) else "bien"


def resumen_galeria(rev, video_url=None):
    """Lo que muestra la etiqueta de Experimentos y de Sprints: {"estado", "n"}."""
    est = estado_revision(rev, video_url)
    return {"estado": est, "n": contar(rev) if est in ("mejorar", "bien") else 0}
