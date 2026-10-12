"""El tope de tiempo de `conectores.url.descargar_archivo` contra un servidor de verdad que gotea (revisión final de las
tarjetas, B5 de verdad): con un servidor falso que entrega los trozos al instante el tope «entre trozos» pasaba las
pruebas, pero `iter_content(65536)` espera a juntar 64 KB y un servidor que suelta 1 byte cada 0.25 s dejaba al
worker bloqueado 12 s con `tiempo_max=2`. Aquí el servidor es real (`http.server` en un hilo, por el loopback)."""
import http.server
import os
import threading
import time

import pytest

from conectores import url as conector_url


class _Gotero(http.server.BaseHTTPRequestHandler):
    """Contesta 200 de video/mp4 y suelta 1 byte cada 0.2 s hasta que el cliente se va (o hasta `parar`)."""
    parar = None

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.end_headers()
        try:
            for _ in range(300):                       # 60 s como mucho: el test no deja un hilo colgado
                if self.parar.is_set():
                    return
                self.wfile.write(b"x")
                self.wfile.flush()
                time.sleep(0.2)
        except OSError:                                # BrokenPipe / ConnectionReset: el cliente cortó
            return

    def log_message(self, *args):
        pass


@pytest.fixture
def servidor_gotero(monkeypatch):
    parar = threading.Event()
    _Gotero.parar = parar
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Gotero)
    servidor.daemon_threads = True
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    # el loopback no pasa la guarda de SSRF (con razón): aquí se deja pasar solo a este servidor de prueba
    monkeypatch.setattr(conector_url, "host_permitido", lambda url: url.startswith("http://127.0.0.1:"))
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    try:
        yield f"http://127.0.0.1:{servidor.server_address[1]}/v.mp4"
    finally:
        parar.set()
        servidor.shutdown()
        servidor.server_close()


@pytest.mark.slow
def test_un_servidor_que_gotea_se_corta_al_tope_de_tiempo_y_no_deja_parcial(servidor_gotero, tmp_path):
    ruta = tmp_path / "v.mp4"
    ruta.write_bytes(b"BUENO")                          # un archivo bueno anterior no se toca
    inicio = time.monotonic()
    with pytest.raises(conector_url.ErrorConector) as ei:
        conector_url.descargar_archivo(servidor_gotero, str(ruta), tiempo_max=1)
    gastado = time.monotonic() - inicio
    assert gastado < 3, f"el tope era 1 s y tardó {gastado:.1f} s"
    assert "tardó demasiado" in ei.value.usuario
    assert ruta.read_bytes() == b"BUENO"
    assert sorted(n for n in os.listdir(tmp_path) if n != "usuarios_prueba.json") == ["v.mp4"]   # sin .part
