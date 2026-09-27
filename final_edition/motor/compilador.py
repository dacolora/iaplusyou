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
transición). `verificar_recortes` (con las duraciones reales de los
materiales, que aquí no se sondean) es quien acorta esa cola cuando el
material no alcanza.

Si la pista principal termina antes que el tramo (la voz sigue después del
último clip), su último cuadro se clona con `tpad` hasta el fin del tramo:
el video nunca acaba antes que el audio.

Ken Burns: `ken_burns` en un clip de la principal agrega `zoompan`
(1.0→1.08) tras `fps=`; `on` se desplaza por la ventana del tramo.

Capas (PNG de texto e imágenes): cada una se escala a la caja que da
`geometria.caja` (`scale=w:h`, misma regla de píxeles que el navegador) y,
con `opacidad < 1`, se atenúa el alfa (`format=rgba,colorchannelmixer=aa=`).
`rotacion` NO se renderiza en la capa 1 (ni `superpuesto`, el PIP: `compilar`
lo rechaza con un error explícito; ni `marca.marca_de_agua`).

Keyframes: solo x/y se interpretan aquí (expresiones lineales por tramos en
t); escala, opacidad y rotación por keyframe quedan para cuando las
animaciones predefinidas lleguen con alfa en PNG (el tamaño de la capa es el
de su transform en t=0).

Audio por tramo: la presencia de audio es una decisión de TODO el documento,
no de la ventana — si el documento tiene algún clip de audio activo pero esta
ventana no tiene ninguno (p. ej. la voz termina antes de este tramo),
`compilar` rellena con `anullsrc` en vez de dejar el tramo sin stream de
audio, porque `concat -c copy` (el renderer) no tolera streams heterogéneos
entre segmentos y cortaría el audio del video entero en esa frontera. Los
roles se reducen a las tres entradas de `mezcla.filtro_mezcla`: `voz`,
`musica` y "sonido" (todo lo demás: `sonido`, `efecto`, `subida`,
`grabacion`), sumado con `amix` cuando hay más de un clip.

Rutas dentro del filtergraph (`subtitles=`, `fontsdir=`): van citadas con
'...' y pasan por `_ruta_filtro`, porque ffmpeg las parsea dos veces
(`av_get_token` del grafo y luego el de las opciones del filtro)."""
import os
from dataclasses import dataclass, field

import final_edition
from final_edition import geometria, mezcla
from final_edition.documento import FORMATOS, duracion_ms, pista_principal
from final_edition.motor import subtitulos as sub_mod

_XFADE = {"fundido": "fade", "deslizar": "slideleft", "zoom": "zoomin", "desenfoque": "fadeblack"}
_DESPLAZ_ANIM_PX = 60
ZOOM_KEN_BURNS = 1.08


def _zoompan(clip, corte_ini_ms, fps, ancho, alto):
    """Ken Burns de un clip de la principal (`ken_burns`: in | out): el
    zoompan de render.py, 1.0 → 1.08 (o al revés) a lo largo del clip
    ENTERO, con `on` desplazado por los cuadros que la ventana del tramo ya
    consumió (`corte_ini_ms`) para que el zoom siga donde iba y no reinicie
    en cada tramo. La cola de una transición satura en el extremo (min/max).
    '' si el clip no lo pide."""
    modo = clip.get("ken_burns")
    if modo not in ("in", "out"):
        return ""
    n = max(1, round(clip["duracion_ms"] * fps / 1000))
    off = round(corte_ini_ms * fps / 1000)
    paso = ZOOM_KEN_BURNS - 1
    if modo == "in":
        z = f"min(1+{paso:.2f}*(on+{off})/{n},{ZOOM_KEN_BURNS})"
    else:
        z = f"max({ZOOM_KEN_BURNS}-{paso:.2f}*(on+{off})/{n},1)"
    return f",zoompan=z='{z}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={ancho}x{alto}:fps={fps}"


# Respaldo: el navegador manda ancho_px/alto_px con cada PNG (capa 3).
_CAPA_ANCHO_DEFECTO = 400
_CAPA_ALTO_DEFECTO = 200
# Fuentes del repo para libass (`subtitles=...:fontsdir=`): las mismas que usa
# `final_edition/tipos.py`; sin esto libass cae a la fuente que encuentre el
# sistema y el VPS no tiene Inter instalada.
FONTSDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(final_edition.__file__))), "static", "fonts")

# Orden en el que `compilar` agrega entradas (`-i`) al plan: la fuente
# principal primero, luego los PNG de capas (imagen/texto) en orden de
# pista/clip, luego los audios en orden de pista/clip.
ORDEN_ENTRADAS = ("principal", "png_capas", "audio")
_ROLES_SONIDO_GRUPO = "sonido"


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


def _ruta_filtro(ruta):
    """Escapa una ruta para ir dentro de `'...'` en una opción de filtro.
    ffmpeg la parsea dos veces con `av_get_token`: el grafo (donde dentro de
    comillas TODO es literal salvo la propia comilla) y luego las opciones del
    filtro (donde `\\` escapa y `:` separa). De ahí: `\\`→`\\\\`, `:`→`\\:` y la
    comilla → `\\'` para el segundo nivel, escrita como `\\'\\''` (cerrar la
    cita, comilla escapada, reabrir) para que el primero la deje pasar.
    Verificado con ffmpeg 9 (`movie=`) sobre una ruta con `:`, `'` y `\\`."""
    return ruta.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'\\''")


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


def _fuente_ms(clip):
    """Milisegundos de FUENTE que consume el clip completo (duración de salida
    × velocidad), redondeados igual que en `compilar`."""
    return round(clip["duracion_ms"] * float(clip.get("velocidad") or 1.0))


def verificar_recortes(doc, duraciones):
    """Comprueba los recortes contra las duraciones reales de los materiales
    (`{material_id: duracion_ms}`, solo los que se conocen; los que faltan no
    se juzgan). Sin disco ni ffmpeg. Modifica `doc` en el sitio y lo
    devuelve:

      - un clip de video/audio que pide más fuente de la que hay
        (`recorte.desde_ms + duracion_ms × velocidad > material`) →
        ValueError con el nombre del clip; la música no cuenta (entra con
        `-stream_loop -1`, así que nunca se acaba);
      - la cola de una transición de la pista principal (`+ d × velocidad`
        de fuente) que no cabe se recorta a lo que queda, en ms de SALIDA;
        si no queda nada, la transición pasa a corte seco (`None`)."""
    principal = pista_principal(doc)
    for p in doc.get("pistas") or []:
        if p.get("tipo") not in ("video", "superpuesto", "audio"):
            continue
        clips = p.get("clips") or []
        if p is principal:
            clips = sorted(clips, key=lambda c: c["inicio_ms"])
        for i, cl in enumerate(clips):
            if p["tipo"] == "audio" and (cl.get("rol_audio") or "subida") == "musica":
                continue
            mid = cl.get("material_id")
            if mid not in duraciones or duraciones[mid] is None:
                continue
            material = int(duraciones[mid])
            desde = int((cl.get("recorte") or {}).get("desde_ms", 0))
            fin_fuente = desde + _fuente_ms(cl)
            if fin_fuente > material:
                raise ValueError(f"El clip '{cl['id']}' pide {fin_fuente} ms de un material de {material} ms; "
                                 f"acorta el clip o el recorte.")
            tr = _transicion_real(cl)
            if p is principal and tr and i + 1 < len(clips):
                vel = float(cl.get("velocidad") or 1.0)
                sobrante_salida = int((material - fin_fuente) / vel)
                if int(tr["duracion_ms"]) > sobrante_salida:
                    if sobrante_salida <= 0:
                        cl["transicion"] = None
                    else:
                        cl["transicion"] = {**tr, "duracion_ms": sobrante_salida}
    return doc


def compilar(doc, rutas, ventana=None, con_ass=True):
    ancho, alto = FORMATOS[doc["formato"]]
    fps = int(doc.get("fps") or 30)
    total = duracion_ms(doc)
    es_imagen = total == 0
    ventana = ventana or (0, total)
    desplaz = ventana[0]
    dur_tramo = ventana[1] - ventana[0]
    plan = Plan(ancho=ancho, alto=alto, duracion_ms=dur_tramo)
    partes = []
    pistas = [p for p in doc["pistas"] if not p.get("oculta")]
    if any(p["tipo"] == "superpuesto" and p.get("clips") for p in pistas):
        raise ValueError("El video superpuesto (PIP) llega en la capa 4.")

    # ---- pista principal (video o imagen) ---------------------------------
    principal = pista_principal(doc)
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
                          f"scale={ancho}:{alto}:force_original_aspect_ratio=increase,crop={ancho}:{alto},fps={fps}"
                          f"{_zoompan(cl, corte_ini, fps, ancho, alto)},format=yuv420p[v{i}]")
        etiquetas.append((f"[v{i}]", cl))
    # Relleno: si la principal termina antes que el tramo (la voz sigue), el
    # último cuadro se clona hasta `dur_tramo`. Cero para una imagen.
    fin_principal = 0 if es_imagen else min(ventana[1], max(cl["inicio_ms"] + cl["duracion_ms"] for cl in clips_v)) - desplaz
    faltante = max(0, dur_tramo - fin_principal)
    etiqueta_cadena = "[vp]" if faltante > 0 else "[vc]"
    # transiciones / concat
    actual = etiquetas[0][0]
    acumulado = 0
    for i in range(1, len(etiquetas)):
        prev_clip = etiquetas[i - 1][1]
        dur_prev = min(ventana[1], prev_clip["inicio_ms"] + prev_clip["duracion_ms"]) - max(ventana[0], prev_clip["inicio_ms"])
        tr = _transicion_real(prev_clip) if prev_clip["inicio_ms"] + prev_clip["duracion_ms"] < ventana[1] else None
        salida = etiqueta_cadena if i == len(etiquetas) - 1 else f"[vx{i}]"
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
    if faltante > 0:
        partes.append(f"{actual}tpad=stop_mode=clone:stop_duration={_s(faltante)}[vc]")
    elif len(etiquetas) == 1:
        partes.append(f"{actual}null[vc]")
    actual = "[vc]"

    # ---- capas overlay (PNG) ---------------------------------------------
    n_png = 0
    for p in pistas:
        if p["tipo"] not in ("imagen", "texto") or p is principal:
            continue
        # Una imagen no tiene ventana: entran todas sus capas, sin `enable`.
        clips_capa = list(p.get("clips") or []) if es_imagen else _clips_en(p, ventana)
        for cl in clips_capa:
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
            # la capa se lleva al tamaño de su caja (escala del transform) y,
            # si es translúcida, se atenúa su alfa antes del overlay.
            capa = f"[{idx}:v]scale={caja_defecto['w']}:{caja_defecto['h']}"
            if caja_defecto["opacidad"] < 1.0:
                capa += f",format=rgba,colorchannelmixer=aa={caja_defecto['opacidad']:g}"
            partes.append(f"{capa}[l{n_png}]")
            salida = f"[o{n_png}]"
            if es_imagen:
                enable = ""
            else:
                ini = max(0, cl["inicio_ms"] - desplaz)
                fin = min(dur_tramo, cl["inicio_ms"] + cl["duracion_ms"] - desplaz)
                enable = f":enable='gte(t,{_s(ini)})*lt(t,{_s(fin)})'"
            partes.append(f"{actual}[l{n_png}]overlay=x='{x}':y='{y}':eof_action=repeat{enable}{salida}")
            actual = salida
    plan.overlays = n_png

    # ---- subtítulos ASS ---------------------------------------------------
    if con_ass and (doc.get("subtitulos") or {}).get("palabras"):
        palabras = [{**w, "t_ms": w["t_ms"] - desplaz} for w in doc["subtitulos"]["palabras"]
                    if w["t_ms"] + w["dur_ms"] > desplaz and w["t_ms"] < ventana[1]]
        if palabras:
            plan.ass_texto = sub_mod.generar_ass({**doc["subtitulos"], "palabras": palabras}, doc["formato"])
            partes.append(f"{actual}subtitles='{_ruta_filtro(rutas['ass'])}':fontsdir='{_ruta_filtro(FONTSDIR)}'[os]")
            actual = "[os]"
    partes.append(f"{actual}format=yuv420p[vout]")

    # ---- audio ------------------------------------------------------------
    # Presencia de audio: decisión de TODO el documento (no de la ventana) —
    # ver el `elif hay_audio_doc` más abajo y el docstring del módulo.
    hay_audio_doc = any(clip for p in doc["pistas"] if p["tipo"] == "audio" and not p.get("silenciada") and not p.get("oculta") for clip in p.get("clips") or [])
    # Primera pasada: agrupar los clips de audio por grupo de mezcla (`voz`,
    # `musica` o `sonido` para todo lo demás), en orden de pista/clip — así se
    # decide, ya con el conteo real por grupo, si el grupo usa su etiqueta
    # simple `[au_<grupo>]` o si varios clips necesitan sumarse con amix.
    por_grupo = {}
    for p in pistas:
        if p["tipo"] != "audio" or p.get("silenciada"):
            continue
        for cl in _clips_en(p, ventana):
            rol = cl.get("rol_audio") or "subida"
            grupo = rol if rol in ("voz", "musica") else _ROLES_SONIDO_GRUPO
            if cl["material_id"] not in rutas:
                raise ValueError(f"Falta la ruta ('{cl['material_id']}') del clip '{cl['id']}'.")
            idx = len(plan.entradas)
            opciones = ["-stream_loop", "-1"] if rol == "musica" else []
            plan.entradas.append({"ruta": rutas[cl["material_id"]], "opciones": opciones})
            por_grupo.setdefault(grupo, []).append((idx, cl))

    etiquetas_grupo = {}
    for grupo, clips_grupo in por_grupo.items():
        n = len(clips_grupo)
        sub_etiquetas = []
        for k, (idx, cl) in enumerate(clips_grupo):
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
            # posición del clip dentro del tramo: dos clips del mismo grupo
            # (dos voces que se turnan, por ejemplo) no pueden sonar los dos
            # desde 0 — adelay los deja donde van. Se omite en 0 para que la
            # línea de un solo clip que ya empieza en el arranque del tramo
            # no cambie de texto.
            ini = max(0, cl["inicio_ms"] - desplaz)
            if ini > 0:
                filtros.append(f"adelay={ini}|{ini}")
            # con un solo clip para este grupo, la etiqueta queda simple
            # (`[au_<grupo>]`, la que espera `mezcla.filtro_mezcla`); con
            # varios, cada uno lleva su índice y se suman con amix.
            etiqueta = f"[au_{grupo}]" if n == 1 else f"[au_{grupo}_{k}]"
            partes.append(f"[{idx}:a]{','.join(filtros)}{etiqueta}")
            sub_etiquetas.append(etiqueta)
        if n == 1:
            etiquetas_grupo[grupo] = sub_etiquetas[0]
        else:
            salida_mix = f"[au_{grupo}]"
            partes.append(f"{''.join(sub_etiquetas)}amix=inputs={n}:normalize=0{salida_mix}")
            etiquetas_grupo[grupo] = salida_mix

    mz = doc.get("mezcla") or {}
    vol = mezcla.volumenes_para(mz.get("preset"), mz.get("volumenes"))
    audio = mezcla.filtro_mezcla(voz=etiquetas_grupo.get("voz"), sonido=etiquetas_grupo.get(_ROLES_SONIDO_GRUPO),
                                 musica=etiquetas_grupo.get("musica"), volumenes=vol)
    if audio:
        partes.append(audio)
        plan.salida_audio = True
    elif hay_audio_doc:
        # Esta ventana no tiene ningún clip de audio activo aunque el
        # documento sí tiene audio en general: sin esto el tramo saldría sin
        # stream de audio y rompería la concatenación (ver docstring).
        # anullsrc no necesita entrada; `-t` en `ejecutar` la acota.
        partes.append("anullsrc=r=48000:cl=stereo[aout]")
        plan.salida_audio = True
    plan.filtergraph = ";".join(partes)
    return plan
