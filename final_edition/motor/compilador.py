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
transición).

Keyframes: solo x/y se interpretan aquí (expresiones lineales por tramos en
t); escala, opacidad y rotación por keyframe quedan para cuando las
animaciones predefinidas lleguen con alfa en PNG."""
from dataclasses import dataclass, field

from final_edition import geometria, mezcla
from final_edition.documento import FORMATOS, duracion_ms
from final_edition.motor import subtitulos as sub_mod

_XFADE = {"fundido": "fade", "deslizar": "slideleft", "zoom": "zoomin", "desenfoque": "fadeblack"}
_DESPLAZ_ANIM_PX = 60
# Respaldo: el navegador manda ancho_px/alto_px con cada PNG (capa 3).
_CAPA_ANCHO_DEFECTO = 400
_CAPA_ALTO_DEFECTO = 200

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
        # el término restado arranca en 60 y baja a 0: la capa empieza 60 px
        # más arriba de su sitio y va bajando hasta su posición final.
        y = f"{caja['y']}-if(lt(t-{ini:.3f}\\,{dur:.3f})\\,(1-(t-{ini:.3f})/{dur:.3f})*{_DESPLAZ_ANIM_PX}\\,0)"
    return x, y


def _expr_piecewise(puntos):
    """`if` anidado de ffmpeg: lineal por tramos entre `puntos`
    (`[(t_s, valor), ...]`, ordenados por `t_s`, ya en segundos relativos a
    la ventana); constante antes del primero y después del último. 3
    decimales. Sin escapar comas: van dentro de un valor citado con `'...'`
    y ffmpeg 9 las acepta así (`enable=` ya lo hace en este mismo filtro)."""
    t0, v0 = puntos[0]
    expr = f"{puntos[-1][1]:.3f}"
    for (ta, va), (tb, vb) in reversed(list(zip(puntos, puntos[1:]))):
        segmento = f"{va:.3f}+({vb:.3f}-{va:.3f})*(t-{ta:.3f})/({tb:.3f}-{ta:.3f})"
        expr = f"if(lt(t,{tb:.3f}),{segmento},{expr})"
    return f"if(lt(t,{t0:.3f}),{v0:.3f},{expr})"


def _expr_posicion(cl, keyframes, capa_w, capa_h, formato, desplaz, caja_defecto, fps):
    """(x_expr, y_expr) del overlay. Con >= 2 keyframes: lineales por tramos
    en `t` a partir de la caja en píxeles de cada keyframe (transform del
    keyframe mezclado sobre el del clip). Sin eso: el comportamiento de
    siempre, `_expr_animacion` sobre una caja constante."""
    if len(keyframes) < 2:
        cl_local = {**cl, "inicio_ms": cl["inicio_ms"] - desplaz}
        return _expr_animacion(cl_local, caja_defecto, fps)
    kfs = sorted(keyframes, key=lambda k: k["t_ms"])
    base_t = cl["transform"]
    pts_x, pts_y = [], []
    for kf in kfs:
        t_s = (cl["inicio_ms"] - desplaz + kf["t_ms"]) / 1000.0
        caja_kf = geometria.caja({**base_t, **(kf.get("transform") or {})}, capa_w, capa_h, formato)
        pts_x.append((t_s, caja_kf["x"]))
        pts_y.append((t_s, caja_kf["y"]))
    return _expr_piecewise(pts_x), _expr_piecewise(pts_y)


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
    if any(cl["material_id"] != fuente for cl in clips_v):
        raise ValueError("La pista principal usa más de una fuente; el montaje de varias piezas llega en la capa 4.")
    if fuente not in rutas:
        raise ValueError(f"Falta la ruta del material '{fuente}' de la pista principal.")
    plan.entradas.append({"ruta": rutas[fuente], "opciones": []})
    etiquetas = []
    for i, cl in enumerate(clips_v):
        rec = cl.get("recorte") or {"desde_ms": 0, "hasta_ms": cl["duracion_ms"]}
        vel = float(cl.get("velocidad") or 1.0)
        # recorte relativo al tramo
        corte_ini = max(ventana[0], cl["inicio_ms"]) - cl["inicio_ms"]
        corte_fin = min(ventana[1], cl["inicio_ms"] + cl["duracion_ms"]) - cl["inicio_ms"]
        desde = rec["desde_ms"] + round(corte_ini * vel)
        hasta = rec["desde_ms"] + round(corte_fin * vel)
        # Modelo de transición: si este clip tiene una transición real hacia
        # el siguiente Y ese siguiente cae dentro del tramo, la cola se
        # extiende `duracion_ms` (de SALIDA) más allá del recorte normal —
        # de ahí sale el crossfade sin robarle tiempo a B (ruling A de la
        # Task 9). Esos ms de salida se escalan por `vel` igual que el resto
        # del recorte: a 2x hacen falta el doble de cuadros de fuente para
        # cubrir la misma duración de salida.
        tr_siguiente = _transicion_real(cl) if i + 1 < len(clips_v) else None
        if tr_siguiente:
            hasta += round(tr_siguiente.get("duracion_ms", 0) * vel)
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
            # concat sale con timebase 1/1000000; si lo que sigue es un xfade
            # (que exige la misma timebase 1/fps en sus dos patas) ffmpeg lo
            # rechaza ("timebase do not match") sin este settb.
            partes.append(f"{actual}{etiquetas[i][0]}concat=n=2:v=1:a=0,settb=1/{fps}{salida}")
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
                raise ValueError(f"Falta la ruta ('{clave}') del clip '{cl['id']}'.")
            n_png += 1
            idx = len(plan.entradas)
            plan.entradas.append({"ruta": rutas[clave], "opciones": []})
            kfs = cl.get("keyframes") or []
            capa_w = cl.get("ancho_px") or _CAPA_ANCHO_DEFECTO
            capa_h = cl.get("alto_px") or _CAPA_ALTO_DEFECTO
            t = geometria.interpolar(kfs, 0, cl["transform"])
            caja_defecto = geometria.caja(t, capa_w, capa_h, doc["formato"])
            x, y = _expr_posicion(cl, kfs, capa_w, capa_h, doc["formato"], desplaz, caja_defecto, fps)
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
    # Primera pasada: agrupar los clips de audio por rol_audio, en orden de
    # pista/clip (así se decide, ya con el conteo real por rol, si el rol usa
    # su etiqueta simple `[au_<rol>]` o si varios clips necesitan mezclarse).
    por_rol = {}
    for p in pistas:
        if p["tipo"] != "audio" or p.get("silenciada"):
            continue
        for cl in _clips_en(p, ventana):
            rol = cl.get("rol_audio") or "subida"
            if cl["material_id"] not in rutas:
                raise ValueError(f"Falta la ruta ('{cl['material_id']}') del clip '{cl['id']}'.")
            idx = len(plan.entradas)
            opciones = ["-stream_loop", "-1"] if rol == "musica" else []
            plan.entradas.append({"ruta": rutas[cl["material_id"]], "opciones": opciones})
            por_rol.setdefault(rol, []).append((idx, cl))

    etiquetas_rol = {}
    for rol, clips_rol in por_rol.items():
        n = len(clips_rol)
        sub_etiquetas = []
        for k, (idx, cl) in enumerate(clips_rol):
            rec = cl.get("recorte") or {"desde_ms": 0, "hasta_ms": cl["duracion_ms"]}
            au = cl.get("audio") or {}
            corte_ini = max(ventana[0], cl["inicio_ms"]) - cl["inicio_ms"]
            corte_fin = min(ventana[1], cl["inicio_ms"] + cl["duracion_ms"]) - cl["inicio_ms"]
            filtros = [f"atrim=start={_s(rec['desde_ms'] + corte_ini)}:end={_s(rec['desde_ms'] + corte_fin)}",
                       "asetpts=PTS-STARTPTS", f"volume={au.get('volumen', 1.0)}"]
            # el fundido es del CLIP, no del tramo: si la ventana lo corta
            # antes de su borde real, ese borde no está aquí y el fundido no
            # suena (sonaría a mitad de frase y el tramo siguiente perdería
            # el pedazo que ya se "gastó" en el fundido de este).
            if au.get("fundido_entrada_ms") and corte_ini == 0:
                filtros.append(f"afade=t=in:st=0:d={_s(au['fundido_entrada_ms'])}")
            if au.get("fundido_salida_ms") and corte_fin == cl["duracion_ms"]:
                fin_local = corte_fin - corte_ini
                filtros.append(f"afade=t=out:st={_s(fin_local - au['fundido_salida_ms'])}:d={_s(au['fundido_salida_ms'])}")
            # posición del clip dentro del tramo: dos clips del mismo rol
            # (dos voces que se turnan, por ejemplo) no pueden sonar los dos
            # desde 0 — adelay los deja donde van. Se omite en 0 para que la
            # línea de un solo clip que ya empieza en el arranque del tramo
            # no cambie de texto.
            ini = max(0, cl["inicio_ms"] - desplaz)
            if ini > 0:
                filtros.append(f"adelay={ini}|{ini}")
            # con un solo clip para este rol, la etiqueta queda simple
            # (`[au_<rol>]`, la que espera `mezcla.filtro_mezcla`); con
            # varios, cada uno lleva su índice y se suman con amix.
            etiqueta = f"[au_{rol}]" if n == 1 else f"[au_{rol}_{k}]"
            partes.append(f"[{idx}:a]{','.join(filtros)}{etiqueta}")
            sub_etiquetas.append(etiqueta)
        if n == 1:
            etiquetas_rol[rol] = sub_etiquetas[0]
        else:
            salida_mix = f"[au_{rol}]"
            partes.append(f"{''.join(sub_etiquetas)}amix=inputs={n}:normalize=0{salida_mix}")
            etiquetas_rol[rol] = salida_mix

    voz = etiquetas_rol.get("voz")
    musica = etiquetas_rol.get("musica")
    sonido = None
    for rol, etq in etiquetas_rol.items():
        if rol not in ("voz", "musica"):
            sonido = etq
    mz = doc.get("mezcla") or {}
    vol = mezcla.volumenes_para(mz.get("preset"), mz.get("volumenes"))
    audio = mezcla.filtro_mezcla(voz=voz, sonido=sonido, musica=musica, volumenes=vol)
    if audio:
        partes.append(audio)
        plan.salida_audio = True
    plan.filtergraph = ";".join(partes)
    return plan
