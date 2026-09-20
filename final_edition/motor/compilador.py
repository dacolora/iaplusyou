"""Compilador (spec §2.1): documento resuelto → Plan {entradas, filtergraph}.
Puro: no toca disco ni ffmpeg. Orden de entradas: 0 = clon/pista principal
(una sola fuente por ahora: los clips de la principal recortan el mismo
material), luego PNG de capas en orden de pista/clip, luego audios en orden
de pista/clip. Los textos libres son PNG del navegador; los subtítulos van
por ASS (o se omiten si `con_ass=False`).

Modelo de transición (decidido en la Task 8): una `transicion` de duración d
en el clip A hacia B ocupa el intervalo de SALIDA `[fin_A, fin_A + d)`: B
conserva su posición exacta en la línea de tiempo y los cuadros extra para el
crossfade salen de la COLA de A (`recorte.hasta + d`, sin sondear el archivo
— eso es trabajo del renderer). La duración total no cambia: es
`dur_A + dur_B`; el solape del `xfade` lo paga la cola extra de A, nunca un
recorte de B. Por eso el `offset` del `xfade` es dónde A termina en la línea
de SALIDA (acumulado de duraciones tal cual, sin restar la duración de la
transición)."""
from dataclasses import dataclass, field

from final_edition import geometria, mezcla
from final_edition.documento import FORMATOS, duracion_ms
from final_edition.motor import subtitulos as sub_mod

_XFADE = {"fundido": "fade", "deslizar": "slideleft", "zoom": "zoomin", "desenfoque": "fadeblack"}
_DESPLAZ_ANIM_PX = 60
# Tamaño de la capa cuando el clip todavía no trae su propio ancho_px/alto_px
# (el PNG real lo rasteriza el navegador a su resolución final; esto es solo
# el valor de reserva para poder calcular la caja del overlay).
_CAPA_ANCHO_DEFECTO = 400
_CAPA_ALTO_DEFECTO = 300

# Orden en el que `compilar` agrega entradas (`-i`) al plan: la fuente
# principal primero, luego los PNG de capas (superpuesto/imagen/texto) en
# orden de pista/clip, luego los audios en orden de pista/clip.
ORDEN_ENTRADAS = ("principal", "png_capas", "audio")


@dataclass
class Plan:
    entradas: list = field(default_factory=list)
    filtergraph: str = ""
    salida_video: bool = True
    salida_audio: bool = False
    duracion_ms: int = 0
    ancho: int = 1080
    alto: int = 1920
    ass_texto: str = ""
    overlays: int = 0


def _transicion_xfade(tipo):
    return _XFADE.get(tipo, "fade")


def _s(ms):
    return f"{ms / 1000.0:.3f}"


def _transicion_real(clip):
    """La `transicion` de `clip` si es real (tipo != corte y duración > 0);
    `None` si no tiene, es un corte seco, o dura 0."""
    tr = clip.get("transicion")
    if tr and tr.get("tipo", "corte") != "corte" and int(tr.get("duracion_ms", 0)) > 0:
        return tr
    return None


def _expr_animacion(clip, caja, fps):
    """Expresiones x, y (alpha no se usa: la opacidad ya está horneada en el
    PNG) para el overlay según la animación de entrada. Sin animación:
    constantes."""
    an = clip.get("animacion") or {}
    ini = clip["inicio_ms"] / 1000.0
    dur = max(0.001, (an.get("duracion_ms") or 0) / 1000.0)
    x = f"{caja['x']}+0"
    y = f"{caja['y']}"
    if an.get("entrada") == "deslizar" and an.get("duracion_ms"):
        # desde 60 px más abajo hasta su sitio, lineal, en `dur` s
        y = f"{caja['y']}-if(lt(t-{ini:.3f}\\,{dur:.3f})\\,(1-(t-{ini:.3f})/{dur:.3f})*{_DESPLAZ_ANIM_PX}\\,0)"
    return x, y


def _clips_en(pista, ventana):
    a, b = ventana
    return [cl for cl in pista.get("clips") or [] if cl["inicio_ms"] < b and cl["inicio_ms"] + cl["duracion_ms"] > a]


def compilar(doc, rutas, ventana=None, con_ass=True):
    ancho, alto = FORMATOS[doc["formato"]]
    fps = int(doc.get("fps") or 30)
    total = duracion_ms(doc)
    ventana = ventana or (0, total)
    desplaz = ventana[0]
    dur_tramo = ventana[1] - ventana[0]
    plan = Plan(ancho=ancho, alto=alto, duracion_ms=dur_tramo)
    partes = []
    pistas = [p for p in doc["pistas"] if not p.get("oculta")]

    # ---- pista principal (video o imagen) ---------------------------------
    principal = next((p for p in pistas if p["tipo"] in ("video", "imagen")), None)
    if principal and principal["tipo"] == "imagen":
        # Una imagen no tiene línea de tiempo real (duración 0 = "la foto de
        # siempre"): se usan sus clips tal cual, sin filtrar por ventana.
        clips_v = list(principal.get("clips") or [])
    else:
        clips_v = _clips_en(principal, ventana) if principal else []
    if not clips_v:
        raise ValueError("El documento no tiene nada en la pista principal en este tramo.")
    fuente = clips_v[0]["material_id"]
    plan.entradas.append({"ruta": rutas[fuente], "opciones": []})
    etiquetas = []
    for i, cl in enumerate(clips_v):
        rec = cl.get("recorte") or {"desde_ms": 0, "hasta_ms": cl["duracion_ms"]}
        vel = float(cl.get("velocidad") or 1.0)
        # recorte relativo al tramo
        corte_ini = max(ventana[0], cl["inicio_ms"]) - cl["inicio_ms"]
        corte_fin = min(ventana[1], cl["inicio_ms"] + cl["duracion_ms"]) - cl["inicio_ms"]
        desde = rec["desde_ms"] + int(corte_ini * vel)
        hasta = rec["desde_ms"] + int(corte_fin * vel)
        # Modelo de transición: si este clip tiene una transición real hacia
        # el siguiente Y ese siguiente cae dentro del tramo, la cola se
        # extiende `duracion_ms` más allá del recorte normal — de ahí sale
        # el crossfade sin robarle tiempo a B (ruling A de la Task 9).
        tr_siguiente = _transicion_real(cl) if i + 1 < len(clips_v) else None
        if tr_siguiente:
            hasta += int(tr_siguiente.get("duracion_ms", 0))
        if principal["tipo"] == "imagen":
            partes.append(f"[0:v]scale={ancho}:{alto}:force_original_aspect_ratio=increase,crop={ancho}:{alto},format=yuv420p[v{i}]")
        else:
            setpts = "setpts=PTS-STARTPTS" if vel == 1.0 else f"setpts=(PTS-STARTPTS)/{vel}"
            partes.append(f"[0:v]trim=start={_s(desde)}:end={_s(hasta)},{setpts},"
                          f"scale={ancho}:{alto}:force_original_aspect_ratio=increase,crop={ancho}:{alto},fps={fps},format=yuv420p[v{i}]")
        etiquetas.append((f"[v{i}]", cl))
    # transiciones / concat
    actual = etiquetas[0][0]
    acumulado = 0
    for i in range(1, len(etiquetas)):
        prev_clip = etiquetas[i - 1][1]
        dur_prev = min(ventana[1], prev_clip["inicio_ms"] + prev_clip["duracion_ms"]) - max(ventana[0], prev_clip["inicio_ms"])
        tr = _transicion_real(prev_clip) if prev_clip["inicio_ms"] + prev_clip["duracion_ms"] < ventana[1] else None
        salida = "[vc]" if i == len(etiquetas) - 1 else f"[vx{i}]"
        if tr:
            d_tr = int(tr.get("duracion_ms", 0))
            # B conserva su posición exacta -> el offset es dónde termina A
            # en la línea de SALIDA (acumulado + lo que dura A en el tramo,
            # sin restar d_tr: ese tiempo lo puso la cola extra de A, no se
            # roba de la duración total).
            offset = acumulado + dur_prev
            partes.append(f"{actual}{etiquetas[i][0]}xfade=transition={_transicion_xfade(tr['tipo'])}:duration={_s(d_tr)}:offset={_s(offset)}{salida}")
        else:
            partes.append(f"{actual}{etiquetas[i][0]}concat=n=2:v=1:a=0{salida}")
        acumulado += dur_prev
        actual = salida
    if len(etiquetas) == 1:
        partes.append(f"{actual}null[vc]"); actual = "[vc]"

    # ---- capas overlay (PNG) ---------------------------------------------
    n_png = 0
    for p in pistas:
        if p["tipo"] not in ("superpuesto", "imagen", "texto") or p is principal:
            continue
        for cl in _clips_en(p, ventana):
            clave = f"png:{cl['id']}" if p["tipo"] == "texto" else cl["material_id"]
            if clave not in rutas:
                continue
            n_png += 1
            idx = len(plan.entradas)
            plan.entradas.append({"ruta": rutas[clave], "opciones": []})
            t = geometria.interpolar(cl.get("keyframes") or [], 0, cl["transform"])
            capa_w = cl.get("ancho_px") or _CAPA_ANCHO_DEFECTO
            capa_h = cl.get("alto_px") or _CAPA_ALTO_DEFECTO
            caja = geometria.caja(t, capa_w, capa_h, doc["formato"])
            cl_local = {**cl, "inicio_ms": cl["inicio_ms"] - desplaz}
            x, y = _expr_animacion(cl_local, caja, fps)
            ini = max(0, cl["inicio_ms"] - desplaz)
            fin = min(dur_tramo, cl["inicio_ms"] + cl["duracion_ms"] - desplaz)
            salida = f"[o{n_png}]"
            partes.append(f"{actual}[{idx}:v]overlay=x='{x}':y='{y}':eof_action=repeat:enable='gte(t,{_s(ini)})*lt(t,{_s(fin)})'{salida}")
            actual = salida
    plan.overlays = n_png

    # ---- subtítulos ASS ---------------------------------------------------
    if con_ass and (doc.get("subtitulos") or {}).get("palabras"):
        palabras = [{**w, "t_ms": w["t_ms"] - desplaz} for w in doc["subtitulos"]["palabras"]
                    if w["t_ms"] + w["dur_ms"] > desplaz and w["t_ms"] < ventana[1]]
        if palabras:
            plan.ass_texto = sub_mod.generar_ass({**doc["subtitulos"], "palabras": palabras}, doc["formato"])
            partes.append(f"{actual}subtitles='{rutas['ass']}'[os]")
            actual = "[os]"
    partes.append(f"{actual}format=yuv420p[vout]")

    # ---- audio ------------------------------------------------------------
    voz = sonido = musica = None
    for p in pistas:
        if p["tipo"] != "audio" or p.get("silenciada"):
            continue
        for cl in _clips_en(p, ventana):
            rol = cl.get("rol_audio") or "subida"
            if cl["material_id"] not in rutas:
                continue
            idx = len(plan.entradas)
            opciones = ["-stream_loop", "-1"] if rol == "musica" else []
            plan.entradas.append({"ruta": rutas[cl["material_id"]], "opciones": opciones})
            rec = cl.get("recorte") or {"desde_ms": 0, "hasta_ms": cl["duracion_ms"]}
            au = cl.get("audio") or {}
            corte_ini = max(ventana[0], cl["inicio_ms"]) - cl["inicio_ms"]
            corte_fin = min(ventana[1], cl["inicio_ms"] + cl["duracion_ms"]) - cl["inicio_ms"]
            filtros = [f"atrim=start={_s(rec['desde_ms'] + corte_ini)}:end={_s(rec['desde_ms'] + corte_fin)}",
                       "asetpts=PTS-STARTPTS", f"volume={au.get('volumen', 1.0)}"]
            if au.get("fundido_entrada_ms"):
                filtros.append(f"afade=t=in:st=0:d={_s(au['fundido_entrada_ms'])}")
            if au.get("fundido_salida_ms"):
                fin_local = corte_fin - corte_ini
                filtros.append(f"afade=t=out:st={_s(fin_local - au['fundido_salida_ms'])}:d={_s(au['fundido_salida_ms'])}")
            etiqueta = f"[au_{rol}]"
            partes.append(f"[{idx}:a]{','.join(filtros)}{etiqueta}")
            if rol == "voz":
                voz = etiqueta
            elif rol == "musica":
                musica = etiqueta
            else:
                sonido = etiqueta
    mz = doc.get("mezcla") or {}
    vol = mezcla.volumenes_para(mz.get("preset"), mz.get("volumenes"))
    audio = mezcla.filtro_mezcla(voz=voz, sonido=sonido, musica=musica, volumenes=vol)
    if audio:
        partes.append(audio)
        plan.salida_audio = True
    plan.filtergraph = ";".join(partes)
    return plan
