"""Lo que el carril de Crear (varias generaciones a la vez en el worker,
spec 2026-09-28-crear-sin-cola) comparte entre hilos tiene que aguantarlo."""
import json
import os
import threading


def _en_hilos(n, fn):
    errores = []

    def correr(i):
        try:
            fn(i)
        except Exception as e:  # noqa: BLE001
            errores.append(e)
    hilos = [threading.Thread(target=correr, args=(i,)) for i in range(n)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    return errores


def test_guardar_json_desde_varios_hilos_no_choca(tmp_path):
    """Todos los hilos de un proceso usaban el mismo `<archivo>.<pid>.tmp`: dos
    guardando a la vez se pisaban el temporal (o uno lo renombraba antes de
    que el otro terminara de escribirlo)."""
    import _json_store
    ruta = str(tmp_path / "estado.json")

    def guardar(i):
        for k in range(40):
            _json_store.guardar(ruta, {"hilo": i, "vuelta": k, "relleno": "x" * 2000})
    assert _en_hilos(8, guardar) == []
    with open(ruta, encoding="utf-8") as f:
        assert json.load(f)["vuelta"] == 39
    assert [n for n in os.listdir(tmp_path) if n.endswith(".tmp")] == []


def test_estado_modificar_no_pierde_entradas_entre_hilos(tmp_path, monkeypatch):
    """Dos videos que terminan a la vez agregan su entrada a estado_videos.json:
    con cargar→guardar sueltos, uno borraba la del otro."""
    import estado
    monkeypatch.setattr(estado, "BASE_DIR", str(tmp_path))

    def agregar(i):
        estado.modificar("acme", lambda e: {**e, f"cf_{i}": {"estado": "pendiente"}})
    assert _en_hilos(10, agregar) == []
    assert sorted(estado.cargar("acme")) == sorted(f"cf_{i}" for i in range(10))


def test_r2_crea_una_sesion_de_boto3_por_llamada(monkeypatch):
    """boto3.client() usa la sesión por defecto, que no es segura entre hilos."""
    import boto3
    from storage import r2_uploader
    for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(k, "x")
    sesiones = []

    class Sesion:
        def __init__(self):
            sesiones.append(self)

        def client(self, *a, **k):
            return ("cliente", self)
    monkeypatch.setattr(boto3.session, "Session", Sesion)
    monkeypatch.setattr(boto3, "client", lambda *a, **k: (_ for _ in ()).throw(AssertionError("sesión por defecto")))
    a, b = r2_uploader._client(), r2_uploader._client()
    assert len(sesiones) == 2 and a[1] is not b[1]


def test_una_pista_de_musica_que_falta_se_paga_una_sola_vez(tmp_path, monkeypatch):
    """Dos piezas con el mismo estilo terminan a la vez: la pista no está en caché
    y las dos la mandaban a generar (y a cobrar)."""
    from final_edition import musica
    from final_edition import tipos
    estilo = sorted(tipos.ESTILOS_MUSICA)[0]
    llamadas = []
    barrera = threading.Barrier(4)

    def generar(prompt, segundos, on_progreso=None):
        llamadas.append(1)
        return {"url": "https://fal/pista.wav", "costo_usd": 0.2}
    monkeypatch.setattr(musica.fal_audio, "musica", generar)
    monkeypatch.setattr(musica, "_descargar", lambda url, destino: open(destino, "wb").write(b"RIFF"))
    monkeypatch.setattr(musica.r2_uploader, "upload_file", lambda *a, **k: "https://r2/musica/pista.wav")
    costos = []

    def pedir(i):
        barrera.wait()
        _pista, costo = musica.obtener_pista(estilo, 8, carpeta_cache=str(tmp_path))
        costos.append(costo)
    assert _en_hilos(4, pedir) == []
    assert len(llamadas) == 1 and sorted(costos) == [0, 0, 0, 0.2]


def test_la_app_de_idiomas_del_worker_se_crea_una_vez(monkeypatch):
    import idiomas
    monkeypatch.setattr(idiomas, "_app_fuera", None)
    apps = []
    barrera = threading.Barrier(6)

    def pedir(i):
        barrera.wait()
        apps.append(idiomas._app_fuera_de_peticion())
    assert _en_hilos(6, pedir) == []
    assert len({id(a) for a in apps}) == 1


def test_una_cancion_propia_se_baja_y_recorta_una_sola_vez(tmp_path, monkeypatch):
    """Dos videos con la misma canción de Mi música terminando a la vez bajaban
    y recortaban el mismo archivo al mismo tiempo."""
    from final_edition import musica
    m = {"id": 7, "hash": "abc", "url": "https://r2/cancion.mp3"}
    monkeypatch.setattr(musica.mi_musica, "resolver", lambda c, v: m)
    monkeypatch.setattr(musica.mi_musica, "inicio_valido", lambda m, s: 0)
    monkeypatch.setattr(musica.mi_musica, "como_cancion", lambda m: {"nombre": "Mía", "fuente": "subida"})
    bajadas, recortes = [], []
    barrera = threading.Barrier(4)

    def descargar(url, destino):
        bajadas.append(url)
        open(destino, "wb").write(b"mp3")

    def ffmpeg(args):
        recortes.append(args)
        open(args[-1], "wb").write(b"wav")
    monkeypatch.setattr(musica, "_descargar", descargar)
    monkeypatch.setattr(musica.cortes, "ffmpeg", ffmpeg)

    def pedir(i):
        barrera.wait()
        musica.pista_propia("acme", "mat:7", 0, carpeta_cache=str(tmp_path))
    assert _en_hilos(4, pedir) == []
    assert len(bajadas) == 1 and len(recortes) == 1
