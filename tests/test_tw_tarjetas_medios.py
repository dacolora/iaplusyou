"""Medios de las tarjetas (spec tarjetas §8.1): qué se incrusta o se baja, y la descarga con tope."""
import os

import pytest

import triple_whale
from conectores import url as conector_url
from tests.test_conectores_archivo_url import _Respuesta, _fingir


@pytest.fixture(autouse=True)
def _dns_publica(monkeypatch):
    monkeypatch.setattr(conector_url.socket, "getaddrinfo", lambda host, *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))])


def test_medio_permitido(monkeypatch):
    monkeypatch.setenv("R2_PUBLIC_BASE_URL", "https://media.creatv.test")
    assert triple_whale.medio_permitido("https://files.triplewhale.com/videos/facebook-ads/act_1/2.mp4")
    assert triple_whale.medio_permitido("https://media.creatv.test/clientes/acme/x.mp4")
    for malo in ("http://files.triplewhale.com/v.mp4", "https://www.tiktok.com/embed/v1",
                 "https://user:pw@files.triplewhale.com/v.mp4", "https://files.triplewhale.com:8443/v.mp4",
                 "https://files.triplewhale.com.evil.com/v.mp4", "https://xfiles.triplewhale.com/v.mp4",
                 "https://cdn.files.triplewhale.com/v.mp4", "javascript:alert(1)", "", None):
        assert not triple_whale.medio_permitido(malo), malo


def test_enlace_permitido_solo_a_la_plataforma_del_anuncio():
    for bueno in ("https://www.tiktok.com/embed/v10033", "https://www.facebook.com/plugins/video.php?x=1",
                  "https://tiktok.com/@marca/video/1"):
        assert triple_whale.enlace_permitido(bueno), bueno
    for malo in ("https://evil.test/v.mp4", "http://www.tiktok.com/embed/1", "https://tiktok.com.evil.test/x",
                 "javascript:alert(1)", None):
        assert not triple_whale.enlace_permitido(malo), malo


def test_descargar_archivo_escribe_y_devuelve_bytes(monkeypatch, tmp_path):
    _fingir(monkeypatch, _Respuesta(b"\x00" * 1000, headers={"Content-Type": "video/mp4"}))
    ruta = tmp_path / "v.mp4"
    assert conector_url.descargar_archivo("https://files.triplewhale.com/v.mp4", str(ruta)) == 1000
    assert ruta.stat().st_size == 1000


def test_descargar_archivo_corta_al_pasar_el_tope_y_borra(monkeypatch, tmp_path):
    _fingir(monkeypatch, _Respuesta(b"\x00" * 5000, headers={"Content-Type": "video/mp4"}))
    ruta = tmp_path / "v.mp4"
    with pytest.raises(conector_url.ErrorConector):
        conector_url.descargar_archivo("https://files.triplewhale.com/v.mp4", str(ruta), max_bytes=1000)
    assert not os.path.exists(ruta)


def test_descargar_archivo_rechaza_otro_tipo_y_error_http(monkeypatch, tmp_path):
    _fingir(monkeypatch, _Respuesta("<html>", headers={"Content-Type": "text/html"}))
    with pytest.raises(conector_url.ErrorConector):
        conector_url.descargar_archivo("https://files.triplewhale.com/v.mp4", str(tmp_path / "a.mp4"))
    _fingir(monkeypatch, _Respuesta(b"", status=404, headers={"Content-Type": "video/mp4"}))
    with pytest.raises(conector_url.ErrorConector):
        conector_url.descargar_archivo("https://files.triplewhale.com/v.mp4", str(tmp_path / "b.mp4"))
    # tmp_path ya trae el usuarios_prueba.json de conftest: lo que no debe quedar es ningún .mp4
    assert not [n for n in os.listdir(tmp_path) if n.endswith(".mp4")]


def test_descargar_archivo_no_sale_a_una_red_interna(monkeypatch, tmp_path):
    monkeypatch.setattr(conector_url.socket, "getaddrinfo", lambda host, *a, **k: [(2, 1, 6, "", ("10.0.0.5", 0))])
    monkeypatch.setattr(conector_url.requests, "get", lambda *a, **k: pytest.fail("no debió pedir nada"))
    with pytest.raises(conector_url.ErrorConector):
        conector_url.descargar_archivo("https://files.triplewhale.com/v.mp4", str(tmp_path / "v.mp4"))
