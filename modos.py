"""
Modos de operación de un experimento (Bloque 4): deciden si una acción que el
decisor recomienda se ejecuta sola o queda como propuesta esperando al humano.

    manual  → todo es propuesta.
    semi    → pausar y archivar se ejecutan (no gastan); el resto es propuesta.
    auto    → todo se ejecuta (acciones.pedir igual propone si el tope está
              alcanzado — ver acciones.py).

Nada se activa solo fuera de acciones.ejecutar("activar").
"""

MODOS = ("manual", "semi", "auto")
ACCIONES = ("pausar", "escalar", "derivar", "rescatar", "activar", "archivar")

# Acciones que no gastan crédito: en semi se ejecutan sin preguntar.
_SIN_GASTO = ("pausar", "archivar")


def resolver(modo, accion):
    """'ejecutar' o 'propuesta' según la tabla de arriba. ValueError si el
    modo o la acción no existen."""
    if modo not in MODOS:
        raise ValueError(f"Modo desconocido: {modo!r} (esperado uno de {', '.join(MODOS)}).")
    if accion not in ACCIONES:
        raise ValueError(f"Acción desconocida: {accion!r} (esperada una de {', '.join(ACCIONES)}).")
    if modo == "auto":
        return "ejecutar"
    if modo == "semi" and accion in _SIN_GASTO:
        return "ejecutar"
    return "propuesta"
