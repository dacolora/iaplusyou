"""Nombres de los idiomas en que se publica (guion, voz, copy), para ponerlos en los prompts a Claude.

Con el código solo, `'no'` se lee como la palabra «no»: por eso un prompt que escribe copy publicable lleva el nombre
del idioma además del código. Sin Flask en el import. Los diccionarios que otros módulos tienen para su propio
propósito (audios, nicho, sprints) siguen aparte (spec 2026-10-08 de Noruega y Suecia, §4).
"""

NOMBRES = {"es": "español", "en": "inglés", "pt": "portugués", "sv": "sueco", "no": "noruego (bokmål)"}
NOMBRES_EN = {"es": "Spanish", "en": "English", "pt": "Portuguese", "sv": "Swedish", "no": "Norwegian (Bokmål)"}


def nombre(codigo, en_ingles=False):
    """Nombre del idioma `codigo` (en español, o en inglés con `en_ingles`); el mismo código si no lo conoce."""
    return (NOMBRES_EN if en_ingles else NOMBRES).get(codigo, codigo)
