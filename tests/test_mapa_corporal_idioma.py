"""Mapa corporal y reglas de categoría en el idioma del proyecto (spec
2026-09-26 §B4): la instrucción que va a los modelos y la que se muestra
bajo cada producto."""
import os

import catalogo_productos as cp
import idiomas
import mapa_corporal as mc
from tests.i18n_util import _con_marca


def test_describir_en_espanol_igual_que_siempre():
    t = mc.describir(["pies"])
    assert t.startswith("UBICACIÓN EXACTA DEL PRODUCTO: va sobre los pies. En proporción del cuerpo, ocupa desde")


def test_describir_en_ingles():
    t = mc.describir(["cadera", "muslo"], idioma="en")
    assert t.startswith("EXACT PRODUCT PLACEMENT: it goes on the hips and groin and the thighs.")
    assert "on an 8-head body" in t and " It does NOT touch " in t
    assert not _con_marca(t), t
    assert mc.describir([], idioma="en") is None


def test_regla_de_categoria():
    assert cp.regla_categoria("producto") == cp.CATEGORIAS["producto"]["regla"]
    assert cp.regla_categoria("producto", "en").startswith("Reproduce it identical to its reference")
    assert all(not _con_marca(cp.regla_categoria(c, "en")) for c in cp.CATEGORIAS)


def test_listar_arma_regla_y_mapa_en_el_idioma_del_proyecto(tmp_path, monkeypatch):
    import proyectos
    monkeypatch.setattr(cp, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    pid = cp.crear("acme", "Blue Sandal", zonas=["pies"])
    with open(os.path.join(cp.carpeta_de("acme", pid), "01.jpg"), "wb") as f:
        f.write(b"x")
    es = cp.encontrar("acme", pid, "producto")
    assert es["regla"].startswith("Reprodúcelo idéntico") and es["mapa_texto"].startswith("UBICACIÓN EXACTA")
    idiomas.guardar_de_proyecto("acme", "en")
    en = cp.encontrar("acme", pid, "producto")
    assert en["regla"].startswith("Reproduce it identical") and en["mapa_texto"].startswith("EXACT PRODUCT PLACEMENT")
