"""Voces propias (spec 2026-09-30 §3): clonar o diseñar con MiniMax vía fal,
estrenarlas, muestras por idioma y borrar."""
import hashlib
import os

import pytest
import sqlalchemy as sa

import db
import gastos
import materiales
import voces_propias


@pytest.fixture()
def r2(monkeypatch):
    subidos, borrados = [], []

    def subir(local, key, ct):
        subidos.append(key)
        return f"https://r2/{key}"
    monkeypatch.setattr(materiales.r2_uploader, "upload_file", subir)
    monkeypatch.setattr(voces_propias.r2_uploader, "upload_file", subir)
    monkeypatch.setattr(materiales.r2_uploader, "delete_file", lambda key: borrados.append(key))
    return {"subidos": subidos, "borrados": borrados}


@pytest.fixture()
def fal(monkeypatch):
    llamadas = []

    def _clonar(audio_url, preview_text, timeout=300):
        llamadas.append(("clonar", audio_url, preview_text))
        return {"voice_id": "mmx_clon", "url_vista_previa": "https://fal/prev.mp3", "costo_usd": 1.5042}

    def _disenar(prompt, preview_text, timeout=300):
        llamadas.append(("disenar", prompt, preview_text))
        return {"voice_id": "mmx_dis", "url_vista_previa": "https://fal/dprev.mp3", "costo_usd": 3.0004}

    def _tts(texto, voice_id, idioma, velocidad=None, timeout=180):
        llamadas.append(("tts", texto, voice_id, idioma))
        return {"url": "https://fal/estreno.mp3", "costo_usd": 0.0045, "duracion_ms": 4000}
    monkeypatch.setattr(voces_propias.fal_audio, "clonar_voz_minimax", _clonar)
    monkeypatch.setattr(voces_propias.fal_audio, "disenar_voz_minimax", _disenar)
    monkeypatch.setattr(voces_propias.fal_audio, "tts_minimax", _tts)
    monkeypatch.setattr(voces_propias.audios, "descargar_url",
                        lambda url, destino: (open(destino, "wb").write(b"MP3"), destino)[1])
    monkeypatch.setattr(voces_propias.cortes, "duracion", lambda path: 4.0)
    return llamadas


class _Archivo:
    """Lo mínimo de werkzeug.FileStorage que usa guardar_grabacion."""
    def __init__(self, nombre, datos=b"RIFF audio falso"):
        self.filename, self._datos = nombre, datos

    def save(self, destino):
        with open(destino, "wb") as f:
            f.write(self._datos)


def _gastos(cliente):
    with db.conectar() as con:
        return [dict(f._mapping) for f in con.execute(sa.select(db.gasto).where(db.gasto.c.cliente == cliente))]


def _voz(cliente="acme", nombre="Ana", voice_id="mmx_1", idioma="es", estrenada=True):
    return materiales.registrar(
        cliente, tipo="audio", origen=voces_propias.ORIGEN,
        url=f"https://r2/clientes/{cliente}/materiales/voz_propia_{voice_id}.mp3",
        hash=materiales.hash_clave("voz_propia", "minimax", voice_id), bytes=10, duracion_ms=3000, costo_usd=3.0,
        extra={"nombre": nombre, "forma": "disenada", "proveedor": "minimax", "voice_id": voice_id,
               "idioma_muestra": idioma, "estrenada": estrenada, "descripcion": "Mujer cálida"})


def test_validar_disenar():
    p = voces_propias.validar_disenar({"nombre": "  Ana  ", "descripcion": " Mujer   cálida, de 30 ", "idioma": "sv"})
    assert p == {"forma": "disenar", "nombre": "Ana", "descripcion": "Mujer cálida, de 30", "idioma": "sv"}
    casos = [({"nombre": "", "descripcion": "Mujer cálida", "idioma": "es"}, "nombre"),
             ({"nombre": "x" * 41, "descripcion": "Mujer cálida", "idioma": "es"}, "nombre"),
             ({"nombre": "Ana", "descripcion": "corta", "idioma": "es"}, "descripcion"),
             ({"nombre": "Ana", "descripcion": "x" * 501, "idioma": "es"}, "descripcion"),
             ({"nombre": "Ana", "descripcion": "Mujer cálida", "idioma": "xx"}, "idioma")]
    for form, clave in casos:
        with pytest.raises(voces_propias.EntradaInvalida) as e:
            voces_propias.validar_disenar(form)
        assert str(e.value) == voces_propias.MENSAJES[clave], form


def test_validar_clonar_exige_la_casilla(base_temporal):
    with pytest.raises(voces_propias.EntradaInvalida) as e:
        voces_propias.validar_clonar({"nombre": "Ana", "idioma": "es"}, "admin")
    assert str(e.value) == voces_propias.MENSAJES["permiso"]
    p = voces_propias.validar_clonar({"nombre": "Ana", "idioma": "fi", "consentimiento": "si"}, "admin")
    assert (p["forma"], p["nombre"], p["idioma"]) == ("clonar", "Ana", "fi")
    c = p["consentimiento"]
    assert c["usuario"] == "admin" and c["texto"] == voces_propias.TEXTO_CONSENTIMIENTO and c["fecha"]


def test_guardar_grabacion_no_choca_con_una_cancion_identica(base_temporal, r2, monkeypatch, tmp_path):
    monkeypatch.setattr(voces_propias, "_duracion_ms", lambda path: 15000)
    datos = b"RIFF audio falso"
    cancion = materiales.registrar("acme", tipo="audio", origen="subida", url="https://r2/c.wav",
                                   hash=hashlib.sha256(datos).hexdigest(), bytes=len(datos), extra={"nombre": "Canción"})
    g = voces_propias.guardar_grabacion("acme", _Archivo("Mi voz.wav", datos), str(tmp_path / "tmp"))
    assert g["id"] != cancion["id"] and g["origen"] == "grabacion" and g["duracion_ms"] == 15000
    (key,) = r2["subidos"]
    assert key.startswith("clientes/acme/materiales/grabacion_") and key.endswith(".wav")
    assert os.listdir(str(tmp_path / "tmp")) == []


def test_grabacion_invalida(base_temporal, r2, monkeypatch, tmp_path):
    carpeta = str(tmp_path / "tmp")
    with pytest.raises(voces_propias.EntradaInvalida) as e:
        voces_propias.guardar_grabacion("acme", _Archivo("voz.png"), carpeta)
    assert str(e.value) == voces_propias.MENSAJES["archivo"]
    for dur, clave in [(9000, "corta"), (300001, "larga")]:
        monkeypatch.setattr(voces_propias, "_duracion_ms", lambda path, d=dur: d)
        with pytest.raises(voces_propias.EntradaInvalida) as e:
            voces_propias.guardar_grabacion("acme", _Archivo("voz.mp3"), carpeta)
        assert str(e.value) == voces_propias.MENSAJES[clave]
    assert r2["subidos"] == [] and os.listdir(carpeta) == []


def test_crear_disenada_registra_gasto_estrena_y_guarda(base_temporal, r2, fal):
    etapas = []
    payload = {"forma": "disenar", "nombre": "Ana", "descripcion": "Mujer cálida", "idioma": "sv"}
    voz, estrenada = voces_propias.crear("acme", payload, ref_sufijo=":t9", reportar=etapas.append)
    frase = "Hej, jag heter Ana. Så här låter min röst i din annons."
    assert fal == [("disenar", "Mujer cálida", frase), ("tts", frase, "mmx_dis", "sv")]
    assert estrenada and etapas == [1, 2]
    assert (voz["nombre"], voz["forma"], voz["voice_id"], voz["estrenada"], voz["idioma_muestra"]) == (
        "Ana", "disenada", "mmx_dis", True, "sv")
    assert voz["valor"] == f"vp:{voz['id']}" and voz["url"].startswith("https://r2/clientes/acme/materiales/voz_propia_")
    fila = materiales.obtener("acme", voz["id"])
    assert fila["origen"] == "voz_propia" and fila["costo_usd"] == 3.0004 and fila["extra"]["descripcion"] == "Mujer cálida"
    assert fila["hash"] == materiales.hash_clave("voz_propia", "minimax", "mmx_dis")
    g = sorted((x["tipo"], x["usd"], x["referencia"], x["proveedor"]) for x in _gastos("acme"))
    assert g == [("locucion", 0.0045, "voz_propia_estreno:t9", "fal/minimax"),
                 ("voz_propia", 3.0004, "voz_propia:disenar:t9", "fal/minimax")]
    assert voces_propias.listar("acme") == [voz]


def test_crear_clonada_guarda_el_consentimiento_y_la_grabacion(base_temporal, r2, fal):
    g = materiales.registrar("acme", tipo="audio", origen="grabacion", url="https://r2/clientes/acme/materiales/grabacion_x.wav",
                             hash="h_grab", bytes=10, duracion_ms=15000, extra={"nombre": "Mi voz"})
    consentimiento = {"usuario": "admin", "fecha": "2026-09-30T10:00:00", "texto": voces_propias.TEXTO_CONSENTIMIENTO}
    voz, _ = voces_propias.crear("acme", {"forma": "clonar", "nombre": "Daniel", "idioma": "cs", "grabacion_id": g["id"],
                                         "consentimiento": consentimiento}, ref_sufijo=":t3")
    assert fal[0] == ("clonar", "https://r2/clientes/acme/materiales/grabacion_x.wav",
                      "Dobrý den, jsem Daniel. Takhle zní můj hlas ve vaší reklamě.")
    fila = materiales.obtener("acme", voz["id"])
    assert fila["extra"]["consentimiento"] == consentimiento and fila["extra"]["grabacion_id"] == g["id"]
    assert voz["forma"] == "clonada"


def test_si_el_estreno_falla_la_voz_pagada_se_guarda_sin_estrenar(base_temporal, r2, fal, monkeypatch):
    def _falla(*a, **k):
        raise RuntimeError("fal caído")
    monkeypatch.setattr(voces_propias.fal_audio, "tts_minimax", _falla)
    voz, estrenada = voces_propias.crear("acme", {"forma": "disenar", "nombre": "Ana", "descripcion": "Mujer cálida",
                                                  "idioma": "es"}, ref_sufijo=":t4")
    assert not estrenada and not voz["estrenada"]
    assert voz["url"].startswith("https://r2/clientes/acme/materiales/voz_propia_")     # la vista previa, en R2
    assert [(x["tipo"], x["usd"]) for x in _gastos("acme")] == [("voz_propia", 3.0004)]


def test_si_la_creacion_falla_no_hay_gasto_ni_voz(base_temporal, r2, fal, monkeypatch):
    def _falla(*a, **k):
        raise RuntimeError("fal caído")
    monkeypatch.setattr(voces_propias.fal_audio, "disenar_voz_minimax", _falla)
    with pytest.raises(RuntimeError):
        voces_propias.crear("acme", {"forma": "disenar", "nombre": "Ana", "descripcion": "Mujer cálida", "idioma": "es"})
    assert _gastos("acme") == [] and voces_propias.listar("acme") == []


def test_resolver_solo_del_proyecto(base_temporal):
    v = _voz()
    ajena = _voz(cliente="otro", voice_id="mmx_2")
    assert voces_propias.resolver("acme", f"vp:{v['id']}")["voice_id"] == "mmx_1"
    assert voces_propias.resolver("acme", f"vp:{ajena['id']}") is None
    assert voces_propias.resolver("acme", "vp:abc") is None and voces_propias.resolver("acme", "Rachel") is None


def test_muestra_propia_en_otro_idioma_se_cobra_al_proyecto_una_vez(base_temporal, r2, fal):
    v = _voz(idioma="es", estrenada=True)
    assert voces_propias.muestra("acme", f"vp:{v['id']}", "es") == v["url"] and fal == []
    url = voces_propias.muestra("acme", f"vp:{v['id']}", "fi")
    assert fal == [("tts", "Hei, olen Ana. Tältä ääneni kuulostaa mainoksessasi.", "mmx_1", "fi")]
    assert voces_propias.muestra("acme", f"vp:{v['id']}", "fi") == url and len(fal) == 1
    (g,) = _gastos("acme")
    assert g["tipo"] == "locucion" and g["referencia"].startswith(f"muestra_propia:{v['id']}:fi:")
    with pytest.raises(ValueError):
        voces_propias.muestra("acme", "vp:999", "fi")


def test_muestra_de_una_voz_sin_estrenar_la_estrena(base_temporal, r2, fal):
    v = _voz(idioma="es", estrenada=False)
    voces_propias.muestra("acme", f"vp:{v['id']}", "es")
    assert fal[0][0] == "tts" and voces_propias.obtener("acme", v["id"])["estrenada"] is True


def test_borrar_quita_voz_grabacion_y_muestras(base_temporal, r2, fal):
    g = materiales.registrar("acme", tipo="audio", origen="grabacion", url="https://r2/clientes/acme/materiales/grabacion_x.wav",
                             hash="h_grab", bytes=10, extra={})
    v = _voz()
    materiales.actualizar_extra("acme", v["id"], grabacion_id=g["id"])
    voces_propias.muestra("acme", f"vp:{v['id']}", "de")
    assert voces_propias.borrar("acme", v["id"]) is True
    assert voces_propias.listar("acme") == [] and materiales.obtener("acme", g["id"]) is None
    assert any(k.startswith("clientes/acme/materiales/muestra_propia_") for k in r2["borrados"])
    assert "clientes/acme/materiales/grabacion_x.wav" in r2["borrados"]
    assert voces_propias.borrar("acme", v["id"]) is False


def test_tipo_de_gasto_y_estimados():
    from providers import fal_audio
    assert "voz_propia" in gastos.TIPOS
    assert gastos.estimar("voz_clonada")["usd"] == fal_audio.COSTO_CLONAR_VOZ
    assert gastos.estimar("voz_disenada")["usd"] == fal_audio.COSTO_DISENAR_VOZ
