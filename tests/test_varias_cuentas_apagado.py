"""Lanzar en varias cuentas de Meta, APAGADO (decisión del 2026-10-16): mientras el reparto del tope entre la web y el
worker no esté en un solo carril, ninguna cuenta aparte de la de `meta.json` se ofrece ni se acepta."""
import pytest

from tests.test_varias_cuentas_meta import DEF, DINAMARCA, FINLANDIA, SUECIA, _sembrar


@pytest.fixture(autouse=True)
def _apagado(monkeypatch):
    monkeypatch.delenv("CREATV_VARIAS_CUENTAS", raising=False)


def test_apagado_no_ofrece_ni_acepta_otra_cuenta(base_temporal, monkeypatch):
    import cuentas_lanzamiento as cl
    import meta_conexion
    monkeypatch.setattr(meta_conexion, "cargar", lambda c: {"moneda": "SEK", "ad_account_id": DEF})
    monkeypatch.setattr(meta_conexion, "cuentas_de_lanzamiento", lambda: {DEF: "acme"})
    _sembrar(((SUECIA, "HappyFlops Sweden", "SE", "SEK", True), (FINLANDIA, "HappyFlops Finland", "FI", "SEK", True),
              (DINAMARCA, "HappyFlops Denmark", "DK", "DKK", True)))
    assert not cl.activo()
    assert cl.disponibles("acme", "SEK") == []
    assert cl.validar("acme", "SEK", {"NO": DEF, "SE": ""}) == {}          # la de siempre sigue funcionando
    with pytest.raises(ValueError):
        cl.validar("acme", "SEK", {"SE": SUECIA})


def test_se_prende_solo_con_un_uno(monkeypatch):
    import cuentas_lanzamiento as cl
    for valor, esperado in (("1", True), ("0", False), ("si", False), ("", False)):
        monkeypatch.setenv("CREATV_VARIAS_CUENTAS", valor)
        assert cl.activo() is esperado
