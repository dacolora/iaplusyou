"""Revisión final de cobros (2026-10-08): los frenos de las rutas y funciones que
llaman al proveedor dentro de la petición, y que son el ÚNICO freno de su
camino (no hay `trabajos.encolar` detrás que vuelva a pedir saldo). Sin saldo:
402 (o el salto que toque) y el proveedor falso no se llama. Cada prueba falla
si se quita el `libro.exigir` que protege."""
import pytest
import sqlalchemy as sa

from tests.test_rutas_guiones_pipeline import app as app_pipeline  # noqa: F401 — fixture
from tests.test_rutas_guiones_pipeline import catalogo_vacio  # noqa: F401 — fixture
from tests.test_rutas_organico import app as app_organico  # noqa: F401 — fixture
from tests.test_rutas_referentes import app as app_referentes  # noqa: F401 — fixture
from tests.test_organico import proyecto  # noqa: F401 — fixture
from tests.test_voces_propias import fal, r2  # noqa: F401 — fixtures


@pytest.fixture()
def libro(base_temporal):
    from cobros import libro as mod
    return mod


def _cobra(libro, cliente="acme", milesimas=0):
    import db
    libro.configurar(cliente, usuario="admin", cobrar=True)
    if milesimas:
        with db.conectar() as con:
            libro.acreditar(con, cliente, "ajuste", milesimas, "ajuste", usuario="admin", detalle="prueba")


def _gastos(cliente="acme"):
    import db
    with db.conectar() as con:
        return [dict(r._mapping) for r in con.execute(sa.select(db.gasto).where(db.gasto.c.cliente == cliente)).all()]


def _es_402(r):
    return r.status_code == 402 and r.get_json()["saldo_insuficiente"] is True


# --- Leer referente (referentes/rutas.py, Claude en la petición) -----------------------------

def test_leer_referente_sin_saldo_no_llama_a_claude(app_referentes, monkeypatch, libro):
    from referentes import lectura
    from tests.test_rutas_referentes import _sembrar
    monkeypatch.setattr("proyectos.referentes_copycoders", lambda cliente: True)
    ids = _sembrar()
    llamadas = []
    monkeypatch.setattr(lectura, "leer", lambda r: llamadas.append(r["id"]) or ({}, 1, 1))
    monkeypatch.setattr(lectura, "medir", lambda url: (1, 1))
    _cobra(libro)
    r = app_referentes["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/leer", headers={"X-Requested-With": "fetch"})
    assert _es_402(r)
    assert llamadas == [] and _gastos() == []


# --- pipeline de Flow Plus: corre en un hilo de la petición (trabajos.iniciar) ----------------

def _video(app):
    from tests.test_rutas_guiones_pipeline import BASE, FORM_VIDEO, _confirmado
    gid = _confirmado(app)
    vid = app["c"].post(f"{BASE}/guiones/{gid}/videos", json=FORM_VIDEO).get_json()["video_id"]
    return BASE, vid


@pytest.mark.parametrize("paso", ["recorte/proponer", "armar"])
def test_pipeline_de_flow_plus_sin_saldo_no_lanza_el_hilo(app_pipeline, catalogo_vacio, libro, paso):
    from guiones import datos
    base, vid = _video(app_pipeline)
    antes = len(app_pipeline["iniciados"])
    estado = datos.video("acme", vid)["estado"]
    _cobra(libro)
    r = app_pipeline["c"].post(f"{base}/videos/{vid}/{paso}", json={})
    assert _es_402(r)
    assert len(app_pipeline["iniciados"]) == antes        # ni recorte ni armar arrancan
    assert datos.video("acme", vid)["estado"] == estado    # tampoco cambia el estado


# --- muestra de una voz propia (fal en la petición) -------------------------------------------

def test_muestra_de_voz_propia_sin_saldo_no_llama_a_fal(base_temporal, r2, fal, libro):
    import voces_propias
    from cobros import SaldoInsuficiente
    from tests.test_voces_propias import _voz
    v = _voz(idioma="es", estrenada=True)
    _cobra(libro)
    with pytest.raises(SaldoInsuficiente):
        voces_propias.muestra("acme", f"vp:{v['id']}", "fi")
    assert fal == [] and _gastos() == []


# --- caption orgánico: organico.redactar y la ruta «Escribir con IA» --------------------------

def test_redactar_sin_saldo_usa_el_texto_determinista_sin_llamar_a_claude(proyecto, monkeypatch, libro):
    import generador_prompts
    from tests.test_organico import _pieza, _producto
    _producto()
    pid = _pieza(proyecto["db"])
    llamadas = []
    monkeypatch.setattr(generador_prompts, "caption_organico", lambda ctx, pl: llamadas.append(pl) or {})
    _cobra(libro)
    out = proyecto["organico"].redactar("acme", pid, ["instagram"])
    assert llamadas == [] and _gastos() == []
    assert out["instagram"]["extra"]["fallback"] is True and out["instagram"]["caption"]


def test_escribir_con_ia_sin_saldo_responde_402_sin_redactar(app_organico, base_temporal, monkeypatch, libro):
    from tests.test_experimentos_db import _pieza
    pid = _pieza(base_temporal)
    pedidas = []
    monkeypatch.setattr(app_organico["dashboard"].organico, "redactar", lambda *a: pedidas.append(a) or {})
    _cobra(libro)
    r = app_organico["c"].post("/cliente/acme/organico/redactar",
                               data={"pieza_id": str(pid), "plataformas": ["instagram"]},
                               headers={"X-Requested-With": "fetch"})
    assert _es_402(r)
    assert pedidas == []


# --- regla de fidelidad de un producto importado (importador, dentro de una sync exenta) ------

def test_regla_de_un_producto_importado_sin_saldo_no_llama_a_claude(libro, monkeypatch):
    import generador_prompts
    import importador
    llamadas = []
    monkeypatch.setattr(generador_prompts, "regla_fidelidad", lambda *a: llamadas.append(a) or "Idéntico.")
    monkeypatch.setattr("idiomas.de_proyecto", lambda c: "es")
    _cobra(libro)
    assert importador._regla_si_hay_saldo("acme", "Espejo", "redondo", "producto") == ""
    assert llamadas == []
    _cobra(libro, milesimas=10_000)
    assert importador._regla_si_hay_saldo("acme", "Espejo", "redondo", "producto") == "Idéntico."
    assert len(llamadas) == 1
