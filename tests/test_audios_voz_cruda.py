"""audios.voz_cruda (spec anuncio hablado §3): la voz cruda que comparten
Audios y el anuncio hablado — la misma caché por hash, el gasto `locucion`
apenas el proveedor cobra y nunca dos veces por la misma voz."""
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
def entorno(base_temporal, monkeypatch):
    llamadas, subidos = [], []
    monkeypatch.setattr(audios.fal_audio, "tts", lambda texto, voz, idioma="es", velocidad=None, **kw:
                        llamadas.append(texto) or {"url": "https://fal/v.mp3", "costo_usd": 0.0034})
    monkeypatch.setattr(audios, "descargar_url", lambda url, destino: (open(destino, "wb").write(b"VOZ"), destino)[1])
    monkeypatch.setattr(audios.r2_uploader, "upload_file", lambda local, key, ct: subidos.append(key) or f"https://r2/{key}")
    monkeypatch.setattr(audios.cortes, "duracion", lambda path: 7.05)
    return {"llamadas": llamadas, "subidos": subidos}


def test_sintetiza_registra_el_gasto_y_crea_la_fila(entorno):
    texto = "Estas chanclas son una nube."
    h = audios.hash_voz(texto, "Rachel", "es", "normal")
    m, creado = audios.voz_cruda("acme", texto, "Rachel", "es", "normal", ":t9")
    assert creado and m["hash"] == h and m["origen"] == "voz" and m["tipo"] == "audio" and m["duracion_ms"] == 7050
    assert m["url"] == f"https://r2/clientes/acme/materiales/voz_{h[:16]}.mp3" and m["costo_usd"] == 0.0034
    assert m["extra"] == {"texto": texto, "voz": "Rachel", "voz_ref": "Rachel", "idioma": "es", "velocidad": "normal",
                          "nombre": texto}   # el nombre con que el editor la lista (capa 5a)
    (g,) = _gastos("acme")
    assert (g["tipo"], g["usd"], g["referencia"], g["proveedor"]) == ("locucion", 0.0034, f"locucion:{h[:12]}:t9",
                                                                      "fal/elevenlabs")


def test_la_misma_voz_no_se_paga_dos_veces(entorno):
    m, _ = audios.voz_cruda("acme", "Hola", "Rachel", "es", "normal", ":t1")
    otra_vez, creado = audios.voz_cruda("acme", "Hola", "Rachel", "es", "normal", ":t2")
    assert not creado and otra_vez["id"] == m["id"]
    assert entorno["llamadas"] == ["Hola"] and len(_gastos("acme")) == 1
    de_otro, creada = audios.voz_cruda("otro", "Hola", "Rachel", "es", "normal", ":t3")   # cada proyecto, su caché
    assert creada and de_otro["id"] != m["id"]


def test_con_carpeta_deja_el_mp3_ahi_y_lo_anota(entorno, tmp_path):
    m, _ = audios.voz_cruda("acme", "Hola", "Rachel", "es", "rapida", ":t4", carpeta=str(tmp_path))
    h = audios.hash_voz("Hola", "Rachel", "es", "rapida")
    local = str(tmp_path / f"voz_{h[:16]}.mp3")
    assert m["extra"]["local"] == local and os.path.isfile(local)


def test_si_falla_la_subida_el_gasto_queda_y_no_hay_fila(entorno, monkeypatch):
    def _revienta(local, key, ct):
        raise RuntimeError("R2 caído")
    monkeypatch.setattr(audios.r2_uploader, "upload_file", _revienta)
    with pytest.raises(RuntimeError):
        audios.voz_cruda("acme", "Hola", "Rachel", "es", "normal", ":t5")
    (g,) = _gastos("acme")
    assert g["usd"] == 0.0034
    assert materiales.buscar_hash("acme", audios.hash_voz("Hola", "Rachel", "es", "normal")) is None
