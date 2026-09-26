"""Imágenes de referencia: qué hace falta, cierres fijos, tabla imagen↔clip y checklist."""
from guiones import imagenes
from tests.fixtures_guiones import CONFIG

PRODUCTO = {"tipo": "producto", "activo_id": "hf", "nombre": "HappyFlops Original", "descripcion": "EVA slipper",
            "casting": {}, "fotos": 3}
CFG = dict(CONFIG, referencias=[PRODUCTO] + CONFIG["referencias"] +
           [{"tipo": "entorno", "activo_id": "sala", "nombre": "Sala", "descripcion": "", "casting": {}, "fotos": 2}])
LEC = {"hooks": [{"id": "hook_2", "texto": "x"}], "hook_con_estilo_distinto": False}
CLIPS = [{"indice": 1, "titulo": "A", "entornos": [3]}, {"indice": 2, "titulo": "B", "entornos": [4, 9]}]


def test_necesarias_en_orden_y_sin_lo_que_ya_existe():
    lista = imagenes.necesarias(CFG, LEC)
    assert [(x["id"], x["tipo"], x["slot"]) for x in lista] == [("img_1", "personaje", 2), ("img_2", "entorno", 3),
                                                                 ("img_3", "producto", 1)]
    con_hooks = imagenes.necesarias(CFG, dict(LEC, hook_con_estilo_distinto=True))
    assert [x["hook_id"] for x in con_hooks if x["tipo"] == "hook"] == ["original", "hook_2"]
    sin_fotos = dict(CFG, referencias=[dict(PRODUCTO, fotos=0)])
    assert imagenes.necesarias(sin_fotos, LEC) == []


def test_componer_pone_formato_y_cierre():
    p, cierre = imagenes.componer({"id": "img_1", "tipo": "personaje", "slot": 2, "hook_id": None}, "A calm man.", CFG)
    assert p.startswith("16:9 character reference sheet") and "fictional" in p and p.endswith(imagenes.CIERRE)
    assert cierre == imagenes.CIERRE
    e, cierre_e = imagenes.componer({"id": "img_2", "tipo": "entorno", "slot": 3, "hook_id": None}, "A clinic.", CFG)
    assert e.startswith("9:16") and e.endswith(imagenes.CIERRE_ENTORNO) and cierre_e == imagenes.CIERRE_ENTORNO
    pr, _ = imagenes.componer({"id": "img_3", "tipo": "producto", "slot": 1, "hook_id": None}, "Clay look.", CFG)
    assert "Image 1 to Image 3" in pr and "Do not redesign the product." in pr and "top-down" in pr
    h, _ = imagenes.componer({"id": "img_4", "tipo": "hook", "slot": None, "hook_id": "hook_2"}, "Cartoon.", CFG)
    assert "STYLE OVERRIDE: Cartoon." in h


def test_tabla_imagen_clip():
    lista = imagenes.necesarias(CFG, LEC)
    filas = imagenes.tabla(CLIPS, CFG, lista)
    assert filas[0]["imagenes"] == ["Image 1 · HappyFlops Original", "Image 2 · por crear (img_1)", "Image 3 · por crear (img_2)"]
    assert filas[1]["imagenes"] == ["Image 1 · HappyFlops Original", "Image 2 · por crear (img_1)", "Image 4 · Sala"]


def test_checklist():
    lista = imagenes.necesarias(CFG, LEC)
    prompts = [{"tipo": "clip", "estado": "abierto"}, {"tipo": "clip", "estado": "aprobado"},
               {"tipo": "imagen", "estado": "abierto"}]
    faltas = imagenes.checklist(CFG, lista, prompts)
    assert any("img_1" in f for f in faltas) and any("img_2" in f for f in faltas)
    assert "Faltan por aprobar 1 prompt de clip en el chat." in faltas
    assert "Faltan por aprobar 1 prompt de imagen en el chat." in faltas
    sin_producto = dict(CFG, referencias=[dict(PRODUCTO, activo_id=None)])
    assert any("elige el producto" in f for f in imagenes.checklist(sin_producto, [], []))
