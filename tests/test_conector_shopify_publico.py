"""Conector `shopify_publico` (spec 2026-09-28 §6): catálogo público de una
tienda Shopify sin llaves. HTTP simulado como en test_conectores_tiendas."""
import json
import os

import pytest
import requests

import conectores
from conectores import ErrorConector, base
from conectores import _http

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture(nombre):
    with open(os.path.join(FIXTURES, nombre), encoding="utf-8") as f:
        return json.load(f)


def test_conector_base_tiene_fuente_none_y_tipos_conectables():
    assert base.Conector.fuente is None
    assert conectores.TIPOS_CONECTABLES == ("shopify_publico",) + conectores.TIPOS_API
    assert "shopify_publico" not in conectores.TIPOS_API


def test_normalizar_variante():
    v = base.normalizar_variante({"id": "Sand Mini", "nombre": " Sand Mini ", "fuente_id": 123,
                                  "url_compra": "https://t/p?variant=123",
                                  "fotos": ["https://c/a.png", "https://c/a.png", "ftp://no", "https://c/b.png"],
                                  "disponible": 0})
    assert v == {"id": "sand-mini", "nombre": "Sand Mini", "fuente_id": "123", "url_compra": "https://t/p?variant=123",
                 "fotos": ["https://c/a.png", "https://c/b.png"], "disponible": False}
    assert base.normalizar_variante({"nombre": "Rojo"})["id"] == "rojo"
    assert base.normalizar_variante({"nombre": "Rojo"})["disponible"] is True
    with pytest.raises(ErrorConector):
        base.normalizar_variante({"nombre": "  "})
