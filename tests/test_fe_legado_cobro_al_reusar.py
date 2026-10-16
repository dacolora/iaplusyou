"""PND-337 (decisión 2026-10-15, lote 3): el camino legado de Final edition (`FINAL_EDITION_LEGADO=1`) no tenía el
cobro al reusar de PND-314. Si una final legada falla después de pagar, el guion base que escribió se revierte y la
pista de música que pagó queda en la caché global; la siguiente producción los reusaba a US$ 0 y esa parte nunca se
cobraba. Ahora se cobra en la final que sí se entrega (el costo pasa de la fila fallida a la entregada)."""
import os

import pytest
import sqlalchemy as sa

import db
import final_edition
from final_edition import musica, render
from tests.test_fe_producir import GUION_BASE, _wav, clip, entorno  # noqa: F401 — el entorno falso del legado

pytestmark = pytest.mark.usefixtures("margen_1_5")


def _filas():
    import gastos
    return {f["referencia"]: f for f in gastos.historial("acme")}


def _cobrado_de(ref):
    g, m = db.gasto, db.movimiento_saldo
    with db.conectar() as con:
        gid = con.execute(sa.select(g.c.id).where(g.c.cliente == "acme", g.c.referencia == ref)).scalar()
        return -sum(r.milesimas for r in con.execute(sa.select(m.c.milesimas).where(m.c.gasto_id == gid)))


def _total_gasto():
    with db.conectar() as con:
        return round(con.execute(sa.select(sa.func.sum(db.gasto.c.usd)).where(db.gasto.c.cliente == "acme")).scalar(), 4)


def _producir(n, cf_id, idioma="es", pais="CO", opciones=None):
    """Como el worker: dentro de su trabajo, y si falla, revierte los cobros de esa tarea."""
    from cobros import libro
    with libro.en_trabajo(n, f"job-{n}"):
        try:
            return final_edition.producir("acme", cf_id, idioma, pais, opciones or {}, ref_sufijo=f":t{n}")
        except Exception:
            libro.revertir_trabajo("acme", f"job-{n}", "falló", desde_tarea=n)
            raise


def _render(monkeypatch, falla):
    original = getattr(render.componer, "original", render.componer)   # el falso del entorno, no otra envoltura

    def componer(*a, **k):
        if falla:
            raise RuntimeError("ffmpeg murió")
        return original(*a, **k)
    componer.original = original
    monkeypatch.setattr(render, "componer", componer)


def test_el_guion_base_de_una_final_legada_fallida_se_cobra_al_reusarlo(entorno, monkeypatch):
    from cobros import libro
    assert os.environ.get("FINAL_EDITION_LEGADO") == "1"
    libro.configurar("acme", usuario="admin", cobrar=True)
    cf_id = entorno["cf_id"]
    _render(monkeypatch, falla=True)
    with pytest.raises(RuntimeError):
        _producir(1, cf_id)
    f = _filas()
    assert f[f"guion:{cf_id}:t1"]["usd"] == pytest.approx(0.011) and _cobrado_de(f"guion:{cf_id}:t1") == 0
    total = _total_gasto()

    _render(monkeypatch, falla=False)
    _producir(2, cf_id)
    f = _filas()
    nueva = f[f"final:{cf_id}__es_CO:t2"]
    assert nueva["usd"] == pytest.approx(0.32 + 0.011)          # localización + voz de esta, + el guion base reusado
    assert _cobrado_de(f"final:{cf_id}__es_CO:t2") == libro.precio_milesimas(0.331, 1.5)
    assert f[f"guion:{cf_id}:t1"]["usd"] == 0
    assert _total_gasto() == pytest.approx(total + 0.32)        # solo lo nuevo de esta corrida; el guion, una vez

    _producir(3, cf_id)                                         # reproducirla no vuelve a cobrar el guion
    assert _filas()[f"final:{cf_id}__es_CO:t3"]["usd"] == pytest.approx(0.32)


def test_la_musica_que_pago_una_final_legada_fallida_se_cobra_al_reusarla(entorno, monkeypatch, tmp_path):
    import creative_flow
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    cf_id = entorno["cf_id"]
    creative_flow.guardar_guion_base("acme", cf_id, dict(GUION_BASE))     # el guion ya existía y estaba cobrado
    cacheadas = set()

    def pista(estilo, segundos, carpeta_cache=None, on_progreso=None):
        clave = f"{estilo}_15"
        generada = clave not in cacheadas
        cacheadas.add(clave)
        return ({"archivo": _wav(str(tmp_path / "pista.wav")), "url": "https://r2/m.wav", "estilo": estilo,
                 "generada": generada, "clave": clave}, 0.02 if generada else 0.0)
    monkeypatch.setattr(musica, "obtener_pista", pista)
    _render(monkeypatch, falla=True)
    with pytest.raises(RuntimeError):
        _producir(1, cf_id)
    fallida = _filas()[f"final:{cf_id}__es_CO:t1"]
    assert fallida["usd"] == pytest.approx(0.34) and _cobrado_de(f"final:{cf_id}__es_CO:t1") == 0

    _render(monkeypatch, falla=False)
    _producir(2, cf_id)
    f = _filas()
    assert f[f"final:{cf_id}__es_CO:t2"]["usd"] == pytest.approx(0.32 + 0.02)    # la pista reusada se cobra aquí
    assert f[f"final:{cf_id}__es_CO:t1"]["usd"] == pytest.approx(0.32)           # y baja de la fila fallida
    assert _cobrado_de(f"final:{cf_id}__es_CO:t2") == libro.precio_milesimas(0.34, 1.5)


def test_un_proyecto_que_no_cobra_no_mueve_nada_en_el_legado(entorno, monkeypatch):
    cf_id = entorno["cf_id"]
    _render(monkeypatch, falla=True)
    with pytest.raises(RuntimeError):
        _producir(1, cf_id)
    _render(monkeypatch, falla=False)
    _producir(2, cf_id)
    f = _filas()
    assert f[f"guion:{cf_id}:t1"]["usd"] == pytest.approx(0.011)
    assert f[f"final:{cf_id}__es_CO:t2"]["usd"] == pytest.approx(0.32)
