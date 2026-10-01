"""Tarea audio_generar (spec 2026-09-28 §4): voz por fal, mezcla, material y gasto."""
import os

import pytest
import sqlalchemy as sa

import audios
import db
import materiales


def _gastos(cliente):
    with db.conectar() as con:
        return [dict(f._mapping) for f in con.execute(sa.select(db.gasto).where(db.gasto.c.cliente == cliente))]


@pytest.fixture()
def entorno(base_temporal, monkeypatch, tmp_path):
    import tareas.audios as ta
    llamadas, mezclas, subidos = [], [], []
    monkeypatch.setattr(ta.fal_audio, "tts",
                        lambda texto, voz, idioma="es", on_progreso=None, velocidad=None, **kw:
                        llamadas.append({"texto": texto, "voz": voz, "velocidad": velocidad}) or {"url": "https://fal/v.mp3", "costo_usd": 0.0011})
    monkeypatch.setattr(ta.audios, "descargar_url", lambda url, destino: (open(destino, "wb").write(b"VOZ"), destino)[1])
    monkeypatch.setattr(ta.r2_uploader, "upload_file", lambda local, key, ct: subidos.append(key) or f"https://r2/{key}")
    monkeypatch.setattr(materiales.r2_uploader, "upload_file", lambda local, key, ct: subidos.append(key) or f"https://r2/{key}")
    monkeypatch.setattr(ta.cortes, "duracion", lambda path: 2.0)

    def _mezclar(voz_path, musica_path, salida, voz_ms, volumen):
        mezclas.append({"musica": musica_path, "voz_ms": voz_ms, "volumen": volumen})
        with open(salida, "wb") as f:
            f.write(b"MP3")
        return {"archivo": salida, "duracion_ms": 4100 if musica_path else 2000}
    monkeypatch.setattr(ta.audios, "mezclar", _mezclar)
    monkeypatch.setattr(ta, "carpeta_trabajo", lambda cliente, h: str(tmp_path / "trabajo" / h[:8]))
    monkeypatch.setattr(ta.trabajos, "reportar", lambda *a, **k: None)
    # Sin red: la voz cacheada ya no tiene `extra.local` (la carpeta se borró)
    # y materiales.descargar bajaría de R2; el tramo de música lo recortaría
    # final_edition.musica.pista_propia bajando la canción. Las dos se simulan,
    # conservando el comportamiento que importa (la canción que no existe
    # sigue lanzando ValueError).
    monkeypatch.setattr(ta.materiales, "descargar", lambda mat, destino: (open(destino, "wb").write(b"VOZ"), destino)[1])

    def _pista(cliente, valor, inicio_s=0, carpeta_cache=None):
        import mi_musica
        m = mi_musica.resolver(cliente, valor)
        if not m:
            raise ValueError("Esa canción ya no está en Mi música.")
        return ({"archivo": "/tramo.wav", "estilo": (m.get("extra") or {}).get("nombre", ""),
                 "inicio_s": mi_musica.inicio_valido(m, inicio_s), "material_id": m["id"]}, 0)
    monkeypatch.setattr(ta.fe_musica, "pista_propia", _pista)
    return {"ta": ta, "llamadas": llamadas, "mezclas": mezclas, "subidos": subidos}


def _cancion(cliente="acme", nombre="Jingle"):
    return materiales.registrar(cliente, tipo="audio", origen="subida", url=f"https://r2/{nombre}.mp3",
                                hash=materiales.hash_clave("cancion", nombre), bytes=10, duracion_ms=30000,
                                extra={"nombre": nombre, "fuente": "subida"})


def _tarea(payload, tid=5):
    return {"id": tid, "job_id": "acme__audio_generar", "payload": {"cliente": "acme", **payload}}


def _payload(**k):
    p = {"texto": "Hola mundo", "voz": "Rachel", "idioma": "es", "velocidad": "rapida", "musica_id": None, "inicio_s": 0, "volumen": "media"}
    p.update(k)
    return p


def test_tarea_solo_voz_crea_el_material_y_registra_el_gasto(entorno):
    ta = entorno["ta"]
    msg = ta.ejecutar(_tarea(_payload()))
    assert msg == ta.MENSAJES["listo"]
    assert entorno["llamadas"] == [{"texto": "Hola mundo", "voz": "Rachel", "velocidad": 1.15}]
    assert entorno["mezclas"] == [{"musica": None, "voz_ms": 2000, "volumen": "media"}]
    (a,) = audios.listar("acme")
    assert a["nombre"] == "Hola mundo" and a["duracion_s"] == 2.0 and a["musica"] is None and a["volumen"] == "media"
    fila = materiales.obtener("acme", a["id"])
    assert fila["costo_usd"] == 0.0011 and fila["padre_id"] and fila["url"].startswith("https://r2/clientes/acme/materiales/locucion_")
    voz = materiales.obtener("acme", fila["padre_id"])
    assert voz["origen"] == "voz" and voz["extra"]["velocidad"] == "rapida" and voz["duracion_ms"] == 2000
    (g,) = _gastos("acme")
    assert (g["tipo"], g["usd"], g["proveedor"]) == ("locucion", 0.0011, "fal/elevenlabs")
    assert g["referencia"] == f"locucion:{audios.hash_voz('Hola mundo', 'Rachel', 'es', 'rapida')[:12]}:t5"
    assert "10 caracteres" in g["detalle"] and "Rachel" in g["detalle"]


def test_tarea_con_musica_pasa_el_tramo_y_guarda_la_cancion(entorno):
    ta = entorno["ta"]
    c = _cancion()
    ta.ejecutar(_tarea(_payload(musica_id=c["id"], inicio_s=7, volumen="alta")))
    assert entorno["mezclas"] == [{"musica": "/tramo.wav", "voz_ms": 2000, "volumen": "alta"}]
    (a,) = audios.listar("acme")
    assert a["musica"] == {"material_id": c["id"], "nombre": "Jingle", "inicio_s": 7, "estado": "ok"} and a["volumen"] == "alta"


def test_cancion_borrada_deja_el_audio_solo_con_la_voz(entorno):
    ta = entorno["ta"]
    msg = ta.ejecutar(_tarea(_payload(musica_id=999, inicio_s=3)))
    assert msg == ta.MENSAJES["solo_voz"]
    assert entorno["mezclas"][0]["musica"] is None
    (a,) = audios.listar("acme")
    assert a["musica"] == {"material_id": 999, "nombre": "", "inicio_s": 3, "estado": "ausente"}


def test_la_voz_cacheada_no_llama_a_fal_ni_registra_gasto(entorno):
    ta = entorno["ta"]
    ta.ejecutar(_tarea(_payload(), tid=5))
    msg = ta.ejecutar(_tarea(_payload(volumen="alta"), tid=6))    # mismo hash sin música: ya existe, no hace nada
    assert msg == ta.MENSAJES["repetido"]
    assert len(entorno["llamadas"]) == 1 and len(entorno["mezclas"]) == 1 and len(_gastos("acme")) == 1
    c = _cancion()
    ta.ejecutar(_tarea(_payload(musica_id=c["id"]), tid=7))       # otro audio, misma voz: mezcla sin pagar
    assert len(entorno["llamadas"]) == 1 and len(entorno["mezclas"]) == 2 and len(_gastos("acme")) == 1
    a_nuevo = audios.listar("acme")[0]
    assert materiales.obtener("acme", a_nuevo["id"])["costo_usd"] == 0.0


def test_si_falla_despues_de_pagar_el_gasto_queda(entorno, monkeypatch):
    ta = entorno["ta"]

    def _revienta(*a, **k):
        raise RuntimeError("ffmpeg murió")
    monkeypatch.setattr(ta.audios, "mezclar", _revienta)
    with pytest.raises(RuntimeError):
        ta.ejecutar(_tarea(_payload()))
    (g,) = _gastos("acme")
    assert g["usd"] == 0.0011 and audios.listar("acme") == []


def test_la_tarea_queda_registrada_y_el_job_id_es_uno_por_cliente():
    import tareas
    tareas.cargar_todas()
    assert "audio_generar" in tareas.REGISTRO
    import tareas.audios as ta
    assert ta.job_id("acme") == "acme__audio_generar" and len(ta.ETAPAS) == 3


def test_tarea_con_voz_propia_lee_con_minimax(entorno, monkeypatch):
    ta = entorno["ta"]
    v = materiales.registrar("acme", tipo="audio", origen="voz_propia", url="https://r2/v.mp3", hash="h_vp", bytes=1,
                             extra={"nombre": "Ana", "voice_id": "mmx_1", "forma": "disenada", "idioma_muestra": "es",
                                    "estrenada": True})
    minimax = []
    monkeypatch.setattr(ta.audios.fal_audio, "tts_minimax", lambda texto, voice_id, idioma, velocidad=None, timeout=180:
                        minimax.append((texto, voice_id, idioma, velocidad)) or
                        {"url": "https://fal/m.mp3", "costo_usd": 0.001, "duracion_ms": 2000})
    ta.ejecutar(_tarea(_payload(voz=f"vp:{v['id']}", idioma="fi")))
    assert minimax == [("Hola mundo", "mmx_1", "fi", 1.15)] and entorno["llamadas"] == []
    (a,) = audios.listar("acme")
    assert a["voz"] == "Ana" and materiales.obtener("acme", a["id"])["extra"]["voz_ref"] == f"vp:{v['id']}"
    (g,) = _gastos("acme")
    assert g["proveedor"] == "fal/minimax" and "MiniMax" in g["detalle"] and "Ana" in g["detalle"]


def test_tarea_en_noruego_con_voz_de_la_galeria_va_por_turbo(entorno, monkeypatch):
    ta = entorno["ta"]
    vistos = []
    monkeypatch.setattr(ta.audios.fal_audio, "tts", lambda texto, voz, idioma="es", **kw:
                        vistos.append(kw) or {"url": "https://fal/v.mp3", "costo_usd": 0.0005})
    ta.ejecutar(_tarea(_payload(idioma="no")))
    assert vistos == [{"velocidad": 1.15, "modelo": ta.audios.fal_audio.MODELO_TTS_TURBO, "language_code": "no"}]
    (g,) = _gastos("acme")
    assert "ElevenLabs Turbo" in g["detalle"]
