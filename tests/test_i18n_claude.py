"""Claude escribe en el idioma del proyecto (spec 2026-09-26 §B4): ningún
prompt de los archivos ya pasados a idioma del proyecto fija «en español» a
mano. Cada fase agrega sus archivos."""
import os
import re

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIJO = re.compile(r"(?i)\b(?:en|al)\s+español\b|todo en español|en espa[nñ]ol neutro")
ARCHIVOS_FASE3 = [
    "director.py", "flowplus_prompt.py", "final_edition/sonido.py",
    "guiones/refinador.py", "guiones/recorte.py", "guiones/imagenes.py",
]


@pytest.mark.parametrize("ruta", ARCHIVOS_FASE3)
def test_sin_espanol_fijo_en_prompts(ruta):
    with open(os.path.join(RAIZ, ruta), encoding="utf-8") as f:
        texto = f.read()
    # Los comentarios y docstrings pueden hablar del español; los prompts no.
    sin_comentarios = re.sub(r'#[^\n]*', "", texto)
    hallazgos = [m.group(0) for m in FIJO.finditer(sin_comentarios)]
    assert not hallazgos, f"{ruta}: idioma fijo en un prompt: {hallazgos}"
