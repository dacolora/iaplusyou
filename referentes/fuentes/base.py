"""
Contrato común de las fuentes de barrido (spec 2026-09-23 §4). Un módulo por
fuente (`atria.py`, y en el bloque 5 `apify_adlibrary.py`) con tres funciones
de nivel de módulo: `estimar(consulta, tope)`, `probar()`,
`traer(consulta, tope, avanzar)`. `ErrorFuente` es el único error que una
fuente deja escapar hacia la ruta o el worker: `.usuario` (== `str(e)`) es un
mensaje en español apto para mostrarse tal cual y nunca lleva llaves ni HTML
ajeno.
"""


class ErrorFuente(Exception):
    """Error mostrable al usuario. `usuario` es el mensaje en español (sin
    llaves, sin HTML) y `str(e)` devuelve exactamente lo mismo."""

    def __init__(self, usuario):
        self.usuario = str(usuario)
        super().__init__(self.usuario)
