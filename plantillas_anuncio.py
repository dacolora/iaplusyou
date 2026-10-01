"""
Recetas de tomas para «Crear super prompt con IA» (spec
docs/superpowers/specs/2026-09-18-director-prompts-crear-design.md §9, Etapa 3).

Una receta es una estructura de actos (qué se ve en cada tramo, en porcentaje
de la duración) que el director (`director.py`) convierte en planos. Es
opcional y solo existe en el camino del director: «Generar video» manda el
texto de la persona tal cual. Datos puros más tres cálculos: los actos en
segundos para una duración, cuántos planos pedirle a Claude y el bloque que
va en su mensaje.

`que_se_ve` e `instruccion` son para Claude (en español, como el resto de las
instrucciones del director); `nombre` y `descripcion` los ve la persona
(`idiomas.N_` + `|traducir`). `camara_inicial` es un id de
`flowplus_prompt.CAMARAS` (los presets con nombre de la Etapa 2 no existen
todavía). Ninguna receta pide «solo producto, sin nadie» (regla de Daniel,
2026-09-22): con enfoque `producto` el producto es el protagonista.
"""
from idiomas import N_

PLANTILLAS = (
    {
        "id": "antes_despues",
        "nombre": N_("Antes y después"),
        "descripcion": N_("Primero el problema, luego el producto haciendo el cambio y al final el resultado a la vista."),
        "enfoque": None,
        "requiere_video": False,
        "camara_inicial": "dolly_in",
        "sonido_sugerido": None,
        "actos": (
            {"nombre": "El antes", "desde_pct": 0, "hasta_pct": 25,
             "que_se_ve": "el problema o el «antes» que se ve: lo que pasa sin el producto"},
            {"nombre": "El cambio", "desde_pct": 25, "hasta_pct": 65,
             "que_se_ve": "el producto en acción haciendo el cambio, de cerca"},
            {"nombre": "El después", "desde_pct": 65, "hasta_pct": 100,
             "que_se_ve": "el resultado a la vista —el «después»— y un detalle o una reacción que lo prueba"},
        ),
    },
    {
        "id": "producto_estudio",
        "nombre": N_("Producto en estudio"),
        "descripcion": N_("El material de cerca, un giro que muestra la forma completa y un cierre de lucimiento sobre el producto."),
        "enfoque": "producto",
        "requiere_video": False,
        "camara_inicial": "macro_a_abierto",
        "sonido_sugerido": "ambiente de estudio en calma y el roce suave del material",
        "actos": (
            {"nombre": "Detalle", "desde_pct": 0, "hasta_pct": 40,
             "que_se_ve": "detalle macro del material y la textura del producto, con una luz que lo recorre"},
            {"nombre": "Forma completa", "desde_pct": 40, "hasta_pct": 80,
             "que_se_ve": "un giro o una apertura que muestra la forma completa del producto"},
            {"nombre": "Cierre", "desde_pct": 80, "hasta_pct": 100,
             "que_se_ve": "el producto entero, de frente y bien iluminado, con un último movimiento suave; sin logo ni fundido"},
        ),
    },
    {
        "id": "producto_entorno",
        "nombre": N_("Producto en su lugar"),
        "descripcion": N_("El lugar y la luz; el producto entra a cuadro y se ve funcionando ahí."),
        "enfoque": "producto",
        "requiere_video": False,
        "camara_inicial": "travelling_lateral",
        "sonido_sugerido": "el ambiente del lugar y el sonido propio del producto al usarse",
        "actos": (
            {"nombre": "El lugar", "desde_pct": 0, "hasta_pct": 30,
             "que_se_ve": "el lugar y la luz; el producto entra en cuadro"},
            {"nombre": "En uso", "desde_pct": 30, "hasta_pct": 75,
             "que_se_ve": "el producto en uso en ese lugar: lo que hace o cambia se ve pasar; si hace falta una mano para usarlo, solo la mano"},
            {"nombre": "Cierre", "desde_pct": 75, "hasta_pct": 100,
             "que_se_ve": "el producto en su lugar con el resultado de usarlo a la vista"},
        ),
    },
    {
        "id": "con_modelo",
        "nombre": N_("Con modelo"),
        "descripcion": N_("Una persona con el producto: un gancho que llama la atención, uso natural y cierre en un gesto o un detalle."),
        "enfoque": "persona",
        "requiere_video": False,
        "camara_inicial": "seguimiento_mano",
        "sonido_sugerido": None,
        "actos": (
            {"nombre": "Gancho", "desde_pct": 0, "hasta_pct": 25,
             "que_se_ve": "la persona con el producto puesto o en la mano, haciendo algo que llama la atención"},
            {"nombre": "Uso", "desde_pct": 25, "hasta_pct": 70,
             "que_se_ve": "uso natural del producto; la cámara la sigue"},
            {"nombre": "Cierre", "desde_pct": 70, "hasta_pct": 100,
             "que_se_ve": "cierre en un gesto de la persona o en un detalle del producto"},
        ),
    },
    {
        "id": "ugc_sin_cara",
        "nombre": N_("UGC sin cara"),
        "descripcion": N_("Solo manos y producto, como grabado con el teléfono: sacarlo, usarlo y mostrarlo."),
        "enfoque": "persona",
        "requiere_video": False,
        "camara_inicial": "seguimiento_mano",
        "sonido_sugerido": "ambiente de casa y el roce del producto en las manos",
        "actos": (
            {"nombre": "Mostrar", "desde_pct": 0, "hasta_pct": 25,
             "que_se_ve": "unas manos sacan o muestran el producto; cámara de teléfono en mano, luz natural, sin cara"},
            {"nombre": "Probar", "desde_pct": 25, "hasta_pct": 75,
             "que_se_ve": "las manos lo usan o lo prueban y se nota el resultado (un gesto de aprobación, un detalle que cambia)"},
            {"nombre": "Cierre", "desde_pct": 75, "hasta_pct": 100,
             "que_se_ve": "cierre en el producto en la mano"},
        ),
    },
    {
        "id": "ugc_silencioso",
        "nombre": N_("Selfie sin voz"),
        "descripcion": N_("Alguien mira a cámara, muestra el producto y reacciona sin decir nada."),
        "enfoque": "persona",
        "requiere_video": False,
        "camara_inicial": "estatico",
        "sonido_sugerido": "ambiente de casa, sin voz",
        "actos": (
            {"nombre": "Gancho", "desde_pct": 0, "hasta_pct": 20,
             "que_se_ve": "selfie: la persona mira a cámara, sin hablar, con un gesto que engancha"},
            {"nombre": "Mostrar y reaccionar", "desde_pct": 20, "hasta_pct": 70,
             "que_se_ve": "muestra el producto a cámara y reacciona: una media sonrisa que llega tarde, un asentir"},
            {"nombre": "Cierre", "desde_pct": 70, "hasta_pct": 100,
             "que_se_ve": "cierre en la cara de la persona con el producto cerca, no en el producto aislado"},
        ),
    },
    {
        "id": "unboxing",
        "nombre": N_("Unboxing"),
        "descripcion": N_("La caja se abre, el producto sale y se mira de cerca."),
        "enfoque": "unboxing",
        "requiere_video": False,
        "camara_inicial": "cenital",
        "sonido_sugerido": "cartón y papel que se rasgan, la caja que se abre",
        "actos": (
            {"nombre": "Abrir", "desde_pct": 0, "hasta_pct": 30,
             "que_se_ve": "la caja o la bolsa cerrada; las manos la abren"},
            {"nombre": "Descubrir", "desde_pct": 30, "hasta_pct": 80,
             "que_se_ve": "sacan el producto y lo miran de cerca"},
            {"nombre": "Estrenar", "desde_pct": 80, "hasta_pct": 100,
             "que_se_ve": "lo muestran, contentos de estrenarlo"},
        ),
    },
    {
        "id": "recrear_referencia",
        "nombre": N_("Recrear mi video de referencia"),
        "descripcion": N_("Copia el ritmo, el movimiento y el encuadre de tu video de referencia. Necesita un video en la bandeja y Wan 3.0."),
        "enfoque": None,
        "requiere_video": True,
        "camara_inicial": None,
        "sonido_sugerido": None,
        "actos": (),
        "instruccion": ("Sin actos fijos: los planos siguen la estructura de {video} tal como la describe la IDEA, con el "
                        "producto y las personas de las imágenes; de {video} toma el movimiento, el ritmo y el encuadre, "
                        "nunca sus objetos ni sus personas."),
    },
)

POR_ID = {p["id"]: p for p in PLANTILLAS}


def por_id(pid):
    """La receta con ese id, o None (un valor desconocido se ignora)."""
    return POR_ID.get(pid) if isinstance(pid, str) else None


def _medio_arriba(x):
    return int(x + 0.5)


def actos_en_segundos(plantilla, duracion):
    """Los actos de la receta para `duracion` segundos: [{nombre, desde_s,
    hasta_s, que_se_ve}], contiguos de 0 a la duración, en segundos enteros.
    En duraciones cortas un acto que se queda sin segundos se suma a otro
    (nunca se pierde lo que tiene que verse). Sin actos: []."""
    d = int(duracion or 0)
    salida, pendientes = [], []
    for acto in plantilla.get("actos") or ():
        partes = pendientes + [acto]
        desde = salida[-1]["hasta_s"] if salida else 0
        hasta = min(d, _medio_arriba(d * acto["hasta_pct"] / 100))
        if hasta > desde:
            salida.append({"nombre": " + ".join(p["nombre"] for p in partes), "desde_s": desde, "hasta_s": hasta,
                           "que_se_ve": "; ".join(p["que_se_ve"] for p in partes)})
            pendientes = []
        elif salida:
            salida[-1]["nombre"] += " + " + " + ".join(p["nombre"] for p in partes)
            salida[-1]["que_se_ve"] += "; " + "; ".join(p["que_se_ve"] for p in partes)
            pendientes = []
        else:
            pendientes = partes
    if salida:
        salida[-1]["hasta_s"] = d
    return salida


def n_planos(plantilla, duracion, base):
    """Cuántos planos pedirle a Claude: al menos uno por acto (si no, un acto
    se come a otro) y nunca más de uno cada 2 s. `base` es el número de la
    tabla por duración (director.n_planos); sin actos manda la tabla."""
    actos = len(actos_en_segundos(plantilla, duracion))
    if not actos:
        return base
    return max(1, min(max(base, actos), int(duracion) // 2))


def bloque_director(plantilla, duracion, referencias=()):
    """Las líneas `PLANTILLA:` del mensaje al director (spec §9: los actos ya
    convertidos a segundos)."""
    lineas = [f"PLANTILLA: «{plantilla['nombre']}» — {plantilla['descripcion']}"]
    actos = actos_en_segundos(plantilla, duracion)
    if actos:
        lineas.append("Actos, en este orden. Los cortes entre planos caen en los límites de los actos cuando el número de "
                      "planos lo permite; si hay menos planos que actos, junta actos seguidos en un plano; si hay más, "
                      "reparte los planos dentro de los actos:")
        lineas += [f"- Acto {i} · {a['desde_s']}-{a['hasta_s']} s · {a['nombre']}: {a['que_se_ve']}"
                   for i, a in enumerate(actos, start=1)]
    if plantilla.get("instruccion"):
        video = next((r["token"] for r in referencias if str(r.get("token") or "").startswith("Video ")), "Video 1")
        lineas.append(plantilla["instruccion"].format(video=video))
    if plantilla.get("camara_inicial"):
        lineas.append(f"Cámara del primer plano de la versión A: {plantilla['camara_inicial']} (la versión B arranca con otra).")
    if plantilla.get("sonido_sugerido"):
        lineas.append(f"Si SONIDO es sí y no trae texto, el sonido sugerido es: {plantilla['sonido_sugerido']}.")
    lineas.append("La IDEA manda en qué se ve (sujetos, producto, lugar); la PLANTILLA manda en cómo se cuenta "
                  "(orden de los actos y tipo de plano).")
    return lineas
