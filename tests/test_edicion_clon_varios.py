"""edicion_clon.documento_varios: varias escenas en orden (cadena de escenas de Flow Plus)."""
from final_edition import documento, edicion_clon


def _clon(mid, ms, audio=True):
    return {"id": mid, "duracion_ms": ms, "extra": {"tiene_audio": audio}}


def test_escenas_contiguas_con_su_sonido():
    doc = edicion_clon.documento_varios([_clon(1, 8000), _clon(2, 12000, audio=False), _clon(3, 5000)], "9:16")
    principal = doc["pistas"][0]["clips"]
    assert [(c["material_id"], c["inicio_ms"], c["duracion_ms"]) for c in principal] == [
        (1, 0, 8000), (2, 8000, 12000), (3, 20000, 5000)]
    sonido = next(p for p in doc["pistas"] if p["id"] == "p_sonido")["clips"]
    assert [(c["material_id"], c["inicio_ms"]) for c in sonido] == [(1, 0), (3, 20000)]
    assert all(c["rol_audio"] == "sonido" for c in sonido)
    documento.validar(doc)  # no lanza


def test_sin_sonido_no_hay_pista_de_sonido():
    doc = edicion_clon.documento_varios([_clon(1, 5000, audio=False)], "9:16")
    assert all(p["id"] != "p_sonido" for p in doc["pistas"])
