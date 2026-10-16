"""PND-057 (Daniel, 2026-10-13: «dale la alerta al cliente»): si el negocio de la conexión de Meta de un proyecto no
está verificado, Meta puede restringir su app (la primera app de Creatv quedó restringida el 2026-09-14 con la
verificación en revisión). La periódica diaria `meta_revisar_acceso` lee `verification_status` del negocio dueño de la
cuenta publicitaria y lo guarda en meta.json; Alertas avisa al cliente (pruebas de la fuente en
`test_alertas_fuentes.py`). Con dobles: nunca se llama a Meta de verdad."""
import json

import pytest

import meta_conexion as mc

APP = {"app_id": "111", "app_secret": "s3cr3t", "login_config_id": "222"}


@pytest.fixture()
def carpeta(monkeypatch, tmp_path):
    monkeypatch.setattr(mc, "BASE_DIR", str(tmp_path))
    return tmp_path


class _Resp:
    def __init__(self, datos, ok=True, status=200):
        self._datos, self.ok, self.status_code = datos, ok, status
        self.content = b"1"

    def json(self):
        return self._datos


def _meta_falsa(monkeypatch, negocio=None, falla=False, al_leer=None):
    """requests.get de Meta para `GET act_…?fields=business{…}`. Devuelve las llamadas (edge, params)."""
    llamadas = []

    def fake_get(url, params=None, timeout=None):
        edge = url.rsplit("/", 1)[-1]
        llamadas.append((edge, dict(params or {})))
        if not edge.startswith("act_"):
            raise AssertionError(f"llamada inesperada a {url}")
        if al_leer:
            al_leer()
        if falla:
            return _Resp({"error": {"message": "Invalid OAuth access token.", "code": 190}},
                         ok=False, status=400)
        datos = {"id": edge}
        if negocio is not False:
            datos["business"] = negocio if negocio is not None else {
                "id": "1766812841431317", "name": "Forja Habit", "verification_status": "not_verified"}
        return _Resp(datos)
    monkeypatch.setattr(mc.requests, "get", fake_get)
    return llamadas


def _conexion(cliente="acme", **campos):
    mc.guardar_app(cliente, APP)
    datos = {"token": "EAAsecreto123456", "ad_account_id": "act_2122370558355633", "page_id": "9", **campos}
    mc.guardar(cliente, datos)
    return datos


def _meta_json(carpeta, cliente="acme"):
    ruta = carpeta / "clientes" / cliente / "meta.json"
    return json.loads(ruta.read_text()) if ruta.exists() else None


def test_revisar_guarda_el_estado_del_negocio_de_la_cuenta(carpeta, monkeypatch):
    antes = _conexion()
    llamadas = _meta_falsa(monkeypatch)
    info = mc.revisar_negocio("acme")
    assert llamadas == [("act_2122370558355633", {"fields": "business{id,name,verification_status}",
                                                   "access_token": "EAAsecreto123456"})]
    assert info["verificacion"] == "not_verified" and info["id"] == "1766812841431317"
    datos = _meta_json(carpeta)
    assert datos["negocio"]["verificacion"] == "not_verified" and datos["negocio"]["nombre"] == "Forja Habit"
    assert datos["negocio"]["ad_account_id"] == "act_2122370558355633" and datos["negocio"]["revisado_en"]
    assert {k: datos[k] for k in antes} == antes                             # lo demás de la conexión no cambia
    assert mc.negocio_sin_verificar("acme") == {"id": "1766812841431317", "nombre": "Forja Habit",
                                                "verificacion": "not_verified"}


def test_un_negocio_verificado_no_avisa(carpeta, monkeypatch):
    _conexion()
    _meta_falsa(monkeypatch, negocio={"id": "1", "name": "N", "verification_status": "verified"})
    assert mc.revisar_negocio("acme")["verificacion"] == "verified"
    assert mc.negocio_sin_verificar("acme") is None


@pytest.mark.parametrize("negocio", [False, {"id": "1", "name": "N"},
                                     {"id": "1", "name": "N", "verification_status": "algo_nuevo"}])
def test_sin_negocio_o_sin_estado_conocido_no_se_inventa_nada(carpeta, monkeypatch, negocio):
    """Una cuenta personal (sin negocio), un campo que Meta no dejó leer o un estado que no conocemos: sin dato, sin
    alerta."""
    _conexion()
    _meta_falsa(monkeypatch, negocio=negocio)
    assert mc.revisar_negocio("acme")["verificacion"] is None
    assert mc.negocio_sin_verificar("acme") is None


def test_la_revision_de_otra_cuenta_no_avisa(carpeta, monkeypatch):
    """El proyecto cambió de cuenta después de la revisión: lo guardado es de la cuenta vieja y no vale."""
    _conexion()
    _meta_falsa(monkeypatch)
    mc.revisar_negocio("acme")
    datos = _meta_json(carpeta)
    mc.guardar("acme", {**datos, "ad_account_id": "act_999"})
    assert mc.negocio_sin_verificar("acme") is None


def test_revisar_no_pisa_una_reconexion_en_medio(carpeta, monkeypatch):
    _conexion()
    _meta_falsa(monkeypatch, al_leer=lambda: mc.guardar("acme", {"token": "nuevo", "ad_account_id": "act_2"}))
    mc.revisar_negocio("acme")
    datos = _meta_json(carpeta)
    assert datos["token"] == "nuevo" and "negocio" not in datos


def test_revisar_no_revive_una_conexion_borrada(carpeta, monkeypatch):
    _conexion()
    _meta_falsa(monkeypatch, al_leer=lambda: mc._borrar_crudo("acme"))
    mc.revisar_negocio("acme")
    assert _meta_json(carpeta) is None


@pytest.mark.parametrize("caso", ["sin_conexion", "agencia", "sin_token", "sin_cuenta", "cuenta_rara"])
def test_revisar_no_pregunta_lo_que_no_es_suyo(carpeta, monkeypatch, caso):
    llamadas = _meta_falsa(monkeypatch)
    if caso == "agencia":
        mc._escribir_atomico(mc._path("acme"), {"modo": "agencia", "ad_account_id": "act_1", "token": "x"})
    elif caso == "sin_token":
        _conexion(token=None)
    elif caso == "sin_cuenta":
        _conexion(ad_account_id=None)
    elif caso == "cuenta_rara":
        _conexion(ad_account_id="act_1/../me")
    assert mc.revisar_negocio("acme") is None
    assert llamadas == []
    assert mc.negocio_sin_verificar("acme") is None


def test_en_modo_agencia_no_avisa_aunque_haya_algo_guardado(carpeta):
    mc._escribir_atomico(mc._path("acme"), {"modo": "agencia", "ad_account_id": "act_1", "negocio": {
        "id": "1", "nombre": "N", "verificacion": "not_verified", "ad_account_id": "act_1"}})
    assert mc.negocio_sin_verificar("acme") is None


def test_revisar_con_meta_caido_lanza_sin_token_y_sin_tocar_nada(carpeta, monkeypatch):
    _conexion()
    _meta_falsa(monkeypatch, falla=True)
    with pytest.raises(mc.MetaConexionError) as e:
        mc.revisar_negocio("acme")
    assert "EAAsecreto123456" not in str(e.value)
    assert "negocio" not in _meta_json(carpeta)


def test_la_periodica_revisa_el_negocio_aunque_falle_el_vencimiento(carpeta, monkeypatch, base_temporal):
    """`meta_revisar_acceso` (diaria, gratis) revisa las dos cosas de cada proyecto, cada una por su lado."""
    import tareas.meta as tm
    _conexion("acme")
    _conexion("beta")

    def vencimientos(cliente):
        raise mc.MetaConexionError("Meta respondió: algo")
    monkeypatch.setattr(tm.meta_conexion, "revisar_vencimientos", vencimientos)
    _meta_falsa(monkeypatch)
    texto = tm.revisar_acceso({"payload": {}})
    assert _meta_json(carpeta, "acme")["negocio"]["verificacion"] == "not_verified"
    assert _meta_json(carpeta, "beta")["negocio"]["verificacion"] == "not_verified"
    assert "2" in texto


def test_ninguna_pagina_llama_a_meta_para_esto():
    """La verificación se lee solo en la periódica: ni una ruta ni la fuente de Alertas usan `revisar_negocio`."""
    import os
    import re
    import subprocess
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    archivos = subprocess.run(["git", "ls-files", "*.py"], cwd=raiz, capture_output=True, text=True,
                              check=True).stdout.split()
    usos = []
    for a in archivos:
        if a.startswith(("tests/", "meta_ads/")):
            continue
        with open(os.path.join(raiz, a), encoding="utf-8") as f:
            if re.search(r"revisar_negocio(?!`)", f.read()):   # código, no una mención entre `…` de un docstring
                usos.append(a)
    assert sorted(usos) == ["meta_conexion.py", "tareas/meta.py"]
