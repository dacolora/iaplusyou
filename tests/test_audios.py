"""Audios en Crear (spec 2026-09-28): audios.py, el precio y el tipo de gasto."""
import pytest

import audios
import gastos
import materiales
from providers import fal_audio


def test_locucion_es_un_tipo_de_gasto_con_estimado_por_caracteres():
    assert "locucion" in gastos.TIPOS
    e = gastos.estimar("locucion", caracteres=500)
    assert e["usd"] == round(500 * fal_audio.COSTO_USD_POR_CARACTER, 4) == 0.05
    assert "500" in e["detalle"]
    assert gastos.estimar("locucion", caracteres=0)["usd"] == round(fal_audio.COSTO_USD_POR_CARACTER, 4)


def test_el_nombre_del_tipo_locucion_existe_en_el_panel_de_gasto():
    import dashboard
    assert dashboard.NOMBRES_TIPO_GASTO["locucion"]


@pytest.fixture()
def r2(monkeypatch):
    subidos, borrados = [], []
    monkeypatch.setattr(materiales.r2_uploader, "upload_file",
                        lambda local, key, ct: subidos.append((key, ct)) or f"https://r2/{key}")
    monkeypatch.setattr(materiales.r2_uploader, "delete_file", lambda key: borrados.append(key))
    monkeypatch.setattr(audios.r2_uploader, "upload_file",
                        lambda local, key, ct: subidos.append((key, ct)) or f"https://r2/{key}")
    return {"subidos": subidos, "borrados": borrados}


def _cancion(cliente="acme", nombre="Jingle", duracion_ms=30000):
    return materiales.registrar(cliente, tipo="audio", origen="subida", url=f"https://r2/{cliente}/{nombre}.mp3",
                                hash=materiales.hash_clave("cancion", cliente, nombre), bytes=10, duracion_ms=duracion_ms,
                                extra={"nombre": nombre, "fuente": "subida"})


def _form(**k):
    base = {"texto": "  Hola   mundo ", "voz": "Rachel", "idioma": "es", "velocidad": "normal", "musica": "", "inicio_s": "0", "volumen": "media"}
    base.update(k)
    return base


def test_validar_devuelve_el_payload_limpio(base_temporal):
    p = audios.validar("acme", _form())
    assert p == {"texto": "Hola mundo", "voz": "Rachel", "idioma": "es", "velocidad": "normal",
                 "musica_id": None, "inicio_s": 0, "volumen": "media"}


def test_validar_rechaza_lo_que_no_esta_en_las_listas(base_temporal):
    for campo, valor, clave in [("texto", "   ", "texto"), ("texto", "x" * 3001, "largo"), ("voz", "Nadie", "voz"),
                                ("idioma", "fr", "idioma"), ("velocidad", "turbo", "velocidad"), ("volumen", "mucho", "volumen"),
                                ("musica", "mat:999", "musica"), ("musica", "basura", "musica")]:
        with pytest.raises(audios.EntradaInvalida) as e:
            audios.validar("acme", _form(**{campo: valor}))
        assert str(e.value) == audios.MENSAJES[clave], (campo, valor)


def test_validar_con_cancion_del_cliente_y_segundo_de_inicio(base_temporal):
    c = _cancion()
    ajena = _cancion(cliente="otro", nombre="Otra")
    p = audios.validar("acme", _form(musica=f"mat:{c['id']}", inicio_s="12", volumen="alta"))
    assert p["musica_id"] == c["id"] and p["inicio_s"] == 12 and p["volumen"] == "alta"
    assert audios.validar("acme", _form(musica=f"mat:{c['id']}", inicio_s="45"))["inicio_s"] == 0   # fuera de la canción
    with pytest.raises(audios.EntradaInvalida):
        audios.validar("acme", _form(musica=f"mat:{ajena['id']}"))


def test_nombre_de_corta_a_sesenta_letras():
    assert audios.nombre_de("  Hola   mundo ") == "Hola mundo"
    largo = "palabra " * 20
    n = audios.nombre_de(largo)
    assert len(n) <= 60 and n.endswith("…")


def test_hash_de_la_voz_cambia_con_texto_voz_y_velocidad_no_con_idioma():
    base = audios.hash_voz("Hola", "Rachel", "es", "normal")
    assert base == audios.hash_voz("Hola", "Rachel", "es", "normal")
    assert base != audios.hash_voz("Hola", "Rachel", "es", "rapida")
    assert base != audios.hash_voz("Hola", "Adam", "es", "normal")
    assert base != audios.hash_voz("Hola.", "Rachel", "es", "normal")
    assert base == audios.hash_voz("Hola", "Rachel", "en", "normal")
    a = audios.hash_audio(base, None, 0, "media")
    assert a == audios.hash_audio(base, None, 0, "alta")            # sin música el volumen no cuenta
    assert a != audios.hash_audio(base, 7, 0, "media") != audios.hash_audio(base, 7, 5, "media")


def test_filtro_con_musica_agacha_la_musica_y_funde_despues_del_loudnorm():
    total = audios.duracion_total_ms(2000, True)
    assert total == 2000 + audios.INTRO_MS + audios.COLA_MS == 4100
    fg = audios.filtro_locucion(True, "baja", total)
    assert "adelay=600|600" in fg and "volume=0.2[mus]" in fg
    assert "sidechaincompress=" in fg and "amix=inputs=2:duration=first:normalize=0" in fg
    assert fg.index("loudnorm=") < fg.index("afade=t=out:st=2.600:d=1.500") and fg.endswith("[aout]")


def test_filtro_sin_musica_es_solo_la_voz_normalizada():
    assert audios.duracion_total_ms(2000, False) == 2000
    fg = audios.filtro_locucion(False, "media", 2000)
    assert "amix" not in fg and "adelay" not in fg and "afade" not in fg and "loudnorm=" in fg and fg.endswith("[aout]")


def test_mezclar_arma_los_argumentos_de_ffmpeg(monkeypatch, tmp_path):
    llamadas = []
    monkeypatch.setattr(audios.cortes, "ffmpeg", lambda args, timeout=300: llamadas.append(list(args)))
    monkeypatch.setattr(audios.cortes, "duracion", lambda path: 4.1)
    r = audios.mezclar("/v.mp3", "/m.wav", str(tmp_path / "a.mp3"), 2000, "alta")
    assert r["duracion_ms"] == 4100
    args = llamadas[0]
    assert args[:2] == ["-i", "/v.mp3"] and args[2:6] == ["-stream_loop", "-1", "-i", "/m.wav"]
    assert "-c:a" in args and args[args.index("-c:a") + 1] == "libmp3lame"
    assert args[args.index("-t") + 1] == "4.100" and args[-1].endswith("a.mp3")
    audios.mezclar("/v.mp3", None, str(tmp_path / "b.mp3"), 2000, "alta")
    assert "-stream_loop" not in llamadas[1] and llamadas[1][llamadas[1].index("-t") + 1] == "2.000"


def _audio(cliente="acme", n=1):
    return materiales.registrar(cliente, tipo="audio", origen=audios.ORIGEN, url=f"https://r2/clientes/{cliente}/materiales/locucion_{n}.mp3",
                                hash=materiales.hash_clave("locucion", cliente, n), bytes=10, duracion_ms=4100,
                                extra={"nombre": f"Audio {n}", "texto": f"texto {n}", "voz": "Rachel", "idioma": "es",
                                       "velocidad": "normal", "volumen": "media", "musica": {"material_id": 3, "nombre": "Jingle", "inicio_s": 0, "estado": "ok"}})


def test_listar_obtener_y_borrar_solo_los_audios_del_cliente(base_temporal, r2):
    a1, a2 = _audio(n=1), _audio(n=2)
    _audio(cliente="otro", n=3)
    _cancion()                                          # una canción no es un audio
    lista = audios.listar("acme")
    assert [a["id"] for a in lista] == [a2["id"], a1["id"]]
    assert lista[1] == {"id": a1["id"], "nombre": "Audio 1", "texto": "texto 1", "duracion_s": 4.1, "url": a1["url"],
                        "voz": "Rachel", "idioma": "es", "velocidad": "normal", "volumen": "media",
                        "musica": {"material_id": 3, "nombre": "Jingle", "inicio_s": 0, "estado": "ok"}, "creado_en": a1["creado_en"]}
    assert audios.obtener("acme", a1["id"])["id"] == a1["id"] and audios.obtener("otro", a1["id"]) is None
    assert audios.obtener("acme", _cancion(nombre="Otra")["id"]) is None
    assert audios.borrar("acme", a1["id"]) is True and audios.borrar("acme", a1["id"]) is False
    assert r2["borrados"] == [f"clientes/acme/materiales/locucion_1.mp3"]
    assert [a["id"] for a in audios.listar("acme")] == [a2["id"]]


def test_muestra_se_sintetiza_una_sola_vez_y_la_paga_creatv(base_temporal, r2, monkeypatch):
    import sqlalchemy as sa
    import db
    llamadas = []
    monkeypatch.setattr(audios.fal_audio, "tts", lambda texto, voz, idioma="es", on_progreso=None, velocidad=None, timeout=180:
                        llamadas.append((texto, voz)) or {"url": "https://fal/m.mp3", "costo_usd": 0.0052})
    monkeypatch.setattr(audios, "descargar_url", lambda url, destino: open(destino, "wb").write(b"MP3") and destino)
    monkeypatch.setattr(audios.cortes, "duracion", lambda path: 2.5)
    url = audios.muestra("Rachel", "es")
    assert url == "https://r2/clientes/_creatv/materiales/muestra_Rachel_es_v1.mp3"
    assert llamadas == [("Hola, soy Rachel. Así suena mi voz en tu anuncio.", "Rachel")]
    assert audios.muestra("Rachel", "es") == url and len(llamadas) == 1          # cacheada
    assert audios.muestra("Rachel", "en") != url and len(llamadas) == 2 and "Hi, I'm Rachel" in llamadas[1][0]
    with db.conectar() as con:
        gastos_ = [dict(f._mapping) for f in con.execute(sa.select(db.gasto).where(db.gasto.c.cliente == "_creatv"))]
    filas = sorted((g["tipo"], g["usd"], g["referencia"]) for g in gastos_)      # "en" < "es"
    assert len(filas) == 2
    assert filas[0][:2] == ("locucion", 0.0052) and filas[0][2].startswith("muestra_voz:Rachel:en:v1:")
    assert filas[1][:2] == ("locucion", 0.0052) and filas[1][2].startswith("muestra_voz:Rachel:es:v1:")
    m = materiales.buscar_hash("_creatv", audios.hash_muestra("Rachel", "es"))
    assert m["origen"] == "voz" and m["duracion_ms"] == 2500 and m["extra"]["muestra"] is True
    with pytest.raises(ValueError):
        audios.muestra("Nadie", "es")


def test_muestra_registra_el_gasto_aunque_falle_despues_de_pagar_a_fal(base_temporal, monkeypatch):
    import sqlalchemy as sa
    import db
    monkeypatch.setattr(audios.fal_audio, "tts", lambda texto, voz, idioma="es", on_progreso=None, velocidad=None, timeout=180:
                        {"url": "https://fal/m.mp3", "costo_usd": 0.0052})

    def _falla(url, destino):
        raise RuntimeError("red caída")
    monkeypatch.setattr(audios, "descargar_url", _falla)
    with pytest.raises(RuntimeError):
        audios.muestra("Rachel", "es")
    with db.conectar() as con:
        gastos_ = [dict(f._mapping) for f in con.execute(sa.select(db.gasto).where(db.gasto.c.cliente == "_creatv"))]
    assert len(gastos_) == 1 and gastos_[0]["usd"] == 0.0052
    assert gastos_[0]["referencia"].startswith("muestra_voz:Rachel:es:v1:")
    assert materiales.buscar_hash("_creatv", audios.hash_muestra("Rachel", "es")) is None


def test_fichas_de_voces_para_la_galeria():
    """Galería de voces (2026-09-29): una ficha por voz de fal_audio.VOCES, en el
    mismo orden, con género (clave de GENEROS) y un tono corto; ningún nombre
    de VOCES_INFO puede ser una voz que ya no exista en fal."""
    fichas = audios.fichas_voces()
    assert [f["nombre"] for f in fichas] == audios.voces()
    assert set(audios.VOCES_INFO) == set(audios.voces())
    for f in fichas:
        assert f["genero"] in audios.GENEROS and f["genero_nombre"] == audios.GENEROS[f["genero"]]
        assert f["tono"] and isinstance(f["tono"], str)
    rachel = fichas[0]
    assert rachel["nombre"] == "Rachel" and rachel["genero"] == "mujer"
    assert {f["genero"] for f in fichas} >= {"mujer", "hombre"}
