"""Cada proyecto trae SU propia app de Meta (id, secret, config de login):
clientes/<cliente>/meta_app.json. meta_conexion nunca vuelve a leer
META_APP_ID / META_APP_SECRET / META_LOGIN_CONFIG_ID del entorno — un
proyecto es un mundo aparte y CreatvMachine solo opera con sus credenciales."""
import json
import os
import stat
from urllib.parse import parse_qs, urlparse

import pytest

import meta_conexion as mc


@pytest.fixture()
def carpeta(monkeypatch, tmp_path):
    monkeypatch.setattr(mc, "BASE_DIR", str(tmp_path))
    monkeypatch.setenv("META_REDIRECT_URI", "https://app.example/meta/callback")
    for clave in ("META_APP_ID", "META_APP_SECRET", "META_LOGIN_CONFIG_ID"):
        monkeypatch.setenv(clave, "DEL-ENTORNO-" + clave)
    return tmp_path


APP = {"app_id": "111", "app_secret": "s3cr3t", "login_config_id": "222"}


def test_guardar_app_escribe_0600_y_cargar_la_devuelve(carpeta):
    mc.guardar_app("acme", APP)
    ruta = carpeta / "clientes" / "acme" / "meta_app.json"
    assert ruta.exists()
    assert stat.S_IMODE(os.stat(ruta).st_mode) == 0o600
    assert mc.cargar_app("acme") == APP


def test_cargar_app_sin_archivo_es_none(carpeta):
    assert mc.cargar_app("acme") is None


def test_guardar_app_recorta_y_exige_los_tres_campos(carpeta):
    mc.guardar_app("acme", {"app_id": " 111 ", "app_secret": " s ", "login_config_id": " 222\n"})
    assert mc.cargar_app("acme") == {"app_id": "111", "app_secret": "s", "login_config_id": "222"}
    with pytest.raises(mc.MetaConexionError, match="login_config_id"):
        mc.guardar_app("acme", {"app_id": "1", "app_secret": "s", "login_config_id": ""})


def test_app_publica_nunca_trae_el_secret(carpeta):
    mc.guardar_app("acme", APP)
    assert mc.app_publica("acme") == {"app_id": "111", "login_config_id": "222"}
    assert mc.app_publica("nadie") is None


def test_url_dialogo_usa_la_app_del_cliente_no_el_entorno(carpeta):
    mc.guardar_app("acme", APP)
    q = parse_qs(urlparse(mc.url_dialogo("acme", "st")).query)
    assert q["client_id"] == ["111"]
    assert q["config_id"] == ["222"]
    assert q["state"] == ["st"]


def test_url_dialogo_sin_app_del_cliente_falla_claro(carpeta):
    with pytest.raises(mc.MetaConexionError, match="app de Meta"):
        mc.url_dialogo("acme", "st")


def test_cambiar_code_por_token_usa_secret_del_cliente(carpeta, monkeypatch):
    mc.guardar_app("acme", APP)
    visto = {}

    class R:
        ok = True
        content = b"1"

        def json(self):
            return {"access_token": "tok", "token_type": "bearer"}

    def fake_get(url, params=None, timeout=None):
        visto.update(params)
        return R()
    monkeypatch.setattr(mc.requests, "get", fake_get)
    assert mc.cambiar_code_por_token("acme", "code1")["token"] == "tok"
    assert visto["client_id"] == "111" and visto["client_secret"] == "s3cr3t"
    assert visto["code"] == "code1"


def test_borrar_app_elimina_el_archivo(carpeta):
    mc.guardar_app("acme", APP)
    mc.borrar_app("acme")
    assert mc.cargar_app("acme") is None
    mc.borrar_app("acme")  # idempotente


def test_meta_app_json_esta_en_gitignore():
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(raiz, ".gitignore"), encoding="utf-8") as f:
        reglas = [l.strip() for l in f]
    assert "clientes/*/meta_app.json" in reglas
    assert "clientes/*/meta_app.json.tmp" in reglas


def test_obtener_perfil_no_exige_client_business_id(monkeypatch):
    """Con un token de usuario (no de usuario del sistema) Meta responde
    (#190) al pedir client_business_id: el perfil sale igual, sin negocio."""
    import meta_conexion as mc
    llamadas = []

    def _graph(edge, token, params=None, timeout=30):
        llamadas.append(params["fields"])
        if "client_business_id" in params["fields"]:
            raise mc.MetaConexionError("Meta respondió: (#190) The client_business_id field can only be accessed "
                                       "using a Business Integration System User access token.", codigo=190)
        return {"id": "1", "name": "Forja"}
    monkeypatch.setattr(mc, "_graph_get", _graph)
    assert mc.obtener_perfil("tok") == {"id": "1", "name": "Forja", "client_business_id": None}
    assert llamadas == ["id,name", "client_business_id"]

    # con token de usuario del sistema el negocio sí llega
    monkeypatch.setattr(mc, "_graph_get", lambda edge, token, params=None, timeout=30:
                        {"id": "1", "name": "Forja", "client_business_id": "999"} if "client_business_id" in params["fields"]
                        else {"id": "1", "name": "Forja"})
    assert mc.obtener_perfil("tok")["client_business_id"] == "999"
