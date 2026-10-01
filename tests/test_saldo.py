"""Proveedor sin saldo (incidente 2026-09-30: WaveSpeed se quedó sin saldo a
las 11:57 y los videos fallaron con el JSON crudo en la tarjeta). `saldo.marcar`
deja constancia (kv `sin_saldo:<proveedor>`) y avisa al administrador UNA vez
por ventana; `vigente` es lo que pinta el aviso de Crear; la próxima generación
que sale bien lo `limpia`. Nada de esto lanza: un aviso nunca tumba una tarea."""
import pytest

import idiomas
import saldo


@pytest.fixture()
def avisos(base_temporal, monkeypatch):
    """`saldo._avisar_admin` ahora pasa funciones (asunto/cuerpo se arman por
    admin, en su idioma, dentro de `notificaciones.avisar_admin`); acá se
    resuelven en español para que las aserciones existentes (texto llano) no
    cambien. `test_aviso_al_admin_en_el_idioma_de_cada_uno` prueba las
    funciones tal cual, sin resolverlas."""
    lista = []
    def _avisar_admin(tipo, asunto, cuerpo, cliente=""):
        with idiomas.en_idioma("es"):
            a = asunto() if callable(asunto) else asunto
            c = cuerpo() if callable(cuerpo) else cuerpo
        lista.append((tipo, a, c, cliente))
        return 0
    monkeypatch.setattr(saldo.notificaciones, "avisar_admin", _avisar_admin)
    return lista


def test_marcar_avisa_al_admin_una_sola_vez(avisos):
    assert saldo.marcar("wavespeed", "Insufficient credits.", cliente="happyflops") is True
    assert saldo.marcar("wavespeed", "Insufficient credits.", cliente="otro") is False
    assert len(avisos) == 1
    tipo, asunto, cuerpo, cliente = avisos[0]
    assert tipo == "sin_saldo" and "WaveSpeed" in asunto and cliente == "happyflops"
    assert "https://wavespeed.ai/top-up" in cuerpo and "happyflops" in cuerpo and "Insufficient credits." in cuerpo
    v = saldo.vigente("wavespeed")
    assert v["proveedor"] == "wavespeed" and v["nombre"] == "WaveSpeed" and v["recarga"] == "https://wavespeed.ai/top-up"
    assert v["desde"] and v["fallos"] == 2


def test_limpiar_quita_el_aviso_y_la_siguiente_falta_vuelve_a_avisar(avisos):
    saldo.marcar("wavespeed", "x", cliente="acme")
    saldo.limpiar("wavespeed")
    assert saldo.vigente("wavespeed") is None
    assert saldo.marcar("wavespeed", "x", cliente="acme") is True
    assert len(avisos) == 2


def test_se_vuelve_a_avisar_pasada_la_ventana(avisos, monkeypatch):
    reloj = [1_000_000.0]
    monkeypatch.setattr(saldo.time, "time", lambda: reloj[0])
    saldo.marcar("wavespeed", "x")
    reloj[0] += saldo.REAVISO_S - 10
    assert saldo.marcar("wavespeed", "x") is False
    reloj[0] += 20
    assert saldo.marcar("wavespeed", "x") is True
    assert len(avisos) == 2


def test_el_aviso_vence_solo_si_nadie_vuelve_a_fallar(avisos, monkeypatch):
    reloj = [1_000_000.0]
    monkeypatch.setattr(saldo.time, "time", lambda: reloj[0])
    saldo.marcar("wavespeed", "x")
    reloj[0] += saldo.VIGENCIA_S + 1
    assert saldo.vigente("wavespeed") is None


def test_nada_lanza_aunque_la_base_falle(base_temporal, monkeypatch):
    def _rota():
        raise RuntimeError("base caída")
    monkeypatch.setattr(saldo.db, "conectar", _rota)
    assert saldo.marcar("wavespeed", "x") is False
    assert saldo.vigente("wavespeed") is None
    saldo.limpiar("wavespeed")


def test_proveedor_desconocido_no_se_marca(avisos):
    assert saldo.marcar("otro", "x") is False and saldo.vigente("otro") is None and avisos == []


def test_aviso_al_admin_en_el_idioma_de_cada_uno(base_temporal, monkeypatch):
    """Bug confirmado tras la fusión: `_avisar_admin` armaba asunto y cuerpo
    con `gettext` ya resueltos en el idioma del worker (el del proyecto) y se
    los pasaba hechos a `avisar_admin`, así que TODO admin los veía en ese
    idioma. Ahora pasa funciones (como los otros tres llamadores en
    dashboard.py): `avisar_admin` las llama una vez por admin, en el suyo."""
    capturado = {}
    monkeypatch.setattr(saldo.notificaciones, "avisar_admin",
                        lambda tipo, asunto, cuerpo, cliente="": capturado.update(
                            tipo=tipo, asunto=asunto, cuerpo=cuerpo, cliente=cliente) or 1)
    saldo.marcar("wavespeed", "Insufficient credits.", cliente="happyflops")
    assert callable(capturado["asunto"]) and callable(capturado["cuerpo"])
    with idiomas.en_idioma("es"):
        assert capturado["asunto"]() == "WaveSpeed se quedó sin saldo"
        assert capturado["cuerpo"]() == (
            "Una generación del proyecto happyflops falló porque la cuenta de WaveSpeed de Creatv no tiene saldo. "
            "Mientras no se recargue en https://wavespeed.ai/top-up, Crear y Cambiar producto no pueden generar; "
            "los intentos fallidos no se cobran. Respuesta del proveedor: Insufficient credits.")
    with idiomas.en_idioma("en"):
        assert capturado["asunto"]() == "WaveSpeed ran out of credit"
        assert capturado["cuerpo"]() == (
            "A generation in project happyflops failed because Creatv's WaveSpeed account has no credit. Until it "
            "is topped up at https://wavespeed.ai/top-up, Create and Change product cannot generate; failed "
            "attempts are not charged. Provider response: Insufficient credits.")
