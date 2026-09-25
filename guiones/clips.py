"""
Paso 2 del pipeline de Flow Plus (spec 2026-09-25 §7): Claude planea los
clips referenciando líneas por número; el código calcula duraciones, escribe
los prompts con plantillas fijas y corre las validaciones V1-V6 y E1-E4, que
bloquean. Claude nunca escribe el diálogo: lo pega el código.
"""
from guiones import duracion, plantillas, refinador
from guiones.refinador import _normalizar

DEFECTOS_BLOQUE = {
    "conteo_objetos": "Exactly one of each character and object in the reference map, unless a beat says otherwise.",
    "disposicion_inicial": "",
    "props": "Every prop keeps the same shape, color, size and material in every clip.",
    "quien_sostiene": "An object stays where it was put: nothing appears, disappears or duplicates on its own.",
    "voz": "",
}
MAX_CLIPS, MAX_MOMENTOS, MAX_AIRE = 40, 20, 6.0


def _str(v, n=2000):
    return str(v if v is not None else "").strip()[:n]


def _enteros(valor):
    salida = []
    for x in valor if isinstance(valor, list) else []:
        if isinstance(x, bool):
            continue
        if isinstance(x, int):
            salida.append(x)
        elif isinstance(x, float) and x.is_integer():
            salida.append(int(x))
        elif isinstance(x, str) and x.strip().isdigit():
            salida.append(int(x.strip()))
    return salida


def hooks_esperados(lectura, config):
    todos = ["original"] + [h["id"] for h in lectura.get("hooks", [])]
    return [h for h in todos if h != config.get("hook", "original")]


def _clip_forma(c, i):
    if not isinstance(c, dict):
        raise ValueError(f"el clip {i} no es un objeto")
    momentos = c.get("momentos")
    if not isinstance(momentos, list) or not momentos:
        raise ValueError(f"el clip {i} no tiene momentos")
    if len(momentos) > MAX_MOMENTOS:
        raise ValueError(f"el clip {i} tiene demasiados momentos")
    ms = []
    for m in momentos:
        if not isinstance(m, dict) or not _str(m.get("visual")):
            raise ValueError(f"un momento del clip {i} no describe qué se ve")
        try:
            aire = min(MAX_AIRE, max(0.0, float(m.get("aire") or 0)))
        except (TypeError, ValueError):
            aire = 0.0
        ms.append({"dice": _enteros(m.get("dice")) or None, "aire": aire, "visual": _str(m["visual"], 1500)})
    return {"titulo": _str(c.get("titulo"), 120) or f"Clip {i}", "lineas": _enteros(c.get("lineas")),
            "estado_inicio": _str(c.get("estado_inicio"), 500), "estado_fin": _str(c.get("estado_fin"), 500),
            "entornos": _enteros(c.get("entornos")), "momentos": ms}


def validar_forma(data, hooks_esperados):
    """El plan normalizado; ValueError si no tiene la forma pedida."""
    crudos = data.get("clips") if isinstance(data, dict) else None
    if not isinstance(crudos, list) or not crudos:
        raise ValueError("no trae clips")
    if len(crudos) > MAX_CLIPS:
        raise ValueError("trae demasiados clips")
    bv = data.get("bloque_video") if isinstance(data.get("bloque_video"), dict) else {}
    hooks = data.get("hooks") if isinstance(data.get("hooks"), dict) else {}
    return {"bloque_video": {k: (_str(bv.get(k)) or d) for k, d in DEFECTOS_BLOQUE.items()},
            "clips": [_clip_forma(c, i) for i, c in enumerate(crudos, start=1)],
            "hooks": {h: _clip_forma(hooks[h], 1) for h in hooks_esperados if h in hooks}}


def _calculado(c, textos, wps, indice, total):
    t = duracion.calcular_clip(c["momentos"], textos, wps)
    return {"indice": indice, "total": total, "titulo": c["titulo"], "lineas": c["lineas"],
            "estado_inicio": c["estado_inicio"], "estado_fin": c["estado_fin"], "entornos": c["entornos"],
            "es_final": indice == total, **t}


def calcular(plan, lectura, config):
    wps = config["palabras_por_segundo"]
    textos = duracion.textos_efectivos(lectura, config.get("hook", "original"))
    total = len(plan["clips"])
    cs = [_calculado(c, textos, wps, i, total) for i, c in enumerate(plan["clips"], start=1)]
    suma = sum(c["duracion"] for c in cs)
    hooks_alt = {}
    for hid, c in plan["hooks"].items():
        th = dict(textos)
        th[1] = duracion.textos_efectivos(lectura, hid)[1]
        h = _calculado(c, th, wps, 1, total)
        h["hook_id"] = hid
        h["duracion_total_video"] = suma - cs[0]["duracion"] + h["duracion"]
        hooks_alt[hid] = h
    return cs, hooks_alt


def fijos(clip):
    return [t for m in clip["momentos"] for t in m["textos"] if t]


def renderizar(cs, hooks_alt, config, bloque_video, bloque_global_txt):
    bv = plantillas.bloque_video(config, bloque_video)
    salida = [{"variante": "principal", "clip": c, "texto": plantillas.prompt_clip(bv, c, config, bloque_global_txt),
               "fijos": fijos(c)} for c in cs]
    salida += [{"variante": f"hook:{hid}", "clip": h, "texto": plantillas.prompt_clip(bv, h, config, bloque_global_txt),
                "fijos": fijos(h)} for hid, h in hooks_alt.items()]
    return salida


def _dichas(c):
    return [n for m in c["momentos"] for n in m["dice"]]


def _momentos_ok(c):
    ms = c["momentos"]
    if not ms or ms[0]["t_ini"] != 0.0 or ms[-1]["t_fin"] != float(c["duracion"]):
        return False
    return all(m["t_fin"] > m["t_ini"] for m in ms) and all(a["t_fin"] == b["t_ini"] for a, b in zip(ms, ms[1:]))


def _lista(ns):
    return ", ".join(str(n) for n in ns)


def _frase(t):
    return t[:1].upper() + t[1:]


def validar(cs, hooks_alt, lectura, config, quitadas, renders, esperados):
    textos = duracion.textos_efectivos(lectura, config.get("hook", "original"))
    cons = duracion.conservadas(textos, quitadas)
    esperadas = [n for n, _ in cons]
    dichas = [n for c in cs for n in _dichas(c)]
    res = []

    def regla(nombre, ok, detalle):
        res.append({"regla": nombre, "ok": bool(ok), "detalle": "" if ok else detalle.strip()})

    dicho = _normalizar(" ".join(m["texto"] for c in cs for m in c["momentos"] if m["texto"]))
    regla("V1 fidelidad", dicho == _normalizar(" ".join(t for _, t in cons)),
          "El texto que se dice en los clips no es idéntico al guion con las líneas quitadas.")

    faltan = [n for n in esperadas if n not in dichas]
    repetidas = sorted({n for n in dichas if dichas.count(n) > 1})
    sobran = sorted({n for n in dichas if n not in esperadas})
    partes = ([f"faltan las líneas {_lista(faltan)}"] if faltan else []) + \
             ([f"se repiten {_lista(repetidas)}"] if repetidas else []) + \
             ([f"sobran {_lista(sobran)} (quitadas o inexistentes)"] if sobran else [])
    regla("V2 cobertura", dichas == esperadas,
          ("Las líneas no cubren el guion: " + "; ".join(partes) + ".") if partes else "Las líneas están fuera de orden.")

    todos = [(f"clip {c['indice']}", c) for c in cs] + [(f"clip 1 con {hid}", h) for hid, h in hooks_alt.items()]
    fuera = [f"{nombre} ({c['duracion']} s)" for nombre, c in todos
             if not duracion.MIN_CLIP <= c["duracion"] <= duracion.MAX_CLIP]
    regla("V3 duración", not fuera, "Fuera de 5–15 s: " + ", ".join(fuera) + ".")
    huecos = [nombre for nombre, c in todos if not _momentos_ok(c)]
    regla("V4 tiempos", not huecos, "Tiempos con huecos o momentos vacíos en: " + ", ".join(huecos) + ".")

    final = cs[-1]
    cierre = final["es_final"] and not final["momentos"][-1]["dice"]
    problemas = [p for r in renders for p in refinador.validar(r["texto"], r["fijos"], "clip")]
    regla("V5 cierre", cierre and not problemas,
          ("El último clip tiene que terminar en un cuadro sostenido sin diálogo. " if not cierre else "")
          + (problemas[0] if problemas else ""))

    objetivo = config.get("duracion_objetivo")
    total = sum(c["duracion"] for c in cs)
    regla("V6 total", objetivo is None or total <= objetivo, f"El video dura {total} s y el objetivo es {objetivo} s.")

    mal = [c["indice"] for c in cs if sorted(c["lineas"]) != sorted(_dichas(c))]
    regla("E1 líneas por clip", not mal, f"En los clips {_lista(mal)} las líneas declaradas no coinciden con las que se dicen.")
    regla("E2 hook al inicio", _dichas(cs[0])[:1] == [1], "El clip 1 tiene que empezar con la línea 1 (el hook).")
    slots = {i for i, r in enumerate(config["referencias"], start=1) if r["tipo"] == "entorno"}
    malos = [nombre for nombre, c in todos if any(s not in slots for s in c["entornos"])]
    regla("E3 entornos", not malos, "Entornos que no son referencias de tipo entorno en: " + ", ".join(malos) + ".")

    errores = [f"falta el clip 1 con {h}" for h in esperados if h not in hooks_alt]
    for hid, h in hooks_alt.items():
        if _dichas(h) != _dichas(cs[0]):
            errores.append(f"el clip 1 con {hid} no dice las mismas líneas que el clip 1")
        elif _normalizar(h["estado_fin"]) != _normalizar(cs[0]["estado_fin"]):
            errores.append(f"el clip 1 con {hid} no termina igual que el clip 1")
    regla("E4 hooks alternativos", not errores, _frase("; ".join(errores)) + ".")

    avisos = [f"Continuidad: el clip {a['indice']} termina «{a['estado_fin']}» y el {b['indice']} empieza «{b['estado_inicio']}»."
              for a, b in zip(cs, cs[1:]) if _normalizar(a["estado_fin"]) != _normalizar(b["estado_inicio"])]
    avisos += [f"El clip {c['indice']} no dice cómo empieza o cómo termina." for c in cs
               if not c["estado_inicio"] or not c["estado_fin"]]
    return res, avisos
