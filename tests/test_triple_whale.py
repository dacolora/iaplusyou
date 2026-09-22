"""Tests para Triple Whale API e integración."""
import pytest
import triple_whale
import triple_whale_tiendas
import db
import cifrado


def test_validar_llave_invalida():
    """Una llave falsa debe ser rechazada."""
    assert not triple_whale.validar_llave("fake_key_xyz")


def test_triple_whale_tiendas_conectar_y_obtener(base_temporal, monkeypatch):
    """Conectar TW y verificar que se cifra la llave."""
    monkeypatch.setenv("FLASK_SECRET_KEY", "test_secret_key_12345678")
    monkeypatch.setattr(db, "ahora", lambda: "2026-09-22T00:00:00")
    
    tw_id = triple_whale_tiendas.conectar(
        cliente="test",
        llave_descifrada="tw_1234567890",
        dominio_tienda="test.myshopify.com",
        moneda="USD",
        modelo_atribucion="Triple Attribution",
        ventana_atribucion="lifetime",
        zona_horaria="America/New_York",
    )
    assert tw_id > 0
    
    # Obtener y verificar
    config = triple_whale_tiendas.obtener("test")
    assert config is not None
    assert config["dominio_tienda"] == "test.myshopify.com"
    assert config["moneda"] == "USD"
    assert config["estado"] == "conectada"
    assert config["error"] is None
    
    # Llave se recobra descifrada
    llave = triple_whale_tiendas.obtener_llave("test")
    assert llave == "tw_1234567890"


def test_triple_whale_tiendas_desconectar(base_temporal, monkeypatch):
    """Desconectar borra la configuración."""
    monkeypatch.setenv("FLASK_SECRET_KEY", "test_secret_key_12345678")
    monkeypatch.setattr(db, "ahora", lambda: "2026-09-22T00:00:00")
    
    tw_id = triple_whale_tiendas.conectar(
        cliente="test2", llave_descifrada="tw_test", dominio_tienda="test2.myshopify.com"
    )
    assert tw_id > 0
    
    triple_whale_tiendas.desconectar("test2")
    
    config = triple_whale_tiendas.obtener("test2")
    assert config is None
