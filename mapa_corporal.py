"""
Mapa corporal: dónde va un producto sobre el cuerpo, y en qué proporción.

Al crear un producto en FlowCatálogo se toca sobre un maniquí las zonas que el
producto ocupa. Ese mapa se traduce acá a una instrucción, en el idioma del
proyecto, anclada a las 8 cabezas del canon clásico de proporción — que es lo
que le da al modelo la referencia de TAMAÑO, no solo de ubicación.

Por qué proporciones y no solo nombres de zona: decir "va en las piernas" deja
al modelo elegir si el pantalón llega al tobillo o a la rodilla. Decir "ocupa
desde la cabeza 3 hasta la 5.5 de 8, de la cintura a media pierna" no.

Y tan importante como decir dónde VA es decir dónde NO va: sin eso, los modelos
tienden a extender la prenda más de la cuenta. Por eso el texto generado siempre
enumera las zonas excluidas.

Ninguno de los modelos que usamos acepta una máscara real (no existe un campo
donde mandarle "edita solo acá"), así que esto es la forma más precisa
disponible: una instrucción, no una restricción dura.
"""

# id -> (etiqueta en la UI, desde, hasta, nombre dentro del prompt)
# desde/hasta van en "cabezas" del canon de 8: 0 es la coronilla, 8 la planta.
ZONAS = {
    "cabeza_corona":  ("Corona de la cabeza", 0.0, 0.5, "la parte alta de la cabeza"),
    "cabeza_ojos":    ("Ojos / rostro",       0.4, 0.6, "los ojos y el puente de la nariz"),
    "cuello":         ("Cuello",              0.9, 1.1, "el cuello"),
    "torso_alto":     ("Torso alto (pecho)",  1.0, 2.0, "el pecho y la parte alta del torso"),
    "torso_bajo":     ("Torso bajo (abdomen)", 2.0, 3.0, "el abdomen y la cintura"),
    "brazo":          ("Brazo (hombro→codo)", 1.2, 2.4, "los brazos, del hombro al codo"),
    "antebrazo":      ("Antebrazo (codo→muñeca)", 2.4, 3.4, "los antebrazos, del codo a la muñeca"),
    "manos":          ("Manos",               3.4, 3.7, "las manos"),
    "cadera":         ("Cadera / entrepierna", 3.0, 4.0, "la cadera y la entrepierna"),
    "muslo":          ("Muslos",              4.0, 5.5, "los muslos"),
    "pantorrilla":    ("Rodilla y pantorrilla", 5.5, 7.3, "las rodillas y las pantorrillas"),
    "pies":           ("Pies",                7.3, 8.0, "los pies"),
}

# Referencias de altura del canon, para traducir un número de cabeza a algo que
# una persona (y un modelo de lenguaje) entienda sin pensar.
HITOS = [
    (0.0, "la coronilla"), (0.5, "la altura de los ojos"), (0.9, "la base del cuello"),
    (1.0, "el mentón"), (1.2, "los hombros"), (2.0, "los pezones"),
    (2.4, "los codos"), (3.0, "el ombligo"), (3.4, "las muñecas"),
    (4.0, "la entrepierna"), (5.5, "media pierna"), (6.0, "las rodillas"),
    (7.3, "los tobillos"), (8.0, "la planta de los pies"),
]

# Nombres dentro del prompt en inglés (mismas claves que ZONAS y mismo orden que HITOS).
NOMBRES_EN = {
    "cabeza_corona": "the top of the head", "cabeza_ojos": "the eyes and the bridge of the nose",
    "cuello": "the neck", "torso_alto": "the chest and upper torso", "torso_bajo": "the abdomen and waist",
    "brazo": "the arms, from shoulder to elbow", "antebrazo": "the forearms, from elbow to wrist",
    "manos": "the hands", "cadera": "the hips and groin", "muslo": "the thighs",
    "pantorrilla": "the knees and calves", "pies": "the feet",
}
HITOS_EN = ["the crown of the head", "eye level", "the base of the neck", "the chin", "the shoulders",
            "the nipples", "the elbows", "the navel", "the wrists", "the groin", "mid-leg", "the knees",
            "the ankles", "the soles of the feet"]

# Combinaciones frecuentes, para que no haya que tocar zona por zona.
PRESETS = {
    "gafas":            ["cabeza_ojos"],
    "gorra":            ["cabeza_corona"],
    "calzado":          ["pies"],
    "camisilla":        ["torso_alto", "torso_bajo"],
    "camisa_manga_corta": ["torso_alto", "torso_bajo", "brazo"],
    "camisa_manga_larga": ["torso_alto", "torso_bajo", "brazo", "antebrazo"],
    "boxer":            ["cadera"],
    "pantaloneta":      ["cadera", "muslo"],
    "pantalon":         ["cadera", "muslo", "pantorrilla"],
    "conjunto_completo": ["torso_alto", "torso_bajo", "brazo", "cadera", "muslo", "pantorrilla"],
    "falda":            ["cadera", "muslo"],
    "vestido":          ["torso_alto", "torso_bajo", "cadera", "muslo"],
}

ETIQUETAS_PRESETS = {
    "gafas": "Gafas", "gorra": "Gorra / sombrero", "calzado": "Calzado",
    "camisilla": "Camisilla", "camisa_manga_corta": "Camisa manga corta",
    "camisa_manga_larga": "Camisa manga larga", "boxer": "Boxer",
    "pantaloneta": "Pantaloneta", "pantalon": "Pantalón",
    "conjunto_completo": "Conjunto completo", "falda": "Falda", "vestido": "Vestido",
}


def _hito(valor, idioma="es"):
    """El punto de referencia anatómico más cercano a una altura del canon."""
    i = min(range(len(HITOS)), key=lambda i: abs(HITOS[i][0] - valor))
    return HITOS_EN[i] if idioma == "en" else HITOS[i][1]


def normalizar(zonas):
    """Deja solo ids conocidos, en el orden anatómico de arriba hacia abajo."""
    validas = [z for z in (zonas or []) if z in ZONAS]
    return sorted(set(validas), key=lambda z: ZONAS[z][1])


def describir(zonas, idioma="es"):
    """Convierte el mapa en la instrucción que se le inyecta al modelo, en el
    idioma del proyecto (spec 2026-09-26 §B4).

    Devuelve None si no hay zonas: un producto que no va sobre el cuerpo (una
    cobija, un objeto de escena) no debe recibir instrucciones corporales."""
    zonas = normalizar(zonas)
    if not zonas:
        return None

    ingles = idioma == "en"
    nombre_de = NOMBRES_EN if ingles else {z: v[3] for z, v in ZONAS.items()}
    nombres = [nombre_de[z] for z in zonas]
    if len(nombres) == 1:
        donde = nombres[0]
    else:
        donde = ", ".join(nombres[:-1]) + (" and " if ingles else " y ") + nombres[-1]

    desde = min(ZONAS[z][1] for z in zonas)
    hasta = max(ZONAS[z][2] for z in zonas)

    excluidas = [nombre_de[z] for z in ZONAS if z not in zonas]
    # Solo se nombran las exclusiones que de verdad importan: las adyacentes al
    # rango ocupado. Listar las doce zonas restantes diluye la instrucción.
    adyacentes = [
        nombre_de[z] for z in ZONAS
        if z not in zonas and (
            abs(ZONAS[z][2] - desde) <= 1.6 or abs(ZONAS[z][1] - hasta) <= 1.6
        )
    ]
    no_toca = adyacentes or excluidas

    if ingles:
        texto = (
            f"EXACT PRODUCT PLACEMENT: it goes on {donde}. "
            f"In body proportions, it covers from {_hito(desde, 'en')} to {_hito(hasta, 'en')} "
            f"(from head {desde:g} to {hasta:g}, on an 8-head body). "
            f"The product does NOT extend beyond that range."
        )
    else:
        texto = (
            f"UBICACIÓN EXACTA DEL PRODUCTO: va sobre {donde}. "
            f"En proporción del cuerpo, ocupa desde {_hito(desde)} hasta {_hito(hasta)} "
            f"(de la cabeza {desde:g} a la {hasta:g}, en un cuerpo de 8 cabezas). "
            f"El producto NO se extiende más allá de ese rango."
        )
    if no_toca:
        lista = ", ".join(no_toca[:5])
        texto += f" It does NOT touch {lista}." if ingles else f" NO toca {lista}."
    return texto


def preset_de(zonas):
    """Si el mapa coincide exactamente con un preset conocido, devuelve su id.
    Sirve para que la UI muestre 'Pantalón' en vez de repetir tres zonas."""
    actual = set(normalizar(zonas))
    for pid, z in PRESETS.items():
        if set(z) == actual:
            return pid
    return None
