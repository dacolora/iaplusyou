"""llaves.py: la lista de servicios de Configuración › Puesta a punto y su
estado, fuera de dashboard.py (para que alertas.py la lea sin importar Flask).
WaveSpeed es la llave que paga todos los videos e imágenes de Crear y no tenía
tarjeta (PND-075); Higgsfield pasa a opcional: solo la usa el flujo viejo
«Nueva idea». El estado se calcula con bool(os.environ.get(var)): ningún valor
de una llave sale de aquí."""
import llaves

VARIABLES_DE_LLAVES = ("ANTHROPIC_API_KEY", "WAVESPEED_API_KEY", "FAL_KEY", "HF_API_KEY_ID", "HF_API_KEY_SECRET")


def _por_id(**kw):
    return {t["id"]: t for t in llaves.estado(**kw)}


def test_wavespeed_sin_la_variable_falta(monkeypatch):
    monkeypatch.delenv("WAVESPEED_API_KEY", raising=False)
    ws = _por_id()["wavespeed"]
    assert ws["estado"] == "falta"
    assert ws["faltan"] == ["WAVESPEED_API_KEY"]
    assert ws["variables"] == ["WAVESPEED_API_KEY"]


def test_wavespeed_con_la_variable_queda_configurada(monkeypatch):
    monkeypatch.setenv("WAVESPEED_API_KEY", "wsp-PRUEBA-999")
    ws = _por_id()["wavespeed"]
    assert ws["estado"] == "configurada" and ws["faltan"] == []


def test_wavespeed_es_obligatoria_y_se_explica_sola(monkeypatch):
    ws = _por_id()["wavespeed"]
    assert ws["opcional"] is False
    assert ws["url"] == "https://wavespeed.ai/"
    assert "Crear" in ws["nota"] and "Sprints" in ws["nota"]
    assert 3 <= len(ws["pasos"]) <= 5
    assert any("WAVESPEED_API_KEY" in p for p in ws["pasos"])
    assert set(ws) >= {"id", "nombre", "para_que", "costo", "estado", "url", "url_texto", "variables", "faltan",
                       "nota", "opcional", "pasos"}


def test_wavespeed_va_justo_despues_de_anthropic_y_el_resto_sigue_igual():
    ids = [t["id"] for t in llaves.estado()]
    assert ids == ["anthropic", "wavespeed", "fal", "gemini", "higgsfield", "r2", "smtp", "meli", "reddit", "youtube_api",
                   "apify", "atria", "trendtrack"]
    assert [s["id"] for s in llaves.SERVICIOS] == ids


def test_higgsfield_es_opcional_y_dice_que_solo_es_del_flujo_viejo():
    hf = next(t for t in llaves.estado() if t["id"] == "higgsfield")
    assert hf["opcional"] is True
    assert "Nueva idea" in hf["nota"] and "Crear no la necesita" in hf["nota"]
    # Las que ya eran obligatorias siguen siéndolo.
    por_id = _por_id()
    assert not por_id["anthropic"]["opcional"] and not por_id["fal"]["opcional"] and not por_id["r2"]["opcional"]


def test_higgsfield_parcial_sigue_diciendo_que_falta(monkeypatch):
    monkeypatch.delenv("HF_API_KEY_SECRET", raising=False)
    monkeypatch.setenv("HF_API_KEY_ID", "solo-el-id")
    hf = _por_id()["higgsfield"]
    assert hf["estado"] == "parcial" and hf["faltan"] == ["HF_API_KEY_SECRET"]


def test_un_valor_en_blanco_cuenta_como_ausente(monkeypatch):
    monkeypatch.setenv("WAVESPEED_API_KEY", "   ")
    assert _por_id()["wavespeed"]["estado"] == "falta"


def test_ningun_valor_de_llave_sale_en_las_tarjetas(monkeypatch):
    for v in VARIABLES_DE_LLAVES:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-prueba-123")
    monkeypatch.setenv("WAVESPEED_API_KEY", "wsp-prueba-456")
    monkeypatch.setenv("HF_API_KEY_ID", "hf-prueba-789")
    plano = repr(llaves.estado())
    for secreto in ("sk-prueba-123", "wsp-prueba-456", "hf-prueba-789"):
        assert secreto not in plano
    assert _por_id()["anthropic"]["estado"] == "configurada"


def test_el_callback_de_meli_reemplaza_el_paso():
    generico = _por_id()["meli"]
    real = _por_id(callback_meli="https://app.test/meli/callback")["meli"]
    assert any("<url del sitio>/meli/callback" in p for p in generico["pasos"])
    assert any("https://app.test/meli/callback" in p for p in real["pasos"])
    assert not any("{callback_meli}" in p for p in generico["pasos"] + real["pasos"])


def test_dashboard_conserva_los_alias(base_temporal):
    import dashboard
    assert dashboard._estado_llaves is llaves.estado
    assert dashboard.SERVICIOS_LLAVES is llaves.SERVICIOS


def test_pnd075_gemini_visible_sin_revelar_llave(monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    tarjeta = _por_id()['gemini']
    assert tarjeta['estado'] == 'falta' and tarjeta['faltan'] == ['GEMINI_API_KEY']
    # También la usa Cambiar producto con Nano Banana, no solo Nueva idea.
    assert not tarjeta['opcional'] and 'Cambiar producto' in tarjeta['para_que']
    secreto = 'valor-falso-gemini-llave-de-prueba'
    monkeypatch.setenv('GEMINI_API_KEY', secreto)
    assert _por_id()['gemini']['estado'] == 'configurada'
    assert secreto not in repr(llaves.estado())
