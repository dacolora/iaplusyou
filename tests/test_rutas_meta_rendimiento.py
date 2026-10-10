"""Pestaña «Meta» (spec 2026-10-08 meta rendimiento §5 y §8): la página del proyecto solo pinta el armazón (sin
Graph ni cálculo), el panel y el selector de cuentas llegan por fetch, «Ver más» trae filas, y los POST (elegir
cuentas, país, actualizar) frenan lo de otro sitio, lo de otro proyecto y lo que el token no ve. Ningún token llega a
una respuesta."""
from datetime import date, datetime, timedelta

import pytest
import sqlalchemy as sa

import db
from meta_rendimiento import cuentas, datos, panel, pausa
from tests.test_rutas_configuracion import app  # noqa: F401  (fixture)
from tests.test_rutas_productos import _flashes

TOKEN = "tok-llave-de-prueba"   # llave-de-prueba
A, B = "act_1", "act_2"


@pytest.fixture(autouse=True)
def _carpeta_de_proyectos(tmp_path, monkeypatch):
    """`meta_conexion.cuentas_de_lanzamiento` lee el meta.json de cada carpeta de proyecto: que sea una temporal."""
    import meta_conexion
    monkeypatch.setattr(meta_conexion, "BASE_DIR", str(tmp_path / "base_meta"))


def _lanza_con(cliente, act):
    """El proyecto `cliente` lanza experimentos con la cuenta `act` (su meta.json)."""
    import json

    import meta_conexion
    ruta = meta_conexion._path(cliente)
    import os
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump({"ad_account_id": act, "token": "t-" + cliente}, f)


def _como_cliente(app, usuario="user_acme", cliente="acme"):
    """Un navegador con la sesión de una persona con rol cliente (existe en usuarios: conftest USUARIOS_PRUEBA)."""
    c = app["dashboard"].app.test_client()
    with c.session_transaction() as s:
        s.update({"usuario": usuario, "rol": "cliente", "cliente": cliente})
    return c


@pytest.fixture()
def conectado(app, monkeypatch):  # noqa: F811
    """Meta conectado (sin Página: solo métricas) y una lista de las respuestas para buscar el token en todas."""
    monkeypatch.setattr(app["dashboard"].meta_conexion, "cargar",
                        lambda c: {"token": TOKEN, "ad_account_id": A, "page_id": None})
    respuestas = []
    c = app["c"]
    for metodo in ("get", "post"):
        original = getattr(c, metodo)

        def envuelto(*a, _original=original, **k):
            r = _original(*a, **k)
            respuestas.append(r.get_data(as_text=True) + str(r.headers))
            return r
        monkeypatch.setattr(c, metodo, envuelto)
    yield {"c": c, "respuestas": respuestas, "dashboard": app["dashboard"]}
    assert all(TOKEN not in texto for texto in respuestas)
    assert all(TOKEN not in m for m in _flashes(c))


def _hace(n):
    return (date.today() - timedelta(days=n)).isoformat()


def _cuentas(cliente="acme", *pares):
    cuentas.elegir(cliente, [{"id": act, "name": nombre, "currency": "SEK", "pais": pais}
                             for act, nombre, pais in pares])


def _dos_cuentas():
    _cuentas("acme", (A, "HappyFlops Norway", "NO"), (B, "HappyFlops Sweden", "SE"))


def _dia(fecha, gasto, valor, compras=1):
    return dict(fecha=fecha, gasto=gasto, impresiones=10000, alcance=800, clics=200, clics_salida=100,
                compras=compras, valor=valor, vistas_3s=3000, thruplays=1000)


def _ad(fecha, ad, gasto, valor, compras=0, adset="s1", campaign="c1"):
    return dict(fecha=fecha, campaign_id=campaign, adset_id=adset, ad_id=ad, gasto=gasto, impresiones=5000,
                clics=100, clics_salida=60, compras=compras, valor=valor, vistas_3s=1500, thruplays=500,
                p25=900, p50=700, p75=500, p100=300)


def _tasa(fecha, usd=0.1, moneda="SEK"):
    with db.conectar() as con:
        con.execute(db.tasa_cambio.insert().values(fecha=fecha, moneda=moneda, usd_por_unidad=usd, fuente="bce",
                                                   creado_en=db.ahora()))


def _sembrar(n_anuncios=4):
    """Dos cuentas SEK con días de cuenta, anuncios (un ganador y perdedores en la 1), objetos y tasas."""
    _dos_cuentas()
    f = _hace(2)
    datos.reemplazar_cuenta_dias("acme", A, f, f, [_dia(f, 400, 1000, compras=5)])
    datos.reemplazar_cuenta_dias("acme", B, f, f, [_dia(f, 200, 300, compras=2)])
    anuncios = [_ad(f, "gana", 100, 1000, compras=20)] + [_ad(f, f"p{i:02d}", 50 + i, 0) for i in range(n_anuncios - 1)]
    datos.reemplazar_anuncio_dias("acme", A, f, f, anuncios)
    datos.reemplazar_anuncio_dias("acme", B, f, f, [_ad(f, "otra", 200, 300, compras=2, adset="s2", campaign="c2")])
    datos.guardar_objetos("acme", A, [
        {"nivel": "campana", "objeto_id": "c1", "nombre": "Campaña Otoño", "estado": "ACTIVE",
         "objetivo": "OUTCOME_SALES", "presupuesto_diario": 500.0},
        {"nivel": "conjunto", "objeto_id": "s1", "nombre": "Conjunto Mujeres", "estado": "ACTIVE",
         "aprendizaje": "FAIL", "campaign_id": "c1"},
        {"nivel": "anuncio", "objeto_id": "gana", "nombre": "Video gana", "estado": "ACTIVE",
         "miniatura_url": "https://scontent.xx.fbcdn.net/gana.jpg"}])
    datos.guardar_alcance("acme", A, [{"nivel": "campana", "objeto_id": "c1", "ventana": 30, "alcance": 4321,
                                       "frecuencia": 1.2}])
    for d in range(0, 70):
        _tasa(_hace(d))


def _tareas(tipo="meta_rend_sincronizar"):
    with db.conectar() as con:
        return [dict(r._mapping) for r in con.execute(
            sa.select(db.tarea.c.job_id, db.tarea.c.payload, db.tarea.c.cliente).where(db.tarea.c.tipo == tipo))]


def _fila(html, marca):
    """El <tr>…</tr> que contiene `marca`."""
    i = html.index(marca)
    return html[html.rindex("<tr", 0, i):html.index("</tr>", i)]


def _activos(*cuentas_meta):
    return {"ad_accounts": [{"id": act, "name": nombre, "currency": "SEK", "account_status": 1}
                            for act, nombre in cuentas_meta], "pages": []}


# ---- la página del proyecto -------------------------------------------------------------------------------

def test_sin_conectar_la_pestana_invita_a_conectar_y_no_calcula_el_panel(app, monkeypatch):  # noqa: F811
    monkeypatch.setattr(panel, "contexto", lambda *a, **k: pytest.fail("el panel va por fetch"))
    monkeypatch.setattr(app["dashboard"].meta_conexion, "listar_activos", lambda t: pytest.fail("nada de Graph"))
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert 'data-tab="meta"' in html and 'id="tab-meta"' in html
    pestana = html[html.index('id="tab-meta"'):html.index('id="tab-nicho"')]
    assert "Conecta Meta para ver tus cuentas" in pestana and 'data-ir-tab="settings"' in pestana
    assert "/meta-rendimiento/panel" not in pestana and "/meta-rendimiento/cuentas" not in pestana
    # El enlace «#meta» de la tarjeta de Conexiones abre esta pestaña (cliente.html la conoce).
    assert "meta: document.getElementById('tab-meta')" in html
    # La pestaña va justo después de Triple Whale en la barra lateral.
    assert html.index('data-tab="triplewhale"') < html.index('data-tab="meta"') < html.index('data-tab="nicho"')


def test_conectado_sin_cuentas_pide_el_selector(conectado, monkeypatch):
    monkeypatch.setattr(panel, "contexto", lambda *a, **k: pytest.fail("el panel va por fetch"))
    html = conectado["c"].get("/cliente/acme").get_data(as_text=True)
    pestana = html[html.index('id="tab-meta"'):html.index('id="tab-nicho"')]
    assert "Elige qué cuentas publicitarias quieres ver" in pestana
    assert 'data-url="/cliente/acme/meta-rendimiento/cuentas"' in pestana
    assert "/meta-rendimiento/panel" not in pestana


def test_conectado_con_cuentas_pide_el_panel_por_fetch(conectado, monkeypatch):
    _dos_cuentas()
    monkeypatch.setattr(panel, "contexto", lambda *a, **k: pytest.fail("el panel va por fetch"))
    html = conectado["c"].get("/cliente/acme").get_data(as_text=True)
    pestana = html[html.index('id="tab-meta"'):html.index('id="tab-nicho"')]
    assert 'data-url="/cliente/acme/meta-rendimiento/panel"' in pestana
    assert 'data-url="/cliente/acme/meta-rendimiento/cuentas"' in pestana and "Elegir cuentas" in pestana


# ---- el panel ---------------------------------------------------------------------------------------------

def test_panel_con_datos(conectado):
    _sembrar()
    html = conectado["c"].get("/cliente/acme/meta-rendimiento/panel").get_data(as_text=True)
    assert "Todas las cuentas (2)" in html and "HappyFlops Norway" in html and "HappyFlops Sweden" in html
    assert "Ganador" in html and "Perdedor" in html and "Video gana" in html
    assert "Por cuenta" in html and f'data-meta-act="{A}"' in html
    assert 'class="tb-grafico"' in html and "USD" in html
    assert "Campaña Otoño" in html and "Conjunto Mujeres" in html and "Aprendizaje limitado" in html
    assert "<td>4.321</td>" in html                                    # alcance de la campaña (spec §8.4)
    assert 'src="https://scontent.xx.fbcdn.net/gana.jpg" alt="" loading="lazy" width="48" height="48"' in html
    assert "Conectado solo para métricas" in html                     # sin Página
    assert "<script" not in html
    # Una cuenta: sin «Por cuenta» y en su moneda.
    una = conectado["c"].get(f"/cliente/acme/meta-rendimiento/panel?cuenta={A}&dias=7").get_data(as_text=True)
    assert "Por cuenta" not in una and "HappyFlops Sweden</option>" in una and "SEK" in una
    assert f'<option value="{A}" selected' in una and '<option value="7" selected>' in una


def test_panel_sin_datos_y_con_una_cuenta_en_error(conectado):
    _dos_cuentas()
    cuentas.actualizar("acme", B, estado="error", error="Meta pidió esperar")
    html = conectado["c"].get("/cliente/acme/meta-rendimiento/panel").get_data(as_text=True)
    assert "Actualizar ahora" in html and "Todavía no hay métricas copiadas" in html
    assert "HappyFlops Sweden" in html and "Meta pidió esperar" in html
    from tareas import meta_rendimiento as tareas_mr
    assert tareas_mr.encolar_sync("acme") == 2
    html = conectado["c"].get("/cliente/acme/meta-rendimiento/panel").get_data(as_text=True)
    assert html.count("data-poll-job=") == 2 and "Trayendo los últimos 13 meses" in html
    assert 'data-poll-job="acme__meta_rend__act_1"' in html and 'id="meta-sync-acme-act_1"' in html


def test_ver_mas_anuncios_trae_solo_filas(conectado):
    _sembrar(n_anuncios=30)
    html = conectado["c"].get("/cliente/acme/meta-rendimiento/panel").get_data(as_text=True)
    assert 'data-meta-mas="' in html
    assert "/cliente/acme/meta-rendimiento/anuncios?dias=30&amp;pagina=1" in html
    mas = conectado["c"].get("/cliente/acme/meta-rendimiento/anuncios?dias=30&pagina=1")
    assert mas.status_code == 200
    filas = mas.get_data(as_text=True)
    # 31 anuncios en total (30 de la cuenta 1 + 1 de la 2): la segunda página trae 7 y ya no ofrece más.
    assert filas.count('<tr data-veredicto=') == 7 and "data-meta-mas" not in filas
    assert "<script" not in filas and "<table" not in filas


def test_ver_mas_conjuntos(conectado, monkeypatch):
    _sembrar()
    monkeypatch.setattr(panel, "POR_PAGINA", 1)
    html = conectado["c"].get("/cliente/acme/meta-rendimiento/panel").get_data(as_text=True)
    assert "/cliente/acme/meta-rendimiento/conjuntos?dias=30&amp;pagina=1" in html
    mas = conectado["c"].get("/cliente/acme/meta-rendimiento/conjuntos?dias=30&pagina=1").get_data(as_text=True)
    assert mas.count("<tr") == 1 and "<script" not in mas
    # Una página absurda (o que no es un número) no revienta: un OFFSET enorme no cabe en SQLite.
    for pagina in ("99999999999999999999999", "-3", "x"):
        for lista in ("conjuntos", "anuncios"):
            r = conectado["c"].get(f"/cliente/acme/meta-rendimiento/{lista}?pagina={pagina}")
            assert r.status_code == 200, (lista, pagina)


def test_otro_proyecto_no_ve_el_panel(app):  # noqa: F811
    _dos_cuentas()
    c = app["dashboard"].app.test_client()
    with c.session_transaction() as s:
        s.update({"usuario": "otro", "rol": "cliente", "cliente": "otro"})
    for url in ("/cliente/acme/meta-rendimiento/panel", "/cliente/acme/meta-rendimiento/cuentas",
                "/cliente/acme/meta-rendimiento/anuncios?pagina=1"):
        assert c.get(url).status_code in (302, 403, 404)
    assert c.post("/cliente/acme/meta-rendimiento/sincronizar").status_code in (302, 403, 404)
    assert _tareas() == []


# ---- elegir cuentas ---------------------------------------------------------------------------------------

def test_cuentas_marca_las_de_otro_proyecto_y_adivina_el_pais(conectado, monkeypatch):
    _cuentas("otro", (B, "HappyFlops Sweden", "SE"))
    llamadas = []
    monkeypatch.setattr(conectado["dashboard"].meta_conexion, "listar_activos",
                        lambda t: llamadas.append(t) or _activos((A, "HappyFlops Norway"), (B, "HappyFlops Sweden")))
    html = conectado["c"].get("/cliente/acme/meta-rendimiento/cuentas").get_data(as_text=True)
    assert llamadas == [TOKEN]
    fila_b, fila_a = _fila(html, f'value="{B}"'), _fila(html, f'value="{A}"')
    assert "disabled" in fila_b and "En otro proyecto" in fila_b
    assert "disabled" not in fila_a and "En otro proyecto" not in fila_a
    assert '<option value="NO" selected>' in fila_a                     # Norway → NO
    assert "<script" not in html


def test_guardar_cuentas_valida_contra_lo_que_ve_el_token_y_encola(conectado, monkeypatch):
    monkeypatch.setattr(conectado["dashboard"].meta_conexion, "listar_activos",
                        lambda t: _activos((A, "HappyFlops Norway")))
    r = conectado["c"].post("/cliente/acme/meta-rendimiento/cuentas", data={"cuenta": ["act_9"], "pais_act_9": "NO"})
    assert r.status_code == 302 and r.headers["Location"].endswith("#meta")
    assert cuentas.ids("acme") == [] and _tareas() == []
    r = conectado["c"].post("/cliente/acme/meta-rendimiento/cuentas",
                            data={"cuenta": [A, "act_9"], f"pais_{A}": "NL"})
    assert r.status_code == 302
    [fila] = cuentas.listar("acme")
    assert fila["ad_account_id"] == A and fila["pais"] == "NL" and fila["moneda"] == "SEK"
    assert _tareas() == [{"job_id": "acme__meta_rend__act_1", "payload": {"cliente": "acme", "ad_account_id": A},
                          "cliente": "acme"}]
    # El país de una cuenta que ya estaba también se guarda con el mismo formulario.
    conectado["c"].post("/cliente/acme/meta-rendimiento/cuentas", data={"cuenta": [A], f"pais_{A}": "NO"})
    assert cuentas.cuenta("acme", A)["pais"] == "NO"


def test_guardar_cuentas_no_quita_una_cuenta_que_el_token_ya_no_ve_si_sigue_marcada(conectado, monkeypatch):
    _cuentas("acme", (B, "HappyFlops Sweden", "SE"))
    monkeypatch.setattr(conectado["dashboard"].meta_conexion, "listar_activos",
                        lambda t: _activos((A, "HappyFlops Norway")))
    html = conectado["c"].get("/cliente/acme/meta-rendimiento/cuentas").get_data(as_text=True)
    assert "Tu conexión ya no ve esta cuenta" in html
    conectado["c"].post("/cliente/acme/meta-rendimiento/cuentas", data={"cuenta": [A, B]})
    assert sorted(cuentas.ids("acme")) == [A, B]
    conectado["c"].post("/cliente/acme/meta-rendimiento/cuentas", data={"cuenta": [A]})
    assert cuentas.ids("acme") == [A]


def test_guardar_cuentas_si_falla_al_quitar_avisa_y_la_cuenta_sigue(conectado, monkeypatch):
    _cuentas("acme", (B, "HappyFlops Sweden", "SE"))
    monkeypatch.setattr(conectado["dashboard"].meta_conexion, "listar_activos",
                        lambda t: _activos((A, "HappyFlops Norway"), (B, "HappyFlops Sweden")))

    def falla(cliente, act):
        raise RuntimeError("disco lleno")
    monkeypatch.setattr(cuentas, "_borrar_copias", falla)
    r = conectado["c"].post("/cliente/acme/meta-rendimiento/cuentas", data={"cuenta": [A]})
    assert r.status_code == 302
    assert B in cuentas.ids("acme")
    assert any("inténtalo de nuevo" in m for m in _flashes(conectado["c"]))
    # La que sí entró antes del fallo queda con su copia en cola.
    assert [t["job_id"] for t in _tareas()] == ["acme__meta_rend__act_1"]


def test_error_de_meta_al_listar_sin_token(conectado, monkeypatch):
    def rota(t):
        raise conectado["dashboard"].meta_conexion.MetaConexionError(f"Meta respondió: el token {t} no sirve")
    monkeypatch.setattr(conectado["dashboard"].meta_conexion, "listar_activos", rota)
    html = conectado["c"].get("/cliente/acme/meta-rendimiento/cuentas").get_data(as_text=True)
    assert "no sirve" in html
    r = conectado["c"].post("/cliente/acme/meta-rendimiento/cuentas", data={"cuenta": [A]})
    assert r.status_code == 302 and cuentas.ids("acme") == []
    # (el fixture comprueba que el token no llegó ni al HTML ni al flash)


def test_modo_agencia_todavia_no(conectado, monkeypatch):
    mc = conectado["dashboard"].meta_conexion
    monkeypatch.setattr(mc, "modo", lambda c: "agencia")
    monkeypatch.setattr(mc, "listar_activos", lambda t: pytest.fail("en agencia no se lista"))
    html = conectado["c"].get("/cliente/acme/meta-rendimiento/cuentas").get_data(as_text=True)
    assert "Todavía no disponible en modo agencia" in html
    r = conectado["c"].post("/cliente/acme/meta-rendimiento/cuentas", data={"cuenta": [A]})
    assert r.status_code == 302 and cuentas.ids("acme") == []


def test_cambiar_pais(conectado):
    _dos_cuentas()
    _cuentas("otro", ("act_7", "Ajena", "MX"))
    c = conectado["c"]
    assert c.post(f"/cliente/acme/meta-rendimiento/cuentas/{A}/pais", data={"pais": "fi"}).status_code == 302
    assert cuentas.cuenta("acme", A)["pais"] == "FI"
    assert c.post(f"/cliente/acme/meta-rendimiento/cuentas/{A}/pais", data={"pais": "ZZ"}).status_code == 400
    assert cuentas.cuenta("acme", A)["pais"] == "FI"
    assert c.post("/cliente/acme/meta-rendimiento/cuentas/act_7/pais", data={"pais": "NO"}).status_code == 404
    assert cuentas.cuenta("otro", "act_7")["pais"] == "MX"
    assert c.post(f"/cliente/acme/meta-rendimiento/cuentas/{A}/pais", data={"pais": ""}).status_code == 302
    assert cuentas.cuenta("acme", A)["pais"] is None


# ---- actualizar ahora -------------------------------------------------------------------------------------

def test_sincronizar(conectado):
    _dos_cuentas()
    _cuentas("otro", ("act_7", "Ajena", "MX"))
    c = conectado["c"]
    r = c.post("/cliente/acme/meta-rendimiento/sincronizar", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403 and _tareas() == []
    assert c.post("/cliente/acme/meta-rendimiento/sincronizar", data={"act": "act_7"}).status_code == 404
    assert c.post("/cliente/acme/meta-rendimiento/sincronizar", data={"act": "x y"}).status_code == 404
    assert _tareas() == []
    r = c.post("/cliente/acme/meta-rendimiento/sincronizar", data={"act": B})
    assert r.status_code == 302 and r.headers["Location"].endswith("#meta")
    assert [t["job_id"] for t in _tareas()] == ["acme__meta_rend__act_2"]
    c.post("/cliente/acme/meta-rendimiento/sincronizar")
    assert sorted(t["job_id"] for t in _tareas()) == ["acme__meta_rend__act_1", "acme__meta_rend__act_2"]


def test_con_la_pausa_de_meta_vigente_actualizar_dice_la_hora_y_no_encola_nada(conectado, app):
    _dos_cuentas()
    hasta = pausa.pausar(90)
    hora = hasta[11:16]
    for c in (conectado["c"], _como_cliente(app)):             # también el admin: no hay nada que esperar de la cola
        r = c.post("/cliente/acme/meta-rendimiento/sincronizar", data={"act": A})
        assert r.status_code == 302
        mensajes = _flashes(c)
        assert any(f"Meta pidió esperar: la copia sigue a las {hora}." in m for m in mensajes)
        assert not any("Trayendo" in m for m in mensajes)
        c.post("/cliente/acme/meta-rendimiento/sincronizar")
    assert _tareas() == []
    # Vencida la pausa, vuelve a encolar como siempre.
    with db.conectar() as con:
        con.execute(db.kv.update().where(db.kv.c.clave == pausa.CLAVE).values(
            valor=(datetime.now() - timedelta(minutes=1)).isoformat(timespec="seconds")))
    assert not pausa.activa()
    conectado["c"].post("/cliente/acme/meta-rendimiento/sincronizar", data={"act": A})
    assert [t["job_id"] for t in _tareas()] == ["acme__meta_rend__act_1"]


def test_post_de_otro_sitio_se_rechaza_en_todas(conectado, monkeypatch):
    _dos_cuentas()
    monkeypatch.setattr(conectado["dashboard"].meta_conexion, "listar_activos",
                        lambda t: pytest.fail("un POST ajeno no llega a Meta"))
    for url, data in (("/cliente/acme/meta-rendimiento/cuentas", {"cuenta": []}),
                      (f"/cliente/acme/meta-rendimiento/cuentas/{A}/pais", {"pais": "FI"})):
        assert conectado["c"].post(url, data=data, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert sorted(cuentas.ids("acme")) == [A, B] and cuentas.cuenta("acme", A)["pais"] == "NO"


def test_sin_meta_el_panel_y_sincronizar_lo_dicen(app):  # noqa: F811
    html = app["c"].get("/cliente/acme/meta-rendimiento/panel").get_data(as_text=True)
    assert "Meta no está conectado" in html
    _dos_cuentas()
    r = app["c"].post("/cliente/acme/meta-rendimiento/sincronizar")
    assert r.status_code == 302 and _tareas() == []


def test_el_panel_no_hace_una_consulta_por_anuncio(conectado):
    from tests.test_escala import _Consultas
    _sembrar(n_anuncios=3)
    with _Consultas() as pocas:
        assert conectado["c"].get("/cliente/acme/meta-rendimiento/panel").status_code == 200
    f = _hace(2)
    datos.reemplazar_anuncio_dias("acme", A, f, f, [_ad(f, f"x{i}", 5 + i, 0, adset=f"s{i}") for i in range(40)])
    with _Consultas() as muchas:
        assert conectado["c"].get("/cliente/acme/meta-rendimiento/panel").status_code == 200
    assert muchas.n - pocas.n <= 2, (pocas.n, muchas.n)


# ---- en inglés ----------------------------------------------------------------------------------------------

def test_panel_y_selector_en_ingles(app, monkeypatch):  # noqa: F811
    """Todo lo que pinta la pestaña pasa por el catálogo: el panel con datos (estados, aprendizaje, objetivo,
    veredictos, avisos) y el selector, en inglés sin español visible."""
    import idiomas
    from tests.i18n_util import espanol_visible
    mc = app["dashboard"].meta_conexion
    monkeypatch.setattr(mc, "cargar", lambda c: {"token": TOKEN, "ad_account_id": A, "page_id": None})
    monkeypatch.setattr(mc, "listar_activos", lambda t: _activos((A, "HappyFlops Norway"), ("act_5", "Shop")))
    _sembrar()
    cuentas.actualizar("acme", B, estado="error", error="Meta asked us to wait")
    idiomas.guardar_de_usuario("admin", "en")      # usuarios.json es temporal por test (conftest)
    c = app["c"]
    panel_en = c.get("/cliente/acme/meta-rendimiento/panel").get_data(as_text=True)
    assert "All accounts (2)" in panel_en and "Learning limited" in panel_en and "Sales" in panel_en
    # Los nombres de campañas y conjuntos son datos de la persona (sembrados en español): no cuentan.
    fugas = [t for t in espanol_visible(panel_en) if "Campaña Otoño" not in t and "Conjunto Mujeres" not in t]
    assert not fugas, fugas[:10]
    sel = c.get("/cliente/acme/meta-rendimiento/cuentas").get_data(as_text=True)
    assert "Choose accounts" in sel and not espanol_visible(sel), espanol_visible(sel)[:10]
    pagina = c.get("/cliente/acme").get_data(as_text=True)
    assert not espanol_visible(pagina, ["tab-meta"])


# ---- aislamiento: elegir cuentas es del admin (ruling R20) ------------------------------------------------

def test_cuentas_de_lanzamiento_lee_el_meta_json_de_cada_proyecto():
    import meta_conexion
    assert meta_conexion.cuentas_de_lanzamiento() == {}
    _lanza_con("acme", "555")
    _lanza_con("otro", "act_7")
    assert meta_conexion.cuentas_de_lanzamiento() == {"act_555": "acme", "act_7": "otro"}


def test_un_cliente_no_elige_cuentas_ni_cambia_el_pais(conectado, app, monkeypatch):
    _dos_cuentas()
    monkeypatch.setattr(conectado["dashboard"].meta_conexion, "listar_activos",
                        lambda t: pytest.fail("a un cliente no se le lista nada de Meta"))
    c = _como_cliente(app)
    assert c.get("/cliente/acme/meta-rendimiento/cuentas").status_code == 403
    assert c.post("/cliente/acme/meta-rendimiento/cuentas", data={"cuenta": ["act_9"]}).status_code == 403
    assert c.post(f"/cliente/acme/meta-rendimiento/cuentas/{A}/pais", data={"pais": "FI"}).status_code == 403
    assert sorted(cuentas.ids("acme")) == [A, B] and cuentas.cuenta("acme", A)["pais"] == "NO"
    assert _tareas() == []


def test_un_cliente_si_ve_el_panel_pero_sin_elegir_cuentas(conectado, app):
    _sembrar()
    c = _como_cliente(app)
    panel_html = c.get("/cliente/acme/meta-rendimiento/panel").get_data(as_text=True)
    assert c.get("/cliente/acme/meta-rendimiento/panel").status_code == 200
    assert "Actualizar ahora" in panel_html and "HappyFlops Norway" in panel_html
    pagina = c.get("/cliente/acme").get_data(as_text=True)
    pestana = pagina[pagina.index('id="tab-meta"'):pagina.index('id="tab-nicho"')]
    assert ">Elegir cuentas<" not in pestana and "data-meta-elegir aria-expanded" not in pestana
    assert "/meta-rendimiento/cuentas" not in pestana and "/meta-rendimiento/panel" in pestana
    # El admin sí lo ve.
    pagina = conectado["c"].get("/cliente/acme").get_data(as_text=True)
    pestana = pagina[pagina.index('id="tab-meta"'):pagina.index('id="tab-nicho"')]
    assert ">Elegir cuentas<" in pestana and "/meta-rendimiento/cuentas" in pestana


def test_un_cliente_sin_cuentas_ve_que_un_administrador_las_elige(conectado, app):
    c = _como_cliente(app)
    pagina = c.get("/cliente/acme").get_data(as_text=True)
    pestana = pagina[pagina.index('id="tab-meta"'):pagina.index('id="tab-nicho"')]
    assert "Un administrador de Creatv tiene que elegir las cuentas." in pestana
    assert "/meta-rendimiento/cuentas" not in pestana and "Cargando tus cuentas de Meta" not in pestana
    assert "Un administrador de Creatv tiene que elegir las cuentas." in c.get(
        "/cliente/acme/meta-rendimiento/panel").get_data(as_text=True)
    admin = conectado["c"].get("/cliente/acme").get_data(as_text=True)
    assert "Elige qué cuentas publicitarias quieres ver" in admin


def test_la_cuenta_con_la_que_lanza_otro_proyecto_es_de_ese_proyecto(conectado, monkeypatch):
    _lanza_con("otro", B)
    monkeypatch.setattr(conectado["dashboard"].meta_conexion, "listar_activos",
                        lambda t: _activos((A, "HappyFlops Norway"), (B, "HappyFlops Sweden")))
    html = conectado["c"].get("/cliente/acme/meta-rendimiento/cuentas").get_data(as_text=True)
    fila_b, fila_a = _fila(html, f'value="{B}"'), _fila(html, f'value="{A}"')
    assert "disabled" in fila_b and "En otro proyecto" in fila_b and "checked" not in fila_b
    assert "disabled" not in fila_a and "En otro proyecto" not in fila_a
    r = conectado["c"].post("/cliente/acme/meta-rendimiento/cuentas", data={"cuenta": [A, B]})
    assert r.status_code == 302
    assert cuentas.ids("acme") == [A]                                   # B no entró
    assert [t["job_id"] for t in _tareas()] == ["acme__meta_rend__act_1"]
    assert any("ya está en otro proyecto" in m for m in _flashes(conectado["c"]))
    # La suya propia sí puede leerla el proyecto que lanza con ella.
    _lanza_con("acme", A)
    conectado["c"].post("/cliente/acme/meta-rendimiento/cuentas", data={"cuenta": [A]})
    assert cuentas.ids("acme") == [A]


def test_una_cuenta_ya_elegida_que_otro_proyecto_usa_para_lanzar_se_quita_al_guardar(conectado, monkeypatch):
    _dos_cuentas()
    _lanza_con("otro", B)
    monkeypatch.setattr(conectado["dashboard"].meta_conexion, "listar_activos",
                        lambda t: _activos((A, "HappyFlops Norway"), (B, "HappyFlops Sweden")))
    html = conectado["c"].get("/cliente/acme/meta-rendimiento/cuentas").get_data(as_text=True)
    fila_b = _fila(html, f'value="{B}"')
    assert "disabled" in fila_b and "checked" not in fila_b
    conectado["c"].post("/cliente/acme/meta-rendimiento/cuentas", data={"cuenta": [A, B]})
    assert cuentas.ids("acme") == [A]


def test_un_proyecto_lee_como_maximo_veinte_cuentas(conectado, monkeypatch):
    todas = [(f"act_{100 + i}", f"Cuenta {i}") for i in range(25)]
    monkeypatch.setattr(conectado["dashboard"].meta_conexion, "listar_activos", lambda t: _activos(*todas))
    r = conectado["c"].post("/cliente/acme/meta-rendimiento/cuentas", data={"cuenta": [a for a, _ in todas]})
    assert r.status_code == 302
    assert len(cuentas.ids("acme")) == cuentas.MAX_POR_PROYECTO == 20
    assert len(_tareas()) == 20
    assert any("máximo 20 cuentas" in m for m in _flashes(conectado["c"]))
    # Con el cupo lleno, las que ya estaban se quedan y las nuevas no entran.
    conectado["c"].post("/cliente/acme/meta-rendimiento/cuentas", data={"cuenta": [a for a, _ in todas]})
    assert len(cuentas.ids("acme")) == 20


def test_con_dieciocho_cuentas_ya_elegidas_cinco_nuevas_no_desplazan_a_ninguna_de_las_que_estaban(conectado, monkeypatch):
    # Mutación A7: `(nuevas + existentes)[:20]` quitaría tres de las 18 (y borraría sus copias).
    viejas = [(f"act_{100 + i}", f"Vieja {i}") for i in range(18)]
    nuevas = [(f"act_{200 + i}", f"Nueva {i}") for i in range(5)]
    cuentas.elegir("acme", [{"id": a, "name": n, "currency": "SEK"} for a, n in viejas])
    monkeypatch.setattr(conectado["dashboard"].meta_conexion, "listar_activos", lambda t: _activos(*viejas, *nuevas))
    # Las nuevas van PRIMERO en el formulario: aun así el cupo es de las que ya estaban.
    r = conectado["c"].post("/cliente/acme/meta-rendimiento/cuentas",
                            data={"cuenta": [a for a, _ in nuevas + viejas]})
    assert r.status_code == 302
    ids = cuentas.ids("acme")
    assert len(ids) == 20 and {a for a, _ in viejas} <= set(ids)
    assert [a for a, _ in nuevas[:2]] == [a for a in ids if a.startswith("act_2")]      # entran las 2 que caben
    assert not any(cuentas.cuenta("acme", a) for a, _ in nuevas[2:])                     # y las 3 de más se rechazan
    assert any("máximo 20 cuentas" in m and "3 cuentas no se agregaron" in m for m in _flashes(conectado["c"]))
    assert sorted(t["job_id"] for t in _tareas()) == sorted(f"acme__meta_rend__{a}" for a, _ in nuevas[:2])


# ---- desconectar Meta borra las copias y libera las cuentas (ruling R21) --------------------------------------

def _filas_copiadas(cliente="acme"):
    """Cuántas filas de métricas copiadas quedan del proyecto, en las cuatro tablas de datos."""
    total = 0
    with db.conectar() as con:
        for tabla in (db.meta_cuenta_dia, db.meta_anuncio_dia, db.meta_objeto, db.meta_alcance):
            total += con.execute(sa.select(sa.func.count()).select_from(tabla).where(tabla.c.cliente == cliente)).scalar()
    return total


def test_desconectar_meta_borra_las_copias_y_deja_libres_las_cuentas(conectado, monkeypatch):
    _sembrar()
    assert _filas_copiadas() > 0
    mc = conectado["dashboard"].meta_conexion
    llamadas = []
    monkeypatch.setattr(mc, "revocar", lambda c: False)
    monkeypatch.setattr(mc, "borrar", lambda c: llamadas.append(c) or True)
    r = conectado["c"].post("/cliente/acme/meta/desconectar")
    assert r.status_code == 302 and llamadas == ["acme"]
    assert cuentas.ids("acme") == [] and _filas_copiadas() == 0
    # Las cuentas quedaron libres: otro proyecto ya puede leerlas.
    assert cuentas.elegir("otro", [{"id": A, "name": "HappyFlops Norway"}])["agregadas"] == [A]


def test_si_borrar_las_copias_falla_la_desconexion_se_queda_y_se_avisa(conectado, monkeypatch):
    _sembrar()
    mc = conectado["dashboard"].meta_conexion
    llamadas = []
    monkeypatch.setattr(mc, "revocar", lambda c: False)
    monkeypatch.setattr(mc, "borrar", lambda c: llamadas.append(c) or True)

    def falla(cliente, act):
        raise RuntimeError(f"disco lleno con {TOKEN}")
    monkeypatch.setattr(cuentas, "_borrar_copias", falla)
    r = conectado["c"].post("/cliente/acme/meta/desconectar")
    assert r.status_code == 302 and llamadas == ["acme"]
    mensajes = _flashes(conectado["c"])
    assert any("no se pudieron borrar sus métricas copiadas (RuntimeError)" in m for m in mensajes)
    assert any("Meta desconectado de este proyecto" in m for m in mensajes)
    assert all("disco lleno" not in m for m in mensajes)           # solo el tipo, nunca el texto
    assert sorted(cuentas.ids("acme")) == [A, B]                    # nada se perdió: se reintenta después


def test_la_politica_de_privacidad_promete_borrar_las_metricas_copiadas(app):  # noqa: F811
    import idiomas
    c = app["c"]
    for ruta in ("/privacidad", "/eliminar-datos"):
        es = " ".join(c.get(ruta).get_data(as_text=True).split())
        assert "métricas copiadas de las cuentas elegidas" in es and "nombres de campañas, conjuntos de anuncios y anuncios" in es
        assert "la cuenta elegida" not in es
    assert "las cuentas publicitarias y la Página elegidas" in " ".join(c.get("/privacidad").get_data(as_text=True).split())
    idiomas.guardar_de_usuario("admin", "en")
    for ruta in ("/privacidad", "/eliminar-datos"):
        en = " ".join(c.get(ruta).get_data(as_text=True).split())
        assert "metrics copied from the chosen accounts" in en and "names of campaigns, ad sets and ads" in en


# ---- «Actualizar ahora» espera 30 minutos para quien no es admin (ruling R22) -----------------------------------

def _copiada(act, hace_min):
    antes = (datetime.now() - timedelta(minutes=hace_min)).isoformat(timespec="seconds")
    cuentas.actualizar("acme", act, estado="ok", ultima_copia=antes)


def test_un_cliente_espera_30_minutos_entre_dos_actualizaciones(conectado, app):
    _dos_cuentas()
    c = _como_cliente(app)
    _copiada(A, 5)
    _copiada(B, 120)
    # Con una cuenta: solo cuenta la suya.
    c.post("/cliente/acme/meta-rendimiento/sincronizar", data={"act": A})
    assert _tareas() == [] and any("espera 30 minutos" in m for m in _flashes(c))
    c.post("/cliente/acme/meta-rendimiento/sincronizar", data={"act": B})
    assert [t["job_id"] for t in _tareas()] == ["acme__meta_rend__act_2"]
    # Sin cuenta: basta una copiada hace poco para frenar el «todas».
    cuentas.actualizar("acme", B, ultima_copia=None)
    c.post("/cliente/acme/meta-rendimiento/sincronizar")
    assert [t["job_id"] for t in _tareas()] == ["acme__meta_rend__act_2"]
    # Pasada la espera, sí.
    _copiada(A, 31)
    c.post("/cliente/acme/meta-rendimiento/sincronizar")
    assert sorted(t["job_id"] for t in _tareas()) == ["acme__meta_rend__act_1", "acme__meta_rend__act_2"]


def test_el_admin_no_espera_y_una_cuenta_sin_copia_tampoco(conectado, app):
    _dos_cuentas()
    _copiada(A, 1)
    conectado["c"].post("/cliente/acme/meta-rendimiento/sincronizar", data={"act": A})
    assert [t["job_id"] for t in _tareas()] == ["acme__meta_rend__act_1"]
    c = _como_cliente(app)
    c.post("/cliente/acme/meta-rendimiento/sincronizar", data={"act": B})        # B nunca se copió
    assert sorted(t["job_id"] for t in _tareas()) == ["acme__meta_rend__act_1", "acme__meta_rend__act_2"]


# ---- los POST piden correo verificado, como las rutas que conectan Meta -------------------------------------------

def test_sin_correo_verificado_un_cliente_no_escribe_nada(conectado, app):
    import usuarios
    _dos_cuentas()
    usuarios.actualizar("user_acme", correo_verificado=False)
    c = _como_cliente(app)
    r = c.post("/cliente/acme/meta-rendimiento/sincronizar")
    assert r.status_code == 302 and r.headers["Location"].endswith("/cliente/acme#settings")
    assert _tareas() == [] and any("Confirma tu correo primero" in m for m in _flashes(c))
    # Leer el panel no es escribir: sigue funcionando.
    assert c.get("/cliente/acme/meta-rendimiento/panel").status_code == 200
    # Verificado, sí; el admin no necesita verificar nada.
    usuarios.actualizar("user_acme", correo_verificado=True)
    c.post("/cliente/acme/meta-rendimiento/sincronizar", data={"act": A})
    assert [t["job_id"] for t in _tareas()] == ["acme__meta_rend__act_1"]
    usuarios.actualizar("admin", correo_verificado=False)
    conectado["c"].post("/cliente/acme/meta-rendimiento/sincronizar", data={"act": B})
    assert sorted(t["job_id"] for t in _tareas()) == ["acme__meta_rend__act_1", "acme__meta_rend__act_2"]


def test_guardar_cuentas_sin_el_campo_de_pais_no_borra_el_pais_guardado(conectado, monkeypatch):
    _dos_cuentas()
    monkeypatch.setattr(conectado["dashboard"].meta_conexion, "listar_activos",
                        lambda t: _activos((A, "HappyFlops Norway"), (B, "HappyFlops Sweden")))
    c = conectado["c"]
    c.post("/cliente/acme/meta-rendimiento/cuentas", data={"cuenta": [A, B]})             # sin ningún pais_<act>
    assert cuentas.cuenta("acme", A)["pais"] == "NO" and cuentas.cuenta("acme", B)["pais"] == "SE"
    c.post("/cliente/acme/meta-rendimiento/cuentas", data={"cuenta": [A, B], f"pais_{A}": "ZZ"})   # inválido: igual
    assert cuentas.cuenta("acme", A)["pais"] == "NO"
    c.post("/cliente/acme/meta-rendimiento/cuentas", data={"cuenta": [A, B], f"pais_{A}": ""})     # enviado vacío: borra
    assert cuentas.cuenta("acme", A)["pais"] is None and cuentas.cuenta("acme", B)["pais"] == "SE"
