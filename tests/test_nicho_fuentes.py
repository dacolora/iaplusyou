from datetime import datetime

import pytest


def test_limpiar_y_hash():
    from nicho.fuentes import base
    assert base.limpiar_texto("  Hola\x00 \n\n mundo\t ya  ") == "Hola mundo ya"
    assert len(base.limpiar_texto("x" * 5000)) == base.MAX_TEXTO
    assert base.hash_texto("Hola   Mundo") == base.hash_texto("hola mundo") and len(base.hash_texto("a")) == 16


def test_normalizar_comentario():
    from nicho.fuentes import base
    c = base.normalizar_comentario({"texto": " La garrafa <b>pesa</b> ", "url": "https://r.com/x", "contexto": "Post: garrafas",
                                    "puntuacion": "12", "fecha": "2026-03-04T10:20:30Z", "extra": {"sub": "sweden"}})
    assert tuple(c) == base.CLAVES_COMENTARIO
    assert c["texto"] == "La garrafa <b>pesa</b>" and c["fuente_id"] == base.hash_texto("La garrafa <b>pesa</b>")
    assert c["url"] == "https://r.com/x" and c["puntuacion"] == 12 and c["fecha"] == "2026-03-04T10:20:30" and c["extra"] == {"sub": "sweden"}
    assert base.normalizar_comentario({"texto": "ab"}) is None
    assert base.normalizar_comentario({"texto": None}) is None
    c2 = base.normalizar_comentario({"fuente_id": " t1_abc ", "texto": "vale", "url": "javascript:x", "puntuacion": "muchos",
                                     "fecha": 1700000000, "extra": "no dict"})
    assert c2["fuente_id"] == "t1_abc" and c2["url"] is None and c2["puntuacion"] is None and c2["extra"] == {}
    assert c2["fecha"] == datetime.fromtimestamp(1700000000).strftime("%Y-%m-%dT%H:%M:%S")
    assert base.normalizar_comentario({"texto": "vale", "fecha": "2026-01-02"})["fecha"] == "2026-01-02T00:00:00"
    assert base.normalizar_comentario({"texto": "vale", "fecha": "ayer"})["fecha"] is None
    assert base.normalizar_comentario({"texto": "vale", "puntuacion": True})["puntuacion"] is None


def test_error_fuente_y_fuente_base():
    from nicho.fuentes import base
    e = base.ErrorFuente("Reddit no aceptó las llaves.")
    assert e.usuario == str(e) == "Reddit no aceptó las llaves."
    f = base.Fuente()
    assert f.probar()["ok"] is True and f.estimar({}) is None
    with pytest.raises(NotImplementedError):
        list(f.recolectar({}))


def test_registro_por_tipo():
    from nicho import fuentes
    assert fuentes.tipos() == ("texto", "csv")
    assert fuentes.por_tipo("texto").tipo == "texto" and fuentes.por_tipo("csv").tipo == "csv"
    with pytest.raises(KeyError):
        fuentes.por_tipo("magia")
    assert fuentes.NOMBRES["apify"].startswith("Amazon")
