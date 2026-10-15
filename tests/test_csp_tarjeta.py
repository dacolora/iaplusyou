"""PND-304 (a), 2026-10-15: la política de scripts de la página de la tarjeta manda sus violaciones a una ruta propia
(`report-uri`), que anota lo justo (la directiva, el origen bloqueado, qué página y si fue reporte o
bloqueo; nunca la URL completa, el proyecto ni un fragmento de código) con tope de tamaño y de cantidad, y avisa al
admin una vez por violación nueva. Así se puede pasar la política a «bloquear» sin depender de que alguien mire la
consola del navegador. Base temporal; nada sale a la red."""
import json
from datetime import datetime, timedelta

import pytest
import sqlalchemy as sa

from tests.test_planes_vista import _cobra, base, falso, pagina, pro  # noqa: F401 — fixtures

RUTA = "/pagos/csp/tarjeta"
DOC = "https://app.creatvmachine.com/cliente/acme/plan/alta?plan=1&ciclo=mensual"


@pytest.fixture()
def csp(base, monkeypatch):  # noqa: F811
    from cobros import csp as modulo
    avisos = []
    monkeypatch.delenv("PLATAFORMA_URL", raising=False)
    monkeypatch.delenv("PLATAFORMA_HOSTS_EXTRA", raising=False)
    monkeypatch.setattr(modulo, "_CUPO", {"desde": None, "n": 0, "ips": {}, "marcada": False})
    monkeypatch.setattr(modulo, "_en_segundo_plano", lambda fn: fn())
    monkeypatch.setattr(modulo.avisos, "admin", lambda tipo, asunto, cuerpo, cliente="": avisos.append(
        (tipo, asunto() if callable(asunto) else asunto, cuerpo() if callable(cuerpo) else cuerpo)))
    modulo.avisos_enviados = avisos
    return modulo


@pytest.fixture()
def http(base, csp):  # noqa: F811
    import dashboard
    dashboard.app.config["TESTING"] = True
    return dashboard.app.test_client()


def _reporte(**cambios):
    rep = {"document-uri": DOC, "referrer": "", "violated-directive": "script-src-elem",
           "effective-directive": "script-src-elem", "original-policy": "script-src 'self' …",
           "disposition": "report", "blocked-uri": "https://cdn.otro.example/x.js?tarjeta=4111111111111111",
           "line-number": 12, "column-number": 3, "source-file": "https://app.creatvmachine.com/static/x.js?v=1",
           "status-code": 200, "script-sample": "4111 1111 1111 1111"}
    rep.update(cambios)
    return json.dumps({"csp-report": rep}).encode()


def _enviar(http, cuerpo, tipo="application/csp-report", **headers):
    return http.post(RUTA, data=cuerpo, content_type=tipo, headers=headers)


def _filas(base):  # noqa: F811
    with base.conectar() as con:
        return dict(con.execute(sa.select(base.kv.c.clave, base.kv.c.valor)
                                .where(base.kv.c.clave.like("cobros:csp:%"))).all())


# --- la página -----------------------------------------------------------------------------------------------------

def test_la_pagina_de_la_tarjeta_manda_sus_violaciones_a_nuestra_ruta(base, pagina, pro, falso, csp):  # noqa: F811
    from cobros import rutas
    _cobra()
    r = pagina().get(f"/cliente/acme/plan/alta?plan={pro}")
    assert rutas.CSP_TARJETA_SOLO_REPORTE is True                 # sigue en «solo reporte» (PND-304 a)
    politica = r.headers["Content-Security-Policy-Report-Only"]
    assert politica.endswith(f"; report-uri {RUTA}")
    # Sin `report-to`: en Chromium reemplaza a `report-uri` y su entrega no se pudo ver (2026-10-15).
    assert "report-to" not in politica and "Reporting-Endpoints" not in r.headers


def test_en_modo_bloquear_tambien_reporta(base, pagina, pro, falso, csp, monkeypatch):  # noqa: F811
    from cobros import rutas
    monkeypatch.setattr(rutas, "CSP_TARJETA_SOLO_REPORTE", False)
    _cobra()
    r = pagina().get(f"/cliente/acme/plan/alta?plan={pro}")
    (politica,) = r.headers.getlist("Content-Security-Policy")
    assert "frame-ancestors 'none'" in politica and f"report-uri {RUTA}" in politica
    assert "Content-Security-Policy-Report-Only" not in r.headers


# --- la ruta: lo que guarda ----------------------------------------------------------------------------------------

def test_un_reporte_se_anota_sin_url_completa_ni_proyecto_ni_codigo(http, base, csp):  # noqa: F811
    r = _enviar(http, _reporte())
    assert r.status_code == 204 and r.data == b""
    (fila,) = csp.resumen()
    assert (fila["directiva"], fila["bloqueado"], fila["pagina"], fila["disposicion"], fila["veces"]) == \
        ("script-src-elem", "https://cdn.otro.example", "alta", "report", 1)
    crudo = json.dumps(_filas(base))
    for dato in ("4111", "tarjeta=", "acme", "plan=", "x.js", "static", "original"):
        assert dato not in crudo, dato


def test_el_formato_de_reporting_api_tambien_vale_y_repetir_suma(http, base, csp):  # noqa: F811
    cuerpo = json.dumps([
        {"type": "csp-violation", "age": 10, "url": DOC, "user_agent": "x",
         "body": {"documentURL": DOC, "effectiveDirective": "frame-src", "blockedURL": "https://pagos.otro.example/f",
                  "disposition": "report", "sample": ""}},
        {"type": "deprecation", "body": {"id": "x"}},                 # otro tipo de reporte: se ignora
        {"type": "csp-violation", "body": {"documentURL": DOC, "effectiveDirective": "frame-src",
                                           "blockedURL": "https://pagos.otro.example/otra", "disposition": "report"}},
    ]).encode()
    assert _enviar(http, cuerpo, tipo="application/reports+json").status_code == 204
    (fila,) = csp.resumen()
    assert (fila["directiva"], fila["bloqueado"], fila["veces"]) == ("frame-src", "https://pagos.otro.example", 2)


@pytest.mark.parametrize("bloqueado, esperado", [
    ("inline", "inline"), ("eval", "eval"), ("data", "data"), ("blob:https://app.creatvmachine.com/1-2", "blob"),
    ("chrome-extension://abcdef/script.js", "chrome-extension"), ("https://CHECKOUT.wompi.co:443/w.js", "https://checkout.wompi.co"),
    ("http://localhost:5050/x", "http://localhost:5050"), ("javascript:alert(1)", "javascript"),
    ("https://user:clave@evil.example/x", "https://evil.example"), ("\n<script>", "otro"),
])
def test_lo_bloqueado_se_reduce_a_su_origen_o_su_palabra(http, csp, bloqueado, esperado):  # noqa: F811
    _enviar(http, _reporte(**{"blocked-uri": bloqueado}))
    (fila,) = csp.resumen()
    assert fila["bloqueado"] == esperado


@pytest.mark.parametrize("cambio", [
    {"document-uri": "https://app.creatvmachine.com/cliente/acme"},            # otra página: no es la tarjeta
    {"document-uri": "https://app.creatvmachine.com/cliente/acme/plan/alta/x"},
    {"effective-directive": "img-src", "violated-directive": "img-src"},      # otra directiva
    {"disposition": "otra"},
])
def test_lo_que_no_es_de_la_tarjeta_no_se_anota(http, csp, cambio):  # noqa: F811
    assert _enviar(http, _reporte(**cambio)).status_code == 204
    assert csp.resumen() == []


def test_la_pagina_de_cambiar_la_tarjeta_tambien_cuenta(http, csp):  # noqa: F811
    _enviar(http, _reporte(**{"document-uri": "/cliente/acme/plan/tarjeta", "disposition": "enforce"}))
    (fila,) = csp.resumen()
    assert (fila["pagina"], fila["disposicion"]) == ("tarjeta", "enforce")


# --- la ruta: sus puertas ------------------------------------------------------------------------------------------

def test_la_ruta_acepta_un_post_de_otro_sitio_y_sin_sesion(http, csp):  # noqa: F811
    # La manda el navegador (sin cookie y a veces marcada de otro sitio): exenta de la barrera CSRF y de la sesión
    # por nombre exacto de endpoint. No mueve plata: anota lo justo, con tope.
    r = _enviar(http, _reporte(), **{"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Dest": "report"})
    assert r.status_code == 204 and len(csp.resumen()) == 1


def test_un_post_de_otro_sitio_que_no_es_un_reporte_se_rechaza(http, csp):  # noqa: F811
    # Auditoría 2026-10-15: un `fetch` de otra página (con text/plain no pide permiso) haría que sus visitantes
    # mandaran reportes falsos desde IP reales. Un reporte de verdad lleva Sec-Fetch-Dest: report, que una página no
    # puede poner; los del mismo sitio (los de nuestra página) pasan siempre.
    for dest in ("empty", None):
        cabeceras = {"Sec-Fetch-Site": "cross-site", **({"Sec-Fetch-Dest": dest} if dest else {})}
        assert _enviar(http, _reporte(), tipo="text/plain", **cabeceras).status_code == 403
    assert csp.resumen() == []
    assert _enviar(http, _reporte(), **{"Sec-Fetch-Site": "same-origin", "Sec-Fetch-Dest": "report"}).status_code == 204
    assert len(csp.resumen()) == 1


def test_una_sesion_vieja_no_convierte_el_reporte_en_redireccion(http, csp):  # noqa: F811
    with http.session_transaction() as s:
        s["usuario"] = "ya_no_existe"; s["rol"] = "cliente"; s["cliente"] = "acme"; s["sv"] = 9
    assert _enviar(http, _reporte()).status_code == 204


def test_las_excepciones_csrf_son_los_dos_webhooks_y_los_reportes_de_la_tarjeta():
    import dashboard
    assert dashboard.ENDPOINTS_OTRO_ORIGEN == {"cobros.bold_webhook", "cobros.wompi_eventos", "cobros.csp_tarjeta"}
    assert "cobros.csp_tarjeta" in dashboard.ENDPOINTS_SIN_GUARD_SESION


def test_un_cuerpo_grande_es_413_y_no_anota(http, csp):  # noqa: F811
    grande = _reporte(**{"referrer": "x" * (csp.MAX_CUERPO + 10)})
    assert _enviar(http, grande).status_code == 413
    assert csp.resumen() == []


@pytest.mark.parametrize("cuerpo", [b"no es json", b"[" * 100000 + b"]" * 100000, b'"texto"', b"{}",
                                    json.dumps({"csp-report": "x"}).encode()])
def test_un_cuerpo_raro_no_anota_nada(http, csp, cuerpo):  # noqa: F811
    assert _enviar(http, cuerpo).status_code in (204, 400, 413)
    assert csp.resumen() == []


def test_solo_acepta_post(http):  # noqa: F811
    assert http.get(RUTA).status_code == 405


# --- topes ----------------------------------------------------------------------------------------------------------

def test_tope_por_hora_entre_todos(http, csp, monkeypatch):  # noqa: F811
    monkeypatch.setattr(csp, "TOPE_HORA", 3)
    monkeypatch.setattr(csp, "TOPE_IP_HORA", 100)
    for i in range(5):
        _enviar(http, _reporte(**{"blocked-uri": f"https://h{i}.example/x"}))
    assert len(csp.resumen()) == 3


def test_tope_por_ip(http, csp, monkeypatch):  # noqa: F811
    monkeypatch.setattr(csp, "TOPE_IP_HORA", 2)
    for i in range(4):
        _enviar(http, _reporte(**{"blocked-uri": f"https://h{i}.example/x"}))
    assert len(csp.resumen()) == 2
    r = http.post(RUTA, data=_reporte(**{"blocked-uri": "https://otra-ip.example/x"}),
                  content_type="application/csp-report", environ_base={"REMOTE_ADDR": "10.9.9.9"})
    assert r.status_code == 204 and len(csp.resumen()) == 3


def test_tope_de_violaciones_distintas_y_las_viejas_se_olvidan(http, base, csp, monkeypatch):  # noqa: F811
    monkeypatch.setattr(csp, "MAX_DISTINTAS", 2)
    for i in range(3):
        _enviar(http, _reporte(**{"blocked-uri": f"https://h{i}.example/x"}))
    assert {f["bloqueado"] for f in csp.resumen()} == {"https://h0.example", "https://h1.example"}
    _enviar(http, _reporte(**{"blocked-uri": "https://h0.example/otra"}))     # una ya anotada sí suma
    assert {f["bloqueado"]: f["veces"] for f in csp.resumen()}["https://h0.example"] == 2
    viejo = (datetime.now() - timedelta(days=csp.DIAS + 1)).isoformat(timespec="seconds")
    with base.conectar() as con:
        for clave, valor in _filas(base).items():
            dato = json.loads(valor)
            if dato["bloqueado"] == "https://h1.example":
                dato["ultima"] = viejo
                con.execute(base.kv.update().where(base.kv.c.clave == clave).values(valor=json.dumps(dato)))
    assert {f["bloqueado"] for f in csp.resumen()} == {"https://h0.example"}   # vieja: no se muestra
    _enviar(http, _reporte(**{"blocked-uri": "https://h2.example/x"}))         # y deja su lugar
    assert {f["bloqueado"] for f in csp.resumen()} == {"https://h0.example", "https://h2.example"}
    assert len(_filas(base)) == 2


# --- aviso y pantalla -----------------------------------------------------------------------------------------------

def test_avisa_al_admin_una_vez_por_violacion_nueva(http, csp):  # noqa: F811
    _enviar(http, _reporte())
    _enviar(http, _reporte())
    _enviar(http, _reporte(**{"blocked-uri": "inline", "effective-directive": "script-src-attr"}))
    assert [a[0] for a in csp.avisos_enviados] == ["csp_tarjeta", "csp_tarjeta"]
    assert "cdn.otro.example" in csp.avisos_enviados[0][2] and "4111" not in csp.avisos_enviados[0][2]


def test_el_aviso_es_un_aviso_de_plata_conocido():
    import notificaciones
    from cobros import vista
    assert "csp_tarjeta" in notificaciones.TIPOS and "csp_tarjeta" in vista.NOMBRES_AVISO_PLATA


def test_admin_cobros_muestra_la_politica_y_lo_anotado(http, base, csp, monkeypatch, tmp_path):  # noqa: F811
    import bitacora
    import estado
    monkeypatch.setattr(bitacora, "LOG_FILE", str(tmp_path / "registro.csv"))
    monkeypatch.setattr(estado, "listar_clientes", lambda: ["acme"])
    c = http
    with c.session_transaction() as s:
        s["usuario"] = "admin"; s["rol"] = "admin"; s["cliente"] = None; s["sv"] = 1
    r = c.get("/admin/cobros")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and 'id="cobros-csp-tarjeta"' in html
    assert "solo reporte" in html and "No hay violaciones anotadas" in html
    _enviar(c, _reporte())
    html = c.get("/admin/cobros").get_data(as_text=True)
    assert "https://cdn.otro.example" in html and "script-src-elem" in html


# --- revisión de seguridad (auditor, 2026-10-15) -------------------------------------------------------------------

def test_un_reporte_sin_disposition_se_anota_como_desconocida(http, csp):  # noqa: F811
    # Un navegador que no manda `disposition`: antes «desconocida» se cortaba a 10 letras y el reporte se tiraba.
    cuerpo = json.loads(_reporte())
    del cuerpo["csp-report"]["disposition"]
    assert _enviar(http, json.dumps(cuerpo).encode()).status_code == 204
    (fila,) = csp.resumen()
    assert fila["disposicion"] == "desconocida"


def test_solo_cuentan_los_reportes_de_nuestra_pagina(http, csp, monkeypatch):  # noqa: F811
    monkeypatch.setenv("PLATAFORMA_URL", "https://app.creatvmachine.com")
    monkeypatch.setenv("PLATAFORMA_HOSTS_EXTRA", "galadsy.com")
    for documento in ("https://evil.example/cliente/acme/plan/alta", "/cliente/acme/plan/alta",
                      "https://app.creatvmachine.com.evil.example/cliente/acme/plan/alta"):
        _enviar(http, _reporte(**{"document-uri": documento}))
    assert csp.resumen() == []
    for i, documento in enumerate(("https://app.creatvmachine.com/cliente/acme/plan/alta",
                                   "https://galadsy.com/cliente/acme/plan/alta",
                                   "http://localhost:5050/cliente/acme/plan/alta")):
        _enviar(http, _reporte(**{"document-uri": documento, "blocked-uri": f"https://h{i}.example/x"}))
    assert len(csp.resumen()) == 3


def test_un_numero_largo_en_el_host_no_se_guarda(http, base, csp):  # noqa: F811
    # Un skimmer que cargue https://<número>.evil.tld/x.js dejaría el número en la base y en el correo.
    _enviar(http, _reporte(**{"blocked-uri": "https://4111111111111111.cdn.evil.example/x.js"}))
    (fila,) = csp.resumen()
    assert fila["bloqueado"] == "https://*.cdn.evil.example"
    assert "4111" not in json.dumps(_filas(base)) and "4111" not in json.dumps(csp.avisos_enviados)


def test_lo_descartado_por_tope_marca_la_lista_como_incompleta(http, csp, monkeypatch):  # noqa: F811
    # Con el cupo gastado (60 reportes de basura desde 6 IP) un reporte real no se anota: la lista se vería limpia.
    # Ahora queda dicho que está incompleta, y /admin/cobros lo muestra.
    monkeypatch.setattr(csp, "TOPE_HORA", 2)
    assert csp.incompleta() is None
    for i in range(3):
        _enviar(http, _reporte(**{"blocked-uri": f"https://h{i}.example/x"}))
    assert len(csp.resumen()) == 2 and csp.incompleta() is not None


def test_con_la_lista_llena_lo_nuestro_o_de_wompi_desplaza_lo_ajeno(http, csp, monkeypatch):  # noqa: F811
    monkeypatch.setattr(csp, "MAX_DISTINTAS", 2)
    monkeypatch.setattr(csp, "TOPE_IP_HORA", 100)
    for i in range(2):
        _enviar(http, _reporte(**{"blocked-uri": f"https://basura{i}.example/x.js"}))
    _enviar(http, _reporte(**{"blocked-uri": "https://otro.example/x.js"}))       # ajeno: no cabe
    assert {f["bloqueado"] for f in csp.resumen()} == {"https://basura0.example", "https://basura1.example"}
    assert csp.incompleta() is not None
    _enviar(http, _reporte(**{"blocked-uri": "https://api.wompi.co/w.js"}))       # de Wompi: desplaza
    _enviar(http, _reporte(**{"blocked-uri": "inline", "effective-directive": "script-src-attr"}))
    assert {f["bloqueado"] for f in csp.resumen()} == {"https://api.wompi.co", "inline"}


def test_ipv6_cuenta_por_su_64():
    from cobros import csp
    assert csp._clave_ip("2001:db8:1:2::1") == csp._clave_ip("2001:db8:1:2:ffff::9")
    assert csp._clave_ip("2001:db8:1:2::1") != csp._clave_ip("2001:db8:1:3::1")
    assert csp._clave_ip("10.0.0.1") == "10.0.0.1" and csp._clave_ip(None) == "desconocida"


def test_el_aviso_dice_que_los_reportes_no_van_firmados(http, csp):  # noqa: F811
    _enviar(http, _reporte(**{"blocked-uri": "https://checkout.wompi.co.pagos-seguros.example/x.js",
                              "disposition": "enforce"}))
    (_tipo, _asunto, cuerpo) = csp.avisos_enviados[0]
    assert "no van firmados" in cuerpo and "https://checkout.wompi.co" in cuerpo


def test_admin_cobros_avisa_cuando_la_lista_esta_incompleta(http, base, csp, monkeypatch, tmp_path):  # noqa: F811
    import bitacora
    import estado
    monkeypatch.setattr(bitacora, "LOG_FILE", str(tmp_path / "registro.csv"))
    monkeypatch.setattr(estado, "listar_clientes", lambda: ["acme"])
    monkeypatch.setattr(csp, "TOPE_HORA", 1)
    _enviar(http, _reporte())
    _enviar(http, _reporte(**{"blocked-uri": "https://h9.example/x"}))
    with http.session_transaction() as s:
        s["usuario"] = "admin"; s["rol"] = "admin"; s["cliente"] = None; s["sv"] = 1
    html = http.get("/admin/cobros").get_data(as_text=True)
    assert 'id="aviso-csp-incompleta"' in html
