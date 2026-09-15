import pytest


@pytest.fixture()
def auth_falsa(monkeypatch):
    from meta_ads import auth
    llamadas = []

    def llamar(metodo, edge, payload=None, params=None, dry_run=False):
        llamadas.append((metodo, edge, payload, params))
        if edge.endswith("/insights"):
            return {"data": [{"impressions": "1000", "reach": "800", "frequency": "1.25", "clicks": "40",
                              "inline_link_clicks": "30", "ctr": "4.0", "cpc": "0.5", "cpm": "15", "spend": "15",
                              "actions": [{"action_type": "link_click", "value": "30"}, {"action_type": "purchase", "value": "2"}],
                              "action_values": [{"action_type": "purchase", "value": "90.5"}],
                              "purchase_roas": [{"action_type": "omni_purchase", "value": "6.03"}],
                              "video_thruplay_watched_actions": [{"action_type": "video_view", "value": "120"}],
                              "cost_per_action_type": [{"action_type": "link_click", "value": "0.5"}]}]}
        if metodo == "GET":
            return {"effective_status": "ACTIVE"}
        return {"id": "999"}

    monkeypatch.setattr(auth, "llamar", llamar)
    monkeypatch.setattr(auth, "ad_account_id", lambda: "123")
    return llamadas


def test_campaign_spend_cap(auth_falsa):
    from meta_ads import campaign
    campaign.crear_campaign("X", "OUTCOME_TRAFFIC", spend_cap_centavos=50_000_00)
    assert auth_falsa[-1][2]["spend_cap"] == 50_000_00
    campaign.crear_campaign("X", "OUTCOME_TRAFFIC")
    assert "spend_cap" not in auth_falsa[-1][2]


def test_adset_y_ad_actualizaciones(auth_falsa):
    from meta_ads import ad, adset
    adset.actualizar_presupuesto("77", 2500)
    assert auth_falsa[-1][:3] == ("POST", "77", {"daily_budget": 2500})
    adset.actualizar_estado("77", "ACTIVE")
    assert auth_falsa[-1][:3] == ("POST", "77", {"status": "ACTIVE"})
    ad.actualizar_estado("88", "PAUSED")
    assert auth_falsa[-1][:3] == ("POST", "88", {"status": "PAUSED"})
    with pytest.raises(ValueError):
        adset.actualizar_estado("77", "DELETED")


def test_insights_thruplay_y_ventas(auth_falsa):
    from meta_ads import insights
    r = insights.obtener_resultados("88", objetivo="OUTCOME_TRAFFIC")
    assert r["thruplay"] == 120 and r["thruplay_rate"] == pytest.approx(0.12)
    assert r["compras"] == 2 and r["ingresos"] == 90.5 and r["roas"] == 6.03 and r["alcance"] == 800
    assert r["resultado"] == 30 and r["gasto_usd"] == 15.0 and r["estado_meta"] == "ACTIVE"
    assert "video_thruplay_watched_actions" in auth_falsa[0][3]["fields"]
