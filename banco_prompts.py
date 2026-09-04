"""
Banco de recetas para la acción central de FlowPlus.

No son prompts finales: son puntos de partida editables. El prompt
cinematográfico completo lo sigue armando Claude con la plantilla maestra
(generador_prompts.PLANTILLA_MAESTRA_CREATIVE_FLOW); esto solo evita escribir
la idea desde cero cada vez.

Están pensadas para lo que se pidió — variedad de escenarios, cambios de
posición, acercamientos — dentro del límite real del proveedor: Wan 3.0 y
Seedance generan UN plano continuo, así que lo que estas recetas piden son
movimientos de cámara y cambios de encuadre DENTRO de una misma toma, no cortes.
Un video con cortes reales necesita generar varios clips y unirlos con ffmpeg,
que es otro flujo (y otro costo).

Para agregar o cambiar recetas se edita esta lista y ya: aparecen solas en la UI.
"""

BANCO = [
    {
        "etiqueta": "Producto en primer plano",
        "texto": (
            "la cámara arranca en un plano cerrado del producto, gira lentamente a su "
            "alrededor mostrando su textura y su color real, y se abre hasta revelar el "
            "entorno completo donde está"
        ),
    },
    {
        "etiqueta": "Descubrimiento",
        "texto": (
            "la persona descubre el producto por primera vez, lo toma con curiosidad y "
            "su expresión cambia a alegría; la cámara pasa de su rostro a sus manos y "
            "termina en un plano completo"
        ),
    },
    {
        "etiqueta": "En movimiento",
        "texto": (
            "la persona camina con el producto puesto mientras la cámara la sigue de "
            "lado, con el fondo desplazándose; a mitad de recorrido la cámara baja a la "
            "altura del producto y vuelve a subir"
        ),
    },
    {
        "etiqueta": "Recorrido del entorno",
        "texto": (
            "la cámara recorre el espacio en un travelling continuo, pasando por "
            "distintos rincones del lugar hasta encontrar a la persona con el producto, "
            "y cierra en un plano medio"
        ),
    },
    {
        "etiqueta": "Bullet-time",
        "texto": (
            "el movimiento se congela en el momento más expresivo y la cámara orbita "
            "alrededor de la escena detenida, mostrando el producto desde varios "
            "ángulos, antes de que la acción se reanude"
        ),
    },
    {
        "etiqueta": "Día a noche",
        "texto": (
            "la escena empieza con luz de día y la iluminación va cambiando hacia el "
            "atardecer mientras la cámara se acerca lentamente, sin cortar, terminando "
            "con luz cálida sobre el producto"
        ),
    },
    {
        "etiqueta": "Grupo",
        "texto": (
            "varias personas comparten el momento con el producto; la cámara se mueve "
            "entre ellas deteniéndose en cada una, y termina en un plano abierto que "
            "las incluye a todas"
        ),
    },
    {
        "etiqueta": "Detalle a escena",
        "texto": (
            "empieza en un macro extremo de la textura del producto y se aleja de forma "
            "continua hasta mostrar la escena completa y quién lo lleva puesto"
        ),
    },
]


def listar():
    return BANCO
