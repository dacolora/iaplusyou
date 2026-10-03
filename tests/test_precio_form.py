"""PND-005: precios escritos con miles y decimales, sin red."""
import pytest


@pytest.mark.parametrize("texto,esperado", [
    ("89.900", 89900), ("1.234.567", 1234567), ("89.900,50", 89900.5),
    ("89,900.50", 89900.5), ("89,90", 89.9), ("89.90", 89.9),
    ("89900", 89900), ("", None), ("precio", None), ("nan", None), ("inf", None),
])
def test_precio_form_conserva_miles(texto, esperado):
    import dashboard
    assert dashboard._precio_form(texto) == esperado
