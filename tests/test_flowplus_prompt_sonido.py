"""Línea SONIDO del prompt (spec estudio S1): describe el sonido de la escena
y prohíbe diálogo y música para que las voces nativas (Kling: chino/inglés)
no aparezcan; sin sonido el prompt es idéntico al de antes."""
import flowplus_prompt

REFS = [{"tipo": "imagen", "etiqueta": "@Producto 1", "categoria": "producto", "activo": "Espejo LED",
         "regla": "Idéntico.", "producto": "Espejo LED"}]
SIN_VOZ = "Sin diálogo hablado ni música de fondo."


def _armar(**kw):
    return flowplus_prompt.armar("gira despacio", REFS, guia_marca="Luz natural.", enfoque="producto", **kw)


def test_sin_sonido_el_prompt_es_identico():
    base = _armar()
    assert _armar(sonido=None, con_sonido=False) == base
    assert "SONIDO" not in base


def test_con_sonido_sin_texto_pide_el_ambiente_natural():
    p = _armar(con_sonido=True)
    lineas = p.split("\n")
    i_esc = next(i for i, l in enumerate(lineas) if l.startswith("ESCENA: "))
    i_son = next(i for i, l in enumerate(lineas) if l.startswith("SONIDO: "))
    i_evi = next(i for i, l in enumerate(lineas) if l.startswith("EVITAR: "))
    assert i_esc < i_son < i_evi
    assert lineas[i_son] == f"SONIDO: ambiente natural de la escena. {SIN_VOZ}"


def test_con_texto_de_sonido_lo_usa_tal_cual():
    p = _armar(sonido="risas de niños, pasos descalzos sobre baldosa.", con_sonido=True)
    assert f"SONIDO: risas de niños, pasos descalzos sobre baldosa. {SIN_VOZ}" in p
    # El texto manda aunque con_sonido venga en False (quien escribe sonido lo quiere).
    assert f"SONIDO: risas de niños, pasos descalzos sobre baldosa. {SIN_VOZ}" in _armar(sonido="risas de niños, pasos descalzos sobre baldosa.")
    # Espacios y vacío no cuentan como texto.
    assert _armar(sonido="   ") == _armar()
    assert "SONIDO: ambiente natural" in _armar(sonido="  ", con_sonido=True)
