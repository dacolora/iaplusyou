"""Imágenes de cada escena de Flow Plus (spec 2026-09-30): pura, sin base ni red."""
import pytest

from guiones import escenas
from guiones.refinador import Conflicto, DatoInvalido
from tests.fixtures_guiones import CONFIG

PRODUCTO = {"tipo": "producto", "activo_id": "hf", "nombre": "HappyFlops Original", "descripcion": "EVA slipper",
            "casting": {}, "fotos": 3}
SALA = {"tipo": "entorno", "activo_id": "sala", "nombre": "Sala", "descripcion": "", "casting": {}, "fotos": 2}
# Image 1 producto (Catálogo) · Image 2 personaje por crear · Image 3 entorno por crear · Image 4 entorno (Catálogo)
CFG = dict(CONFIG, referencias=[PRODUCTO] + CONFIG["referencias"] + [SALA])
CLIPS = [{"indice": 1, "titulo": "A", "duracion": 8, "entornos": [3]},
         {"indice": 2, "titulo": "B", "duracion": 12, "entornos": [4, 9]}]
FOTO = {"material_id": 7, "url": "https://r2/x.jpg", "nombre": "doctor"}


def _video(estado=None, clips=CLIPS, config=CFG):
    return {"config": config, "clips": clips, "extra": {"imagenes_escenas": estado} if estado is not None else {}}


def test_pool_numera_referencias_y_despues_las_extra():
    est = escenas.agregar_extra(escenas.estado(_video()), _video(), dict(FOTO, material_id=8, nombre="calle"))
    pool = escenas.pool(_video(est))
    assert [(x["clave"], x["numero"], x["origen"]) for x in pool] == [
        ("r1", 1, "catalogo"), ("r2", 2, "falta"), ("r3", 3, "falta"), ("r4", 4, "catalogo"), ("x1", 5, "subida")]
    assert pool[0]["imagen"] == {"activo_id": "hf", "categoria": "producto", "nombre": "HappyFlops Original"}
    assert pool[1]["por_crear"] and not pool[0]["por_crear"]
    assert pool[1]["nombre"] == "the AI podiatrist, adult British man (~45)"


def test_sugeridas_como_la_tabla_de_imagenes():
    assert escenas.sugeridas(CLIPS[0], CFG) == ["r1", "r2", "r3"]
    assert escenas.sugeridas(CLIPS[1], CFG) == ["r1", "r2", "r4"]  # el 9 no existe: fuera


def test_por_escena_usa_lo_sugerido_hasta_que_la_persona_elige():
    v = _video()
    filas = escenas.por_escena(v)
    assert [(f["indice"], f["claves"], f["propia"]) for f in filas] == [(1, ["r1", "r2", "r3"], False),
                                                                       (2, ["r1", "r2", "r4"], False)]
    est = escenas.usar(escenas.estado(v), v, 1, "r3", False)
    filas = escenas.por_escena(_video(est))
    assert filas[0]["claves"] == ["r1", "r2"] and filas[0]["propia"]
    assert filas[1]["claves"] == ["r1", "r2", "r4"] and not filas[1]["propia"]


def test_usar_ordena_por_numero_y_es_idempotente():
    v = _video()
    est = escenas.usar(escenas.estado(v), v, 2, "r3", True)
    est = escenas.usar(est, _video(est), 2, "r3", True)
    assert escenas.por_escena(_video(est))[1]["claves"] == ["r1", "r2", "r3", "r4"]


def test_usar_rechaza_lo_que_no_existe():
    v = _video()
    with pytest.raises(DatoInvalido):
        escenas.usar(escenas.estado(v), v, 1, "r9", True)
    with pytest.raises(DatoInvalido):
        escenas.usar(escenas.estado(v), v, 5, "r1", True)
    with pytest.raises(DatoInvalido):
        escenas.usar(escenas.estado(v), v, 1, "x1", True)


def test_volver_a_lo_sugerido():
    v = _video()
    est = escenas.usar(escenas.estado(v), v, 1, "r1", False)
    est = escenas.sugeridas_de_nuevo(est, 1)
    assert not escenas.por_escena(_video(est))[0]["propia"]


def test_subir_la_imagen_de_una_referencia_por_crear():
    v = _video()
    est = escenas.poner_ref(escenas.estado(v), v, 2, FOTO)
    pool = escenas.pool(_video(est))
    assert pool[1]["origen"] == "subida" and pool[1]["imagen"]["url"] == "https://r2/x.jpg"
    with pytest.raises(Conflicto):
        escenas.poner_ref(est, v, 1, FOTO)  # la del Catálogo ya tiene su foto
    with pytest.raises(DatoInvalido):
        escenas.poner_ref(est, v, 9, FOTO)
    est = escenas.quitar(est, _video(est), "r2")
    assert escenas.pool(_video(est))[1]["origen"] == "falta"


def test_extra_para_una_escena_y_sin_duplicados():
    v = _video()
    est = escenas.agregar_extra(escenas.estado(v), v, FOTO, escena=2)
    assert escenas.por_escena(_video(est))[1]["claves"] == ["r1", "r2", "r4", "x1"]
    assert not escenas.por_escena(_video(est))[0]["propia"]  # la escena 1 no se toca
    otra = escenas.agregar_extra(est, _video(est), dict(FOTO, nombre="otra vez"), escena=1)
    assert len(otra["extra"]) == 1  # mismo material: no se duplica
    assert escenas.por_escena(_video(otra))[0]["claves"] == ["r1", "r2", "r3", "x1"]
    cat = escenas.agregar_extra(otra, _video(otra), {"activo_id": "sala", "categoria": "entorno", "nombre": "Sala"})
    cat = escenas.agregar_extra(cat, _video(cat), {"activo_id": "sala", "categoria": "entorno", "nombre": "Sala"})
    assert [x["id"] for x in cat["extra"]] == ["x1", "x2"]


def test_quitar_extra_la_saca_de_todas_las_escenas_y_renumera():
    v = _video()
    est = escenas.agregar_extra(escenas.estado(v), v, FOTO, escena=1)
    est = escenas.agregar_extra(est, _video(est), dict(FOTO, material_id=9), escena=2)
    est = escenas.quitar(est, _video(est), "x1")
    assert escenas.por_escena(_video(est))[0]["claves"] == ["r1", "r2", "r3"]
    assert [(x["clave"], x["numero"]) for x in escenas.pool(_video(est))][-1] == ("x2", 5)
    with pytest.raises(DatoInvalido):
        escenas.quitar(est, _video(est), "x1")


def test_topes():
    v = _video()
    est = escenas.estado(v)
    for n in range(escenas.MAX_EXTRA):
        est = escenas.agregar_extra(est, _video(est), dict(FOTO, material_id=100 + n))
    with pytest.raises(Conflicto):
        escenas.agregar_extra(est, _video(est), dict(FOTO, material_id=999))


def test_estado_ignora_basura():
    v = _video({"refs": {"2": {"url": "javascript:alert(1)"}, "x": "y"}, "extra": "nada", "escenas": {"1": "r1"}})
    est = escenas.estado(v)
    assert est == {"refs": {}, "extra": [], "escenas": {}}


def test_heredar_en_una_version_nueva():
    v = _video()
    est = escenas.poner_ref(escenas.estado(v), v, 2, FOTO)
    est = escenas.poner_ref(est, _video(est), 3, dict(FOTO, material_id=8))
    est = escenas.agregar_extra(est, _video(est), dict(FOTO, material_id=9), escena=1)
    otra_sala = [PRODUCTO, CONFIG["referencias"][0], dict(CONFIG["referencias"][1], descripcion="a street"), SALA]
    h = escenas.heredar(est, CFG, dict(CFG, referencias=otra_sala))
    assert list(h["refs"]) == ["2"]           # el entorno cambió de descripción: su imagen no sirve
    assert [x["id"] for x in h["extra"]] == ["x1"] and h["escenas"] == {}  # los clips cambian


def test_heredar_lo_elegido_cuando_los_clips_no_cambian():
    v = _video()
    est = escenas.usar(escenas.estado(v), v, 1, "r1", False)
    assert escenas.heredar(est, CFG, CFG, mismos_clips=True)["escenas"] == {"1": ["r2", "r3"]}
    assert escenas.heredar(est, CFG, dict(CFG, formato="1:1"), mismos_clips=True)["escenas"] == {}


def test_texto_por_clip_para_los_documentos():
    v = _video()
    est = escenas.poner_ref(escenas.estado(v), v, 2, FOTO)
    txt = escenas.texto_por_clip(_video(est), lambda img: img.get("url"))
    assert txt[1] == ["Image 1 · HappyFlops Original",
                      "Image 2 · the AI podiatrist, adult British man (~45) — https://r2/x.jpg",
                      "Image 3 · modern bright podiatry clinic — falta la imagen"]
    assert escenas.refs_con_imagen(_video(est)) == {2}
