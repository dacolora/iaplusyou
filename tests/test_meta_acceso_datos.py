"""PND-058 (2026-10-15): cuándo vence de verdad el acceso de Creatv a los datos de Meta.

`meta.json` guardaba una caducidad calculada con `expires_in` (2026-11-18 para colorado_forja) cuando el token en
realidad no caduca: lo que vence es el acceso a los datos (`data_access_expires_at`, 2026-12-18), y nada avisaba.
Ahora se lee con `debug_token` al conectar y una vez al día (la periódica `meta_revisar_acceso`, que también rellena
las conexiones hechas antes de este cambio), y Alertas avisa 14 días antes (pruebas en `test_alertas_fuentes.py`)."""
import json
import os
import stat
import threading
import time
from datetime import datetime, timezone

import pytest

import meta_conexion as mc

APP = {"app_id": "111", "app_secret": "s3cr3t", "login_config_id": "222"}
# 2026-12-18 a las 17:00 UTC: el mismo día en cualquier zona entre UTC−12 y UTC+6 (Bogotá: 12:00).
VENCE_DATOS = int(datetime(2026, 12, 18, 17, 0, tzinfo=timezone.utc).timestamp())


@pytest.fixture()
def carpeta(monkeypatch, tmp_path):
    monkeypatch.setattr(mc, "BASE_DIR", str(tmp_path))
    monkeypatch.setenv("META_REDIRECT_URI", "https://app.example/meta/callback")
    return tmp_path


class _Resp:
    def __init__(self, datos, ok=True, status=200):
        self._datos, self.ok, self.status_code = datos, ok, status
        self.content = b"1"

    def json(self):
        return self._datos


def _meta_falsa(monkeypatch, debug=None, falla_debug=False, al_depurar=None):
    """requests.get de Meta: el cambio de code por token y `debug_token`. Devuelve las llamadas (edge, params)."""
    llamadas = []

    def fake_get(url, params=None, timeout=None):
        edge = url.rsplit("/", 1)[-1]
        llamadas.append((edge, dict(params or {})))
        if edge == "access_token":
            return _Resp({"access_token": "tok", "token_type": "bearer", "expires_in": 5184000})
        if edge == "debug_token":
            if al_depurar:
                al_depurar()
            if falla_debug:
                return _Resp({"error": {"message": "Invalid OAuth access token.", "code": 190}}, ok=False, status=400)
            return _Resp({"data": debug if debug is not None else {
                "app_id": "111", "type": "USER", "is_valid": True, "expires_at": 0,
                "data_access_expires_at": VENCE_DATOS}})
        raise AssertionError(f"llamada inesperada a {url}")
    monkeypatch.setattr(mc.requests, "get", fake_get)
    return llamadas


def _conexion(carpeta, cliente="acme", **campos):
    """Una conexión propia ya guardada (como la de colorado_forja antes de este cambio) y su app."""
    mc.guardar_app(cliente, APP)
    datos = {"token": "tok", "tipo_token": "bearer", "expira_en": "2026-11-18T10:00:00", "ad_account_id": "act_1",
             "moneda": "COP", "page_id": "9", "conectado_en": "2026-09-19T10:00:00", **campos}
    mc.guardar(cliente, datos)
    return datos


def _meta_json(carpeta, cliente="acme"):
    ruta = carpeta / "clientes" / cliente / "meta.json"
    return json.loads(ruta.read_text()) if ruta.exists() else None


# ---------- al conectar ----------

def test_conectar_guarda_cuando_vence_de_verdad(carpeta, monkeypatch):
    mc.guardar_app("acme", APP)
    llamadas = _meta_falsa(monkeypatch)
    info = mc.cambiar_code_por_token("acme", "code1")
    assert info["token"] == "tok"
    assert info["acceso_datos_vence_en"].startswith("2026-12-18")
    assert info["expira_en"] is None                       # expires_at 0: el token no caduca (no 60 días después)
    edge, params = llamadas[-1]
    assert edge == "debug_token" and params["input_token"] == "tok"
    assert params["access_token"] == "111|s3cr3t"           # token de la app del proyecto: sirve para cualquier usuario


def test_si_debug_token_falla_la_conexion_sigue(carpeta, monkeypatch):
    """Leer la fecha no puede tumbar la conexión: queda sin fecha y la periódica la vuelve a leer."""
    mc.guardar_app("acme", APP)
    _meta_falsa(monkeypatch, falla_debug=True)
    info = mc.cambiar_code_por_token("acme", "code1")
    assert info["token"] == "tok" and info["acceso_datos_vence_en"] is None
    assert info["expira_en"]                                 # el cálculo viejo con expires_in, como respaldo


def test_un_token_que_caduca_guarda_su_fecha(carpeta, monkeypatch):
    mc.guardar_app("acme", APP)
    caduca = int(datetime(2026, 11, 30, 17, 0, tzinfo=timezone.utc).timestamp())
    _meta_falsa(monkeypatch, debug={"is_valid": True, "expires_at": caduca, "data_access_expires_at": 0})
    info = mc.cambiar_code_por_token("acme", "code1")
    assert info["expira_en"].startswith("2026-11-30") and info["acceso_datos_vence_en"] is None


def test_elegir_la_cuenta_deja_la_fecha_en_meta_json(carpeta, monkeypatch):
    import dashboard
    pendiente = {"token": "tok", "tipo_token": "bearer", "expira_en": None,
                 "acceso_datos_vence_en": "2026-12-18T12:00:00", "acceso_revisado_en": "2026-10-15T09:00:00"}
    with dashboard.app.test_request_context():
        dashboard._guardar_conexion_propia("acme", pendiente, {"id": "act_1", "name": "C", "currency": "COP"},
                                           {"id": "9", "name": "P", "access_token": "PT"})
    datos = _meta_json(carpeta)
    assert datos["acceso_datos_vence_en"] == "2026-12-18T12:00:00"
    assert datos["acceso_revisado_en"] == "2026-10-15T09:00:00"


def test_acceso_datos_vence_en_solo_con_app_propia_conectada(carpeta):
    assert mc.acceso_datos_vence_en("acme") is None                     # sin conexión
    _conexion(carpeta)
    assert mc.acceso_datos_vence_en("acme") is None                     # conexión vieja, sin fecha todavía
    _conexion(carpeta, acceso_datos_vence_en="2026-12-18T12:00:00")
    assert mc.acceso_datos_vence_en("acme") == "2026-12-18T12:00:00"
    _conexion(carpeta, token=None, acceso_datos_vence_en="2026-12-18T12:00:00")
    assert mc.acceso_datos_vence_en("acme") is None                     # sin token no hay acceso que venza
    mc._escribir_atomico(mc._path("acme"), {"modo": "agencia", "ad_account_id": "act_1",
                                            "acceso_datos_vence_en": "2026-12-18T12:00:00"})
    assert mc.acceso_datos_vence_en("acme") is None                     # agencia: el token no es del proyecto


# ---------- la revisión diaria ----------

def test_revisar_rellena_una_conexion_hecha_antes_del_cambio(carpeta, monkeypatch):
    """El caso de colorado_forja: meta.json sin la fecha (y con la caducidad falsa del 2026-11-18)."""
    antes = _conexion(carpeta)
    _meta_falsa(monkeypatch)
    vence = mc.revisar_vencimientos("acme")
    assert vence["acceso_datos_vence_en"].startswith("2026-12-18")
    datos = _meta_json(carpeta)
    assert datos["acceso_datos_vence_en"].startswith("2026-12-18") and datos["acceso_revisado_en"]
    assert datos["expira_en"] is None                                     # la caducidad falsa se corrige
    assert {k: datos[k] for k in antes if k != "expira_en"} == {k: v for k, v in antes.items() if k != "expira_en"}
    ruta = carpeta / "clientes" / "acme" / "meta.json"
    assert stat.S_IMODE(os.stat(ruta).st_mode) == 0o600


def test_revisar_no_pisa_una_reconexion_en_medio(carpeta, monkeypatch):
    """Si la persona reconecta mientras se le pregunta a Meta, lo nuevo se queda: no se escribe el token viejo."""
    _conexion(carpeta)

    def reconecta():
        mc.guardar("acme", {"token": "nuevo", "ad_account_id": "act_2"})
    _meta_falsa(monkeypatch, al_depurar=reconecta)
    mc.revisar_vencimientos("acme")
    datos = _meta_json(carpeta)
    assert datos["token"] == "nuevo" and datos["ad_account_id"] == "act_2"
    assert "acceso_datos_vence_en" not in datos


def test_revisar_no_revive_una_conexion_borrada(carpeta, monkeypatch):
    """Desconectar mientras se le pregunta a Meta: meta.json no vuelve a aparecer (con el token adentro)."""
    _conexion(carpeta)
    _meta_falsa(monkeypatch, al_depurar=lambda: mc.borrar("acme"))
    mc.revisar_vencimientos("acme")
    assert _meta_json(carpeta) is None


@pytest.mark.parametrize("caso", ["sin_conexion", "agencia", "sin_app", "sin_token"])
def test_revisar_no_pregunta_lo_que_no_es_suyo(carpeta, monkeypatch, caso):
    llamadas = _meta_falsa(monkeypatch)
    if caso == "agencia":
        mc._escribir_atomico(mc._path("acme"), {"modo": "agencia", "ad_account_id": "act_1"})
    elif caso == "sin_app":
        mc.guardar("acme", {"token": "tok", "ad_account_id": "act_1"})
    elif caso == "sin_token":
        _conexion(carpeta, token=None)
    assert mc.revisar_vencimientos("acme") is None
    assert llamadas == []


def test_revisar_con_meta_caido_lanza_sin_tocar_nada(carpeta, monkeypatch):
    _conexion(carpeta, token="EAAsecreto123456")
    _meta_falsa(monkeypatch, falla_debug=True)
    with pytest.raises(mc.MetaConexionError) as e:
        mc.revisar_vencimientos("acme")
    assert "EAAsecreto123456" not in str(e.value) and "s3cr3t" not in str(e.value)
    assert "acceso_datos_vence_en" not in _meta_json(carpeta)


def test_guardar_espera_al_candado_de_meta_json(carpeta):
    """El candado que toma la revisión (entre leer y escribir) también lo toman guardar y borrar."""
    _conexion(carpeta)
    hecho = threading.Event()

    def otro_hilo():
        mc.guardar("acme", {"token": "nuevo", "ad_account_id": "act_2"})
        hecho.set()
    with mc._candado("acme"):
        hilo = threading.Thread(target=otro_hilo)
        hilo.start()
        time.sleep(0.2)
        assert not hecho.is_set()
    hilo.join(5)
    assert hecho.is_set() and _meta_json(carpeta)["token"] == "nuevo"


def test_el_candado_no_se_versiona():
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(raiz, ".gitignore"), encoding="utf-8") as f:
        assert "clientes/*/meta.json.lock" in [linea.strip() for linea in f]


# ---------- la periódica ----------

def test_la_periodica_revisa_cada_proyecto_y_uno_que_falla_no_frena_a_los_demas(carpeta, monkeypatch, base_temporal):
    import tareas.meta as tm
    _conexion(carpeta, "acme")
    _conexion(carpeta, "beta")
    (carpeta / "clientes" / "sin_meta").mkdir()
    vistos = []
    real = mc.revisar_vencimientos

    def revisar(cliente):
        vistos.append(cliente)
        if cliente == "acme":
            raise mc.MetaConexionError("Meta respondió: algo")
        return real(cliente)
    monkeypatch.setattr(tm.meta_conexion, "revisar_vencimientos", revisar)
    _meta_falsa(monkeypatch)
    texto = tm.revisar_acceso({"payload": {}})
    assert sorted(vistos) == ["acme", "beta", "sin_meta"]
    assert _meta_json(carpeta, "beta")["acceso_datos_vence_en"].startswith("2026-12-18")
    assert "1" in texto


def test_la_periodica_corre_una_vez_al_dia_y_no_cobra():
    import tareas
    import worker
    assert ("meta_revisar_acceso", 86400) in worker.PERIODICAS
    assert "meta_revisar_acceso" in tareas.REGISTRO
    assert "meta_revisar_acceso" in tareas.TIPOS_EXENTOS_DE_COBRO


# ---------- la tarjeta de Configuración › Conexiones ----------

@pytest.fixture()
def pagina(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import proyectos
    from tests.test_rutas_experimentos import _cliente_admin
    monkeypatch.setattr(mc, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    proyectos.guardar_meta_forma("acme", "propia")

    def html(**campos):
        mc.guardar_app("acme", APP)
        mc.guardar("acme", {"token": "TOK", "ad_account_id": "act_1", "ad_account_nombre": "Cuenta COP",
                            "moneda": "COP", "page_id": "9", "page_nombre": "Forja", "ig_username": "forja",
                            "conectado_en": "2026-09-19T10:00:00", **campos})
        detalle = mc._detalle(mc.cargar("acme"))
        monkeypatch.setattr(dashboard.meta_conexion, "estado",
                            lambda c: {"estado": "conectado", "verificado": True, "detalle": detalle})
        return _cliente_admin(dashboard).get("/cliente/acme").get_data(as_text=True)
    return html


def test_la_tarjeta_dice_hasta_cuando_y_deja_renovar_sin_desconectar(pagina):
    """La alerta manda aquí: tiene que haber cómo renovar que no sea «Desconectar» (que borra las métricas copiadas)."""
    html = pagina(acceso_datos_vence_en="2026-12-18T12:00:00")
    trozo = html.split('id="meta-acceso-datos"')[1].split("</small>")[0]
    assert "Acceso a los datos de Meta hasta el 2026-12-18" in trozo
    assert 'href="/cliente/acme/meta/conectar"' in trozo and "Renovar el acceso" in trozo


def test_la_tarjeta_sin_fecha_no_inventa_una(pagina):
    html = pagina()
    assert 'id="meta-acceso-datos"' not in html and "Renovar el acceso" not in html
