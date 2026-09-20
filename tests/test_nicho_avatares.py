import json

import pytest


def _c(i, fuente="texto", puntuacion=None, fecha=None, texto=None, excluido=False):
    return {"id": i, "fuente": fuente, "puntuacion": puntuacion, "fecha": fecha, "excluido": excluido,
            "contexto": None, "texto": texto or f"Comentario {i} sobre la garrafa que pesa y gotea en el estante."}


def test_seleccionar_excluye_ordena_y_alterna_fuentes():
    from nicho import avatares
    lista = [_c(1, "texto", puntuacion=1), _c(2, "texto", puntuacion=9), _c(3, "reddit", puntuacion=5),
             _c(4, "reddit", puntuacion=5, fecha="2026-02-01"), _c(5, "youtube", excluido=True), _c(6, "youtube")]
    sel = avatares.seleccionar(lista)
    assert [c["id"] for c in sel] == [4, 2, 6, 3, 1]      # ronda reddit/texto/youtube; dentro: puntuación desc, fecha desc, id
    assert [c["id"] for c in avatares.seleccionar(lista, max_n=2)] == [4, 2]
    corto = avatares.seleccionar(lista, max_caracteres=len(lista[0]["texto"]) * 2 + 1)
    assert len(corto) == 2
    assert avatares.seleccionar([]) == []


def test_estimar_costo_y_costo_real(monkeypatch):
    from nicho import avatares
    lista = [_c(i, texto="x" * 350) for i in range(1, 21)]           # 20 comentarios × 350 caracteres = 7 000 chars
    e = avatares.estimar_costo(lista, modelo="claude-sonnet-5")
    tokens_texto = int(7000 * avatares.TOKENS_POR_CARACTER)
    assert e["comentarios"] == 20 and e["suficientes"] is True and e["referencia"] is False and e["modelo"] == "claude-sonnet-5"
    assert e["tokens_entrada"] == tokens_texto * 2 + avatares.TOKENS_PROMPT * (1 + avatares.MAX_NUCLEOS)
    assert e["tokens_salida"] == avatares.TOKENS_SALIDA_ESTIMADO_NUCLEOS + avatares.TOKENS_SALIDA_ESTIMADO_SUBS * avatares.MAX_NUCLEOS
    esperado = (e["tokens_entrada"] * 2.0 + e["tokens_salida"] * 10.0) / 1e6
    assert e["usd"] >= esperado and e["usd"] - esperado < 0.01           # redondeado hacia arriba al centavo
    assert avatares.estimar_costo(lista[:5], modelo="claude-sonnet-5")["suficientes"] is False
    raro = avatares.estimar_costo(lista, modelo="claude-desconocido-9")
    assert raro["referencia"] is True and raro["usd"] >= e["usd"]         # precio de referencia = el más caro
    assert avatares.costo_real(1_000_000, 100_000, modelo="claude-sonnet-5") == pytest.approx(3.0)
    monkeypatch.setattr(avatares, "modelo_actual", lambda: "claude-haiku-4-5")
    assert avatares.costo_real(1_000_000, 0) == pytest.approx(1.0) and avatares.estimar_costo(lista)["modelo"] == "claude-haiku-4-5"
