"""
Los prompts de "cambiar producto" (antes "cambiar calzado"), en UN solo lugar.

Antes vivían copiados en providers/nano_banana_client.py, en
providers/comparador_modelos.py y en tres ramas de dashboard.py, todos con la
palabra "calzado" incrustada. Por eso agregar un producto que no fuera calzado
—una cobija— obligaba a editar cinco textos casi iguales y a mantenerlos
sincronizados a mano. Ahora el tipo de producto es un dato del catálogo y acá
se arma el prompt que le corresponde.

Un tipo NO es sinónimo de cambiar el sustantivo: un calzado va en los pies y no
puede sobresalir del contorno del pie; una cobija se drapea sobre una persona o
un mueble, sigue pliegues y ni siquiera hay una por persona. Cada tipo trae sus
propias reglas de dónde vive el producto, cómo se cuenta y qué significa que
"quede bien".
"""

TIPO_POR_DEFECTO = "calzado"

# Cada tipo define:
#   etiqueta   — cómo se llama en la UI
#   articulo   — "el"/"la", para que el prompt no salga mal escrito
#   sustantivo — cómo nombrarlo dentro del prompt
#   ubicacion  — dónde buscarlo en la foto
#   unidad     — qué se cuenta en el PASO 0 (no siempre es "por persona")
#   ajuste     — qué significa que quede bien puesto (la regla de tamaño/caída)
#   residuos   — qué restos del original hay que borrar además del objeto
#   plural     — ("todos", "ninguno") o ("todas", "ninguna"), para que el texto
#                concuerde: con "la cobija" no puede decir "ninguno se queda"
TIPOS = {
    "calzado": {
        "etiqueta": "Calzado (chanclas, zapatos, sandalias)",
        "articulo": "el",
        "sustantivo": "calzado",
        "ubicacion": "en los pies de cada persona",
        "unidad": (
            "contá cuántas personas aparecen y cuántas de ellas tienen calzado puesto "
            "(no cuenta quien esté descalzo o sosteniendo su calzado en la mano). Vas a "
            "editar ese número exacto de pares de calzado — ni uno menos"
        ),
        "ajuste": (
            "El calzado nuevo tiene que medir, en cada persona, EXACTAMENTE lo mismo que "
            "medía su calzado original — mismo largo de punta a talón, mismo ancho, ni un "
            "milímetro más. Compáralo con el tamaño del propio pie/tobillo de cada persona "
            "como referencia real: el calzado nunca debe sobresalir del contorno natural "
            "del pie de nadie. Si el resultado se ve más grande, ancho, inflado o "
            "\"exagerado\" que un calzado normal puesto en ese pie, está mal."
        ),
        "residuos": "cualquier media, calcetín o parte del calzado original que quede asomada",
        "plural": ("todos", "ninguno"),
    },
    "prenda": {
        "etiqueta": "Prenda de vestir (saco, camiseta, chaqueta)",
        "articulo": "la",
        "sustantivo": "prenda",
        "ubicacion": "sobre el cuerpo de cada persona",
        "unidad": (
            "contá cuántas personas aparecen llevando puesta esa prenda. Vas a editar ese "
            "número exacto de prendas — ni una menos"
        ),
        "ajuste": (
            "La prenda nueva debe quedarle a cada persona en su talla real: sigue el "
            "volumen del cuerpo, los hombros, los brazos y la postura exacta que ya tenía "
            "la prenda original, con la caída y los pliegues que tendría esa tela sobre ese "
            "cuerpo en esa pose. No agrandes ni achiques a la persona para que le quede."
        ),
        "residuos": "cualquier parte de la prenda original que asome por el cuello, los puños o el borde inferior",
        "plural": ("todas", "ninguna"),
    },
    "bolso": {
        "etiqueta": "Bolso o accesorio que se carga",
        "articulo": "el",
        "sustantivo": "bolso",
        "ubicacion": "que carga, sostiene o lleva colgado cada persona",
        "unidad": (
            "contá cuántos bolsos/accesorios de ese tipo aparecen cargados en la foto. Vas a "
            "editar ese número exacto — ni uno menos"
        ),
        "ajuste": (
            "El bolso nuevo debe conservar EXACTAMENTE cómo lo sostenía la persona: la misma "
            "mano o el mismo hombro, el mismo ángulo, la misma altura, la correa cayendo "
            "igual y los dedos agarrándolo del mismo modo. Su tamaño debe ser realista "
            "comparado con el cuerpo de quien lo carga."
        ),
        "residuos": "cualquier parte del bolso original que quede asomada detrás del cuerpo o del brazo",
        "plural": ("todos", "ninguno"),
    },
    "textil_hogar": {
        "etiqueta": "Textil de hogar (cobija, manta, cojín)",
        "articulo": "la",
        "sustantivo": "cobija o textil",
        "ubicacion": "sobre la persona, la cama, el sofá o donde esté puesta en la escena",
        "unidad": (
            "contá cuántas cobijas/mantas/textiles de ese tipo aparecen en la escena — puede "
            "haber una sola compartida por varias personas, o varias. Vas a editar ese número "
            "exacto — ni uno menos. OJO: acá NO se cuenta por persona"
        ),
        "ajuste": (
            "La cobija nueva debe ocupar exactamente el mismo espacio que ocupaba la original "
            "y seguir la misma forma: los mismos pliegues, la misma caída, el mismo volumen, "
            "cubriendo lo mismo que cubría antes y dejando ver lo mismo que dejaba ver. Debe "
            "verse como tela real apoyada sobre ese cuerpo o ese mueble, no como una imagen "
            "plana pegada encima."
        ),
        "residuos": "cualquier borde, esquina o parte de la cobija original que quede asomada por debajo",
        "plural": ("todas", "ninguna"),
    },
    "otro": {
        "etiqueta": "Otro (usa la descripción del producto)",
        "articulo": "el",
        "sustantivo": "producto",
        "ubicacion": "en el lugar exacto de la escena donde está el producto original",
        "unidad": (
            "contá cuántas unidades del producto aparecen en la escena. Vas a editar ese "
            "número exacto — ni una menos"
        ),
        "ajuste": (
            "El producto nuevo debe ocupar exactamente el mismo espacio, el mismo tamaño y la "
            "misma orientación que el original en la escena, con una escala realista respecto "
            "a lo que tiene alrededor."
        ),
        "residuos": "cualquier resto del producto original que quede asomado",
        "plural": ("todos", "ninguno"),
    },
}


def tipo_valido(tipo):
    return tipo if tipo in TIPOS else TIPO_POR_DEFECTO


def _t(tipo):
    return TIPOS[tipo_valido(tipo)]


def descripcion_por_defecto(tipo):
    """Texto para los modelos que NO ven la foto del producto (Higgsfield) cuando
    el producto no tiene descripción propia escrita. Es un mínimo honesto, no un
    reemplazo de escribirla."""
    t = _t(tipo)
    return f"{t['articulo']} {t['sustantivo']} mostrado en la referencia"


def prompt_imagen(tipo, referencias_lista=""):
    """Prompt de edición de FOTO. referencias_lista: las líneas que enumeran las
    imágenes de referencia del producto ("Imagen 2: ...", "Imagen 3: ..."), que
    cada proveedor arma según cuántas imágenes le quepan."""
    t = _t(tipo)
    art, sus = t["articulo"], t["sustantivo"]
    todos, ninguno = t["plural"]
    return f"""Esto es una EDICIÓN de foto, no la creación de una foto nueva. No \
generes una escena nueva ni una persona nueva — parte de la imagen 1 tal cual \
existe, píxel por píxel, y edítala.

Imagen 1 (OBLIGATORIO usar esta base, no otra): la foto a editar.
{referencias_lista}

PASO 0 — antes de editar nada: {t['unidad']}. Es un error grave dejar alguna \
sin cambiar.

La ÚNICA edición permitida: en la Imagen 1, localiza {art} {sus} que aparece \
{t['ubicacion']} — si hay más de una unidad, se editan {todos}, {ninguno} se \
queda con el original — y BÓRRALO POR COMPLETO en cada caso, incluyendo {t['residuos']}, \
antes de dibujar el producto nuevo. No debe quedar ningún resto visible del \
original debajo, detrás o alrededor del producto nuevo.

Reemplázalo por el producto mostrado en las imágenes de referencia (mismo color \
exacto, mismo diseño, misma textura).

ADVERTENCIA sobre el tamaño: las imágenes de referencia del producto son \
ACERCAMIENTOS de estudio — el producto llena casi todo el cuadro ahí, pero eso \
NO significa que el producto sea grande. Ignora por completo qué tan grande se \
ve el producto en sus propias fotos de referencia; eso es solo zoom de cámara, \
no su tamaño real.

{t['ajuste']}

Son las mismas personas y la misma escena de la Imagen 1 — mismos rostros \
exactos, mismo pelo, misma edad, misma piel, mismo cuerpo, misma ropa, misma \
pose exacta, mismo fondo exacto, misma luz exacta, mismo encuadre exacto. No es \
una foto nueva: es la Imagen 1 con {art} {sus} cambiado y nada más. Si dudas si \
cambiar algo que no sea {art} {sus}, no lo cambies."""


def prompt_video(tipo, descripcion_producto=None, citas=""):
    """Prompt de edición de VIDEO. citas: las referencias citables que acepte el
    modelo (ej. "@Image1 @Image2" en Kling O1); vacío si el modelo recibe las
    imágenes sin citarlas. descripcion_producto: solo para los modelos que NO
    ven la foto y necesitan el producto descrito en texto."""
    t = _t(tipo)
    art, sus = t["articulo"], t["sustantivo"]
    todos, ninguno = t["plural"]
    donde = f" en {citas}" if citas else " en las imágenes de referencia"
    que_es = f" ({descripcion_producto})" if descripcion_producto else ""
    return (
        f"En este video, reemplaza {art} {sus} que aparece {t['ubicacion']} — si "
        f"hay más de una unidad, {todos}, {ninguno} se queda con el original — por "
        f"el que se muestra{donde}{que_es}: mismo color, diseño y textura exactos. "
        f"{t['ajuste']} "
        f"No cambies nada más del video: mismo movimiento, mismas personas, mismo "
        f"fondo, misma iluminación, mismo encuadre."
    )
