"""meta_ads/insights.py::obtener_resultados. Regresión: un fallo al leer el
estado/motivo de rechazo del anuncio se tragaba con `except Exception: pass`
sin dejar ningún rastro -- la única excepción de toda la plataforma que no
loguea nada. Un fallo persistente de Graph ahí escondería para siempre los
motivos de rechazo, sin que nadie lo notara."""
import logging

from meta_ads import insights


def _fila_metricas():
    return {"data": [{
        "impressions": "1000", "reach": "900", "frequency": "1.1", "clicks": "20", "inline_link_clicks": "15",
        "ctr": "2.0", "cpc": "0.5", "cpm": "10.0", "spend": "10.0", "actions": [{"action_type": "link_click", "value": "15"}],
    }]}


def test_fallo_al_leer_estado_no_pierde_las_metricas_y_deja_registro(monkeypatch, caplog):
    llamadas = {"n": 0}

    def _llamar_falso(metodo, edge, payload=None, params=None, dry_run=False):
        llamadas["n"] += 1
        if edge == "ad_1/insights":
            return _fila_metricas()
        raise RuntimeError("Graph caído")

    monkeypatch.setattr(insights.auth, "llamar", _llamar_falso)

    with caplog.at_level(logging.WARNING):
        r = insights.obtener_resultados("ad_1", objetivo="OUTCOME_TRAFFIC")

    assert r["impresiones"] == 1000 and r["gasto_usd"] == 10.0   # las métricas sí llegaron
    assert llamadas["n"] == 2   # sí intentó las dos llamadas
    assert any("ad_1" in m and "estado" in m.lower() for m in caplog.messages)


def test_estado_se_lee_bien_cuando_no_falla(monkeypatch):
    def _llamar_falso(metodo, edge, payload=None, params=None, dry_run=False):
        if edge == "ad_1/insights":
            return _fila_metricas()
        return {"effective_status": "ACTIVE", "ad_review_feedback": {}, "issues_info": []}

    monkeypatch.setattr(insights.auth, "llamar", _llamar_falso)
    r = insights.obtener_resultados("ad_1")
    assert r["impresiones"] == 1000
