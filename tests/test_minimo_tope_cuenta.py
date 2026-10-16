"""PND-323 (decisión 2026-10-13): «Nuevo experimento» dice desde qué total Meta acepta el tope de campaña con el
mínimo REAL de la cuenta (`min_campaign_group_spend_cap`), leído de Meta una vez y guardado con la conexión; sin
esa lectura dice «el mínimo de tu cuenta de Meta» sin inventar una cifra. Antes decía 400 000 COP (una estimación)
cuando colorado_forja acepta 200 000 COP y happyflops 1 000 SEK. Sin red: Meta va con dobles."""
import json
import os

import pytest

from tests.test_lanzador import entorno  # noqa: F401  (fixture: experimento con piezas y Meta falso)
from tests.test_rutas_experimentos import app  # noqa: F401  (fixture: la app con Meta conectado en COP)


@pytest.fixture()
def mc(tmp_path, monkeypatch):
    import meta_conexion
    monkeypatch.setattr(meta_conexion, "BASE_DIR", str(tmp_path))
    return meta_conexion


def _guardar(mc, datos, cliente="acme"):
    ruta = os.path.join(mc.BASE_DIR, "clientes", cliente)
    os.makedirs(ruta, exist_ok=True)
    with open(os.path.join(ruta, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(datos, f)


# ---------- guardar el mínimo con la conexión ----------

def test_el_minimo_se_guarda_con_la_conexion_de_esa_cuenta_y_solo_si_cambia(mc):
    _guardar(mc, {"ad_account_id": "act_1", "moneda": "COP", "token": "t", "page_id": "p"})
    assert mc.guardar_tope_minimo("acme", "1", {"min_campaign_group_spend_cap": "200000"}) is True
    datos = mc._cargar_crudo("acme")
    assert datos[mc.CAMPO_TOPE_MINIMO] == 200000 and datos["token"] == "t" and datos["page_id"] == "p"
    assert mc.guardar_tope_minimo("acme", "act_1", {"min_campaign_group_spend_cap": 200000}) is False   # ya estaba
    # Otra cuenta (una reconexión en medio): no se pisa.
    assert mc.guardar_tope_minimo("acme", "act_2", {"min_campaign_group_spend_cap": "5"}) is False
    # Sin dato, cero o basura: no se guarda nada.
    for raro in ({}, {"min_campaign_group_spend_cap": None}, {"min_campaign_group_spend_cap": "0"},
                 {"min_campaign_group_spend_cap": "x"}):
        assert mc.guardar_tope_minimo("acme", "act_1", raro) is False
    assert mc._cargar_crudo("acme")[mc.CAMPO_TOPE_MINIMO] == 200000


def test_en_modo_agencia_se_suma_sin_tocar_la_asignacion(mc):
    _guardar(mc, {"modo": "agencia", "ad_account_id": "act_7", "moneda": "SEK", "asignado_por": "admin",
                  "propia_respaldo": {"token": "viejo"}})
    assert mc.guardar_tope_minimo("acme", "act_7", {"min_campaign_group_spend_cap": "100000"}) is True
    datos = mc._cargar_crudo("acme")
    assert datos["modo"] == "agencia" and datos["propia_respaldo"] == {"token": "viejo"} and datos["asignado_por"] == "admin"
    assert datos[mc.CAMPO_TOPE_MINIMO] == 100000


def test_sin_conexion_no_escribe_nada(mc, tmp_path):
    assert mc.guardar_tope_minimo("acme", "act_1", {"min_campaign_group_spend_cap": "200000"}) is False
    assert not (tmp_path / "clientes").exists()          # ni el meta.json ni su .lock


def test_lanzar_lee_la_cuenta_y_deja_el_minimo_guardado(entorno, mc):  # noqa: F811
    _guardar(mc, {"ad_account_id": "act_1", "moneda": "COP", "token": "t", "page_id": "2"})
    entorno["lanzador"].lanzar("acme", entorno["eid"])
    assert mc._cargar_crudo("acme")[mc.CAMPO_TOPE_MINIMO] == 200000      # lo que la cuenta falsa dice en COP


def test_conectar_propia_guarda_el_minimo_de_la_cuenta_elegida(mc, base_temporal, monkeypatch):
    import dashboard
    import proyectos
    from tests.test_rutas_experimentos import _cliente_admin
    monkeypatch.setattr(proyectos, "_path", lambda cliente: os.path.join(mc.BASE_DIR, f"{cliente}.json"))
    cuenta = {"id": "act_1", "name": "Cuenta SEK", "currency": "SEK", "min_campaign_group_spend_cap": "100000"}
    mc.guardar_pendiente("acme", {"token": "TOK", "tipo_token": "bearer", "expira_en": None, "business_id": "b1",
                                  "usuario_meta": "Dueño", "activos": {"ad_accounts": [cuenta], "pages": []}})
    r = _cliente_admin(dashboard).post("/cliente/acme/meta/elegir", data={"ad_account_id": "act_1", "page_id": ""})
    assert r.status_code == 302
    assert mc._cargar_crudo("acme")[mc.CAMPO_TOPE_MINIMO] == 100000


def test_la_lectura_de_cuentas_pide_el_minimo(mc, monkeypatch):
    import meta_agencia
    pedidos = []
    monkeypatch.setattr(mc, "_graph_get", lambda edge, token, params=None, timeout=30: pedidos.append((edge, params)) or {"data": []})
    mc.listar_activos("TOK")
    assert "min_campaign_group_spend_cap" in pedidos[0][1]["fields"]
    assert "min_campaign_group_spend_cap" in meta_agencia.CAMPOS_CUENTA
    assert meta_agencia._cuenta({"id": "act_9", "min_campaign_group_spend_cap": "300000"}, "socio")[
        "min_campaign_group_spend_cap"] == "300000"


# ---------- lo que dice la pantalla ----------

def test_minimo_de_cuenta_en_la_moneda_y_nada_inventado_sin_lectura():
    import lanzador
    assert lanzador.minimo_tope_de_cuenta({"tope_minimo_meta": 200000}, "COP") == 200000.0     # COP va entero
    assert lanzador.minimo_tope_de_cuenta({"tope_minimo_meta": 100000}, "SEK") == 1000.0       # SEK en centavos
    assert lanzador.minimo_tope_de_cuenta({"moneda": "COP"}, "COP") is None
    assert lanzador.minimo_tope_de_cuenta(None, "COP") is None
    assert lanzador.minimo_tope_de_cuenta({"tope_minimo_meta": 100000}, "XXX") is None         # fuera de la tabla


def _nota(html):
    i = html.index('<div class="exp-nota">')
    return html[i:html.index("</div>", i)]


def _con_cuenta(app, monkeypatch, datos):  # noqa: F811
    from tests.test_experimentos_db import _pieza
    monkeypatch.setattr(app["dashboard"].meta_conexion, "cargar", lambda c: datos)
    return _pieza


@pytest.mark.parametrize("datos, cifra, data_tope", [
    ({"moneda": "COP", "tope_minimo_meta": 200000}, "200.000 COP", "200000.0"),      # colorado_forja
    ({"moneda": "SEK", "tope_minimo_meta": 100000}, "1.000 SEK", "1000.0"),          # happyflops
])
def test_la_pantalla_dice_el_minimo_real_de_la_cuenta(app, base_temporal, monkeypatch, datos, cifra, data_tope):  # noqa: F811
    _pieza = _con_cuenta(app, monkeypatch, datos)
    _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_2")
    html = app["c"].get("/cliente/acme/experimentos/nuevo").get_data(as_text=True)
    nota = _nota(html)
    assert f"tope de la campaña desde {cifra}, el mínimo que tu cuenta de Meta acepta" in nota
    assert "400.000" not in html and f'data-tope-campana="{data_tope}"' in html


def test_sin_lectura_dice_el_minimo_de_tu_cuenta_sin_cifra(app, base_temporal, monkeypatch):  # noqa: F811
    _pieza = _con_cuenta(app, monkeypatch, {"moneda": "COP"})
    _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_2")
    html = app["c"].get("/cliente/acme/experimentos/nuevo").get_data(as_text=True)
    nota = _nota(html)
    assert "si llega al mínimo de tu cuenta de Meta" in nota
    assert not any(ch.isdigit() for ch in nota.split("</p>")[1]), nota      # la línea del tope no trae números
    assert "400.000" not in html and 'data-tope-campana=""' in html
