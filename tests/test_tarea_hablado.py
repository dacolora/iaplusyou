"""Tarea hablado_voz (spec 2026-10-01 §3): la voz del anuncio hablado con la
caché de Audios, el gasto `locucion` y errores que nunca llevan el guion."""
import pytest
import sqlalchemy as sa

import audios
import db
import materiales

SECRETO = 'fal.ai 422: {"input": {"text": "mi guion secreto"}}'


def _gastos(cliente):
    with db.conectar() as con:
        return [dict(f._mapping) for f in con.execute(sa.select(db.gasto).where(db.gasto.c.cliente == cliente))]


@pytest.fixture()
def entorno(base_temporal, monkeypatch):
    import tareas.hablado as th
    llamadas = []
    monkeypatch.setattr(audios.fal_audio, "tts", lambda texto, voz, idioma="es", velocidad=None, **kw:
                        llamadas.append(texto) or {"url": "https://fal/v.mp3", "costo_usd": 0.0028})
    monkeypatch.setattr(audios, "descargar_url", lambda url, destino: (open(destino, "wb").write(b"VOZ"), destino)[1])
    monkeypatch.setattr(audios.r2_uploader, "upload_file", lambda local, key, ct: f"https://r2/{key}")
    monkeypatch.setattr(audios.cortes, "duracion", lambda path: 7.05)
    monkeypatch.setattr(th.trabajos, "reportar", lambda *a, **k: None)
    return {"th": th, "llamadas": llamadas}


def _tarea(tid=4, **k):
    p = {"cliente": "acme", "texto": "Estas chanclas son una nube.", "voz": "Rachel", "idioma": "es",
         "velocidad": "normal"}
    p.update(k)
    return {"id": tid, "job_id": "acme__hablado_voz", "payload": p}


def test_crea_la_voz_y_registra_el_gasto_una_sola_vez(entorno):
    th = entorno["th"]
    assert th.ejecutar(_tarea()) == th.MENSAJES["lista"]
    h = audios.hash_voz("Estas chanclas son una nube.", "Rachel", "es", "normal")
    m = materiales.buscar_hash("acme", h)
    assert m["origen"] == "voz" and m["duracion_ms"] == 7050
    th.ejecutar(_tarea(tid=5))                    # misma voz: sale de la caché
    assert entorno["llamadas"] == ["Estas chanclas son una nube."]
    (g,) = _gastos("acme")
    assert (g["tipo"], g["usd"], g["referencia"]) == ("locucion", 0.0028, f"locucion:{h[:12]}:t4")


def test_el_error_del_proveedor_nunca_lleva_el_guion(entorno, monkeypatch):
    def _revienta(*a, **k):
        raise RuntimeError(SECRETO)
    monkeypatch.setattr(audios.fal_audio, "tts", _revienta)
    with pytest.raises(RuntimeError) as e:
        entorno["th"].ejecutar(_tarea())
    assert str(e.value) == "No pude crear la voz; intenta de nuevo (RuntimeError)."
    assert "secreto" not in str(e.value) and str(e.value.__cause__) == SECRETO


def test_una_voz_propia_borrada_sale_con_su_mensaje_fijo(entorno):
    with pytest.raises(ValueError) as e:
        entorno["th"].ejecutar(_tarea(voz="vp:999"))
    assert str(e.value) == "Esa voz ya no está en Mis voces."


def test_registrada_en_el_carril_de_crear_y_un_trabajo_por_proyecto():
    import tareas
    import worker
    tareas.cargar_todas()
    import tareas.hablado as th
    assert tareas.REGISTRO["hablado_voz"] is th.ejecutar
    assert "hablado_voz" in worker.CARRIL_CREAR
    assert th.job_id("acme") == "acme__hablado_voz" and th.ETAPAS[0][0] == "Sintetizando la voz"
