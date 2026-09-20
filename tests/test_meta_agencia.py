"""Meta en modo agencia (meta_agencia.py + meta_conexion): la conexión del
Business de Creatv va cifrada en kv, los activos salen de los edges del
Business, un proyecto asignado recibe el token al leer meta.json (sin que el
token toque el disco) y el modo propia se restaura al desasignar. Sin red:
meta_conexion._graph_get va parcheado con un despachador por edge."""
import json
import logging
import os
import stat

import pytest
import sqlalchemy as sa

import meta_conexion as mc

TOKEN = "EAAB-token-de-agencia-super-secreto"
BID = "123456"
PAGINAS = [
    {"id": "p1", "name": "Página Propia", "instagram_business_account": {"id": "ig1", "username": "propia_ig"}},
]
PAGINAS_CLIENTE = [{"id": "p2", "name": "Página Cliente"}]


def _respuestas(cuentas_propias=None):
    """Respuestas de Graph por edge; owned_ad_accounts viene en dos páginas."""
    propias = cuentas_propias if cuentas_propias is not None else [
        {"id": "act_1", "name": "Cuenta 1", "currency": "COP", "account_status": 1},
    ]
    return {
        "me": {"id": "u1", "name": "Creatv Sistema"},
        BID: {"id": BID, "name": "Creatv BM"},
        f"{BID}/owned_ad_accounts": {
            None: {"data": propias, "paging": {"cursors": {"after": "CUR1"},
                                                "next": f"https://graph.facebook.com/x?access_token={TOKEN}&after=CUR1"}},
            "CUR1": {"data": [{"id": "act_2", "name": "Cuenta 2", "currency": "USD", "account_status": 2}],
                     "paging": {"cursors": {"after": "CUR2"}}},
        },
        f"{BID}/client_ad_accounts": {"data": [{"id": "act_9", "name": "Cuenta Socio", "currency": "MXN", "account_status": 1}]},
        f"{BID}/owned_pages": {"data": PAGINAS},
        f"{BID}/client_pages": {"data": PAGINAS_CLIENTE},
        "p1": {"id": "p1", "name": "Página Propia", "access_token": "PAGE-TOKEN-1",
               "instagram_business_account": {"id": "ig1", "username": "propia_ig"}},
        "p2": {"id": "p2", "name": "Página Cliente", "access_token": "PAGE-TOKEN-2"},
    }


@pytest.fixture()
def entorno(base_temporal, monkeypatch, tmp_path):
    """kv en base temporal, clientes/ temporal, FLASK_SECRET_KEY falsa y Graph
    falso. `graph["llamadas"]` acumula (edge, params sin token);
    `graph["respuestas"]` se puede editar por test."""
    import estado as estado_mod
    import meta_agencia as ma
    monkeypatch.setenv("FLASK_SECRET_KEY", "clave-de-prueba")
    monkeypatch.setattr(mc, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    (tmp_path / "clientes" / "otro").mkdir(parents=True)
    monkeypatch.setattr(estado_mod, "listar_clientes",
                        lambda: sorted(d for d in os.listdir(tmp_path / "clientes") if not d.startswith(".")))
    ma._cache_activos = None
    ma._cache_estado = None
    ma._cache_registro = None

    graph = {"llamadas": [], "respuestas": _respuestas(), "tokens": []}

    def _graph_get(edge, token, params=None, timeout=30):
        params = dict(params or {})
        graph["tokens"].append(token)
        graph["llamadas"].append((edge, params))
        r = graph["respuestas"].get(edge)
        if r is None:
            raise mc.MetaConexionError("Meta respondió: Unsupported get request.", codigo=100)
        if isinstance(r, Exception):
            raise r
        if isinstance(r, dict) and None in r:   # paginado por cursor
            return r[params.get("after")]
        return r
    monkeypatch.setattr(mc, "_graph_get", _graph_get)
    yield {"graph": graph, "ma": ma, "raiz": tmp_path}
    ma._cache_activos = None
    ma._cache_estado = None
    ma._cache_registro = None


def _kv_crudo(base_temporal):
    with base_temporal.conectar() as con:
        return con.execute(sa.select(base_temporal.kv.c.valor).where(base_temporal.kv.c.clave == "meta_agencia")).scalar()


def _meta_json(entorno, cliente):
    ruta = entorno["raiz"] / "clientes" / cliente / "meta.json"
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None


# ---------- conexión ----------

def test_sin_conectar(entorno):
    ma = entorno["ma"]
    assert ma.conectada() is False
    assert ma.publica() is None
    assert ma.estado()["estado"] == "sin_conectar"
    with pytest.raises(ma.MetaAgenciaError, match="no está conectada"):
        ma.token()
    with pytest.raises(ma.MetaAgenciaError):
        ma.listar_activos()


def test_conectar_valida_guarda_cifrado_y_publica_sin_token(entorno, base_temporal):
    ma, graph = entorno["ma"], entorno["graph"]
    pub = ma.conectar(f"  {TOKEN} ", f" {BID} ")
    assert pub["business_id"] == BID and pub["business_nombre"] == "Creatv BM"
    assert pub["usuario_nombre"] == "Creatv Sistema" and pub["conectado_en"]
    assert "token" not in pub
    assert [e for e, _ in graph["llamadas"]] == ["me", BID]
    assert graph["llamadas"][0][1] == {"fields": "id,name"}
    assert graph["llamadas"][1][1] == {"fields": "id,name"}

    crudo = _kv_crudo(base_temporal)
    assert crudo and TOKEN not in crudo
    assert ma.conectada() and ma.token() == TOKEN
    assert ma.publica() == pub
    assert TOKEN not in json.dumps(ma.publica())


def test_conectar_falla_si_falta_flask_secret_key(entorno, monkeypatch, base_temporal):
    ma = entorno["ma"]
    monkeypatch.delenv("FLASK_SECRET_KEY")
    with pytest.raises(ma.MetaAgenciaError, match="FLASK_SECRET_KEY"):
        ma.conectar(TOKEN, BID)
    assert _kv_crudo(base_temporal) is None


def test_conectar_falla_si_el_token_no_sirve_y_no_guarda(entorno, base_temporal, caplog):
    ma, graph = entorno["ma"], entorno["graph"]
    graph["respuestas"]["me"] = mc.MetaConexionError("Meta respondió: Invalid OAuth access token.", codigo=190)
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(mc.MetaConexionError, match="Invalid OAuth") as ei:
            ma.conectar(TOKEN, BID)
    assert TOKEN not in str(ei.value) and TOKEN not in caplog.text
    assert _kv_crudo(base_temporal) is None and not ma.conectada()


def test_conectar_falla_si_el_token_no_ve_el_business(entorno, base_temporal):
    ma = entorno["ma"]
    with pytest.raises(ma.MetaAgenciaError, match="no ve el Business 999"):
        ma.conectar(TOKEN, "999")
    assert _kv_crudo(base_temporal) is None


def test_conectar_exige_datos(entorno):
    ma = entorno["ma"]
    with pytest.raises(ma.MetaAgenciaError, match="Faltan datos"):
        ma.conectar("", BID)
    with pytest.raises(ma.MetaAgenciaError, match="Faltan datos"):
        ma.conectar(TOKEN, "")


def test_desconectar_borra_kv_y_desasigna_los_proyectos(entorno, base_temporal):
    """M4: desconectar() ya no deja proyectos en modo agencia sin token (con
    su page_access_token todavía sirviendo) — los desasigna, así
    organico/meta_uploader dejan de poder publicar con Páginas del Business
    que ya no está conectado."""
    ma = entorno["ma"]
    ma.conectar(TOKEN, BID)
    ma.asignar("acme", "act_1", "p1")
    assert mc.estado("acme")["estado"] == "conectado"
    r = ma.desconectar()
    assert r == {"habia": True, "desasignados": 1}
    assert _kv_crudo(base_temporal) is None
    assert not ma.conectada() and ma.publica() is None
    # el proyecto vuelve a modo propia (sin respaldo previo: sin meta.json)
    assert mc.modo("acme") == "propia"
    assert mc.cargar("acme") is None
    assert mc.estado("acme") == {"estado": "sin_conectar", "detalle": {}, "verificado": True}
    with pytest.raises(mc.MetaConexionError, match="no tiene Meta conectado"):
        mc.credenciales_ads("acme")
    assert ma.proyectos_asignados() == {}
    # segunda vez: no había nada que borrar ni nadie que desasignar
    assert ma.desconectar() == {"habia": False, "desasignados": 0}


def test_desconectar_restaura_el_respaldo_propio_de_cada_proyecto(entorno):
    ma = entorno["ma"]
    propia = {"token": "TOKEN-PROPIO", "ad_account_id": "act_propia", "page_id": "pp"}
    mc.guardar("acme", propia)
    ma.conectar(TOKEN, BID)
    ma.asignar("acme", "act_1", "p1")
    ma.asignar("otro", "act_2")
    assert ma.desconectar() == {"habia": True, "desasignados": 2}
    assert mc.modo("acme") == "propia" and mc.cargar("acme") == propia
    assert mc.modo("otro") == "propia" and mc.cargar("otro") is None


def test_registro_ilegible_cuenta_como_sin_conectar(entorno, base_temporal, monkeypatch, caplog):
    ma = entorno["ma"]
    ma.conectar(TOKEN, BID)
    monkeypatch.setenv("FLASK_SECRET_KEY", "otra-clave")   # rotó la clave
    ma._cache_registro = None
    with caplog.at_level(logging.WARNING):
        assert ma.conectada() is False
    assert TOKEN not in caplog.text
    with pytest.raises(ma.MetaAgenciaError):
        ma.token()


def test_registro_ilegible_se_cachea_y_avisa_una_sola_vez(entorno, monkeypatch, caplog):
    """M2: cada cargar() de un proyecto en modo agencia (uno por render) no
    debe volver a descifrar ni a loguear mientras el registro siga
    ilegible."""
    ma = entorno["ma"]
    ma.conectar(TOKEN, BID)
    monkeypatch.setenv("FLASK_SECRET_KEY", "otra-clave")   # rotó la clave
    ma._cache_registro = None
    with caplog.at_level(logging.WARNING):
        for _ in range(5):
            assert ma.conectada() is False
    avisos = [r for r in caplog.records if "no se puede leer" in r.message]
    assert len(avisos) == 1


def test_estado_del_proyecto_agencia_con_registro_ilegible(entorno, monkeypatch):
    """M3: distinto motivo cuando el registro de la agencia existe pero no
    se puede leer (rotó FLASK_SECRET_KEY) frente a cuando nadie la conectó."""
    ma = entorno["ma"]
    ma.conectar(TOKEN, BID)
    ma.asignar("acme", "act_1", "p1")
    monkeypatch.setenv("FLASK_SECRET_KEY", "otra-clave")
    ma._cache_registro = None
    r = mc.estado("acme")
    assert r["estado"] == "roto"
    assert "ilegible" in r["motivo"] and "FLASK_SECRET_KEY" in r["motivo"]
    assert TOKEN not in r["motivo"]


def test_estado_del_proyecto_agencia_realmente_sin_conectar(entorno, base_temporal):
    """Caso distinto del anterior: la fila de kv desapareció (no rotó la
    clave) — el motivo sigue siendo el genérico de siempre."""
    ma = entorno["ma"]
    ma.conectar(TOKEN, BID)
    ma.asignar("acme", "act_1", "p1")
    with base_temporal.conectar() as con:
        con.execute(base_temporal.kv.delete().where(base_temporal.kv.c.clave == "meta_agencia"))
    ma._cache_registro = None
    r = mc.estado("acme")
    assert r["estado"] == "roto" and r["motivo"] == "La agencia no está conectada"


def test_estado_agencia_conectada_rota_y_cache(entorno, monkeypatch):
    ma, graph = entorno["ma"], entorno["graph"]
    ma.conectar(TOKEN, BID)
    n = len(graph["llamadas"])
    r = ma.estado()
    assert r["estado"] == "conectada" and r["verificado"] and r["detalle"]["business_id"] == BID
    assert "token" not in r["detalle"] and TOKEN not in json.dumps(r)
    assert graph["llamadas"][n] == ("me", {"fields": "id"})
    assert ma.estado() is r and len(graph["llamadas"]) == n + 1   # cacheado
    # vence el TTL y el token ya no vale
    t0 = ma._cache_estado[0]
    monkeypatch.setattr(ma.time, "time", lambda: t0 + ma._TTL_ESTADO_SEG + 1)
    graph["respuestas"]["me"] = mc.MetaConexionError("Meta respondió: Error validating access token", codigo=190)
    r = ma.estado()
    assert r["estado"] == "rota" and "validating" in r["motivo"] and TOKEN not in r["motivo"]


def test_estado_agencia_fallo_de_red_conserva_lo_ultimo(entorno, monkeypatch):
    ma, graph = entorno["ma"], entorno["graph"]
    ma.conectar(TOKEN, BID)
    assert ma.estado()["estado"] == "conectada"
    t0 = ma._cache_estado[0]
    monkeypatch.setattr(ma.time, "time", lambda: t0 + ma._TTL_ESTADO_SEG + 1)
    graph["respuestas"]["me"] = mc.MetaConexionError("No pude hablar con Meta (Timeout).")
    assert ma.estado()["estado"] == "conectada"


# ---------- activos ----------

def test_listar_activos_marca_activa_segun_account_status(entorno):
    """M7: no se filtran cuentas por estado, pero se marca cuál está activa
    (account_status == 1) para que Task 2 pueda avisar en el <select>."""
    ma = entorno["ma"]
    ma.conectar(TOKEN, BID)
    activos = ma.listar_activos()
    por_id = {a["id"]: a for a in activos["ad_accounts"]}
    assert por_id["act_1"]["activa"] is True and por_id["act_1"]["account_status"] == 1
    assert por_id["act_2"]["activa"] is False and por_id["act_2"]["account_status"] == 2
    assert por_id["act_9"]["activa"] is True and por_id["act_9"]["account_status"] == 1


def test_paginar_corta_si_el_cursor_no_avanza(entorno):
    """M1: un Graph que devuelve `next` con el mismo cursor `after` de
    siempre (visto en una sonda manual) no debe colgar el proceso."""
    ma, graph = entorno["ma"], entorno["graph"]
    ma.conectar(TOKEN, BID)
    edge = f"{BID}/owned_ad_accounts"
    graph["respuestas"][edge] = {
        "data": [{"id": "act_1", "name": "Cuenta 1", "currency": "COP", "account_status": 1}],
        "paging": {"cursors": {"after": "CUR-FIJO"},
                   "next": f"https://graph.facebook.com/x?access_token={TOKEN}&after=CUR-FIJO"},
    }
    graph["llamadas"].clear()
    activos = ma.listar_activos()
    llamadas_edge = [ll for ll in graph["llamadas"] if ll[0] == edge]
    assert len(llamadas_edge) == 2   # primera página + la que repite el cursor, y corta ahí
    assert any(a["id"] == "act_1" for a in activos["ad_accounts"])


def test_paginar_corta_con_tope_si_el_cursor_nunca_termina(entorno, monkeypatch):
    """M1: si el cursor sí avanza pero Graph jamás deja de traer `next`
    (bucle real contra un tercero), corta a las 50 páginas con un error
    claro en vez de colgar el proceso."""
    ma = entorno["ma"]
    ma.conectar(TOKEN, BID)
    edge = f"{BID}/owned_ad_accounts"
    original = mc._graph_get
    contador = {"n": 0}

    def _graph_get(e, token, params=None, timeout=30):
        if e != edge:
            return original(e, token, params, timeout)
        contador["n"] += 1
        return {"data": [{"id": f"act_pag{contador['n']}", "name": "x", "currency": "COP", "account_status": 1}],
                "paging": {"cursors": {"after": f"CUR{contador['n']}"}, "next": "https://x"}}
    monkeypatch.setattr(mc, "_graph_get", _graph_get)
    with pytest.raises(ma.MetaAgenciaError, match="no termina de paginar"):
        ma.listar_activos()
    assert contador["n"] == ma._TOPE_PAGINAS


def test_listar_activos_origen_paginacion_y_cache(entorno):
    ma, graph = entorno["ma"], entorno["graph"]
    ma.conectar(TOKEN, BID)
    graph["llamadas"].clear()
    activos = ma.listar_activos()
    assert [(a["id"], a["origen"], a["currency"]) for a in activos["ad_accounts"]] == [
        ("act_1", "propia", "COP"), ("act_2", "propia", "USD"), ("act_9", "cliente", "MXN")]
    assert activos["pages"] == [
        {"id": "p1", "name": "Página Propia", "ig_user_id": "ig1", "ig_username": "propia_ig", "origen": "propia"},
        {"id": "p2", "name": "Página Cliente", "ig_user_id": None, "ig_username": None, "origen": "cliente"},
    ]
    edges = [e for e, _ in graph["llamadas"]]
    assert edges == [f"{BID}/owned_ad_accounts", f"{BID}/owned_ad_accounts", f"{BID}/client_ad_accounts",
                     f"{BID}/owned_pages", f"{BID}/client_pages"]
    # segunda página por cursor `after`, nunca por la URL `next` (lleva el token)
    assert graph["llamadas"][1][1]["after"] == "CUR1"
    assert all(p.get("limit") == 100 for _, p in graph["llamadas"])
    assert all("access_token" not in json.dumps(p) for _, p in graph["llamadas"])
    assert graph["llamadas"][0][1]["fields"] == "id,name,currency,account_status"
    assert graph["llamadas"][3][1]["fields"] == "id,name,instagram_business_account{id,username}"
    # caché
    n = len(graph["llamadas"])
    assert ma.listar_activos() is activos and len(graph["llamadas"]) == n
    assert ma.listar_activos(forzar=True) is not activos and len(graph["llamadas"]) == 2 * n


def test_listar_activos_no_registra_el_token_en_logs(entorno, caplog):
    ma = entorno["ma"]
    with caplog.at_level(logging.DEBUG):
        ma.conectar(TOKEN, BID)
        ma.listar_activos()
        ma.asignar("acme", "act_1", "p1")
        ma.estado()
    assert TOKEN not in caplog.text and "PAGE-TOKEN" not in caplog.text


# ---------- asignación ----------

def test_asignar_escribe_meta_json_sin_token_de_usuario(entorno, monkeypatch):
    ma, graph = entorno["ma"], entorno["graph"]
    ma.conectar(TOKEN, BID)
    detalle = ma.asignar("acme", "act_1", "p1", asignado_por="admin")
    assert detalle["modo"] == "agencia" and detalle["ad_account_id"] == "act_1"
    assert detalle["page_id"] == "p1" and detalle["ig_username"] == "propia_ig"
    assert detalle["cambio_cuenta"] is False
    # M6: asignado_por (correo/usuario del admin) no sale en el detalle público
    assert "asignado_por" not in detalle
    assert "token" not in detalle and "page_access_token" not in detalle

    ruta = entorno["raiz"] / "clientes" / "acme" / "meta.json"
    assert stat.S_IMODE(os.stat(ruta).st_mode) == 0o600
    crudo = ruta.read_text(encoding="utf-8")
    assert TOKEN not in crudo
    datos = json.loads(crudo)
    assert datos["modo"] == "agencia" and datos["modo_anterior"] == "propia"
    assert datos["business_id"] == BID
    assert datos["ad_account_id"] == "act_1" and datos["ad_account_nombre"] == "Cuenta 1" and datos["moneda"] == "COP"
    assert datos["page_id"] == "p1" and datos["page_access_token"] == "PAGE-TOKEN-1"
    assert datos["ig_user_id"] == "ig1" and datos["ig_username"] == "propia_ig"
    assert datos["asignado_en"] and datos["asignado_por"] == "admin"
    assert "token" not in datos and "propia_respaldo" not in datos
    # el token de Página se pidió con el token de agencia al edge de la Página
    assert ("p1", {"fields": "access_token,name,instagram_business_account{id,username}"}) in graph["llamadas"]

    # cargar() inyecta el token de agencia; credenciales_ads y el uploader funcionan
    cargado = mc.cargar("acme")
    assert cargado["token"] == TOKEN and cargado["ad_account_id"] == "act_1"
    assert mc.credenciales_ads("acme") == {"token": TOKEN, "ad_account_id": "act_1", "page_id": "p1", "ig_user_id": "ig1"}
    from uploaders import meta_uploader
    assert meta_uploader._credenciales("acme") == {"page_access_token": "PAGE-TOKEN-1", "page_id": "p1", "ig_user_id": "ig1"}
    assert mc.modo("acme") == "agencia" and mc.modo("otro") == "propia"
    assert ma.proyectos_asignados() == {"acme": mc._detalle(datos)}
    assert TOKEN not in json.dumps(ma.proyectos_asignados())


def test_asignar_sin_pagina(entorno):
    ma = entorno["ma"]
    ma.conectar(TOKEN, BID)
    detalle = ma.asignar("acme", "act_9")
    assert detalle["page_id"] is None and detalle["ad_account_id"] == "act_9"
    datos = _meta_json(entorno, "acme")
    assert datos["page_access_token"] is None and datos["moneda"] == "MXN" and datos["ad_account_origen"] == "cliente"
    creds = mc.credenciales_ads("acme")
    assert creds["page_id"] is None and creds["token"] == TOKEN
    with pytest.raises(RuntimeError, match="no tiene Meta conectado"):
        from uploaders import meta_uploader
        meta_uploader._credenciales("acme")


def test_asignar_rechaza_activos_que_no_ve_el_business(entorno):
    ma = entorno["ma"]
    ma.conectar(TOKEN, BID)
    with pytest.raises(ma.MetaAgenciaError, match="act_77"):
        ma.asignar("acme", "act_77")
    with pytest.raises(ma.MetaAgenciaError, match="Página p77"):
        ma.asignar("acme", "act_1", "p77")
    assert _meta_json(entorno, "acme") is None


def test_asignar_sin_token_de_pagina_falla_sin_escribir(entorno):
    ma, graph = entorno["ma"], entorno["graph"]
    ma.conectar(TOKEN, BID)
    graph["respuestas"]["p2"] = {"id": "p2", "name": "Página Cliente"}
    with pytest.raises(ma.MetaAgenciaError, match="no entregó token para la Página p2"):
        ma.asignar("acme", "act_1", "p2")
    assert _meta_json(entorno, "acme") is None


def test_asignar_sin_agencia_conectada(entorno):
    ma = entorno["ma"]
    with pytest.raises(ma.MetaAgenciaError, match="no está conectada"):
        ma.asignar("acme", "act_1")


def test_asignar_guarda_respaldo_propio_y_desasignar_lo_restaura(entorno):
    ma = entorno["ma"]
    propia = {"token": "TOKEN-PROPIO", "ad_account_id": "act_propia", "ad_account_nombre": "Mía",
              "page_id": "pp", "page_access_token": "PT-PROPIO", "moneda": "COP", "conectado_en": "2026-01-01T00:00:00"}
    mc.guardar("acme", propia)
    assert mc.modo("acme") == "propia" and mc.estado("acme")["detalle"]["modo"] == "propia"
    ma.conectar(TOKEN, BID)
    detalle = ma.asignar("acme", "act_1", "p1")
    assert detalle["cambio_cuenta"] is True
    datos = _meta_json(entorno, "acme")
    assert datos["propia_respaldo"] == propia and datos["modo_anterior"] == "propia"
    assert datos["ad_account_id"] == "act_1" and "token" not in datos
    # cargar() no expone el respaldo (trae el token propio) y trae el de la agencia
    cargado = mc.cargar("acme")
    assert "propia_respaldo" not in cargado and cargado["token"] == TOKEN
    assert mc.estado("acme")["detalle"]["modo"] == "agencia"
    assert "TOKEN-PROPIO" not in json.dumps(mc.estado("acme"))
    # reasignar conserva el respaldo original
    ma.asignar("acme", "act_2", "p2")
    datos = _meta_json(entorno, "acme")
    assert datos["propia_respaldo"] == propia and datos["ad_account_id"] == "act_2"
    # desasignar restaura lo propio tal cual
    assert ma.desasignar("acme") is True
    assert mc.modo("acme") == "propia"
    assert _meta_json(entorno, "acme") == propia
    assert mc.cargar("acme")["token"] == "TOKEN-PROPIO"
    assert ma.desasignar("acme") is False
    assert ma.conectada()   # la agencia sigue conectada


def test_desasignar_sin_respaldo_borra_meta_json(entorno):
    ma = entorno["ma"]
    ma.conectar(TOKEN, BID)
    ma.asignar("acme", "act_1", "p1")
    mc.estado("acme")
    assert "acme" in mc._cache_estado
    assert ma.desasignar("acme") is True
    assert _meta_json(entorno, "acme") is None
    assert "acme" not in mc._cache_estado
    assert mc.estado("acme")["estado"] == "sin_conectar" and mc.modo("acme") == "propia"
    assert ma.proyectos_asignados() == {}


def test_revocar_en_agencia_no_toca_nada(entorno):
    ma = entorno["ma"]
    ma.conectar(TOKEN, BID)
    ma.asignar("acme", "act_1", "p1")
    assert mc.revocar("acme") is False        # nada que revocar: el token es de la agencia
    assert mc.modo("acme") == "agencia" and mc.cargar("acme")["token"] == TOKEN


def test_borrar_en_agencia_rechaza_hay_que_desasignar(entorno):
    """I2: borrar() ya no desasigna por su cuenta — un botón "desconectar"
    pensado para modo propia no puede sacar de agencia a un proyecto sin que
    un admin lo decida explícitamente (meta_agencia.desasignar)."""
    ma = entorno["ma"]
    ma.conectar(TOKEN, BID)
    ma.asignar("acme", "act_1", "p1")
    ma.asignar("otro", "act_2")
    with pytest.raises(mc.ModoAgenciaError, match="modo agencia"):
        mc.borrar("acme")
    assert mc.modo("acme") == "agencia" and mc.cargar("acme")["token"] == TOKEN
    # el camino correcto (Task 2 lo expone en una ruta admin) sigue andando
    assert ma.desasignar("acme") is True
    assert mc.modo("acme") == "propia"
    assert ma.proyectos_asignados().keys() == {"otro"}
    assert mc.cargar("otro")["token"] == TOKEN


def test_url_dialogo_y_app_propia_rechazan_en_agencia(entorno, monkeypatch):
    ma = entorno["ma"]
    monkeypatch.setenv("META_REDIRECT_URI", "https://app.example/meta/callback")
    mc.guardar_app("acme", {"app_id": "1", "app_secret": "s", "login_config_id": "2"})
    ma.conectar(TOKEN, BID)
    ma.asignar("acme", "act_1", "p1")
    with pytest.raises(ValueError, match="modo agencia"):
        mc.url_dialogo("acme", "st")
    with pytest.raises(ValueError, match="modo agencia"):
        mc.cambiar_code_por_token("acme", "code")
    with pytest.raises(ValueError, match="modo agencia"):
        mc.guardar_app("acme", {"app_id": "1", "app_secret": "s", "login_config_id": "2"})
    # el otro proyecto (propia) sigue igual
    mc.guardar_app("otro", {"app_id": "1", "app_secret": "s", "login_config_id": "2"})
    assert "client_id=1" in mc.url_dialogo("otro", "st")


def test_modo_agencia_error_es_value_error_y_meta_conexion_error(entorno):
    """I1: sigue siendo un ValueError (lo que pedía el brief) pero también
    un MetaConexionError, así las rutas de hoy (meta_conectar, meta_app_guardar,
    meta_callback) que solo capturan `except meta_conexion.MetaConexionError`
    la atrapan y hacen flash en vez de un 500, sin tocar dashboard.py."""
    ma = entorno["ma"]
    ma.conectar(TOKEN, BID)
    ma.asignar("acme", "act_1", "p1")
    with pytest.raises(ValueError):
        mc.url_dialogo("acme", "st")
    with pytest.raises(mc.MetaConexionError):
        mc.url_dialogo("acme", "st")
    try:
        mc.url_dialogo("acme", "st")
        pytest.fail("esperaba ModoAgenciaError")
    except mc.ModoAgenciaError as e:
        assert isinstance(e, ValueError) and isinstance(e, mc.MetaConexionError)


def test_guardar_en_modo_agencia_rechaza_sin_permitir_agencia(entorno):
    """I2: nadie fuera de asignar/desasignar puede pisar meta.json de un
    proyecto en modo agencia — ni siquiera con datos "de buena fe" (p. ej.
    una ruta que complete un meta.pendiente.json viejo)."""
    ma = entorno["ma"]
    ma.conectar(TOKEN, BID)
    ma.asignar("acme", "act_1", "p1")
    with pytest.raises(mc.ModoAgenciaError, match="modo agencia"):
        mc.guardar("acme", {"token": "otro-token-propio"})
    assert mc.cargar("acme")["token"] == TOKEN   # no se pisó nada
    # permitir_agencia=True es lo que usan asignar/desasignar por dentro
    mc.guardar("acme", {"modo": "agencia", "ad_account_id": "act_9"}, permitir_agencia=True)
    assert mc._cargar_crudo("acme")["ad_account_id"] == "act_9"
    # en modo propia sigue sin exigir nada
    mc.guardar("otro", {"token": "T"})
    assert mc.cargar("otro")["token"] == "T"


def test_cargar_pendiente_no_sirve_en_modo_agencia(entorno):
    """I2: un meta.pendiente.json de una autorización propia vieja (de
    antes de que el admin asignara el proyecto) no debe poder completarse y
    pisar la asignación."""
    ma = entorno["ma"]
    ma.conectar(TOKEN, BID)
    ma.asignar("acme", "act_1", "p1")
    mc.guardar_pendiente("acme", {"token": "T", "tipo_token": "", "activos": {}})
    assert mc.cargar_pendiente("acme") is None
    # el otro proyecto (propia) no se ve afectado
    mc.guardar_pendiente("otro", {"token": "T", "tipo_token": "", "activos": {}})
    assert mc.cargar_pendiente("otro") is not None


def test_estado_del_proyecto_en_agencia_usa_el_token_de_agencia(entorno):
    ma, graph = entorno["ma"], entorno["graph"]
    ma.conectar(TOKEN, BID)
    ma.asignar("acme", "act_1", "p1")
    graph["tokens"].clear()
    r = mc.estado("acme")
    assert r["estado"] == "conectado" and r["verificado"]
    assert r["detalle"]["modo"] == "agencia" and r["detalle"]["ad_account_nombre"] == "Cuenta 1"
    assert graph["tokens"] == [TOKEN]
    assert TOKEN not in json.dumps(r)


def test_estado_pixel_con_token_de_agencia(entorno, monkeypatch):
    ma = entorno["ma"]
    from meta_ads import auth
    ma.conectar(TOKEN, BID)
    ma.asignar("acme", "act_1", "p1")
    llamadas = []

    def llamar(metodo, edge, payload=None, params=None, dry_run=False):
        llamadas.append((metodo, edge))
        assert auth._CREDENCIALES["token"] == TOKEN
        return {"data": [{"id": "px1", "name": "Px", "last_fired_time": "2099-01-01T00:00:00+0000"}]}
    monkeypatch.setattr(auth, "llamar", llamar)
    r = mc.estado_pixel("acme")
    assert r["estado"] == "ok" and r["pixel_id"] == "px1"
    assert llamadas == [("GET", "act_1/adspixels")]
    assert auth._CREDENCIALES["token"] is None
    assert TOKEN not in json.dumps(r)


def test_conectar_invalida_el_estado_cacheado_de_los_proyectos(entorno):
    ma = entorno["ma"]
    ma.conectar(TOKEN, BID)
    ma.asignar("acme", "act_1", "p1")
    mc.estado("acme")
    mc._cache_pixel["acme"] = (ma.time.time(), {"estado": "ok"})
    assert "acme" in mc._cache_estado
    ma.conectar(TOKEN + "-nuevo", BID)
    assert "acme" not in mc._cache_estado and "acme" not in mc._cache_pixel
    assert mc.cargar("acme")["token"] == TOKEN + "-nuevo"


def test_cache_del_registro_sigue_a_kv(entorno, base_temporal):
    """Otro proceso (worker) cambia kv: este proceso ve el token nuevo sin
    reiniciar, porque la caché va atada al texto cifrado."""
    import cifrado
    ma = entorno["ma"]
    ma.conectar(TOKEN, BID)
    assert ma.token() == TOKEN
    nuevo = json.dumps({**json.loads(cifrado.descifrar(_kv_crudo(base_temporal))), "token": "OTRO"})
    with base_temporal.conectar() as con:
        con.execute(base_temporal.kv.update().where(base_temporal.kv.c.clave == "meta_agencia")
                    .values(valor=cifrado.cifrar(nuevo)))
    assert ma.token() == "OTRO"


def test_modo_propia_no_cambia_nada(entorno):
    """Un proyecto en modo propia se lee exactamente como antes, aunque la
    agencia esté conectada."""
    ma = entorno["ma"]
    propia = {"token": "TOKEN-PROPIO", "ad_account_id": "act_p", "page_id": "pp", "page_access_token": "PT"}
    mc.guardar("acme", propia)
    ma.conectar(TOKEN, BID)
    assert mc.cargar("acme") == propia
    assert mc.credenciales_ads("acme")["token"] == "TOKEN-PROPIO"
    assert mc.estado("acme")["detalle"]["modo"] == "propia"
    assert mc.borrar("acme") is True and _meta_json(entorno, "acme") is None
