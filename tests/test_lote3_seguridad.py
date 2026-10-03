import pytest
import cola


@pytest.mark.parametrize('texto', [
    'access_token: valor_ficticio',  # llave-de-prueba
    '{"access_token":"valor_ficticio","ok":1}',  # llave-de-prueba
    "{'upload_token': 'valor_ficticio'}",  # llave-de-prueba
    'TOKEN = valor_ficticio&ok=1',  # llave-de-prueba
])
def test_redacta_formatos_de_error(texto):
    assert 'valor_ficticio' not in cola.sin_token(texto)
    assert '***' in cola.sin_token(texto)
