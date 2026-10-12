"""Medios de las tarjetas (spec tarjetas §8.1): qué se incrusta o se baja, y la descarga con tope."""
import os

import pytest
import requests

import triple_whale
from conectores import url as conector_url
from tests.test_conectores_archivo_url import _Respuesta, _fingir


@pytest.fixture(autouse=True)
def _dns_publica(monkeypatch):
    monkeypatch.setattr(conector_url.socket, "getaddrinfo", lambda host, *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))])


def _restos(tmp_path):
    """Lo que quedó en tmp_path, sin el usuarios_prueba.json que siembra conftest (autouse)."""
    return sorted(n for n in os.listdir(tmp_path) if n != "usuarios_prueba.json")


class _RespuestaPorTrozos:
    """Respuesta que entrega `trozos` uno a uno, cuenta cuántos se pidieron y, si se le da `corte`, lanza esa
    excepción en lugar de seguir después del último trozo."""

    def __init__(self, trozos, corte=None, headers=None):
        self._trozos = list(trozos)
        self._corte = corte
        self.consumidos = 0
        self.status_code = 200
        self.headers = headers or {"Content-Type": "video/mp4"}

    def iter_content(self, chunk_size=65536):
        for trozo in self._trozos:
            self.consumidos += 1
            yield trozo
        if self._corte is not None:
            raise self._corte

    def close(self):
        pass


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
    assert _restos(tmp_path) == []


def test_descargar_archivo_no_sale_a_una_red_interna(monkeypatch, tmp_path):
    monkeypatch.setattr(conector_url.socket, "getaddrinfo", lambda host, *a, **k: [(2, 1, 6, "", ("10.0.0.5", 0))])
    monkeypatch.setattr(conector_url.requests, "get", lambda *a, **k: pytest.fail("no debió pedir nada"))
    with pytest.raises(conector_url.ErrorConector):
        conector_url.descargar_archivo("https://files.triplewhale.com/v.mp4", str(tmp_path / "v.mp4"))


def test_descargar_archivo_se_corta_a_mitad_de_la_descarga_y_no_deja_nada(monkeypatch, tmp_path):
    resp = _RespuestaPorTrozos([b"\x00" * 1000] * 3, corte=requests.exceptions.ChunkedEncodingError("se cayó"))
    _fingir(monkeypatch, resp)
    ruta = tmp_path / "v.mp4"
    with pytest.raises(conector_url.ErrorConector) as ei:
        conector_url.descargar_archivo("https://files.triplewhale.com/v.mp4", str(ruta))
    assert "ChunkedEncodingError" in ei.value.usuario
    assert resp.consumidos == 3
    assert _restos(tmp_path) == []


def test_descargar_archivo_deja_de_leer_justo_al_pasar_el_tope(monkeypatch, tmp_path):
    resp = _RespuestaPorTrozos([b"\x00" * 1000] * 10)
    _fingir(monkeypatch, resp)
    with pytest.raises(conector_url.ErrorConector):
        conector_url.descargar_archivo("https://files.triplewhale.com/v.mp4", str(tmp_path / "v.mp4"), max_bytes=2500)
    assert resp.consumidos <= 3, "siguió leyendo después de pasar el tope"
    assert _restos(tmp_path) == []


def test_descargar_archivo_fallido_no_toca_el_archivo_que_ya_estaba(monkeypatch, tmp_path):
    ruta = tmp_path / "v.mp4"
    ruta.write_bytes(b"BUENO")
    for resp in (_RespuestaPorTrozos([b"\x00" * 1000] * 3, corte=requests.exceptions.ConnectionError("x")),
                 _RespuestaPorTrozos([b"\x00" * 1000] * 3),                                  # pasa el tope
                 _RespuestaPorTrozos([b"<html>"], headers={"Content-Type": "text/html"})):    # otro tipo
        _fingir(monkeypatch, resp)
        with pytest.raises(conector_url.ErrorConector):
            conector_url.descargar_archivo("https://files.triplewhale.com/v.mp4", str(ruta), max_bytes=2500)
        assert ruta.read_bytes() == b"BUENO"
        assert _restos(tmp_path) == ["v.mp4"]


def test_descargar_archivo_exitoso_reemplaza_el_anterior_sin_dejar_parcial(monkeypatch, tmp_path):
    ruta = tmp_path / "v.mp4"
    ruta.write_bytes(b"VIEJO")
    _fingir(monkeypatch, _RespuestaPorTrozos([b"N" * 10, b"N" * 5]))
    assert conector_url.descargar_archivo("https://files.triplewhale.com/v.mp4", str(ruta)) == 15
    assert ruta.read_bytes() == b"N" * 15
    assert _restos(tmp_path) == ["v.mp4"]


@pytest.mark.parametrize("corte", [KeyboardInterrupt, SystemExit])
def test_descargar_archivo_interrumpido_borra_el_parcial_y_deja_pasar_la_interrupcion(monkeypatch, tmp_path, corte):
    _fingir(monkeypatch, _RespuestaPorTrozos([b"\x00" * 1000] * 2, corte=corte()))
    with pytest.raises(corte):
        conector_url.descargar_archivo("https://files.triplewhale.com/v.mp4", str(tmp_path / "v.mp4"))
    assert _restos(tmp_path) == []


def test_enlace_permitido_ata_el_enlace_a_la_plataforma_del_canal():
    assert triple_whale.enlace_permitido("https://www.tiktok.com/embed/v1", "tiktok-ads")
    assert triple_whale.enlace_permitido("https://www.instagram.com/reel/abc/", "facebook-ads")
    assert triple_whale.enlace_permitido("https://fb.watch/abc/", "facebook-ads")
    assert triple_whale.enlace_permitido("https://www.youtube.com/watch?v=x", "google-ads")
    assert triple_whale.enlace_permitido("https://www.snapchat.com/spotlight/x", "snapchat-ads")
    assert triple_whale.enlace_permitido("https://www.pinterest.com/pin/1/", "pinterest-ads")
    # un enlace de otra plataforma, o de un canal que no conocemos, no se pinta
    assert not triple_whale.enlace_permitido("https://www.tiktok.com/embed/v1", "facebook-ads")
    assert not triple_whale.enlace_permitido("https://www.facebook.com/plugins/video.php", "tiktok-ads")
    assert not triple_whale.enlace_permitido("https://www.tiktok.com/embed/v1", "bing")
    assert not triple_whale.enlace_permitido("https://www.tiktok.com/embed/v1", "")


@pytest.mark.parametrize("malo", [
    "https://l.facebook.com/l.php?u=https%3A%2F%2Fevil.test",   # redirector de Facebook
    "https://lm.facebook.com/l.php?u=x",
    "https://l.facebook.com/otra-ruta?u=x",                       # el host solo basta
    "https://lm.facebook.com/x",
    "https://www.facebook.com/l.php?u=x",
    "https://www.youtube.com/redirect?q=https%3A%2F%2Fevil.test",   # redirector de YouTube
    "https://eviltiktok.com/x",                                     # sufijo sin punto
    "https://user@tiktok.com/x",
    "https://user:pw@www.tiktok.com/x",
    "https://www.tiktok.com:1/x",
    "https://www.tiktok.com:8443/x",
    "ftp://www.tiktok.com/x",
    "https://www.tiktok.com.evil.test/x",
    # Revisión final B8: los otros redirectores de las plataformas, y las formas de escribir la misma ruta.
    "https://www.tiktok.com/link/v2?target=https%3A%2F%2Fevil.test",          # TikTok
    "https://www.pinterest.com/offsite/?url=https%3A%2F%2Fevil.test",         # Pinterest
    "https://www.facebook.com/flx/warn/?u=https%3A%2F%2Fevil.test",           # Facebook
    "https://www.facebook.com//l.php?u=x",                                    # doble barra
    "https://www.tiktok.com///link/v2?target=x",
    "https://www.facebook.com/%6C.php?u=x",                                   # %-codificada
    "https://www.facebook.com/FLX/Warn/?u=x",
    # Última vuelta de B8: segmentos «.» y «..» (el servidor los resuelve antes de enrutar)
    "https://www.facebook.com/./l.php?u=x",
    "https://www.facebook.com/a/../l.php?u=x",
    "https://www.facebook.com/%2e/l.php?u=x",
    "https://www.facebook.com/%2E%2E/l.php?u=x",
    "https://www.facebook.com/a/%2e%2e/l.php?u=x",
    "https://www.facebook.com/a%2f..%2fl.php?u=x",
    "https://www.facebook.com/a/b/../../l.php?u=x",
    "https://www.facebook.com/%252e/l.php?u=x",                               # doblemente %-codificada
    "https://www.facebook.com/.//l.php?u=x",
    "https://www.facebook.com/\\l.php?u=x",                                    # «\» es «/» para un navegador
    "https://www.tiktok.com/./link/v2?target=x",
    "https://www.tiktok.com/a/../link/v2?target=x",
    "https://www.pinterest.com/%2e/offsite/?url=x",
    "https://www.facebook.com/a/./../flx/./warn/?u=x",
])
def test_enlace_permitido_rechaza_redirectores_y_formas_raras(malo):
    assert not triple_whale.enlace_permitido(malo), malo
    for canal in ("tiktok-ads", "facebook-ads", "google-ads", None):
        assert not triple_whale.enlace_permitido(malo, canal), (malo, canal)


def test_enlace_permitido_acepta_el_puerto_443():
    assert triple_whale.enlace_permitido("https://www.tiktok.com:443/embed/v1", "tiktok-ads")


def test_descargar_archivo_tiene_tope_de_tiempo_total_y_borra_el_parcial(monkeypatch, tmp_path):
    """Revisión final B5: `timeout` es por lectura; un servidor que suelta un trozo cada pocos segundos no puede
    tener al worker bajando sin fin. Pasado `tiempo_max` desde antes de conectar, se corta y no queda ningún `.part`
    (y un archivo bueno que ya estaba sigue intacto)."""
    reloj = iter(range(0, 10_000, 50))                       # cada consulta del reloj avanza 50 s
    monkeypatch.setattr(conector_url.time, "monotonic", lambda: next(reloj))
    resp = _RespuestaPorTrozos([b"\x00" * 1000] * 10)
    _fingir(monkeypatch, resp)
    ruta = tmp_path / "v.mp4"
    ruta.write_bytes(b"BUENO")
    with pytest.raises(conector_url.ErrorConector) as ei:
        conector_url.descargar_archivo("https://files.triplewhale.com/v.mp4", str(ruta), tiempo_max=120)
    assert "tardó demasiado" in ei.value.usuario
    assert resp.consumidos == 3, "siguió leyendo después del tope de tiempo"
    assert ruta.read_bytes() == b"BUENO" and _restos(tmp_path) == ["v.mp4"]
    assert conector_url.TIEMPO_MAX_ARCHIVO == 120         # el tope por defecto de quien no lo pasa


def test_descargar_archivo_dentro_del_tiempo_termina(monkeypatch, tmp_path):
    monkeypatch.setattr(conector_url.time, "monotonic", lambda: 0)
    _fingir(monkeypatch, _RespuestaPorTrozos([b"N" * 10] * 3))
    assert conector_url.descargar_archivo("https://files.triplewhale.com/v.mp4", str(tmp_path / "v.mp4")) == 30


class _VigiaAlInstante:
    """Reemplazo de `threading.Timer`: dispara el corte del vigía apenas arranca (sin esperar `tiempo_max`), así que
    `vencio` ya está puesto cuando empieza la lectura. `dispara=False` lo deja sin disparar (el control)."""

    def __init__(self, dispara=True):
        self.dispara = dispara

    def __call__(self, intervalo, funcion):
        self._funcion = funcion
        self.daemon = False
        return self

    def start(self):
        if self.dispara:
            self._funcion()

    def cancel(self):
        pass


def _vigia(monkeypatch, dispara=True):
    """Sustituye el vigía de `descargar_archivo` por uno que salta de inmediato (o nunca): sin esperas reales."""
    monkeypatch.setattr(conector_url.threading, "Timer", _VigiaAlInstante(dispara))


@pytest.mark.parametrize("error", [
    AttributeError("'NoneType' object has no attribute 'close'"),
    AttributeError("'NoneType' object has no attribute 'readline'"),
    ValueError("I/O operation on closed file"),
    RuntimeError("cualquier otra cosa"),
])
def test_descargar_archivo_con_el_vigia_disparado_todo_error_de_la_lectura_es_el_corte_por_tiempo(
        monkeypatch, tmp_path, error):
    """Revisión de las tarjetas (2026-10-08): al cortar el socket por debajo, urllib3/http.client pueden dejar
    escapar un `AttributeError` en vez de un error de red. Con `vencio` puesto es el corte por tiempo: un
    `ErrorConector` (nunca la excepción cruda), sin `.part`, y el archivo bueno que ya estaba sigue intacto."""
    _vigia(monkeypatch)
    resp = _RespuestaPorTrozos([b"\x00" * 1000] * 2, corte=error)
    _fingir(monkeypatch, resp)
    ruta = tmp_path / "v.mp4"
    ruta.write_bytes(b"BUENO")
    with pytest.raises(conector_url.ErrorConector) as ei:
        conector_url.descargar_archivo("https://files.triplewhale.com/v.mp4", str(ruta))
    assert "tardó demasiado" in ei.value.usuario
    assert resp.consumidos == 2                       # sí llegó a leer: el error salió de la lectura
    assert ruta.read_bytes() == b"BUENO" and _restos(tmp_path) == ["v.mp4"]


def test_descargar_archivo_un_error_que_no_es_del_corte_sigue_siendo_ese_error(monkeypatch, tmp_path):
    """El control: sin el vigía disparado, un `AttributeError` es un fallo nuestro y no se disfraza de timeout
    (y de todos modos no deja `.part`)."""
    _vigia(monkeypatch, dispara=False)
    _fingir(monkeypatch, _RespuestaPorTrozos([b"\x00" * 1000], corte=AttributeError("de verdad")))
    with pytest.raises(AttributeError):
        conector_url.descargar_archivo("https://files.triplewhale.com/v.mp4", str(tmp_path / "v.mp4"))
    assert _restos(tmp_path) == []


def test_descargar_archivo_un_error_de_red_sin_vigia_sigue_diciendo_que_se_corto(monkeypatch, tmp_path):
    _vigia(monkeypatch, dispara=False)
    _fingir(monkeypatch, _RespuestaPorTrozos([b"\x00" * 10], corte=requests.exceptions.ConnectionError("x")))
    with pytest.raises(conector_url.ErrorConector) as ei:
        conector_url.descargar_archivo("https://files.triplewhale.com/v.mp4", str(tmp_path / "v.mp4"))
    assert "ConnectionError" in ei.value.usuario and "tardó" not in ei.value.usuario


def test_descargar_archivo_el_tope_de_tamano_con_el_vigia_disparado_conserva_su_mensaje(monkeypatch, tmp_path):
    _vigia(monkeypatch)
    _fingir(monkeypatch, _RespuestaPorTrozos([b"\x00" * 1000] * 5))
    with pytest.raises(conector_url.ErrorConector) as ei:
        conector_url.descargar_archivo("https://files.triplewhale.com/v.mp4", str(tmp_path / "v.mp4"), max_bytes=1500)
    assert "pesa demasiado" in ei.value.usuario
    assert _restos(tmp_path) == []


def test_descargar_archivo_que_termina_limpio_pero_con_el_vigia_disparado_es_un_corte_por_tiempo(monkeypatch, tmp_path):
    """La rama de después del ciclo: el vigía cortó la conexión y la lectura terminó «limpia» (EOF), o sea, el
    archivo está truncado. No se entrega como bueno: `ErrorConector`, sin `.part`, el archivo anterior intacto."""
    _vigia(monkeypatch)
    resp = _RespuestaPorTrozos([b"\x00" * 1000] * 3)
    _fingir(monkeypatch, resp)
    ruta = tmp_path / "v.mp4"
    ruta.write_bytes(b"BUENO")
    with pytest.raises(conector_url.ErrorConector) as ei:
        conector_url.descargar_archivo("https://files.triplewhale.com/v.mp4", str(ruta))
    assert "tardó demasiado" in ei.value.usuario
    assert resp.consumidos == 3                       # leyó todo hasta el EOF: salió por la rama de después del ciclo
    assert ruta.read_bytes() == b"BUENO" and _restos(tmp_path) == ["v.mp4"]


def test_enlace_permitido_no_confunde_una_ruta_normal_con_un_redirector():
    assert triple_whale.enlace_permitido("https://www.tiktok.com/@marca/video/1", "tiktok-ads")
    assert triple_whale.enlace_permitido("https://www.pinterest.com/pin/1/", "pinterest-ads")
    assert triple_whale.enlace_permitido("https://www.facebook.com/watch/?v=1", "facebook-ads")
    # la barra del final (arriba, «/pin/1/») y la ruta vacía no son segmentos raros
    assert triple_whale.enlace_permitido("https://www.tiktok.com/", "tiktok-ads")
    assert triple_whale.enlace_permitido("https://www.tiktok.com", "tiktok-ads")


@pytest.mark.parametrize("malo", [
    # Ruling 2026-10-08: ningún enlace de anuncio de verdad lleva segmentos vacíos, «.» ni «..», ni aunque la ruta
    # resuelta no sea un redirector (antes estos tres pasaban; ahora se rechazan).
    "https://www.facebook.com/./watch/?v=1",
    "https://www.facebook.com/a/../watch/?v=1",
    "https://www.tiktok.com/@marca/video/1/../2",
    # `normpath` junta «//» antes de resolver «..» («/link//../v2» -> «/v2»), pero el navegador lo manda a /link/v2
    "https://www.tiktok.com/link//../v2?target=https://evil.test",
    "https://www.tiktok.com/link//../v2",
    "https://www.tiktok.com//link/v2",
    "https://www.tiktok.com/link/./v2",
    "https://www.tiktok.com/a//b",
    "https://www.tiktok.com/%2e%2e/link",
    "https://www.tiktok.com/%2E%2E/link/v2",
    "https://www.tiktok.com/a%2f%2fb",                    # «//» escondido como %2f%2f
    "https://www.tiktok.com/a/%252e%252e/b",              # «..» doblemente %-codificado
    "https://www.tiktok.com/a\\\\b",                          # dos «\» son «//» para el navegador: segmento vacío
    "https://www.tiktok.com/a/\\..\\b",                       # «\..\» es «/../»
    "https://www.tiktok.com/embed//v1",
    "https://www.tiktok.com/embed/v1//",                  # solo se perdona UNA barra al final
    "https://www.tiktok.com//",
    "https://www.tiktok.com/embed/v1/..",
    "https://www.tiktok.com/embed/v1/.",
])
def test_enlace_permitido_rechaza_segmentos_vacios_o_con_puntos(malo):
    assert not triple_whale.enlace_permitido(malo), malo
    assert not triple_whale.enlace_permitido(malo, "tiktok-ads"), malo
