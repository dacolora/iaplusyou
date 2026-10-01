"""Revisión final de Audios Europa (F1): el error de un proveedor nunca llega a
/trabajo/<job_id>/estado, que no tiene auth y cuyo job_id se adivina
(`<proyecto>__voz_propia`, `<proyecto>__audio_generar`). El cuerpo de un error
de fal repite el input — la URL de la grabación, la descripción, el texto del
anuncio —: las dos tareas solo dejan pasar sus msgids fijos, traducidos, y
cualquier otro error sale como un mensaje fijo con su tipo."""
import json

import pytest
import sqlalchemy as sa

import audios
import db
import idiomas
import materiales
import voces_propias

SECRETO = 'fal.ai 422: {"input": {"audio_url": "https://r2/clientes/acme/materiales/grabacion_secreta.wav"}}'


def _revienta(*a, **k):
    raise RuntimeError(SECRETO)


def _sin_secreto(texto):
    return "grabacion_secreta" not in (texto or "") and "fal.ai 422" not in (texto or "")


@pytest.fixture()
def entorno(base_temporal, monkeypatch, tmp_path):
    import proyectos
    import tareas.audios as ta
    import tareas.voces_propias as tv
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(tv.trabajos, "reportar", lambda *a, **k: None)
    borrados = []
    monkeypatch.setattr(materiales.r2_uploader, "delete_file", lambda key: borrados.append(key))
    monkeypatch.setattr(ta, "carpeta_trabajo", lambda cliente, h: str(tmp_path / "trabajo" / h[:8]))
    return {"ta": ta, "tv": tv, "borrados": borrados}


def _grabacion():
    return materiales.registrar("acme", tipo="audio", origen="grabacion",
                                url="https://r2/clientes/acme/materiales/grabacion_secreta.wav",
                                hash="h_grabacion_secreta", bytes=10, duracion_ms=15000, extra={"nombre": "Mi voz"})


def _clon(grabacion_id):
    return {"cliente": "acme", "forma": "clonar", "nombre": "Ana", "idioma": "es", "grabacion_id": grabacion_id,
            "consentimiento": {"usuario": "admin", "fecha": "2026-09-30T10:00:00",
                               "texto": voces_propias.TEXTO_CONSENTIMIENTO}}


def _audio(**k):
    p = {"cliente": "acme", "texto": "Hola mundo", "voz": "Rachel", "idioma": "es", "velocidad": "normal",
         "musica_id": None, "inicio_s": 0, "volumen": "media"}
    p.update(k)
    return p


def test_voz_propia_el_error_del_proveedor_sale_como_mensaje_fijo(entorno, monkeypatch):
    monkeypatch.setattr(voces_propias.fal_audio, "clonar_voz_minimax", _revienta)
    with pytest.raises(RuntimeError) as e:
        entorno["tv"].ejecutar({"id": 11, "job_id": "acme__voz_propia", "payload": _clon(_grabacion()["id"])})
    assert _sin_secreto(str(e.value)) and "RuntimeError" in str(e.value)
    assert str(e.value) == "No pude crear la voz; intenta de nuevo (RuntimeError)."
    # La causa queda encadenada para el log del servidor, nunca en el mensaje.
    assert str(e.value.__cause__) == SECRETO


def test_audio_el_error_del_proveedor_sale_como_mensaje_fijo(entorno, monkeypatch):
    monkeypatch.setattr(audios.fal_audio, "tts", _revienta)
    with pytest.raises(RuntimeError) as e:
        entorno["ta"].ejecutar({"id": 12, "job_id": "acme__audio_generar", "payload": _audio()})
    assert _sin_secreto(str(e.value)) and "RuntimeError" in str(e.value)
    assert str(e.value) == "No pude crear el audio; intenta de nuevo (RuntimeError)."
    # En el idioma del proyecto (el worker corre cada tarea dentro de él).
    with idiomas.en_idioma("en"), pytest.raises(RuntimeError) as e:
        entorno["ta"].ejecutar({"id": 18, "job_id": "acme__audio_generar", "payload": _audio()})
    assert str(e.value) == "I couldn't create the audio; try again (RuntimeError)."


def test_un_valueerror_que_no_es_msgid_tampoco_pasa(entorno, monkeypatch):
    def _valor(*a, **k):
        raise ValueError(SECRETO)
    monkeypatch.setattr(voces_propias.fal_audio, "clonar_voz_minimax", _valor)
    monkeypatch.setattr(audios.fal_audio, "tts", _valor)
    with pytest.raises(RuntimeError) as e:
        entorno["tv"].ejecutar({"id": 13, "job_id": "acme__voz_propia", "payload": _clon(_grabacion()["id"])})
    assert _sin_secreto(str(e.value)) and str(e.value).endswith("(ValueError).")
    with pytest.raises(RuntimeError) as e:
        entorno["ta"].ejecutar({"id": 14, "job_id": "acme__audio_generar", "payload": _audio()})
    assert _sin_secreto(str(e.value)) and str(e.value).endswith("(ValueError).")


def test_la_voz_borrada_sigue_mostrando_su_mensaje_traducido(entorno):
    """Un msgid fijo pasa tal cual: la voz propia se borró entre el clic y el
    worker (sin pagar nada)."""
    with pytest.raises(ValueError) as e:
        entorno["ta"].ejecutar({"id": 15, "job_id": "acme__audio_generar", "payload": _audio(voz="vp:999")})
    assert str(e.value) == audios.MENSAJES["voz_borrada"] == "Esa voz ya no está en Mis voces."
    with idiomas.en_idioma("en"), pytest.raises(ValueError) as e:
        entorno["ta"].ejecutar({"id": 16, "job_id": "acme__audio_generar", "payload": _audio(voz="vp:999")})
    assert str(e.value) == "That voice is no longer in My voices."


def test_la_grabacion_borrada_sigue_mostrando_su_mensaje(entorno, monkeypatch):
    monkeypatch.setattr(voces_propias.fal_audio, "clonar_voz_minimax", _revienta)
    with pytest.raises(ValueError) as e:
        entorno["tv"].ejecutar({"id": 17, "job_id": "acme__voz_propia", "payload": _clon(999)})
    assert str(e.value) == voces_propias.MENSAJES["grabacion_borrada"]


def test_el_estado_del_trabajo_nunca_muestra_el_error_del_proveedor(entorno, monkeypatch):
    """De punta a punta: la tarea falla en el worker y ni la fila `tarea` ni lo
    que responde /trabajo/<job_id>/estado traen el cuerpo de fal. Desde la
    auditoría de seguridad 2026-10-01 ese estado solo se le da a quien puede
    entrar al proyecto; sin sesión, el trabajo «no existe»."""
    import cola
    import dashboard
    import tareas
    import worker
    tareas.cargar_todas()
    monkeypatch.setattr(voces_propias.fal_audio, "clonar_voz_minimax", _revienta)
    jid = entorno["tv"].job_id("acme")
    cola.encolar("voz_propia_crear", _clon(_grabacion()["id"]), cliente="acme", job_id=jid, max_intentos=1,
                 etapas=list(entorno["tv"].ETAPAS))
    worker._correr(cola.reclamar(tipos=("voz_propia_crear",)))
    with db.conectar() as con:
        fila = con.execute(sa.select(db.tarea.c.estado, db.tarea.c.error, db.tarea.c.mensaje)
                           .where(db.tarea.c.job_id == jid)).first()
    assert fila.estado == "error" and _sin_secreto(fila.error) and _sin_secreto(fila.mensaje)
    dashboard.app.config["TESTING"] = True
    anonimo = dashboard.app.test_client().get(f"/trabajo/{jid}/estado").get_json()
    assert anonimo["estado"] == "desconocido" and anonimo["mensaje"] is None
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "user_acme"; s["rol"] = "cliente"; s["cliente"] = "acme"
    estado = c.get(f"/trabajo/{jid}/estado").get_json()
    assert estado["estado"] == "error" and "No pude crear la voz; intenta de nuevo (RuntimeError)." in estado["mensaje"]
    assert _sin_secreto(json.dumps(estado, ensure_ascii=False))
