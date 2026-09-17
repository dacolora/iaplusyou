"""Chequeo del Pixel de Meta: meta_ads/pixel.listar_pixels (submódulo) y
meta_conexion.estado_pixel (estados, caché e invalidación). Sin red:
meta_ads.auth.llamar y meta_conexion.estado van parcheados."""
from datetime import datetime, timedelta, timezone

import pytest


def _hace(dias, horas=0):
    return (datetime.now(timezone.utc) - timedelta(days=dias, hours=horas)).strftime("%Y-%m-%dT%H:%M:%S+0000")


@pytest.fixture()
def conectado(monkeypatch):
    """Meta 'conectado' con credenciales falsas; `respuesta` es lo que devuelve
    Graph en act_1/adspixels (o una excepción que lanzar). Devuelve la lista
    de llamadas hechas a auth.llamar."""
    import meta_conexion
    from meta_ads import auth
    meta_conexion._cache_pixel.clear()
    monkeypatch.setattr(meta_conexion, "estado", lambda c: {"estado": "conectado"})
    monkeypatch.setattr(meta_conexion, "credenciales_ads",
                        lambda c: {"token": "tok_secreto", "ad_account_id": "act_1", "page_id": "p", "ig_user_id": None})
    llamadas = []
    estado = {"respuesta": {"data": []}}

    def llamar(metodo, edge, payload=None, params=None, dry_run=False):
        llamadas.append((metodo, edge, dict(params or {})))
        assert auth._CREDENCIALES["token"] == "tok_secreto"   # configurar() corrió antes
        if isinstance(estado["respuesta"], Exception):
            raise estado["respuesta"]
        return estado["respuesta"]
    monkeypatch.setattr(auth, "llamar", llamar)
    yield {"llamadas": llamadas, "estado": estado}
    meta_conexion._cache_pixel.clear()


def test_listar_pixels_llama_al_edge_correcto(conectado):
    from meta_ads import auth, pixel
    conectado["estado"]["respuesta"] = {"data": [{"id": "1", "name": "Px", "last_fired_time": "2026-09-15T10:00:00+0000"},
                                                 {"id": "2", "name": "Viejo"}]}
    auth.configurar("tok_secreto", "act_1", "p")
    try:
        lista = pixel.listar_pixels()
    finally:
        auth.limpiar()
    assert conectado["llamadas"] == [("GET", "act_1/adspixels", {"fields": "id,name,last_fired_time"})]
    assert lista == [{"id": "1", "name": "Px", "last_fired_time": "2026-09-15T10:00:00+0000"},
                     {"id": "2", "name": "Viejo", "last_fired_time": None}]


def test_estado_pixel_ok_elige_el_mas_reciente(conectado):
    import meta_conexion
    from meta_ads import auth
    reciente = _hace(1)
    conectado["estado"]["respuesta"] = {"data": [
        {"id": "1", "name": "Viejo", "last_fired_time": _hace(30)},
        {"id": "2", "name": "Nunca"},
        {"id": "3", "name": "Vivo", "last_fired_time": reciente},
    ]}
    r = meta_conexion.estado_pixel("acme")
    assert r["estado"] == "ok" and r["pixel_id"] == "3" and r["nombre"] == "Vivo" and r["ultimo_disparo"] == reciente
    assert auth._CREDENCIALES["token"] is None   # limpiar() en el finally


def test_estado_pixel_sin_datos_si_no_dispara_hace_7_dias(conectado):
    import meta_conexion
    conectado["estado"]["respuesta"] = {"data": [{"id": "1", "name": "Px", "last_fired_time": _hace(8)}]}
    r = meta_conexion.estado_pixel("acme")
    assert r["estado"] == "sin_datos" and r["pixel_id"] == "1" and "7 días" in r["detalle"]
    meta_conexion.invalidar_pixel("acme")
    conectado["estado"]["respuesta"] = {"data": [{"id": "1", "name": "Px", "last_fired_time": _hace(6, 23)}]}
    assert meta_conexion.estado_pixel("acme")["estado"] == "ok"


def test_estado_pixel_sin_datos_si_nunca_disparo(conectado):
    import meta_conexion
    conectado["estado"]["respuesta"] = {"data": [{"id": "1", "name": "Px"}]}
    r = meta_conexion.estado_pixel("acme")
    assert r["estado"] == "sin_datos" and r["pixel_id"] == "1" and r["ultimo_disparo"] is None
    assert "nunca" in r["detalle"]


def test_estado_pixel_sin_pixel(conectado):
    import meta_conexion
    r = meta_conexion.estado_pixel("acme")
    assert r["estado"] == "sin_pixel" and r["pixel_id"] is None


def test_estado_pixel_sin_conexion_no_llama_a_meta(conectado, monkeypatch):
    import meta_conexion
    monkeypatch.setattr(meta_conexion, "estado", lambda c: {"estado": "sin_conectar"})
    r = meta_conexion.estado_pixel("acme")
    assert r["estado"] == "sin_conexion" and conectado["llamadas"] == []
    monkeypatch.setattr(meta_conexion, "estado", lambda c: {"estado": "roto"})
    meta_conexion.invalidar_pixel("acme")
    assert meta_conexion.estado_pixel("acme")["estado"] == "sin_conexion" and conectado["llamadas"] == []


def test_estado_pixel_error_sin_token(conectado):
    import meta_conexion
    from meta_ads import auth
    conectado["estado"]["respuesta"] = RuntimeError("Meta Ads (act_1/adspixels) respondió 400: access_token=tok_secreto caducó")
    r = meta_conexion.estado_pixel("acme")
    assert r["estado"] == "error" and "tok_secreto" not in r["detalle"] and "respondió 400" in r["detalle"]
    assert auth._CREDENCIALES["token"] is None


def test_estado_pixel_cachea_10_min_e_invalida(conectado, monkeypatch):
    import meta_conexion
    conectado["estado"]["respuesta"] = {"data": [{"id": "1", "name": "Px", "last_fired_time": _hace(0, 1)}]}
    assert meta_conexion.estado_pixel("acme")["estado"] == "ok"
    conectado["estado"]["respuesta"] = {"data": []}
    assert meta_conexion.estado_pixel("acme")["estado"] == "ok"        # cacheado
    assert len(conectado["llamadas"]) == 1
    assert meta_conexion.estado_pixel("otro")["estado"] == "sin_pixel"  # caché por cliente
    assert len(conectado["llamadas"]) == 2
    meta_conexion.invalidar_pixel("acme")
    assert meta_conexion.estado_pixel("acme")["estado"] == "sin_pixel"
    assert len(conectado["llamadas"]) == 3
    # vencido el TTL, vuelve a preguntar
    conectado["estado"]["respuesta"] = {"data": [{"id": "1", "name": "Px", "last_fired_time": _hace(0, 1)}]}
    t0 = meta_conexion._cache_pixel["acme"][0]
    monkeypatch.setattr(meta_conexion.time, "time", lambda: t0 + meta_conexion._TTL_ESTADO_SEG + 1)
    assert meta_conexion.estado_pixel("acme")["estado"] == "ok"
    assert len(conectado["llamadas"]) == 4


def test_guardar_y_borrar_conexion_tiran_la_cache_del_pixel(conectado, monkeypatch, tmp_path):
    import meta_conexion
    monkeypatch.setattr(meta_conexion, "BASE_DIR", str(tmp_path))
    conectado["estado"]["respuesta"] = {"data": []}
    meta_conexion.estado_pixel("acme")
    assert "acme" in meta_conexion._cache_pixel
    meta_conexion.guardar("acme", {"token": "x"})
    assert "acme" not in meta_conexion._cache_pixel
    meta_conexion.estado_pixel("acme")
    meta_conexion.borrar("acme")
    assert "acme" not in meta_conexion._cache_pixel


def test_parsear_fecha_meta_formatos():
    import meta_conexion
    assert meta_conexion._parsear_fecha_meta("2026-09-15T10:00:00+0000").tzinfo is not None
    assert meta_conexion._parsear_fecha_meta("2026-09-15T10:00:00+00:00").year == 2026
    assert meta_conexion._parsear_fecha_meta("2026-09-15T10:00:00").tzinfo is not None
    assert meta_conexion._parsear_fecha_meta("ayer") is None
    assert meta_conexion._parsear_fecha_meta(None) is None


def test_estado_pixel_solo_cache_no_llama_a_meta(conectado):
    """F6: el POST de crear experimento solo mira el caché — sin nada
    vigente devuelve None y no toca Graph; con caché, lo devuelve."""
    import meta_conexion
    conectado["estado"]["respuesta"] = {"data": [{"id": "1", "name": "Px", "last_fired_time": _hace(0, 1)}]}
    assert meta_conexion.estado_pixel("acme", solo_cache=True) is None
    assert conectado["llamadas"] == []
    assert meta_conexion.estado_pixel("acme")["estado"] == "ok"
    assert meta_conexion.estado_pixel("acme", solo_cache=True)["estado"] == "ok"
    assert len(conectado["llamadas"]) == 1
