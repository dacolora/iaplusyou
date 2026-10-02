"""Stickers propios del editor (capa 5c, D11): 20 PNG blancos sobre transparente, sin palabras, dibujados con
Pillow por `final_edition/stickers.py` y commiteados en `static/stickers/` con su manifiesto. El editor los tiñe
después con el `tinte` de la capa, así que aquí se prueba lo que ese color necesita: todo píxel visible es blanco
puro, ninguno está vacío y el generador da siempre lo mismo."""
import json
import os

import PIL
import pytest
from PIL import Image

from final_edition import stickers

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARPETA = os.path.join(RAIZ, "static", "stickers")

IDS = ["flecha_recta", "flecha_curva", "flecha_mano", "flecha_abajo",
       "circulo_mano", "subrayado_mano", "tachado_mano", "chulo", "equis", "exclamacion",
       "estallido", "estrella", "estrellas_5", "corazon", "etiqueta", "cinta", "circulo", "burbuja", "rayo",
       "destellos"]
CATEGORIA = {**{i: "flechas" for i in IDS[:4]}, **{i: "marcas" for i in IDS[4:10]}, **{i: "formas" for i in IDS[10:]}}

# La versión de Pillow con la que se generaron los PNG commiteados. Con esa misma versión (mayor.menor) el
# generador tiene que dar los MISMOS píxeles; con otra (la del VPS es más nueva) el suavizado de LANCZOS puede
# cambiar un valor de alfa aquí y allá, y la prueba compara tamaños y el alfa total (±1 %). Al regenerar el paquete
# con otro Pillow, se actualiza esta constante en el mismo cambio.
PILLOW_DEL_PAQUETE = "11.3"


def _version_pillow():
    return ".".join(PIL.__version__.split(".")[:2])


def _alfa_total(imagen):
    return sum(imagen.getchannel("A").getdata())


def test_las_constantes_del_contrato():
    assert stickers.CATEGORIAS == ("flechas", "marcas", "formas")
    assert list(stickers.IDS) == IDS
    assert (stickers.LADO, stickers.SUPER) == (512, 4)
    assert stickers.COLORES == {"flechas": "#FFD400", "formas": "#FFD400", "marcas": "#E11D48"}
    assert os.path.samefile(stickers.CARPETA, CARPETA)
    assert stickers.ID_RE.pattern == r"^[a-z0-9_]{1,40}$"


def test_el_manifiesto_del_repo_trae_los_20_en_orden_con_su_categoria_y_color():
    with open(os.path.join(CARPETA, "stickers.json"), encoding="utf-8") as f:
        crudo = json.load(f)
    assert crudo["version"] == 1
    assert [s["id"] for s in crudo["stickers"]] == IDS
    for s in crudo["stickers"]:
        assert set(s) == {"id", "categoria", "archivo", "ancho", "alto", "color"}
        assert s["categoria"] == CATEGORIA[s["id"]]
        assert s["color"] == stickers.COLORES[s["categoria"]]
        assert s["archivo"] == f"{s['id']}.png"
    assert stickers.manifiesto() == crudo


@pytest.mark.parametrize("id_", IDS)
def test_cada_png_mide_lo_que_dice_es_blanco_puro_y_no_esta_vacio(id_):
    ficha = stickers.por_id(id_)
    ruta = os.path.join(CARPETA, ficha["archivo"])
    assert stickers.ruta(id_) == ruta and os.path.isfile(ruta)
    with Image.open(ruta) as im:
        assert im.mode == "RGBA"
        assert im.size == (ficha["ancho"], ficha["alto"])
        assert max(im.size) == 512 and min(im.size) >= 40
        rgba = list(im.getdata())
    visibles = [p for p in rgba if p[3] > 0]
    assert all(p[:3] == (255, 255, 255) for p in visibles), "un píxel visible no es blanco: el tinte no lo cubriría"
    assert len(visibles) >= 0.05 * len(rgba), "el sticker está casi vacío"
    # 8 px de aire: nada visible pega con el borde
    ancho, alto = ficha["ancho"], ficha["alto"]
    for i, p in enumerate(rgba):
        if p[3] > 0:
            x, y = i % ancho, i // ancho
            assert 8 <= x < ancho - 8 and 8 <= y < alto - 8, f"{id_}: tinta a menos de 8 px del borde en {(x, y)}"


def test_generar_es_determinista_y_da_lo_que_esta_commiteado(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    man_a = stickers.generar(str(a))
    man_b = stickers.generar(str(b))
    assert man_a == man_b
    assert (a / "stickers.json").read_text(encoding="utf-8") == (b / "stickers.json").read_text(encoding="utf-8")
    with open(os.path.join(CARPETA, "stickers.json"), encoding="utf-8") as f:
        assert json.load(f) == man_a, "el manifiesto commiteado quedó viejo: PY -m final_edition.stickers"
    exacto = _version_pillow() == PILLOW_DEL_PAQUETE
    for id_ in IDS:
        with Image.open(a / f"{id_}.png") as ia, Image.open(b / f"{id_}.png") as ib:
            assert ia.tobytes() == ib.tobytes(), f"{id_}: dos corridas dieron píxeles distintos"
            with Image.open(os.path.join(CARPETA, f"{id_}.png")) as repo:
                assert ia.size == repo.size, f"{id_}: el PNG commiteado quedó viejo"
                if exacto:
                    assert ia.tobytes() == repo.tobytes(), f"{id_}: el PNG commiteado quedó viejo"
                else:
                    total, total_repo = _alfa_total(ia), _alfa_total(repo)
                    assert abs(total - total_repo) <= 0.01 * total_repo, f"{id_}: el alfa total cambió más de 1 %"


def test_por_id_solo_acepta_ids_del_manifiesto():
    assert stickers.por_id("flecha_curva")["categoria"] == "flechas"
    assert stickers.por_id("estrella")["id"] == "estrella"
    for malo in ("../x", "Flecha", "nope", "", "flecha curva", "x" * 41, "../../etc/passwd", None, 3):
        assert stickers.por_id(malo) is None
    with pytest.raises(KeyError):
        stickers.ruta("../x")
