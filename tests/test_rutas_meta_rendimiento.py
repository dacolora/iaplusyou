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


# ---- Diagnóstico y Segmentos (E2) ----------------------------------------------------------------------------

def _rec(i, nivel="media", tipo="perdedores_gastando", titulo=None, enlace="https://adsmanager.facebook.com/adsmanager/manage/ads?act=1&selected_ad_ids=9"):
    return {"id": f"{i:064x}", "nivel": nivel, "tipo": tipo, "cuenta": A, "cuenta_nombre": "HappyFlops Norway",
            "titulo": titulo or f"Recomendación {i}", "que_hacer": f"Haz la cosa {i}", "por_que": f"Porque {i}",
            "impacto": {"monto": 10.0, "moneda": "SEK", "texto": "10 SEK por día en juego"} if i % 2 else None,
            "objetos": [], "enlace": enlace}


def test_el_diagnostico_va_tras_los_kpis_con_enlaces_al_administrador(conectado):
    _sembrar()
    f = _hace(2)
    # La cuenta 1 vende menos de lo que gasta: la regla `cuenta_roas_bajo` (alta) sale con su enlace.
    datos.reemplazar_cuenta_dias("acme", A, f, f, [_dia(f, 4000, 1000, compras=5)])
    html = conectado["c"].get("/cliente/acme/meta-rendimiento/panel").get_data(as_text=True)
    assert 'id="meta-diagnostico"' in html and "Diagnóstico" in html
    assert html.index("CTR de salida") < html.index('id="meta-diagnostico"') < html.index("Día a día")
    # Alta: la cuenta vende menos de lo que gasta y su único conjunto activo está en aprendizaje limitado.
    assert "La cuenta vende menos de lo que gasta" in html and "Prioridad alta · 2" in html
    tarjeta = html[html.rindex("<article", 0, html.index("La cuenta vende menos de lo que gasta")):]
    tarjeta = tarjeta[:tarjeta.index("</article>")]
    assert 'class="meta-diag meta-diag-alta"' in tarjeta and "133 SEK por día en juego" in tarjeta
    # Los ids de prueba no son numéricos: el enlace es el de las campañas de la cuenta, sin selección.
    assert 'href="https://adsmanager.facebook.com/adsmanager/manage/campaigns?act=1"' in tarjeta
    assert 'target="_blank" rel="noopener noreferrer"' in tarjeta and "HappyFlops Norway" in tarjeta
    assert "<script" not in html


def test_mas_de_seis_recomendaciones_el_resto_va_plegado_y_lo_de_meta_se_escapa(conectado, monkeypatch):
    _sembrar()
    recs = [_rec(i, nivel="alta" if i < 2 else "media") for i in range(8)]
    recs[0]["titulo"] = '<img src=x onerror=alert(1)> Campaña "rara"'
    recs.append(_rec(9, nivel="baja", tipo="fatiga"))
    monkeypatch.setattr(panel.recomendaciones, "calcular", lambda entrada: recs)
    html = conectado["c"].get("/cliente/acme/meta-rendimiento/panel").get_data(as_text=True)
    diag = html[html.index('id="meta-diagnostico"'):html.index("</section>", html.index('id="meta-diagnostico"'))]
    visibles, plegadas = diag.split('<details class="meta-diag-mas">')
    assert visibles.count("<article") == 6 and plegadas.count("<article") == 3
    assert "Ver todas (9)" in plegadas
    assert "Prioridad alta · 2" in diag and "Prioridad media · 6" in diag and "Prioridad baja · 1" in diag
    assert "<img src=x" not in diag and "&lt;img src=x onerror=alert(1)&gt;" in diag
    assert diag.count('rel="noopener noreferrer"') == 9 and diag.count('target="_blank"') == 9
    assert 'href="#meta-evaluacion"' in plegadas and diag.count('href="#meta-evaluacion"') == 1
    assert "10 SEK por día en juego" in diag


def test_sin_recomendaciones_lo_dice(conectado, monkeypatch):
    _sembrar()
    monkeypatch.setattr(panel.recomendaciones, "calcular", lambda entrada: [])
    html = conectado["c"].get("/cliente/acme/meta-rendimiento/panel").get_data(as_text=True)
    assert "Las reglas no encontraron nada que corregir" in html and "meta-diag-mas" not in html


def test_segmentos_al_final_con_los_caros_marcados_y_los_viejos_avisados(conectado):
    _sembrar()
    seg = lambda clave, gasto, valor, compras: dict(clave=clave, gasto=gasto, impresiones=1000, clics=40,  # noqa: E731
                                                    clics_salida=25, compras=compras, valor=valor)
    datos.reemplazar_desgloses("acme", A, 30, "pais", [seg("NO", 800, 2400, 8), seg("SE", 200, 0, 0)])
    datos.reemplazar_desgloses("acme", B, 30, "edad_genero", [seg("25-34|female", 50, 100, 1)])
    html = conectado["c"].get("/cliente/acme/meta-rendimiento/panel").get_data(as_text=True)
    assert 'id="meta-segmentos"' in html and html.index("Anuncios") < html.index('id="meta-segmentos"')
    segs = html[html.index('id="meta-segmentos"'):]
    assert "País" in segs and "Edad y género" in segs and "25–34 · Mujeres" in segs
    fila = _fila(segs, "Suecia")
    assert 'class="meta-seg-caro"' in fila and "Caro en HappyFlops Norway" in fila and "20 %" in fila
    assert "Caro" not in _fila(segs, "Noruega")
    # Más de 48 h: no se muestra y se dice de cuándo es.
    viejo = (datetime.now() - timedelta(hours=80)).isoformat(timespec="seconds")
    with db.conectar() as con:
        con.execute(db.meta_desglose.update().where(db.meta_desglose.c.ad_account_id == A).values(calculado_en=viejo))
    segs = conectado["c"].get("/cliente/acme/meta-rendimiento/panel").get_data(as_text=True)
    segs = segs[segs.index('id="meta-segmentos"'):]
    assert "Suecia" not in segs and "Hay desgloses de HappyFlops Norway con datos de hace 3 días" in segs
    assert "25–34 · Mujeres" in segs
    assert "<script" not in segs


def test_segmentos_sin_desgloses_lo_dice(conectado):
    _sembrar()
    html = conectado["c"].get("/cliente/acme/meta-rendimiento/panel").get_data(as_text=True)
    assert "Todavía no hay desgloses: la copia los trae una vez al día." in html


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
    """Cuántas filas de métricas copiadas quedan del proyecto, en las cinco tablas de datos (E2 sumó los desgloses)."""
    total = 0
    with db.conectar() as con:
        for tabla in (db.meta_cuenta_dia, db.meta_anuncio_dia, db.meta_objeto, db.meta_alcance, db.meta_desglose):
            total += con.execute(sa.select(sa.func.count()).select_from(tabla).where(tabla.c.cliente == cliente)).scalar()
    return total


def test_desconectar_meta_borra_las_copias_y_deja_libres_las_cuentas(conectado, monkeypatch):
    _sembrar()
    datos.reemplazar_desgloses("acme", A, 30, "pais", [dict(clave="NO", gasto=10, impresiones=1, clics=1,
                                                            clics_salida=1, compras=1, valor=3)])
    assert _filas_copiadas() > 0 and datos.desgloses("acme", [A], 30)
    mc = conectado["dashboard"].meta_conexion
    llamadas = []
    monkeypatch.setattr(mc, "revocar", lambda c: False)
    monkeypatch.setattr(mc, "borrar", lambda c: llamadas.append(c) or True)
    r = conectado["c"].post("/cliente/acme/meta/desconectar")
    assert r.status_code == 302 and llamadas == ["acme"]
    assert cuentas.ids("acme") == [] and _filas_copiadas() == 0
    # Las cuentas quedaron libres: otro proyecto ya puede leerlas.
    assert cuentas.elegir("otro", [{"id": A, "name": "HappyFlops Norway"}])["agregadas"] == [A]


def _evaluar(cliente):
    return datos.crear_evaluacion(cliente, [A], "2026-09-10", "2026-10-09", "SEK",
                                  [{"ref": "a1", "anuncio": "Video gana"}], [], "ana")


def _filas_gasto(cliente):
    with db.conectar() as con:
        return con.execute(sa.select(sa.func.count()).select_from(db.gasto).where(db.gasto.c.cliente == cliente)).scalar()


def _desconectar(conectado, monkeypatch):
    mc = conectado["dashboard"].meta_conexion
    monkeypatch.setattr(mc, "revocar", lambda c: False)
    monkeypatch.setattr(mc, "borrar", lambda c: True)
    return conectado["c"].post("/cliente/acme/meta/desconectar")


def test_desconectar_meta_borra_las_evaluaciones_de_ese_proyecto_y_no_las_de_otro(conectado, monkeypatch):
    # E2-R2: una evaluación guarda nombres y métricas de anuncios de Meta; desconectar las borra (no el gasto).
    import gastos
    _sembrar()
    mias = [_evaluar("acme"), _evaluar("acme")]
    ajena = _evaluar("otro")
    assert gastos.registrar_seguro("acme", "evaluacion", 0.4, f"meta_eval:{mias[0]}") is not None
    assert _filas_gasto("acme") == 1
    r = _desconectar(conectado, monkeypatch)
    assert r.status_code == 302
    assert datos.evaluaciones("acme") == [] and all(datos.evaluacion("acme", i) is None for i in mias)
    assert datos.evaluacion("otro", ajena) is not None                     # el otro proyecto sigue igual
    assert _filas_gasto("acme") == 1                                       # lo que se pagó queda en el gasto
    assert not any("no se pudieron borrar" in m for m in _flashes(conectado["c"]))


def test_cambiar_las_cuentas_elegidas_no_borra_las_evaluaciones(conectado):
    # `cuentas.elegir` también corre al cambiar la selección: lo pagado no se pierde por eso.
    _sembrar()
    e = _evaluar("acme")
    cuentas.elegir("acme", [])
    datos.borrar_cuenta("acme", A)
    assert datos.evaluacion("acme", e) is not None


def test_si_falla_borrar_las_copias_las_evaluaciones_se_borran_igual(conectado, monkeypatch):
    _sembrar()
    e = _evaluar("acme")

    def falla(cliente, act):
        raise RuntimeError(f"disco lleno con {TOKEN}")
    monkeypatch.setattr(cuentas, "_borrar_copias", falla)
    _desconectar(conectado, monkeypatch)
    assert datos.evaluacion("acme", e) is None
    mensajes = _flashes(conectado["c"])
    assert sum("no se pudieron borrar sus métricas copiadas (RuntimeError)" in m for m in mensajes) == 1
    assert all("disco lleno" not in m for m in mensajes)
    assert sorted(cuentas.ids("acme")) == [A, B]


def test_si_falla_borrar_las_evaluaciones_las_copias_se_borran_igual_y_se_avisa_una_vez(conectado, monkeypatch):
    _sembrar()
    e = _evaluar("acme")

    def falla(cliente):
        raise ValueError(f"base bloqueada con {TOKEN}")
    monkeypatch.setattr(datos, "borrar_evaluaciones", falla)
    _desconectar(conectado, monkeypatch)
    assert cuentas.ids("acme") == [] and _filas_copiadas() == 0           # lo de las cuentas no se saltó
    assert datos.evaluacion("acme", e) is not None                         # y la evaluación se reintenta después
    mensajes = _flashes(conectado["c"])
    assert sum("no se pudieron borrar sus métricas copiadas (ValueError)" in m for m in mensajes) == 1
    assert all("base bloqueada" not in m for m in mensajes)


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


# ---------------------------------------------------------- «Evaluar con IA» (spec E2 §8) ---

from tests.test_triple_whale_ideas_piezas import app as app_crear  # noqa: E402,F401  (fixture: Crear sin lanzar nada)

EVALUAR = "/cliente/acme/meta-rendimiento/evaluar"


def _evaluaciones(cliente="acme"):
    return datos.evaluaciones(cliente, limite=50)


def _visto(dias="30", cuenta="", cliente="acme"):
    """Lo que manda el botón (E2-R6): cuántos anuncios mostró y el precio que la persona vio (con el margen)."""
    import gastos
    from cobros import libro
    from meta_rendimiento import analisis
    prep = analisis.preparar(cliente, dias, cuenta)
    n = len((prep or {}).get("muestra") or [])
    usd = gastos.estimar("evaluacion_meta", n=n)["usd"]
    return {"dias": dias, "cuenta": cuenta, "n": str(n), "precio_visto": repr(usd * libro.margen_precio(cliente))}


def _encolados(monkeypatch):
    """Lo que la ruta pasa a `trabajos.encolar` (sigue encolando de verdad)."""
    from tareas import meta_rendimiento as tmr
    llamadas = []
    original = tmr.trabajos.encolar

    def envuelto(*a, **k):
        llamadas.append(k)
        return original(*a, **k)
    monkeypatch.setattr(tmr.trabajos, "encolar", envuelto)
    return llamadas


def test_evaluar_crea_la_fila_y_la_encola_con_su_precio(conectado, monkeypatch):
    import gastos
    _sembrar()
    llamadas = _encolados(monkeypatch)
    r = conectado["c"].post(EVALUAR, data=_visto())
    assert r.status_code == 302 and r.headers["Location"].endswith("/cliente/acme#meta")
    ev, = _evaluaciones()
    n = len(ev["muestra"])
    assert n >= 2 and ev["estado"] == "en_cola" and ev["cuentas"] == [A, B] and ev["moneda"] == "SEK"
    assert ev["pedido_por"] == "admin" and ev["extra"]["dias"] == 30 and ev["extra"]["resumen"]
    assert [r["ref"] for r in ev["recomendaciones"]][:1] == ["R1"]
    # Primero el precio: la reserva usa el estimado de la tarifa con los anuncios de la muestra.
    assert llamadas[-1]["costo_estimado"] == pytest.approx(gastos.estimar("evaluacion_meta", n=n)["usd"])
    assert llamadas[-1]["max_intentos"] == 1
    tarea, = _tareas("meta_rend_evaluar")
    assert tarea["job_id"] == "acme__meta_eval" and tarea["payload"] == {"cliente": "acme", "evaluacion_id": ev["id"]}
    assert any(f"Evaluando {n} anuncio(s) con IA" in m for m in _flashes(conectado["c"]))


def test_evaluar_de_una_cuenta_guarda_ese_alcance(conectado):
    _sembrar()
    conectado["c"].post(EVALUAR, data=_visto("7", A))
    ev, = _evaluaciones()
    assert ev["cuentas"] == [A] and ev["extra"]["cuenta"] == A and ev["extra"]["dias"] == 7


def test_evaluar_sin_anuncios_suficientes_lo_dice_y_no_cobra_nada(conectado):
    _dos_cuentas()
    r = conectado["c"].post(EVALUAR, data=_visto())
    assert r.status_code == 302 and _evaluaciones() == [] and _tareas("meta_rend_evaluar") == []
    assert any("Todavía no hay anuncios con datos suficientes" in m for m in _flashes(conectado["c"]))


def test_evaluar_sin_cuentas_o_sin_meta_no_crea_nada(conectado, app, monkeypatch):  # noqa: F811
    conectado["c"].post(EVALUAR, data=_visto())
    assert _evaluaciones() == [] and any("Elige primero" in m for m in _flashes(conectado["c"]))
    monkeypatch.setattr(conectado["dashboard"].meta_conexion, "cargar", lambda c: {})
    _sembrar()
    conectado["c"].post(EVALUAR, data=_visto())
    assert _evaluaciones() == [] and any("Meta no está conectado" in m for m in _flashes(conectado["c"]))


def test_una_sola_evaluacion_viva_por_proyecto(conectado):
    _sembrar()
    conectado["c"].post(EVALUAR, data=_visto())
    conectado["c"].post(EVALUAR, data=_visto())
    assert len(_evaluaciones()) == 1 and len(_tareas("meta_rend_evaluar")) == 1
    assert any("Ya hay una evaluación con IA en curso" in m for m in _flashes(conectado["c"]))


@pytest.mark.parametrize("cambio", [{"n": None}, {"precio_visto": None}, {"n": "99"}, {"precio_visto": "0.01"},
                                    {"precio_visto": "abc"}, {"precio_visto": "inf"}])
def test_evaluar_sin_el_precio_visto_o_si_cambio_no_crea_ni_reserva_nada(conectado, cambio):
    """E2-R6: sin `n` o sin `precio_visto`, o si ya no coinciden con la muestra y el precio de ahora, nada se crea ni
    se reserva y el aviso dice el precio de ahora."""
    _sembrar()
    data = {k: v for k, v in dict(_visto(), **cambio).items() if v is not None}
    r = conectado["c"].post(EVALUAR, data=data)
    assert r.status_code == 302 and _evaluaciones() == [] and _tareas("meta_rend_evaluar") == []
    with db.conectar() as con:
        assert con.execute(sa.select(sa.func.count()).select_from(db.reserva_saldo)).scalar() == 0
    assert any("Revisa el precio y vuelve a confirmar" in m and "US$" in m for m in _flashes(conectado["c"]))
    conectado["c"].post(EVALUAR, data=_visto())
    assert len(_evaluaciones()) == 1


def _cobra(milesimas=0):
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    if milesimas:
        with db.conectar() as con:
            libro.acreditar(con, "acme", "ajuste", milesimas, "ajuste", usuario="admin", detalle="prueba")


def test_evaluar_sin_saldo_responde_402_y_no_crea_nada(conectado):
    _sembrar()
    _cobra()
    r = conectado["c"].post(EVALUAR, data=_visto(), headers={"X-Requested-With": "fetch"})
    assert r.status_code == 402 and r.get_json()["saldo_insuficiente"] is True
    assert _evaluaciones() == [] and _tareas("meta_rend_evaluar") == []


def test_evaluar_con_saldo_reserva_el_precio(conectado):
    import gastos
    from cobros import libro
    _sembrar()
    _cobra(milesimas=50_000)
    conectado["c"].post(EVALUAR, data=_visto())
    ev, = _evaluaciones()
    usd = gastos.estimar("evaluacion_meta", n=len(ev["muestra"]))["usd"]
    with db.conectar() as con:
        reserva, = con.execute(sa.select(db.reserva_saldo)).mappings().all()
    assert reserva["job_id"] == "acme__meta_eval"
    assert reserva["milesimas"] == libro.precio_milesimas(usd, libro.margen_precio("acme"))


def test_evaluar_si_el_margen_cambio_desde_que_vio_el_precio_no_cobra(conectado):
    from cobros import libro
    _sembrar()
    _cobra(milesimas=50_000)
    visto = _visto()                                   # el precio con el margen de cuando abrió la pestaña
    libro.configurar("acme", usuario="admin", margen=2.0)
    conectado["c"].post(EVALUAR, data=visto)
    assert _evaluaciones() == []
    with db.conectar() as con:
        assert con.execute(sa.select(sa.func.count()).select_from(db.reserva_saldo)).scalar() == 0
    assert any("Revisa el precio" in m for m in _flashes(conectado["c"]))
    conectado["c"].post(EVALUAR, data=_visto())        # con el precio de ahora, sí
    assert len(_evaluaciones()) == 1


def test_evaluar_si_encolar_falla_por_saldo_borra_la_fila(conectado, monkeypatch):
    from cobros import SaldoInsuficiente
    from tareas import meta_rendimiento as tmr
    _sembrar()

    def _sin_saldo(*a, **k):
        raise SaldoInsuficiente("acme", 1000, 0)
    monkeypatch.setattr(tmr, "encolar_evaluacion", _sin_saldo)
    r = conectado["c"].post(EVALUAR, data=_visto(), headers={"X-Requested-With": "fetch"})
    assert r.status_code == 402 and _evaluaciones() == []


def _evaluacion_lista(cliente="acme", ideas=None):
    eid = datos.crear_evaluacion(cliente, [A], _hace(29), _hace(0), "SEK",
                                 [{"ref": "A1", "ad_id": "gana", "nombre": "Video <b>gana</b>"}], [])
    datos.actualizar_evaluacion(eid, estado="lista", usd=0.2, resultado={
        "resumen": "Norway vende con <script>un video</script>.", "diagnostico": [{"causa": "Perdedores", "evidencia": ""}],
        "plan": [{"prioridad": 1, "accion": "pausar", "objetos": ["A1"], "que_hacer": "Pausa el perdedor",
                  "por_que": "gasta", "impacto": None,
                  "enlace": "https://adsmanager.facebook.com/adsmanager/manage/ads?act=1&selected_ad_ids=9"}],
        "patrones_ganadores": [{"patron": "Demostración", "anuncios": ["A1"]}], "patrones_perdedores": [],
        "anuncios": {}, "cifras_sin_dato": [],
        "ideas": ideas if ideas is not None else [{"titulo": "Sandalia en la lluvia", "prompt": "Close-up of feet",
                                                   "angulo": {"gancho": "¿Pies mojados?"}}]})
    return eid


def test_ver_una_evaluacion_y_la_de_otro_proyecto_es_404(conectado):
    eid = _evaluacion_lista()
    html = conectado["c"].get(f"/cliente/acme/meta-rendimiento/evaluacion/{eid}").get_data(as_text=True)
    assert "Pausa el perdedor" in html and "Sandalia en la lluvia" in html and "Video &lt;b&gt;gana&lt;/b&gt;" in html
    assert "<script>un video" not in html and 'rel="noopener noreferrer"' in html
    assert f"/cliente/acme/meta-rendimiento/evaluacion/{eid}/idea/0/crear" in html
    ajena = _evaluacion_lista(cliente="otro")
    assert conectado["c"].get(f"/cliente/acme/meta-rendimiento/evaluacion/{ajena}").status_code == 404
    assert conectado["c"].get("/cliente/acme/meta-rendimiento/evaluacion/99999").status_code == 404
    assert conectado["c"].get(f"/cliente/acme/meta-rendimiento/evaluacion/{2 ** 64}").status_code == 404


def test_una_evaluacion_en_curso_o_fallida_se_dice_en_palabras(conectado):
    eid = datos.crear_evaluacion("acme", [A], _hace(29), _hace(0), "SEK", [], [])
    assert "Evaluando con IA" in conectado["c"].get(f"/cliente/acme/meta-rendimiento/evaluacion/{eid}").get_data(as_text=True)
    datos.actualizar_evaluacion(eid, estado="error", error="Claude no devolvió un análisis que se pueda usar.")
    html = conectado["c"].get(f"/cliente/acme/meta-rendimiento/evaluacion/{eid}").get_data(as_text=True)
    assert "falló" in html and "Claude no devolvió" in html


def test_llevar_una_idea_a_crear_deja_el_prefill_con_el_origen_de_meta_sin_generar_nada(conectado):
    eid = _evaluacion_lista()
    r = conectado["c"].post(f"/cliente/acme/meta-rendimiento/evaluacion/{eid}/idea/0/crear")
    assert r.status_code == 302 and r.headers["Location"].endswith("/cliente/acme#creativeflowplus")
    with conectado["c"].session_transaction() as s:
        assert s["fp_prefill"]["texto"] == "Close-up of feet" and s["fp_prefill"]["origen_tw"] == f"meta:{eid}:0"
    with db.conectar() as con:
        assert con.execute(sa.select(sa.func.count()).select_from(db.tarea)).scalar() == 0
    assert conectado["c"].post(f"/cliente/acme/meta-rendimiento/evaluacion/{eid}/idea/1/crear").status_code == 404
    ajena = _evaluacion_lista(cliente="otro")
    assert conectado["c"].post(f"/cliente/acme/meta-rendimiento/evaluacion/{ajena}/idea/0/crear").status_code == 404
    en_cola = datos.crear_evaluacion("acme", [A], _hace(29), _hace(0), "SEK", [], [])
    assert conectado["c"].post(f"/cliente/acme/meta-rendimiento/evaluacion/{en_cola}/idea/0/crear").status_code == 404
    sin_prompt = _evaluacion_lista(ideas=[{"titulo": "X", "prompt": ""}])
    r = conectado["c"].post(f"/cliente/acme/meta-rendimiento/evaluacion/{sin_prompt}/idea/0/crear")
    assert r.status_code == 302 and any("no tiene prompt" in m for m in _flashes(conectado["c"]))


def test_crear_guarda_la_idea_de_meta_aparte_y_triple_whale_no_la_toma_por_suya(app_crear):
    import creative_flow as cf
    from triple_whale import datos as tw_datos
    eid = _evaluacion_lista()
    # Una evaluación de Triple Whale con el MISMO id: el origen de Meta nunca se confunde con ella.
    tw_eid = tw_datos.crear_evaluacion("acme", "2026-09-01", "2026-09-28", "USD", [])
    tw_datos.actualizar_evaluacion(tw_eid, estado="lista", resultado={"ideas": [{"titulo": "De TW", "prompt": "p"}]})
    assert tw_eid == eid
    data = {"accion_central": "el florero se quiebra", "duracion_objetivo": "8", "aspect_ratio": "9:16",
            "tipo": "video", "modelo": "wan3", "musica_estilo": "", "bandeja_vista": "1", "origen_tw": f"meta:{eid}:0"}
    assert app_crear["c"].post("/cliente/acme/creative_flow/crear", data=data).status_code == 302
    [(_, entry)] = cf.cargar("acme").items()
    assert entry["meta_idea"] == {"evaluacion_id": eid, "idea": 0, "titulo": "Sandalia en la lluvia"}
    assert "tw_idea" not in entry


def test_los_post_de_la_evaluacion_frenan_otro_sitio_y_el_correo_sin_verificar(conectado, app):  # noqa: F811
    import usuarios
    _sembrar()
    eid = _evaluacion_lista()
    for url in (EVALUAR, f"/cliente/acme/meta-rendimiento/evaluacion/{eid}/idea/0/crear"):
        assert conectado["c"].post(url, data={"dias": "30"}, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    usuarios.actualizar("user_acme", correo_verificado=False)
    r = _como_cliente(app).post(EVALUAR, data=_visto())
    assert r.headers["Location"].endswith("/cliente/acme#settings") and len(_evaluaciones()) == 1
    # Cualquier persona del proyecto con su correo verificado la puede pedir (paga su saldo): no es solo del admin.
    usuarios.actualizar("user_acme", correo_verificado=True)
    _como_cliente(app).post(EVALUAR, data=_visto())
    assert len(_evaluaciones()) == 2 and _evaluaciones()[0]["pedido_por"] == "user_acme"


def test_una_idea_llevada_a_crear_en_un_proyecto_no_se_usa_en_otro(conectado):
    """El prefill lleva su proyecto: abierto Crear en otro, `_prefill_para` lo descarta (revisión de seguridad E2;
    vale también para Triple Whale, que usa el mismo `prefill_crear`)."""
    import flask
    dashboard = conectado["dashboard"]
    eid = _evaluacion_lista()
    conectado["c"].post(f"/cliente/acme/meta-rendimiento/evaluacion/{eid}/idea/0/crear")
    with conectado["c"].session_transaction() as s:
        prefill = s["fp_prefill"]
    assert prefill["cliente"] == "acme"
    with dashboard.app.test_request_context():
        flask.session["fp_prefill"] = dict(prefill)
        assert dashboard._prefill_para("otro") is None and "fp_prefill" not in flask.session
        flask.session["fp_prefill"] = dict(prefill)
        assert dashboard._prefill_para("acme")["texto"] == "Close-up of feet"


def _evaluacion_con_miniaturas(cliente, estado, muestra):
    eid = datos.crear_evaluacion(cliente, [A], "2026-09-10", "2026-10-09", "SEK", muestra, [], "ana")
    datos.actualizar_evaluacion(eid, estado=estado)
    return eid


COPIADA = {"imagen": "https://r2.example/x.jpg", "imagen_origen": "https://scontent.xx.fbcdn.net/x.jpg"}


def test_desconectar_meta_borra_de_r2_las_miniaturas_de_sus_evaluaciones(conectado, monkeypatch):
    """Revisión de seguridad E2: lo que la evaluación copió de Meta a R2 se va con la desconexión, como sus filas."""
    from storage import r2_uploader
    borradas, momentos = [], []

    def borrar(claves):
        # Las filas con los nombres y las métricas ya no están cuando se tocan las miniaturas (E2, orden de borrado).
        momentos.append(datos.evaluaciones("acme", limite=50))
        borradas.extend(claves)
        return len(claves), []
    monkeypatch.setattr(r2_uploader, "delete_files", borrar)
    lista = _evaluacion_con_miniaturas("acme", "lista", [
        {"ref": "A1", "medio": COPIADA}, {"ref": "A2", "medio": {"imagen": None}},
        {"ref": "A3", "medio": {"imagen": "https://r2.example/p.jpg", "imagen_origen": "https://r2.example/p.jpg",
                                "origen": "creatv"}}])                   # la pieza de Creatv no es suya: no se borra
    fallida = _evaluacion_con_miniaturas("acme", "error", [{"ref": "A1"}, {"ref": "A2"}])   # pudo copiar antes de fallar
    ajena = _evaluacion_con_miniaturas("otro", "lista", [{"ref": "A1", "medio": COPIADA}])
    _desconectar(conectado, monkeypatch)
    base = "clientes/acme/meta_rendimiento"
    assert sorted(borradas) == sorted([f"{base}/eval{lista}_A1.jpg", f"{base}/eval{fallida}_A1.jpg",
                                       f"{base}/eval{fallida}_A2.jpg"])
    assert datos.evaluaciones("acme") == [] and datos.evaluacion("otro", ajena) is not None
    assert momentos == [[]]                                                # una sola llamada, con las filas ya borradas
    assert not any("no se pudieron borrar" in m for m in _flashes(conectado["c"]))


def test_si_r2_falla_las_evaluaciones_ya_estaban_borradas_y_se_avisa_una_vez(conectado, monkeypatch):
    """Un R2 caído o lento no deja nombres ni métricas guardados: las filas se borran ANTES de tocar R2."""
    from storage import r2_uploader
    vistas = []

    def _falla(claves):
        vistas.append(datos.evaluaciones("acme", limite=50))
        raise RuntimeError(f"Faltan R2_ACCOUNT_ID {TOKEN}")
    monkeypatch.setattr(r2_uploader, "delete_files", _falla)
    _evaluacion_con_miniaturas("acme", "lista", [{"ref": "A1", "medio": COPIADA}])
    assert _desconectar(conectado, monkeypatch).status_code == 302
    assert datos.evaluaciones("acme") == [] and vistas == [[]]
    mensajes = _flashes(conectado["c"])
    assert sum("no se pudieron borrar sus métricas copiadas (RuntimeError)" in m for m in mensajes) == 1
    assert all(TOKEN not in m and "R2_ACCOUNT_ID" not in m for m in mensajes)        # solo el tipo, nunca el texto


def test_si_a_r2_se_le_quedan_algunas_claves_se_avisa_con_el_tipo_y_las_filas_se_borraron(conectado, monkeypatch):
    from storage import r2_uploader
    monkeypatch.setattr(r2_uploader, "delete_files", lambda claves: (len(claves) - 1, ["EndpointConnectionError"]))
    _evaluacion_con_miniaturas("acme", "lista", [{"ref": "A1", "medio": COPIADA}, {"ref": "A2", "medio": COPIADA}])
    _desconectar(conectado, monkeypatch)
    assert datos.evaluaciones("acme") == []
    assert sum("no se pudieron borrar sus métricas copiadas (EndpointConnectionError)" in m
               for m in _flashes(conectado["c"])) == 1


def test_sin_miniaturas_que_borrar_no_se_toca_r2(conectado, monkeypatch):
    from storage import r2_uploader
    llamadas = []
    monkeypatch.setattr(r2_uploader, "_client", lambda: llamadas.append(1))      # armar un cliente sería un error
    monkeypatch.delenv("R2_BUCKET_NAME", raising=False)
    _evaluacion_con_miniaturas("acme", "lista", [{"ref": "A1", "medio": {"imagen": None}}])
    _desconectar(conectado, monkeypatch)
    assert datos.evaluaciones("acme") == [] and llamadas == []
    assert not any("no se pudieron borrar" in m for m in _flashes(conectado["c"]))


def test_si_borrar_las_filas_falla_las_miniaturas_se_borran_igual_y_se_reintenta_con_las_filas_que_queden(
        conectado, monkeypatch):
    from storage import r2_uploader
    borradas = []
    monkeypatch.setattr(r2_uploader, "delete_files", lambda claves: (borradas.extend(claves), (len(claves), []))[1])

    def _falla(cliente):
        raise ValueError("base bloqueada")
    monkeypatch.setattr(datos, "borrar_evaluaciones", _falla)
    eid = _evaluacion_con_miniaturas("acme", "lista", [{"ref": "A1", "medio": COPIADA}])
    _desconectar(conectado, monkeypatch)
    assert borradas == [f"clientes/acme/meta_rendimiento/eval{eid}_A1.jpg"] and datos.evaluacion("acme", eid)
    assert sum("(ValueError)" in m for m in _flashes(conectado["c"])) == 1


# ---- «Evaluación con IA» en el panel (E2, Task 6) ----------------------------------------------------------

PANEL = "/cliente/acme/meta-rendimiento/panel"


def _ocultos(html):
    """Los campos ocultos del formulario «Evaluar con IA» del panel, como los mandaría el navegador."""
    import re
    i = html.index('id="meta-evaluacion"')
    form = html[html.index("<form", i):html.index("</form>", i)]
    return dict(re.findall(r'<input type="hidden" name="([a-z_]+)" value="([^"]*)"', form)), form


def test_el_panel_trae_evaluar_con_ia_tras_el_diagnostico_con_el_precio_de_lo_que_cobra(conectado):
    import gastos
    from meta_rendimiento import analisis
    _sembrar()
    html = conectado["c"].get(PANEL).get_data(as_text=True)
    assert html.index('id="meta-diagnostico"') < html.index('id="meta-evaluacion"') < html.index("Día a día")
    n = len(analisis.preparar("acme", 30, "")["muestra"])
    precio = gastos.estimar("evaluacion_meta", n=n)
    campos, form = _ocultos(html)
    assert campos == {"dias": "30", "cuenta": "", "n": str(n), "precio_visto": str(precio["usd_precio"])}
    assert f"Evaluar {n} anuncio(s) con IA · {precio['texto']}" in form
    assert f"data-confirmar=\"¿Evaluar {n} anuncio(s) con IA? Precio: {precio['texto']}\"" in form
    assert "Evalúa lo que ves arriba: Todas las cuentas, últimos 30 días." in form
    assert "<script" not in html
    # Lo que manda ese formulario es justo lo que la ruta acepta: crea la evaluación y la encola.
    r = conectado["c"].post(EVALUAR, data=campos)
    assert r.status_code == 302 and len(_evaluaciones()) == 1 and len(_tareas("meta_rend_evaluar")) == 1


def test_el_boton_de_una_cuenta_y_otro_periodo_manda_ese_alcance(conectado):
    _sembrar()
    html = conectado["c"].get(PANEL + f"?cuenta={A}&dias=7").get_data(as_text=True)
    campos, form = _ocultos(html)
    assert campos["dias"] == "7" and campos["cuenta"] == A and "HappyFlops Norway, últimos 7 días" in form
    conectado["c"].post(EVALUAR, data=campos)
    ev, = _evaluaciones()
    assert ev["cuentas"] == [A] and ev["extra"]["dias"] == 7


def test_sin_muestra_el_panel_lo_dice_sin_boton(conectado):
    _dos_cuentas()
    f = _hace(2)
    datos.reemplazar_cuenta_dias("acme", A, f, f, [_dia(f, 400, 1000, compras=5)])
    html = conectado["c"].get(PANEL).get_data(as_text=True)
    seccion = html[html.index('id="meta-evaluacion"'):]
    assert "Todavía no hay anuncios con datos suficientes para evaluar con IA." in seccion
    assert EVALUAR not in html


def test_con_una_evaluacion_viva_el_panel_pinta_su_barra_y_no_el_boton(conectado):
    _sembrar()
    conectado["c"].post(EVALUAR, data=_visto())
    html = conectado["c"].get(PANEL).get_data(as_text=True)
    seccion = html[html.index('id="meta-evaluacion"'):html.index("</section>", html.index('id="meta-evaluacion"'))]
    assert 'data-poll-job="acme__meta_eval"' in seccion and 'data-poll-al-terminar="evento"' in seccion
    assert 'id="meta-eval-barra-acme"' in seccion and "Evaluando con IA…" in seccion
    assert EVALUAR not in seccion and "<script" not in html


def test_el_panel_muestra_la_ultima_lista_entera_y_las_anteriores_por_fetch(conectado):
    _sembrar()
    vieja = _evaluacion_lista()
    fallo_viejo = datos.crear_evaluacion("acme", [A], _hace(29), _hace(0), "SEK", [], [])
    datos.actualizar_evaluacion(fallo_viejo, estado="error", error="Se cortó la conexión.")
    lista = _evaluacion_lista()
    fallo = datos.crear_evaluacion("acme", [A], _hace(29), _hace(0), "SEK", [], [])
    datos.actualizar_evaluacion(fallo, estado="error", error="Claude no devolvió un análisis que se pueda usar.")
    html = conectado["c"].get(PANEL).get_data(as_text=True)
    seccion = html[html.index('id="meta-evaluacion"'):html.index("Día a día")]
    assert "La última evaluación (Todas las cuentas) falló: Claude no devolvió" in seccion
    assert f'id="meta-eval-{lista}"' in seccion and "Pausa el perdedor" in seccion and "Sandalia en la lluvia" in seccion
    assert f"/cliente/acme/meta-rendimiento/evaluacion/{lista}/idea/0/crear" in seccion
    assert "Norway vende con &lt;script&gt;" in seccion and "<script>un video" not in seccion
    # Las anteriores no vienen pintadas: cada una se pide al abrirla.
    assert "2 evaluaciones anteriores" in seccion and f'id="meta-eval-{vieja}"' not in seccion
    for eid in (vieja, fallo_viejo):
        assert f'data-meta-ev="/cliente/acme/meta-rendimiento/evaluacion/{eid}"' in seccion
        assert f'aria-controls="meta-ev-{eid}"' in seccion and f'id="meta-ev-{eid}" hidden' in seccion
    assert f'data-meta-ev="/cliente/acme/meta-rendimiento/evaluacion/{fallo}"' not in seccion
    # La que falló hace tiempo, abierta sola, no dice que es «la última».
    vieja_html = conectado["c"].get(f"/cliente/acme/meta-rendimiento/evaluacion/{fallo_viejo}").get_data(as_text=True)
    assert "Esta evaluación falló: Se cortó la conexión." in vieja_html and "La última evaluación" not in vieja_html


def test_el_plan_nombra_sus_objetos_marca_las_cifras_sin_dato_y_solo_enlaza_al_administrador(conectado):
    eid = datos.crear_evaluacion(
        "acme", [A], _hace(29), _hace(0), "SEK",
        [{"ref": "A1", "ad_id": "9", "nombre": "Video <b>gana</b>", "veredicto": "ganador",
          "medio": {"imagen": "https://scontent.xx.fbcdn.net/gana.jpg"}},
         {"ref": "A2", "ad_id": "8", "nombre": "Foto pierde", "veredicto": "perdedor",
          "medio": {"imagen": "https://malo.example/x.jpg"}}],
        [{"ref": "R1", "titulo": "Consolida <i>los conjuntos</i>"}], extra={"cuenta": A, "resumen": [
            {"ad_account_id": A, "nombre": "HappyFlops Norway"}]})
    datos.actualizar_evaluacion(eid, estado="lista", usd=0.2, resultado={
        "resumen": "Va bien.", "diagnostico": [{"causa": "Fatiga", "evidencia": "frecuencia 4,1"}],
        "plan": [{"prioridad": 1, "accion": "consolidar", "objetos": ["A1", "R1"], "que_hacer": "Junta los conjuntos",
                  "por_que": "Hay 461 en aprendizaje limitado", "impacto": "1.200 SEK por semana",
                  "enlace": "https://adsmanager.facebook.com/adsmanager/manage/ads?act=1&selected_ad_ids=9"},
                 {"prioridad": 2, "accion": "otro", "objetos": [], "que_hacer": "Revisa la página",
                  "por_que": "", "impacto": None, "enlace": "javascript:alert(1)"}],
        "patrones_ganadores": [{"patron": "Demostración", "anuncios": ["A1"]}], "patrones_perdedores": [],
        "anuncios": {"A1": {"por_que": "Muestra el producto en uso", "gancho": "pies mojados"}}, "ideas": [],
        "cifras_sin_dato": ["461", "1.200 SEK"]})
    html = conectado["c"].get(f"/cliente/acme/meta-rendimiento/evaluacion/{eid}").get_data(as_text=True)
    assert "Evaluación de HappyFlops Norway del" in html
    assert "Claude citó cifras que no están en los datos: 461, 1.200 SEK. Compruébalas" in html
    paso1 = html[html.index("Junta los conjuntos") - 400:html.index("Revisa la página")]
    assert "Consolidar" in paso1 and "Video &lt;b&gt;gana&lt;/b&gt;" in paso1
    assert "Consolida &lt;i&gt;los conjuntos&lt;/i&gt;" in paso1 and "Recomendación" in paso1
    assert 'href="https://adsmanager.facebook.com/adsmanager/manage/ads?act=1&amp;selected_ad_ids=9"' in paso1
    assert "javascript:" not in html and html.count("Ver en el Administrador de anuncios") == 1
    # «Anuncio por anuncio»: la miniatura de Meta válida sí, la de otro host no.
    assert 'src="https://scontent.xx.fbcdn.net/gana.jpg"' in html and "malo.example" not in html
    assert "Muestra el producto en uso" in html and "<script" not in html
