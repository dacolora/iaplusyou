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


@pytest.mark.parametrize("ext, convierte", [(".ogg", True), (".aac", True), (".m4a", False)])
def test_grabacion_aac_u_ogg_se_sube_convertida_a_mp3(base_temporal, monkeypatch, tmp_path, ext, convierte):
    """Revisión final F6: MiniMax clona desde mp3, m4a o wav; un .aac u .ogg se
    convierte a mp3 antes de medirlo y subirlo, y la carpeta temporal queda vacía."""
    conversiones, medidos, subidos = [], [], []

    def _ffmpeg(args, timeout=300):
        conversiones.append(list(args))
        with open(args[-1], "wb") as f:
            f.write(b"ID3 mp3 convertido")
    monkeypatch.setattr(voces_propias.cortes, "ffmpeg", _ffmpeg)
    monkeypatch.setattr(voces_propias, "_duracion_ms", lambda path: medidos.append(path) or 15000)
    monkeypatch.setattr(voces_propias.r2_uploader, "upload_file",
                        lambda local, key, ct: subidos.append((key, ct)) or f"https://r2/{key}")
    carpeta = str(tmp_path / "tmp")
    g = voces_propias.guardar_grabacion("acme", _Archivo("Mi voz" + ext), carpeta)
    ((key, ct),) = subidos
    assert key.startswith("clientes/acme/materiales/grabacion_") and g["extra"]["nombre"] == "Mi voz"
    if convierte:
        (args,) = conversiones
        origen, salida = args[1], args[-1]
        assert args == ["-i", origen, "-vn", "-ac", "1", "-ar", "44100", "-c:a", "libmp3lame", "-b:a", "128k", salida]
        assert origen.endswith(ext) and salida.endswith(".mp3") and medidos == [origen, salida]
        assert key.endswith(".mp3") and ct == "audio/mpeg" and g["bytes"] == len(b"ID3 mp3 convertido")
    else:
        assert conversiones == [] and key.endswith(".m4a") and ct == "audio/mp4"
    assert os.listdir(carpeta) == []


def test_grabacion_que_ffmpeg_no_puede_convertir(base_temporal, r2, monkeypatch, tmp_path):
    def _falla(args, timeout=300):
        raise RuntimeError("ffmpeg falló (código 1): Invalid data found when processing input")
    monkeypatch.setattr(voces_propias.cortes, "ffmpeg", _falla)
    carpeta = str(tmp_path / "tmp")
    with pytest.raises(voces_propias.EntradaInvalida) as e:
        voces_propias.guardar_grabacion("acme", _Archivo("voz.ogg"), carpeta)
    assert str(e.value) == voces_propias.MENSAJES["leer"]
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
    (gasto_diseno,) = [x for x in _gastos("acme") if x["tipo"] == "voz_propia"]
    assert gasto_diseno["extra"]["voice_id"] == "mmx_dis" and "consentimiento" not in gasto_diseno["extra"]      # un diseño no lleva consentimiento
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
    (gasto_clon,) = [x for x in _gastos("acme") if x["tipo"] == "voz_propia"]
    assert (gasto_clon["usd"], gasto_clon["referencia"]) == (1.5042, "voz_propia:clonar:t3")
    # Revisión final F5: la constancia del permiso viaja con el cobro del clon
    # (sobrevive a borrar la voz y su extra).
    assert gasto_clon["extra"]["voice_id"] == "mmx_clon" and gasto_clon["extra"]["consentimiento"] == consentimiento
    assert gasto_clon["extra"]["ficha"]["extra"]["grabacion_id"] == g["id"]


def test_crear_clon_sin_consentimiento_no_paga(base_temporal, r2, fal):
    g = materiales.registrar("acme", tipo="audio", origen="grabacion", url="https://r2/clientes/acme/materiales/grabacion_x.wav",
                             hash="h_grab_sc", bytes=10, duracion_ms=15000, extra={"nombre": "Mi voz"})
    with pytest.raises(ValueError) as e:
        voces_propias.crear("acme", {"forma": "clonar", "nombre": "Daniel", "idioma": "cs", "grabacion_id": g["id"],
                                     "consentimiento": {}}, ref_sufijo=":t7")
    assert str(e.value) == voces_propias.MENSAJES["permiso"]
    assert fal == [] and _gastos("acme") == [] and voces_propias.listar("acme") == []


def test_crear_registra_el_gasto_antes_de_estrenar(base_temporal, r2, fal, monkeypatch):
    vistos = []

    def _tts(texto, voice_id, idioma, velocidad=None, timeout=180):
        vistos.append([x["tipo"] for x in _gastos("acme")])
        return {"url": "https://fal/estreno.mp3", "costo_usd": 0.0045, "duracion_ms": 4000}
    monkeypatch.setattr(voces_propias.fal_audio, "tts_minimax", _tts)
    voces_propias.crear("acme", {"forma": "disenar", "nombre": "Ana", "descripcion": "Mujer cálida", "idioma": "es"},
                        ref_sufijo=":t6")
    assert vistos == [["voz_propia"]]


def test_crear_sin_sufijo_no_pisa_gastos(base_temporal, r2, fal, monkeypatch):
    ids = iter(["mmx_s1", "mmx_s2"])

    def _disenar(prompt, preview_text, timeout=300):
        return {"voice_id": next(ids), "url_vista_previa": "https://fal/dprev.mp3", "costo_usd": 3.0004}
    monkeypatch.setattr(voces_propias.fal_audio, "disenar_voz_minimax", _disenar)
    tiempos = iter([1_000_000.0, 2_000_000.0])
    monkeypatch.setattr(voces_propias.time, "time", lambda: next(tiempos))
    payload = {"forma": "disenar", "nombre": "Ana", "descripcion": "Mujer cálida", "idioma": "es"}
    voces_propias.crear("acme", dict(payload))
    voces_propias.crear("acme", dict(payload, nombre="Eva"))
    filas = [x for x in _gastos("acme") if x["tipo"] == "voz_propia"]
    assert len(filas) == 2 and len({x["referencia"] for x in filas}) == 2


def test_si_falla_subir_la_muestra_la_voz_pagada_se_guarda_igual(base_temporal, r2, fal, monkeypatch):
    def _falla(url, destino):
        raise RuntimeError("red caída")
    monkeypatch.setattr(voces_propias.audios, "descargar_url", _falla)
    voz, estrenada = voces_propias.crear("acme", {"forma": "disenar", "nombre": "Ana", "descripcion": "Mujer cálida",
                                                  "idioma": "es"}, ref_sufijo=":t5")
    assert estrenada is True and voz["url"] == ""
    assert sorted(x["tipo"] for x in _gastos("acme")) == ["locucion", "voz_propia"]


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


def _clon_que_falla(monkeypatch, grabacion_id):
    def _falla(*a, **k):
        raise RuntimeError("fal caído")
    monkeypatch.setattr(voces_propias.fal_audio, "clonar_voz_minimax", _falla)
    consentimiento = {"usuario": "admin", "fecha": "2026-09-30T10:00:00", "texto": voces_propias.TEXTO_CONSENTIMIENTO}
    with pytest.raises(RuntimeError):
        voces_propias.crear("acme", {"forma": "clonar", "nombre": "Daniel", "idioma": "cs", "grabacion_id": grabacion_id,
                                     "consentimiento": consentimiento}, ref_sufijo=":t2")


def test_si_el_clon_falla_la_grabacion_no_se_queda(base_temporal, r2, fal, monkeypatch):
    """Revisión final F2: fal no devolvió una voz, así que la grabación de la
    persona (fila y objeto en R2) no se queda sin una voz que la use."""
    g = materiales.registrar("acme", tipo="audio", origen="grabacion", url="https://r2/clientes/acme/materiales/grabacion_f.wav",
                             hash="h_grab_f", bytes=10, duracion_ms=15000, extra={"nombre": "Mi voz"})
    _clon_que_falla(monkeypatch, g["id"])
    assert materiales.obtener("acme", g["id"]) is None
    assert "clientes/acme/materiales/grabacion_f.wav" in r2["borrados"]
    assert _gastos("acme") == [] and voces_propias.listar("acme") == []


def test_si_el_clon_falla_no_borra_una_grabacion_que_usa_otra_voz(base_temporal, r2, fal, monkeypatch):
    g = materiales.registrar("acme", tipo="audio", origen="grabacion", url="https://r2/clientes/acme/materiales/grabacion_c.wav",
                             hash="h_grab_c", bytes=10, duracion_ms=15000, extra={"nombre": "Mi voz"})
    v = _voz(voice_id="mmx_previa")
    materiales.actualizar_extra("acme", v["id"], grabacion_id=g["id"])
    _clon_que_falla(monkeypatch, g["id"])
    assert materiales.obtener("acme", g["id"]) is not None
    assert "clientes/acme/materiales/grabacion_c.wav" not in r2["borrados"]


def test_borrar_grabacion_huerfana_solo_toca_grabaciones_del_proyecto_y_nunca_lanza(base_temporal, r2, monkeypatch):
    cancion = materiales.registrar("acme", tipo="audio", origen="subida", url="https://r2/clientes/acme/materiales/c.mp3",
                                   hash="h_cancion", bytes=10, extra={"nombre": "Canción"})
    ajena = materiales.registrar("otro", tipo="audio", origen="grabacion", url="https://r2/clientes/otro/materiales/g.wav",
                                 hash="h_ajena", bytes=10, extra={})
    voces_propias._borrar_grabacion_si_huerfana("acme", cancion["id"])
    voces_propias._borrar_grabacion_si_huerfana("acme", ajena["id"])
    voces_propias._borrar_grabacion_si_huerfana("acme", 999)
    assert materiales.obtener("acme", cancion["id"]) and materiales.obtener("otro", ajena["id"]) and r2["borrados"] == []
    g = materiales.registrar("acme", tipo="audio", origen="grabacion", url="https://r2/clientes/acme/materiales/g.wav",
                             hash="h_grab_r2", bytes=10, extra={})

    def _r2_caido(key):
        raise RuntimeError("R2 caído")
    monkeypatch.setattr(materiales.r2_uploader, "delete_file", _r2_caido)
    voces_propias._borrar_grabacion_si_huerfana("acme", g["id"])      # no lanza
    assert materiales.obtener("acme", g["id"]) is not None             # la fila queda para reintentar


def test_resolver_solo_del_proyecto(base_temporal):
    v = _voz()
    ajena = _voz(cliente="otro", voice_id="mmx_2")
    assert voces_propias.resolver("acme", f"vp:{v['id']}")["voice_id"] == "mmx_1"
    assert voces_propias.resolver("acme", f"vp:{ajena['id']}") is None
    assert voces_propias.resolver("acme", "vp:abc") is None and voces_propias.resolver("acme", "Rachel") is None


def test_resolver_con_un_id_enorme_es_none(base_temporal):
    # int() lo acepta (Python no tiene límite), pero SQLite sí: liga con
    # OverflowError, no ValueError.
    assert voces_propias.resolver("acme", "vp:" + "9" * 30) is None


def test_sintetizar_lee_con_minimax_y_estrena_una_vez(base_temporal, fal):
    v = voces_propias.resolver("acme", f"vp:{_voz(estrenada=False)['id']}")
    r = voces_propias.sintetizar("acme", v, "Hola", "pt", velocidad=1.15)
    assert r == {"url": "https://fal/estreno.mp3", "costo_usd": 0.0045, "duracion_ms": 4000}
    assert fal == [("tts", "Hola", "mmx_1", "pt")]
    assert voces_propias.obtener("acme", v["id"])["estrenada"] is True


def test_sintetizar_no_pierde_lo_pagado_si_no_puede_marcar_estrenada(base_temporal, fal, monkeypatch):
    v = voces_propias.resolver("acme", f"vp:{_voz(estrenada=False)['id']}")

    def _falla(*a, **k):
        raise RuntimeError("base bloqueada")
    monkeypatch.setattr(voces_propias, "marcar_estrenada", _falla)
    assert voces_propias.sintetizar("acme", v, "Hola", "es")["url"] == "https://fal/estreno.mp3"


def test_sintetizar_con_voz_ya_estrenada_no_reescribe_la_fila(base_temporal, fal, monkeypatch):
    v = voces_propias.resolver("acme", f"vp:{_voz(estrenada=True)['id']}")
    # Se cuenta en vez de lanzar: `sintetizar` atrapa cualquier error al marcar
    # (fal ya cobró), así que un AssertionError aquí nunca haría fallar la prueba.
    marcadas = []
    monkeypatch.setattr(voces_propias, "marcar_estrenada", lambda *a, **k: marcadas.append(a))
    voces_propias.sintetizar("acme", v, "Hola", "es")
    assert marcadas == []


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


def test_muestra_no_pierde_lo_pagado_si_no_puede_marcar_estrenada(base_temporal, r2, fal, monkeypatch):
    # La muestra pasa por `sintetizar`: con la base bloqueada justo después de
    # que fal cobró, la muestra se guarda igual y el siguiente ▶ no vuelve a pagar.
    v = _voz(idioma="es", estrenada=False)
    tts, esperas = voces_propias.fal_audio.tts_minimax, []

    def _tts(texto, voice_id, idioma, velocidad=None, timeout=180):
        esperas.append(timeout)
        return tts(texto, voice_id, idioma, velocidad=velocidad, timeout=timeout)
    monkeypatch.setattr(voces_propias.fal_audio, "tts_minimax", _tts)

    def _falla(*a, **k):
        raise RuntimeError("base bloqueada")
    monkeypatch.setattr(voces_propias, "marcar_estrenada", _falla)
    url = voces_propias.muestra("acme", f"vp:{v['id']}", "fi")
    assert url and voces_propias.muestra("acme", f"vp:{v['id']}", "fi") == url
    assert len(fal) == 1 and len(_gastos("acme")) == 1 and esperas == [45]


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
    assert "clientes/acme/materiales/voz_propia_mmx_1.mp3" in r2["borrados"]
    assert voces_propias.borrar("acme", v["id"]) is False


def test_borrar_no_toca_una_grabacion_que_usa_otra_voz(base_temporal, r2, fal):
    g = materiales.registrar("acme", tipo="audio", origen="grabacion", url="https://r2/clientes/acme/materiales/grabacion_y.wav",
                             hash="h_grab_compartida", bytes=10, extra={})
    v1 = _voz(voice_id="mmx_a")
    v2 = _voz(voice_id="mmx_b")
    materiales.actualizar_extra("acme", v1["id"], grabacion_id=g["id"])
    materiales.actualizar_extra("acme", v2["id"], grabacion_id=g["id"])
    assert voces_propias.borrar("acme", v1["id"]) is True
    assert materiales.obtener("acme", g["id"]) is not None
    assert "clientes/acme/materiales/grabacion_y.wav" not in r2["borrados"]
    assert voces_propias.borrar("acme", v2["id"]) is True
    assert materiales.obtener("acme", g["id"]) is None
    assert "clientes/acme/materiales/grabacion_y.wav" in r2["borrados"]


def test_tipo_de_gasto_y_estimados():
    from providers import fal_audio
    assert "voz_propia" in gastos.TIPOS
    assert gastos.estimar("voz_clonada")["usd"] > fal_audio.COSTO_CLONAR_VOZ
    assert gastos.estimar("voz_disenada")["usd"] > fal_audio.COSTO_DISENAR_VOZ  # incluye vista previa y estreno


def test_muestra_propia_guarda_el_detalle_del_gasto_en_el_idioma_del_proyecto(base_temporal, r2, fal, monkeypatch):
    """La ruta au_muestra la pide quien mira, pero el detalle del gasto se
    GUARDA: va en el idioma del proyecto (spec 2026-09-26 §B8)."""
    import idiomas
    v = _voz(idioma="es", estrenada=True)
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    with idiomas.en_idioma("es"):                       # quien escucha, en español
        voces_propias.muestra("acme", f"vp:{v['id']}", "fi")
    (g,) = _gastos("acme")
    assert g["detalle"] == "custom voice sample · Ana · fi"


@pytest.mark.parametrize('mensaje', ['voice not found', 'voice_id does not exist', 'invalid voice id'])
def test_pnd038_voz_remota_borrada_es_error_publico_fijo(base_temporal, monkeypatch, mensaje):
    from tareas.errores_voz import publico
    def fallar(*a, **kw):
        raise RuntimeError(mensaje)
    monkeypatch.setattr(voces_propias.fal_audio, 'tts_minimax', fallar)
    with pytest.raises(ValueError, match='Esa voz ya no está en Mis voces') as exc:
        voces_propias.sintetizar('acme', {'voice_id': 'remota', 'id': 1}, 'hola', 'es')
    assert 'Esa voz ya no está en Mis voces' in str(publico(exc.value, {'id': 1}, 'voz', 'Error %(tipo)s'))


def test_pnd040_borrar_ultima_voz_no_reutiliza_su_id(base_temporal):
    vieja = _voz(voice_id='vieja')
    with db.conectar() as con:
        con.execute(db.material.delete().where(db.material.c.id == vieja['id']))
    nueva = _voz(voice_id='nueva')
    assert nueva['id'] > vieja['id']
    assert voces_propias.resolver('acme', f"vp:{vieja['id']}") is None


@pytest.mark.parametrize("ext", [".ogg", ".aac"])
def test_pnd095_grabacion_larga_rechazada_antes_de_convertir(base_temporal, monkeypatch, tmp_path, ext):
    monkeypatch.setattr(voces_propias, "_duracion_ms", lambda ruta: voces_propias.MAX_GRABACION_MS + 1)
    conversiones = []
    def convertir(origen, salida):
        conversiones.append((origen, salida))
        with open(salida, "wb") as f:
            f.write(b"mp3 falso")
    monkeypatch.setattr(voces_propias, "_convertir_a_mp3", convertir)
    with pytest.raises(voces_propias.EntradaInvalida) as exc:
        voces_propias.guardar_grabacion("acme", _Archivo("voz" + ext), str(tmp_path / "grabacion"))
    assert exc.value.args[0] == voces_propias.MENSAJES["larga"]
    assert conversiones == []
    assert list((tmp_path / "grabacion").iterdir()) == []
