"""El cliente elige cómo conectar Meta (spec §1-§4): elegir forma, buscar y
conectar sus activos por portafolio (autoservicio), avisar a Creatv como
respaldo, y cambiar de forma solo con nada en marcha. Reusa la fixture `app`
y los ayudantes de tests/test_rutas_meta_agencia.py. Ningún token en HTML."""
import pytest

import meta_conexion as mc
import proyectos
from tests.test_rutas_meta_agencia import (  # noqa: F401 — `app` es la fixture compartida
    BID, PAGE_TOKEN_FALSO, SAME_ORIGIN, TOKEN_FALSO, _asignar_en_disco, _cliente_rol_cliente, _fake_conectada,
    _flashes, app,
)

ACTIVOS_777 = {
    "ad_accounts": [{"id": "act_9", "name": "Cuenta Socio", "currency": "MXN", "account_status": 1, "activa": True,
                     "origen": "cliente", "business_id": "77700077700", "business_nombre": "Socio SA"}],
    "pages": [{"id": "p2", "name": "Página Cliente", "ig_user_id": None, "ig_username": None, "origen": "cliente",
               "business_id": "77700077700", "business_nombre": "Socio SA"}],
    "paginas_sin_dueno": False,
}
DETALLE_OK = {"ad_account_id": "act_9", "ad_account_nombre": "Cuenta Socio", "page_id": "p2", "page_nombre": "Página Cliente",
              "ig_username": None, "moneda": "MXN", "modo": "agencia", "asignado_en": "2026-09-20T10:00:00", "cambio_cuenta": False}


@pytest.fixture()
def cliente(app, monkeypatch):
    """Sesión rol cliente de acme, correo verificado, avisos al admin y
    bloqueo de forma simulados. Devuelve el test client y los registros."""
    d = app["dashboard"]
    monkeypatch.setattr(d, "_requiere_correo_verificado", lambda: None)
    avisos = []
    monkeypatch.setattr(d.notificaciones, "avisar_admin", lambda tipo, asunto, cuerpo, cliente="": avisos.append((tipo, cliente)) or 1)
    monkeypatch.setattr(d.experimentos, "cargar", lambda c: [])
    monkeypatch.setattr(d.organico, "listar", lambda c, pieza_id=None, ep_id=None: [])
    return {"c": _cliente_rol_cliente(d), "avisos": avisos, "d": d}


def _post(cliente, ruta, **data):
    return cliente["c"].post(ruta, data=data, headers=SAME_ORIGIN)


# ---- elegir forma (§1) ----

def test_elegir_propia_guarda_la_forma_y_vuelve_a_configuracion(cliente):
    r = _post(cliente, "/cliente/acme/meta/forma", forma="propia")
    assert r.status_code == 302 and r.headers["Location"].endswith("/cliente/acme#settings")
    assert proyectos.meta_forma("acme") == "propia"
    assert any("propia app" in m for m in _flashes(cliente["c"]))


def test_elegir_agencia_exige_agencia_conectada(cliente, app, monkeypatch):
    monkeypatch.setattr(app["ma"], "conectada", lambda: False)
    _post(cliente, "/cliente/acme/meta/forma", forma="agencia")
    assert proyectos.meta_forma("acme") is None
    assert any("todavía no está disponible" in m for m in _flashes(cliente["c"]))
    _fake_conectada(app, monkeypatch)
    _post(cliente, "/cliente/acme/meta/forma", forma="agencia")
    assert proyectos.meta_forma("acme") == "agencia"


def test_elegir_forma_invalida_o_de_otro_sitio(cliente):
    _post(cliente, "/cliente/acme/meta/forma", forma="otra")
    assert proyectos.meta_forma("acme") is None and any("una de las dos" in m for m in _flashes(cliente["c"]))
    r = cliente["c"].post("/cliente/acme/meta/forma", data={"forma": "propia"}, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


def test_cambiar_forma_con_conexion_propia_viva_exige_nada_en_marcha(cliente, app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    mc.guardar("acme", {"token": TOKEN_FALSO, "ad_account_id": "act_1", "page_id": "p1", "conectado_en": "2026-09-01T00:00:00"})
    monkeypatch.setattr(cliente["d"].experimentos, "cargar", lambda c: [{"estado": "corriendo"}, {"estado": "cerrado"}])
    _post(cliente, "/cliente/acme/meta/forma", forma="agencia")
    assert proyectos.meta_forma("acme") is None
    assert any(m.startswith("Termina o cierra primero: 1 experimento vivo") for m in _flashes(cliente["c"]))


# ---- buscar y conectar (§2.2-§2.3) ----

def test_buscar_redirige_con_el_portafolio_validado(cliente, app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    proyectos.guardar_meta_forma("acme", "agencia")
    r = _post(cliente, "/cliente/acme/meta/agencia/buscar", portafolio_id=" 77700077700 ", refrescar="1")
    assert r.status_code == 302 and r.headers["Location"].endswith("/cliente/acme?agencia_portafolio=77700077700&refrescar=1#settings")
    _post(cliente, "/cliente/acme/meta/agencia/buscar", portafolio_id="abc")
    assert any("solo números" in m for m in _flashes(cliente["c"]))


def test_ver_cliente_consulta_los_activos_del_portafolio(cliente, app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    proyectos.guardar_meta_forma("acme", "agencia")
    llamadas = []
    monkeypatch.setattr(app["ma"], "activos_de_portafolio",
                        lambda portafolio_id, cliente=None, forzar=False: llamadas.append((portafolio_id, cliente, forzar)) or ACTIVOS_777)
    r = cliente["c"].get("/cliente/acme?agencia_portafolio=77700077700&refrescar=1")
    assert r.status_code == 200 and llamadas == [("77700077700", "acme", True)]
    # Sin forma agencia no se consulta nada aunque venga el parámetro.
    proyectos.guardar_meta_forma("acme", "propia")
    cliente["c"].get("/cliente/acme?agencia_portafolio=77700077700")
    assert len(llamadas) == 1


def test_conectar_revalida_ids_y_asigna_como_cliente(cliente, app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    monkeypatch.setattr(app["ma"], "activos_de_portafolio", lambda portafolio_id, cliente=None, forzar=False: ACTIVOS_777)
    asignaciones = []
    monkeypatch.setattr(app["ma"], "asignar", lambda *a, **k: asignaciones.append((a, k)) or dict(DETALLE_OK))
    r = _post(cliente, "/cliente/acme/meta/agencia/conectar", portafolio_id="77700077700", ad_account_id="act_9", page_id="p2")
    assert r.status_code == 302
    assert asignaciones == [(("acme", "act_9", "p2"), {"asignado_por": "cliente:alguien", "portafolio_id": "77700077700"})]
    assert proyectos.meta_forma("acme") == "agencia"
    assert cliente["avisos"] == [("meta_conexion_cliente", "acme")]
    assert any(m.startswith("Listo: Creatv ya gestiona tu Meta con Cuenta Socio") for m in _flashes(cliente["c"]))


def test_conectar_rechaza_cuenta_o_pagina_ajenas(cliente, app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    monkeypatch.setattr(app["ma"], "activos_de_portafolio", lambda portafolio_id, cliente=None, forzar=False: ACTIVOS_777)
    asignaciones = []
    monkeypatch.setattr(app["ma"], "asignar", lambda *a, **k: asignaciones.append(a))
    _post(cliente, "/cliente/acme/meta/agencia/conectar", portafolio_id="77700077700", ad_account_id="act_1", page_id="p2")
    _post(cliente, "/cliente/acme/meta/agencia/conectar", portafolio_id="77700077700", ad_account_id="act_9", page_id="p1")
    assert asignaciones == [] and cliente["avisos"] == []
    mensajes = _flashes(cliente["c"])
    assert any("cuenta publicitaria no aparece" in m for m in mensajes) and any("Página no aparece" in m for m in mensajes)


def test_conectar_pagina_manual_solo_cuando_meta_no_dio_dueno(cliente, app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    sin_dueno = {**ACTIVOS_777, "pages": [], "paginas_sin_dueno": True}
    monkeypatch.setattr(app["ma"], "activos_de_portafolio", lambda portafolio_id, cliente=None, forzar=False: sin_dueno)
    monkeypatch.setattr(app["ma"], "pagina_de_socio", lambda page_id: {"id": "p3", "name": "Página Otro"} if page_id == "p3" else None)
    asignaciones = []
    monkeypatch.setattr(app["ma"], "asignar", lambda *a, **k: asignaciones.append(a) or dict(DETALLE_OK))
    _post(cliente, "/cliente/acme/meta/agencia/conectar", portafolio_id="77700077700", ad_account_id="act_9", page_id="", page_id_manual="p9")
    assert asignaciones == [] and any("no está compartida con Creatv" in m for m in _flashes(cliente["c"]))
    _post(cliente, "/cliente/acme/meta/agencia/conectar", portafolio_id="77700077700", ad_account_id="act_9", page_id="", page_id_manual="p3")
    assert asignaciones == [("acme", "act_9", "p3")]


def test_conectar_y_avisar_exigen_correo_verificado(app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    d = app["dashboard"]
    monkeypatch.setattr(d.usuarios, "obtener", lambda u: {"usuario": u, "rol": "cliente", "correo_verificado": False})
    llamadas = []
    monkeypatch.setattr(app["ma"], "asignar", lambda *a, **k: llamadas.append(a))
    monkeypatch.setattr(app["ma"], "solicitar", lambda *a, **k: llamadas.append(a))
    c = _cliente_rol_cliente(d)
    for ruta in ("/cliente/acme/meta/agencia/conectar", "/cliente/acme/meta/agencia/avisar"):
        r = c.post(ruta, data={"portafolio_id": "77700077700", "ad_account_id": "act_9"}, headers=SAME_ORIGIN)
        assert r.status_code == 302 and r.headers["Location"].endswith("#settings")
    assert llamadas == [] and any("Confirma tu correo" in m for m in _flashes(c))


# ---- avisar a Creatv (§2.4) ----

def test_avisar_guarda_solicitud_y_avisa_al_admin(cliente, app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    _post(cliente, "/cliente/acme/meta/agencia/avisar", portafolio_id="77700077700", ad_account_id="act_9", page_id="", nota="no veo nada")
    s = app["ma"].solicitud("acme")
    assert s["portafolio_id"] == "77700077700" and s["ad_account_id"] == "act_9" and s["nota"] == "no veo nada" and s["usuario"] == "alguien"
    assert proyectos.meta_forma("acme") == "agencia" and cliente["avisos"] == [("meta_solicitud", "acme")]
    assert any(m.startswith("Listo: Creatv recibió tu solicitud") for m in _flashes(cliente["c"]))
    _post(cliente, "/cliente/acme/meta/agencia/avisar/cancelar")
    assert app["ma"].solicitud("acme") is None


def test_avisar_sin_portafolio_valido(cliente, app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    _post(cliente, "/cliente/acme/meta/agencia/avisar", portafolio_id="12")
    assert app["ma"].solicitud("acme") is None and any("solo números" in m for m in _flashes(cliente["c"]))


# ---- salir del modo agencia (§4) ----

def test_salir_bloqueado_con_algo_en_marcha(cliente, app, monkeypatch):
    _asignar_en_disco("acme")
    monkeypatch.setattr(cliente["d"].organico, "listar", lambda c, pieza_id=None, ep_id=None: [{"estado": "publicando"}, {"estado": "publicada"}])
    _post(cliente, "/cliente/acme/meta/agencia/salir")
    assert mc.modo("acme") == "agencia" and cliente["avisos"] == []
    assert any("Termina o cierra primero: 1 publicación en curso" in m for m in _flashes(cliente["c"]))


def test_salir_desasigna_restaura_y_avisa(cliente, app):
    _asignar_en_disco("acme", propia_respaldo={"token": TOKEN_FALSO, "ad_account_id": "act_1", "page_id": "p1"})
    _post(cliente, "/cliente/acme/meta/agencia/salir")
    assert mc.modo("acme") == "propia" and mc.cargar("acme")["ad_account_id"] == "act_1"
    assert proyectos.meta_forma("acme") == "propia" and cliente["avisos"] == [("meta_cambio_forma", "acme")]
    assert any("Tu conexión anterior se restauró" in m for m in _flashes(cliente["c"]))
    # Sin estar en agencia, avisa y no toca nada.
    _post(cliente, "/cliente/acme/meta/agencia/salir")
    assert any("no está en modo agencia" in m for m in _flashes(cliente["c"]))


# ---- lo que ve el cliente (§1-§4) ----

def _html(cliente, ruta="/cliente/acme"):
    return cliente["c"].get(ruta).get_data(as_text=True)


def test_sin_forma_muestra_las_dos_tarjetas(cliente, app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    html = _html(cliente)
    assert "¿Cómo quieres conectar Meta?" in html
    assert "Que Creatv lo gestione" in html and "Recomendada" in html and "Con mi propia app de Meta" in html
    assert 'name="forma" value="agencia"' in html and 'name="forma" value="propia"' in html
    assert 'action="/cliente/acme/meta/forma"' in html
    # Ni el formulario de la app propia ni el enlace de conectar: primero se elige.
    assert 'action="/cliente/acme/meta/app"' not in html and 'href="/cliente/acme/meta/conectar"' not in html


def test_sin_agencia_conectada_la_tarjeta_agencia_esta_apagada(cliente, app, monkeypatch):
    monkeypatch.setattr(app["ma"], "conectada", lambda: False)
    html = _html(cliente)
    assert "Disponible en cuanto Creatv termine de activarlo" in html
    assert 'name="forma" value="agencia"' not in html and 'name="forma" value="propia"' in html


def test_forma_agencia_muestra_guia_id_de_creatv_y_buscador(cliente, app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    proyectos.guardar_meta_forma("acme", "agencia")
    html = _html(cliente)
    assert BID in html and "Creatv BM" in html and "Dar acceso a un socio a tus activos" in html
    assert "Administrar campañas" in html and "Crear anuncios" in html and "Crear contenido" in html
    assert "ID de tu portafolio comercial" in html and 'action="/cliente/acme/meta/agencia/buscar"' in html
    assert "¿Prefieres usar tu propia app?" in html
    assert TOKEN_FALSO not in html and PAGE_TOKEN_FALSO not in html


def test_resultados_muestran_solo_los_activos_del_portafolio(cliente, app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    proyectos.guardar_meta_forma("acme", "agencia")
    monkeypatch.setattr(app["ma"], "activos_de_portafolio", lambda portafolio_id, cliente=None, forzar=False: ACTIVOS_777)
    html = _html(cliente, "/cliente/acme?agencia_portafolio=77700077700")
    assert 'action="/cliente/acme/meta/agencia/conectar"' in html and 'name="portafolio_id" value="77700077700"' in html
    assert 'value="act_9"' in html and "Cuenta Socio · act_9 · MXN" in html and 'value="p2"' in html
    assert "Cuenta Uno" not in html and "Página Propia" not in html
    assert "Sin Página (solo anuncios)" in html and 'name="page_id_manual"' not in html


def test_sin_resultados_ofrece_volver_a_buscar_y_avisar(cliente, app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    proyectos.guardar_meta_forma("acme", "agencia")
    vacio = {"ad_accounts": [], "pages": [], "paginas_sin_dueno": False}
    monkeypatch.setattr(app["ma"], "activos_de_portafolio", lambda portafolio_id, cliente=None, forzar=False: vacio)
    html = _html(cliente, "/cliente/acme?agencia_portafolio=77700077700")
    assert "Todavía no vemos activos compartidos desde el portafolio 77700077700" in html
    assert 'name="refrescar" value="1"' in html and "Volver a buscar" in html
    assert 'action="/cliente/acme/meta/agencia/avisar"' in html and "Avisar a Creatv" in html


def test_pagina_manual_solo_si_meta_no_dio_dueno(cliente, app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    proyectos.guardar_meta_forma("acme", "agencia")
    sin_dueno = {**ACTIVOS_777, "pages": [], "paginas_sin_dueno": True}
    monkeypatch.setattr(app["ma"], "activos_de_portafolio", lambda portafolio_id, cliente=None, forzar=False: sin_dueno)
    html = _html(cliente, "/cliente/acme?agencia_portafolio=77700077700")
    assert 'name="page_id_manual"' in html


def test_solicitud_pendiente_se_ve_con_cancelar(cliente, app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    proyectos.guardar_meta_forma("acme", "agencia")
    app["ma"].solicitar("acme", "77700077700")
    html = _html(cliente)
    assert "Solicitud enviada el" in html and 'action="/cliente/acme/meta/agencia/avisar/cancelar"' in html


def test_forma_propia_muestra_la_guia_corregida(cliente, app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    proyectos.guardar_meta_forma("acme", "propia")
    html = _html(cliente)
    assert "Modo de la app" in html and "Live" in html and "1885183" in html
    assert "token de usuario" in html and "usuario del sistema no sirve" in html
    assert 'action="/cliente/acme/meta/app"' in html and "¿Prefieres que Creatv lo gestione?" in html
    assert "caduca a los 60 días" in html


def test_conectado_en_agencia_ofrece_cambiar_de_forma_o_explica_el_bloqueo(cliente, app, monkeypatch):
    _asignar_en_disco("acme")
    html = _html(cliente)
    assert "Gestionado por Creatv" in html and 'action="/cliente/acme/meta/agencia/salir"' in html
    assert "lo hace el administrador" not in html
    monkeypatch.setattr(cliente["d"], "_bloqueo_cambio_forma",
                        lambda c, experimentos_lista=None: "Termina o cierra primero: 1 experimento vivo")
    html = _html(cliente)
    assert 'action="/cliente/acme/meta/agencia/salir"' not in html and "termina o cierra primero" in html.lower()
    assert PAGE_TOKEN_FALSO not in html


def test_conectado_en_propia_ofrece_pasar_a_agencia(cliente, app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    mc.guardar("acme", {"token": TOKEN_FALSO, "ad_account_id": "act_1", "ad_account_nombre": "Cuenta Uno",
                        "page_id": "p1", "page_nombre": "Página Propia", "conectado_en": "2026-09-01T00:00:00"})
    monkeypatch.setattr(mc, "estado", lambda c: {"estado": "conectado", "detalle": mc._detalle(mc.cargar(c)), "verificado": True})
    html = _html(cliente)
    assert "Meta conectado" in html and 'name="forma" value="agencia"' in html and "Cambiar de forma" in html
    assert TOKEN_FALSO not in html
