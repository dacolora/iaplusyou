"""2026-09-28: la persona pidió quitar el «solo producto, sin nadie» del prompt
armado (director y Sprints). Sin personaje del catálogo ni enfoque «persona»
el prompt ya no prohíbe personas ni manos, no poda la guía de marca y no
remata con el recordatorio; el producto es el protagonista."""
import flowplus_prompt

REFS = [{"tipo": "imagen", "etiqueta": "@Producto 1", "categoria": "producto", "activo": "Espejo LED",
         "regla": "Idéntico.", "producto": "Espejo LED"}]


def _evitar(p):
    return next(l for l in p.splitlines() if l.startswith("EVITAR: ") or l.startswith("AVOID: "))


def test_enfoque_producto_ya_no_prohibe_personas_ni_poda_la_guia():
    p = flowplus_prompt.armar("gira despacio", REFS, guia_marca="Luz natural. Manos de mujer joven.", enfoque="producto")
    assert "Recordatorio final" not in p and "sin nadie" not in p
    assert not any(palabra in _evitar(p) for palabra in ("personas", "pies", "manos"))
    assert "ESTILO DE MARCA: Luz natural. Manos de mujer joven." in p
    assert "CON PERSONA" not in p
    assert p.splitlines()[-1] == _evitar(p)


def test_sin_enfoque_tampoco():
    p = flowplus_prompt.armar("gira despacio", REFS, guia_marca="Luz natural.")
    assert "Recordatorio final" not in p and "personas" not in _evitar(p)


def test_enfoque_persona_sigue_con_su_bloque():
    p = flowplus_prompt.armar("camina", REFS, guia_marca="Luz natural.", enfoque="persona")
    assert "CON PERSONA:" in p and "Recordatorio final" not in p


def test_en_ingles_tampoco():
    p = flowplus_prompt.armar("spins", REFS, guia_marca="Soft light. Young hands.", enfoque="producto", idioma="en")
    assert "Final reminder" not in p and "people" not in _evitar(p) and "BRAND STYLE: Soft light. Young hands." in p


def test_la_descripcion_del_enfoque_producto_ya_no_dice_sin_nadie():
    d = flowplus_prompt.ENFOQUES["producto"]["descripcion"]
    assert "sin nadie" not in d and "protagonista" in d
