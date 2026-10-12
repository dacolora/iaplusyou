import json
import pytest
from tests.test_meta_ads_bloque3 import auth_falsa  # noqa: F401


def test_campana_acepta_app_promotion(auth_falsa):
    from meta_ads import campaign
    campaign.crear_campaign("X", "OUTCOME_APP_PROMOTION")
    assert json.loads(json.dumps(auth_falsa[-1][2]))["objective"] == "OUTCOME_APP_PROMOTION"


def test_adset_app_lleva_promoted_object_y_link_clicks(auth_falsa):
    from meta_ads import adset
    po = {"application_id": "111", "object_store_url": "https://play.google.com/store/apps/details?id=com.x"}
    adset.crear_adset("A", "c1", "OUTCOME_APP_PROMOTION", {"geo_locations": {"countries": ["CO"]}}, 10000, 7, promoted_object=po)
    payload = auth_falsa[-1][2]
    assert payload["optimization_goal"] == "LINK_CLICKS" and payload["billing_event"] == "IMPRESSIONS"
    assert json.loads(payload["promoted_object"]) == po


def test_adset_app_sin_promoted_object_falla_antes_de_llamar(auth_falsa):
    from meta_ads import adset
    n = len(auth_falsa)
    with pytest.raises(ValueError):
        adset.crear_adset("A", "c1", "OUTCOME_APP_PROMOTION", {}, 10000, 7)
    assert len(auth_falsa) == n


def test_targeting_sistema():
    from meta_ads.targeting import Targeting
    d = Targeting().edad(18, 65).paises(["CO"]).sistema("iOS").to_dict()
    assert d["user_os"] == ["iOS"] and d["device_platforms"] == ["mobile"]
    assert "user_os" not in Targeting().paises(["CO"]).to_dict()
