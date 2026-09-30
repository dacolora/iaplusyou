"""
Qué es un avatar «completo» (spec 2026-09-29 §2) y cómo se funde lo que
completa Claude sin pisar lo que ya estaba. Puro: sin base ni red.

Completo = nombre, deseo, demografía, edad, emoción, las tres respuestas de
identidad, encaje del producto, comportamiento, nivel de conciencia y tono no
vacíos; al menos MIN_SITUACIONES situaciones, MIN_SOLUCIONES solución probada
con al menos un motivo de falla, MIN_PALABRAS palabras clave y, solo para
avatares de estudio, MIN_CITAS citas verificadas.
"""
from idiomas import N_

MIN_SITUACIONES = 2
MIN_SOLUCIONES = 1
MIN_PALABRAS = 3
MIN_CITAS = 2
TEXTOS = ("nombre", "deseo", "demografia", "edad_rango", "emocion", "encaje_producto", "comportamiento", "tono")
CLAVES_IDENTIDAD = ("quiere_que_vean", "cree_de_si", "quiere_lograr")
ORDEN = ("nombre", "deseo", "demografia", "edad_rango", "emocion", "identidad", "encaje_producto", "soluciones_previas",
         "situaciones", "comportamiento", "conciencia", "tono", "palabras_clave", "evidencia")
ETIQUETAS = {"nombre": N_("nombre"), "deseo": N_("deseo"), "demografia": N_("demografía"), "edad_rango": N_("edad"),
             "emocion": N_("emoción"), "identidad": N_("identidad"), "encaje_producto": N_("encaje del producto"),
             "soluciones_previas": N_("soluciones que probó"), "situaciones": N_("situaciones (mínimo 2)"),
             "comportamiento": N_("comportamiento"), "conciencia": N_("nivel de conciencia"), "tono": N_("tono"),
             "palabras_clave": N_("palabras clave (mínimo 3)"), "evidencia": N_("citas (mínimo 2)")}


def _vacio(v):
    return not str(v or "").strip()


def _dict(v):
    return v if isinstance(v, dict) else {}


def _llenos(lista):
    return [x for x in (lista or []) if str(x).strip()]


def soluciones_validas(a):
    return [s for s in ((a or {}).get("soluciones_previas") or [])
            if isinstance(s, dict) and not _vacio(s.get("que")) and _llenos(s.get("por_que_fallo"))]


def faltantes(a, con_evidencia=True):
    """Claves que le faltan al avatar para estar completo, en ORDEN (vacío = completo)."""
    a = a or {}
    falta = {k for k in TEXTOS if _vacio(a.get(k))}
    if any(_vacio(_dict(a.get("identidad")).get(k)) for k in CLAVES_IDENTIDAD):
        falta.add("identidad")
    if _vacio(_dict(a.get("conciencia")).get("nivel")):
        falta.add("conciencia")
    if len(soluciones_validas(a)) < MIN_SOLUCIONES:
        falta.add("soluciones_previas")
    if len(_llenos(a.get("situaciones"))) < MIN_SITUACIONES:
        falta.add("situaciones")
    if len(_llenos(a.get("palabras_clave"))) < MIN_PALABRAS:
        falta.add("palabras_clave")
    if con_evidencia and len(a.get("evidencia") or []) < MIN_CITAS:
        falta.add("evidencia")
    return [k for k in ORDEN if k in falta]


def fundir(sub, nuevos):
    """Copia de `sub` con lo que le faltaba tomado de `nuevos` (ya normalizados
    por `nicho.datos.validar_campos_avatar`). Nunca pisa un texto lleno ni el
    nombre; completa las listas cortas sin repetir (sin distinguir mayúsculas);
    no toca la evidencia (el llamador la verifica y la agrega)."""
    s, n = dict(sub or {}), dict(nuevos or {})
    for k in TEXTOS:
        if k != "nombre" and _vacio(s.get(k)) and not _vacio(n.get(k)):
            s[k] = n[k]
    if _dict(n.get("identidad")):
        ident = dict(_dict(s.get("identidad")))
        for k in CLAVES_IDENTIDAD:
            if _vacio(ident.get(k)) and not _vacio(n["identidad"].get(k)):
                ident[k] = n["identidad"][k]
        s["identidad"] = ident
    if _vacio(_dict(s.get("conciencia")).get("nivel")) and not _vacio(_dict(n.get("conciencia")).get("nivel")):
        s["conciencia"] = dict(n["conciencia"])
    if len(soluciones_validas(s)) < MIN_SOLUCIONES and n.get("soluciones_previas"):
        # Ruling 20 (1): conserva TODO lo que ya había (válido o no -- una
        # persona pudo escribir una solución sin "por qué falló") y solo
        # agrega las nuevas válidas cuyo "que" no repite una ya existente.
        existentes = list(s.get("soluciones_previas") or [])
        vistos = {str(x.get("que") or "").strip().lower() for x in existentes if isinstance(x, dict)}
        nuevas = []
        for x in n["soluciones_previas"]:
            if not isinstance(x, dict) or _vacio(x.get("que")) or not _llenos(x.get("por_que_fallo")):
                continue
            clave = str(x.get("que") or "").strip().lower()
            if clave in vistos:
                continue
            vistos.add(clave)
            nuevas.append(x)
        s["soluciones_previas"] = existentes + nuevas
    for k, minimo in (("situaciones", MIN_SITUACIONES), ("palabras_clave", MIN_PALABRAS)):
        actuales = _llenos(s.get(k))
        if len(actuales) < minimo:
            vistos = {str(x).strip().lower() for x in actuales}
            for x in n.get(k) or []:
                if str(x).strip() and str(x).strip().lower() not in vistos:
                    actuales.append(x)
                    vistos.add(str(x).strip().lower())
            s[k] = actuales[:8]
    return s
