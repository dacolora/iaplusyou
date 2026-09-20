"""
Fuente `texto` (spec §3.2): comentarios pegados a mano en un cuadro de texto.
`modo` = "lineas" (una línea por comentario) o "parrafos" (separados por una
línea en blanco; los saltos internos se vuelven espacios). Corre en la ruta,
sin worker. `fuente_id` = hash del texto (lo pone normalizar_comentario).
"""
import re

from nicho.fuentes.base import Fuente, normalizar_comentario

MODOS = ("lineas", "parrafos")
NOMBRES_MODO = {"lineas": "Una línea por comentario", "parrafos": "Separados por una línea en blanco"}
_RE_PARRAFO = re.compile(r"\n\s*\n")


def partir_texto(texto, modo="lineas"):
    t = "" if texto is None else str(texto).replace("\r\n", "\n").replace("\r", "\n")
    if modo == "parrafos":
        trozos = [" ".join(p.split()) for p in _RE_PARRAFO.split(t)]
    else:
        trozos = [l.strip() for l in t.split("\n")]
    return [x for x in trozos if x]


class FuenteTexto(Fuente):
    tipo = "texto"

    def recolectar(self, params, avanzar=None):
        params = dict(params or {})
        for trozo in partir_texto(params.get("texto"), params.get("modo") or "lineas"):
            c = normalizar_comentario({"texto": trozo})
            if c:
                yield c
