"""Configuración de un video desde el formulario del panel."""
import pytest

import catalogo_productos
import marca
from guiones import config
from guiones.refinador import DatoInvalido
from tests.fixtures_guiones import GUION_CRUDO, TEXTO

ACTIVOS = {("producto", "hf"): {"id": "hf", "nombre": "HappyFlops Original", "descripcion": "EVA slipper",
                                "referencias": ["/x/1.jpg", "/x/2.jpg"]}}


@pytest.fixture(autouse=True)
def _catalogo(monkeypatch):
    monkeypatch.setattr(catalogo_productos, "encontrar", lambda c, pid, categoria=None: ACTIVOS.get((categoria, pid)))
    monkeypatch.setattr(marca, "guia_efectiva", lambda c: "")


def _lectura():
    from guiones import lectura
    return lectura.numerar(GUION_CRUDO, TEXTO)


def _form(**kw):
    f = {"modo": "lipsync", "duracion_objetivo": "80", "formato": "9:16", "palabras_por_segundo": "2.4",
         "hook": "hook_2", "estilo": "ultra-photorealistic", "voz": "",
         "ref_tipo_1": "personaje", "ref_activo_1": "", "ref_desc_1": "the AI podiatrist", "ref_edad_1": "45",
         "ref_vestuario_1": "white coat", "ref_paleta_1": "",
         "ref_tipo_2": "producto", "ref_activo_2": "hf", "ref_desc_2": "",
         "ref_tipo_3": "", "ref_activo_3": "", "ref_desc_3": "algo que no se usa"}
    f.update(kw)
    return f


def test_defecto_usa_la_guia_o_el_estilo_generico(monkeypatch):
    assert config.defecto("acme")["estilo"] == config.ESTILO_DEFECTO
    monkeypatch.setattr(marca, "guia_efectiva", lambda c: "Warm pastel look")
    assert config.defecto("acme")["estilo"] == "Warm pastel look"


def test_desde_formulario_valido():
    cfg = config.desde_formulario("acme", _form(), _lectura())
    assert cfg["duracion_objetivo"] == 80 and cfg["hook"] == "hook_2" and cfg["palabras_por_segundo"] == 2.4
    assert [r["tipo"] for r in cfg["referencias"]] == ["personaje", "producto"]
    assert cfg["referencias"][0]["casting"] == {"edad": "45", "vestuario": "white coat", "paleta": ""}
    assert cfg["referencias"][1] == {"tipo": "producto", "activo_id": "hf", "nombre": "HappyFlops Original",
                                     "descripcion": "EVA slipper", "casting": {}, "fotos": 2}


def test_duracion_vacia_es_guion_completo():
    assert config.desde_formulario("acme", _form(duracion_objetivo=""), _lectura())["duracion_objetivo"] is None


@pytest.mark.parametrize("cambio, mensaje", [
    ({"modo": "otro"}, "modo"),
    ({"duracion_objetivo": "3"}, "duración"),
    ({"formato": "2:1"}, "Formato"),
    ({"palabras_por_segundo": "9"}, "ritmo"),
    ({"hook": "hook_9"}, "hook"),
    ({"ref_tipo_1": "", "ref_tipo_2": ""}, "al menos una referencia"),
    ({"ref_activo_2": "nada"}, "Catálogo"),
    ({"ref_desc_1": ""}, "descripción"),
    ({"estilo": "  "}, "estilo"),
])
def test_desde_formulario_invalido(cambio, mensaje):
    with pytest.raises(DatoInvalido) as e:
        config.desde_formulario("acme", _form(**cambio), _lectura())
    assert mensaje.lower() in str(e.value).lower()


def test_maximo_siete_referencias():
    extra = {}
    for i in range(1, 9):
        extra.update({f"ref_tipo_{i}": "entorno", f"ref_activo_{i}": "", f"ref_desc_{i}": f"room {i}"})
    cfg = config.desde_formulario("acme", _form(**extra), _lectura())
    assert len(cfg["referencias"]) == 7
