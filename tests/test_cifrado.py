import pytest


def test_cifra_y_descifra(monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "clave-de-prueba-larga-1234567890")
    import cifrado
    t = cifrado.cifrar('{"token": "abc"}')
    assert t != '{"token": "abc"}' and "abc" not in t
    assert cifrado.descifrar(t) == '{"token": "abc"}'
    assert cifrado.disponible()


def test_sin_clave(monkeypatch):
    monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)
    import cifrado
    assert cifrado.disponible() is False
    with pytest.raises(cifrado.ErrorCifrado):
        cifrado.cifrar("x")


def test_clave_distinta_no_descifra(monkeypatch):
    import cifrado
    monkeypatch.setenv("FLASK_SECRET_KEY", "a" * 32)
    t = cifrado.cifrar("hola")
    monkeypatch.setenv("FLASK_SECRET_KEY", "b" * 32)
    with pytest.raises(cifrado.ErrorCifrado):
        cifrado.descifrar(t)


def test_token_corrupto_o_no_ascii(monkeypatch):
    import cifrado
    monkeypatch.setenv("FLASK_SECRET_KEY", "a" * 32)
    for malo in ("ñandú", "basura", ""):
        with pytest.raises(cifrado.ErrorCifrado):
            cifrado.descifrar(malo)
