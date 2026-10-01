"""Subtítulos derivados del audio (editor, capa 5a, spec D1-D4): el
documento guarda QUÉ subtitular (`subtitulos.fuentes`) y las correcciones
(`subtitulos.correcciones`); las palabras en sí viven en el MATERIAL
(`material.extra.palabras`, tiempo propio del archivo). Este módulo mapea
esas palabras a la línea de tiempo de un documento YA RESUELTO
(`documento.resolver`) — nada se guarda con tiempos absolutos, así que
cortar, recortar, reordenar, borrar o cambiar la velocidad nunca desincroniza
un subtítulo: por construcción, siguen al audio.

Puro: sin base, sin red, sin ffmpeg. `aplicar` es lo que usan el render
(`tareas.edicion.renderizar_final`) y la vista previa (su espejo
`static/editor/subtitulos_fuente.js`) después de `documento.resolver`; nunca
antes (el resuelto ya aplicó `por_destino` y quitó los audios de otro
idioma, D10)."""
from final_edition import documento

# D2 punto 4: las velocidades del editor son cuartos de 1.0 (0.25, 0.5...);
# con `k = round(4·v)` exacto, el mapeo es una división ENTERA (`divmod`,
# nunca flotante) redondeada a la par — paridad exacta con la JS.
_EPS = 1e-9


def _k_de_velocidad(velocidad):
    v = float(velocidad)
    k = round(4 * v)
    if k and abs(4 * v - k) < _EPS:
        return k
    return None


def _division_par(n, d):
    """n/d entero, redondeado a la par (round-half-to-even); n, d >= 0."""
    q, r = divmod(n, d)
    doble = 2 * r
    if doble < d:
        return q
    if doble > d:
        return q + 1
    return q if q % 2 == 0 else q + 1


def mapear(dt_ms, velocidad):
    """ms de línea de tiempo que corresponden a `dt_ms` ms de material a
    esta `velocidad` (D2 punto 4): con `velocidad` un cuarto exacto, división
    entera `4·dt_ms / k` redondeada a la par; si no, `round()` de Python (ya
    redondea a la par)."""
    dt = int(dt_ms)
    k = _k_de_velocidad(velocidad)
    if k is not None:
        return _division_par(4 * dt, k)
    return round(dt / float(velocidad))


def _tramo(duracion_ms, velocidad):
    """Material (ms) que consume en pantalla un clip de `duracion_ms` ms de
    línea de tiempo a esta `velocidad` (D2 punto 1): `duracion_ms·k / 4`,
    mismo redondeo a la par que `mapear`."""
    dur = int(duracion_ms)
    k = _k_de_velocidad(velocidad)
    if k is not None:
        return _division_par(dur * k, 4)
    return round(dur * float(velocidad))


def _fin_principal(doc):
    p = documento.pista_principal(doc)
    return max((int(c["inicio_ms"]) + int(c["duracion_ms"]) for c in (p or {}).get("clips") or []), default=0)


def _limpiar_texto(texto):
    return " ".join(str(texto or "").split())


def fuentes_de(subtitulos, idioma, pais):
    """La lista de fuentes de ese destino (D4): `None` si la clave está
    ausente (clip ausente = legado, se usan las `palabras` guardadas);
    `[]` si ese idioma está marcado explícitamente «sin subtítulos»."""
    mapa = (subtitulos or {}).get("fuentes") or {}
    return documento.valor_destino(mapa, idioma, pais)


def clips_de_fuente(resuelto, fuentes):
    """[(pista, clip)] que alimentan esta lista de fuentes (D4), en el
    orden del documento (pista y luego clip) y sin repetir un clip que dos
    fuentes nombren. Solo cuentan pistas no `oculta` ni `silenciada`: la
    pista principal de VIDEO para `sonido` (y, por material, también para
    `material`), y cualquier pista de audio que no sea `p_sonido` (el
    espejo del sonido de la principal) para `voz` y `material`."""
    principal = documento.pista_principal(resuelto)
    quiere_voz = any(f.get("tipo") == "voz" for f in fuentes or [])
    quiere_sonido = any(f.get("tipo") == "sonido" for f in fuentes or [])
    materiales_pedidos = {f.get("material_id") for f in (fuentes or []) if f.get("tipo") == "material"}
    vistos = set()
    salida = []
    for pista in resuelto.get("pistas") or []:
        if pista.get("oculta") or pista.get("silenciada"):
            continue
        es_principal_video = pista is principal and pista.get("tipo") == "video"
        es_audio_fuente = pista.get("tipo") == "audio" and pista.get("id") != "p_sonido"
        if not es_principal_video and not es_audio_fuente:
            continue
        for clip in pista.get("clips") or []:
            incluir = (
                (es_principal_video and quiere_sonido)
                or (es_audio_fuente and quiere_voz and clip.get("rol_audio") == "voz")
                or (materiales_pedidos and clip.get("material_id") in materiales_pedidos)
            )
            if not incluir:
                continue
            clave = id(clip)
            if clave in vistos:
                continue
            vistos.add(clave)
            salida.append((pista, clip))
    return salida


def derivar(resuelto, palabras_por_material):
    """Las palabras derivadas de las fuentes del destino de `resuelto`
    (`resuelto["destino"]`, el que deja `documento.resolver`), en la línea
    de tiempo (D2). `palabras_por_material` es `{material_id: [{t_ms,
    dur_ms, texto}]}` (tiempo del material). Sin fuentes (ausente o vacía),
    lista vacía. Orden: por `t_ms` y, a igual `t_ms`, por el orden de
    pistas/clips/palabras del documento (sort estable sobre ese orden de
    construcción)."""
    destino = resuelto.get("destino") or {}
    idioma, pais = destino.get("idioma"), destino.get("pais")
    sub = resuelto.get("subtitulos") or {}
    fuentes = fuentes_de(sub, idioma, pais) or []
    correcciones = sub.get("correcciones") or {}
    fin_pral = _fin_principal(resuelto)
    salida = []
    for _pista, clip in clips_de_fuente(resuelto, fuentes):
        mid = clip.get("material_id")
        if mid is None:
            continue
        palabras = (palabras_por_material or {}).get(mid)
        if not palabras:
            continue
        desde = int((clip.get("recorte") or {}).get("desde_ms", 0))
        v = float(clip.get("velocidad") or 1.0)
        duracion = int(clip.get("duracion_ms", 0))
        tramo = _tramo(duracion, v)
        inicio = int(clip.get("inicio_ms", 0))
        tope = min(inicio + duracion, fin_pral)
        correcciones_mat = correcciones.get(str(mid)) or {}
        for indice, palabra in enumerate(palabras):
            t_ms = int(palabra.get("t_ms", 0))
            dur_ms = int(palabra.get("dur_ms", 0))
            centro2 = 2 * t_ms + dur_ms                 # regla del centro (D2 punto 2), en enteros
            if not (2 * desde <= centro2 < 2 * (desde + tramo)):
                continue
            texto = _limpiar_texto(correcciones_mat.get(str(indice), palabra.get("texto", "")))
            if not texto:
                continue
            ini = inicio + mapear(max(0, t_ms - desde), v)
            if ini >= tope:
                continue
            fin = min(inicio + mapear(max(0, t_ms + dur_ms - desde), v), tope)
            salida.append({"t_ms": ini, "dur_ms": max(0, fin - ini), "texto": texto,
                           "material_id": mid, "indice": indice, "clip_id": clip.get("id")})
    salida.sort(key=lambda w: w["t_ms"])
    return salida


def aplicar(resuelto, palabras_por_material):
    """Reemplaza `resuelto["subtitulos"]["palabras"]` por las derivadas de
    sus fuentes (mismo objeto `resuelto`, lo modifica y lo devuelve). Si
    `visibles` está apagado o el idioma del destino no tiene `fuentes`
    (clave ausente: legado), no toca `palabras` — ya quedaron como las dejó
    `documento.resolver`."""
    sub = resuelto.get("subtitulos") or {}
    destino = resuelto.get("destino") or {}
    fuentes = fuentes_de(sub, destino.get("idioma"), destino.get("pais"))
    if sub.get("visibles") is False or fuentes is None:
        return resuelto
    derivadas = derivar(resuelto, palabras_por_material)
    sub["palabras"] = [{"t_ms": w["t_ms"], "dur_ms": w["dur_ms"], "texto": w["texto"]} for w in derivadas]
    resuelto["subtitulos"] = sub
    return resuelto
