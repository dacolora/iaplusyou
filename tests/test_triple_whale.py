"""Cliente de la API de Triple Whale y conexión por proyecto (spec
2026-09-28 §2). Nada de esto llama a la red: `_enviar` y `requests.get` se
reemplazan."""
import pytest
import requests

import cifrado
import db
import triple_whale
import triple_whale_tiendas


class Resp:
    def __init__(self, status, datos=None, texto="", headers=None):
        self.status_code = status
        self._datos = datos
        self.text = texto or ("" if datos is None else str(datos))
        self.headers = headers or {}

    def json(self):
        if isinstance(self._datos, Exception):
            raise self._datos
        return self._datos


@pytest.fixture()
def envios(monkeypatch):
    """Cola de respuestas para `_enviar`; guarda lo que se mandó."""
    estado = {"respuestas": [], "cuerpos": [], "headers": []}

    def _enviar(url, headers, cuerpo):
        assert url == "https://api.triplewhale.com/api/v2/orcabase/api/sql"
        estado["headers"].append(headers)
        estado["cuerpos"].append(cuerpo)
        r = estado["respuestas"].pop(0)
        if isinstance(r, Exception):
            raise r
        return r
    monkeypatch.setattr(triple_whale, "_enviar", _enviar)
    monkeypatch.setattr(triple_whale, "_dormir", lambda s: estado.setdefault("esperas", []).append(s))
    return estado


# ------------------------------------------------------------ vocabulario ---

@pytest.mark.parametrize("entrada,salida", [
    ("acme.myshopify.com", "acme.myshopify.com"),
    ("https://Acme.MyShopify.com/admin?x=1", "acme.myshopify.com"),
    ("  www.mitienda.com/ ", "mitienda.com"),
    ("sin-punto", None), ("", None), (None, None), ("acme.myshopify.com'; DROP", None),
])
def test_normalizar_dominio(entrada, salida):
    assert triple_whale.normalizar_dominio(entrada) == salida


def test_modelos_y_ventanas_viejos_se_traducen_al_vocabulario_de_triple_whale():
    assert triple_whale.normalizar_modelo("First Touch") == "First Click"
    assert triple_whale.normalizar_modelo("Last Touch") == "Last Click"
    assert triple_whale.normalizar_modelo("Linear Paid") == "Linear Paid"
    assert triple_whale.normalizar_modelo("inventado") == triple_whale.MODELO_DEFECTO
    assert triple_whale.normalizar_ventana("7") == "7_days"
    assert triple_whale.normalizar_ventana("30") == "28_days"
    assert triple_whale.normalizar_ventana("Lifetime") == "lifetime"
    assert triple_whale.normalizar_ventana("") == triple_whale.VENTANA_DEFECTO


def test_consultas_del_pixel_solo_llevan_valores_de_la_lista_blanca():
    completa, minima = triple_whale.consultas_pixel("Last Click", "7_days")
    assert "model = 'Last Click'" in completa and "attribution_window = '7_days'" in completa
    assert "pixel_joined_tvf()" in completa and "orders_quantity" in minima
    # Un valor raro nunca entra a la consulta: cae al defecto.
    raro, _ = triple_whale.consultas_pixel("x' OR 1=1 --", "lifetime'--")
    assert "OR 1=1" not in raro and "model = 'Triple Attribution'" in raro and "= 'lifetime'" in raro
    with pytest.raises(ValueError):
        triple_whale._literal("otro", triple_whale.MODELOS)


def test_las_consultas_nombran_columnas_y_nunca_select_asterisco():
    for q in triple_whale.consultas_anuncios() + triple_whale.consultas_tienda() + triple_whale.consultas_pixel("", ""):
        assert "SELECT *" not in q.upper().replace("  ", " ")
        assert "@startDate" in q and "@endDate" in q


# ------------------------------------------------------------ sql_query ---

def test_sql_query_manda_el_cuerpo_documentado_y_lee_data(envios):
    envios["respuestas"].append(Resp(200, {"success": True, "data": [{"spend": "12.5"}]}))
    filas = triple_whale.sql_query("tw_llave", "acme.myshopify.com", "SELECT 1", "2026-09-01", "2026-09-07", "USD")
    assert filas == [{"spend": "12.5"}]
    assert envios["cuerpos"][0] == {"shopId": "acme.myshopify.com", "query": "SELECT 1",
                                    "period": {"startDate": "2026-09-01", "endDate": "2026-09-07"}, "currency": "USD"}
    assert envios["headers"][0]["x-api-key"] == "tw_llave"
    assert "parameters" not in envios["cuerpos"][0]


def test_sql_query_acepta_rows_o_lista_suelta(envios):
    envios["respuestas"] += [Resp(200, {"rows": [{"a": 1}]}), Resp(200, [{"b": 2}, "basura"])]
    assert triple_whale.sql_query("k", "s.com", "q", "2026-09-01", "2026-09-01") == [{"a": 1}]
    assert triple_whale.sql_query("k", "s.com", "q", "2026-09-01", "2026-09-01") == [{"b": 2}]


@pytest.mark.parametrize("resp,clase", [
    (Resp(401, texto="Unauthorized"), triple_whale.ErrorLlave),
    (Resp(403, texto="Access token is required"), triple_whale.ErrorTienda),
    (Resp(400, texto="Unknown identifier: video_p50_watched"), triple_whale.ErrorConsulta),
])
def test_sql_query_clasifica_los_errores(envios, resp, clase):
    envios["respuestas"].append(resp)
    with pytest.raises(clase):
        triple_whale.sql_query("k", "s.com", "q", "2026-09-01", "2026-09-01")


def test_sql_query_tienda_desconocida_en_un_500_es_error_de_tienda(envios):
    envios["respuestas"].append(Resp(500, texto='{"message":"Unrecognized shop identifier"}'))
    with pytest.raises(triple_whale.ErrorTienda):
        triple_whale.sql_query("k", "s.com", "q", "2026-09-01", "2026-09-01")


def test_sql_query_respeta_retry_after_en_429(envios):
    envios["respuestas"] += [Resp(429, headers={"Retry-After": "2"}), Resp(200, {"data": []})]
    assert triple_whale.sql_query("k", "s.com", "q", "2026-09-01", "2026-09-01") == []
    assert envios["esperas"] == [2.0]


def test_sql_query_un_5xx_que_persiste_es_error_de_consulta(envios):
    envios["respuestas"] += [Resp(502, texto="bad gateway")] * triple_whale.REINTENTOS_MAX
    with pytest.raises(triple_whale.ErrorConsulta):
        triple_whale.sql_query("k", "s.com", "q", "2026-09-01", "2026-09-01")


def test_sql_query_timeout_reintenta_y_error_de_red_no_filtra_nada(envios):
    envios["respuestas"] += [requests.Timeout(), Resp(200, {"data": [{"x": 1}]})]
    assert triple_whale.sql_query("k", "s.com", "q", "2026-09-01", "2026-09-01") == [{"x": 1}]
    envios["respuestas"].append(requests.ConnectionError("https://api...?x-api-key=tw_secreto"))
    with pytest.raises(triple_whale.ErrorTripleWhale) as e:
        triple_whale.sql_query("tw_secreto", "s.com", "q", "2026-09-01", "2026-09-01")
    assert "tw_secreto" not in str(e.value)


def test_consultar_con_respaldo_solo_baja_a_la_minima_con_error_de_consulta(envios):
    envios["respuestas"] += [Resp(400, texto="columna"), Resp(200, {"data": [{"ok": 1}]})]
    filas, indice = triple_whale.consultar_con_respaldo("k", "s.com", ["completa", "minima"], "2026-09-01", "2026-09-01")
    assert (filas, indice) == ([{"ok": 1}], 1)
    assert [c["query"] for c in envios["cuerpos"]] == ["completa", "minima"]
    envios["respuestas"].append(Resp(401))
    with pytest.raises(triple_whale.ErrorLlave):
        triple_whale.consultar_con_respaldo("k", "s.com", ["completa", "minima"], "2026-09-01", "2026-09-01")


def test_probar_suma_el_gasto_de_7_dias(envios):
    from datetime import date
    envios["respuestas"].append(Resp(200, {"data": [{"spend": "10.5"}, {"spend": None}]}))
    assert triple_whale.probar("k", "s.com", "USD", hoy=date(2026, 9, 28)) == {"gasto_7d": 10.5}
    assert envios["cuerpos"][0]["period"] == {"startDate": "2026-09-22", "endDate": "2026-09-28"}


def test_validar_llave_sin_red(monkeypatch):
    monkeypatch.setattr(triple_whale.requests, "get", lambda url, headers, timeout: Resp(200, {}))
    assert triple_whale.validar_llave("tw_ok")
    monkeypatch.setattr(triple_whale.requests, "get", lambda url, headers, timeout: Resp(401))
    assert not triple_whale.validar_llave("tw_mala")

    def _sin_red(*a, **k):
        raise requests.ConnectionError()
    monkeypatch.setattr(triple_whale.requests, "get", _sin_red)
    assert not triple_whale.validar_llave("tw_x")


@pytest.mark.parametrize("valor,esperado", [("12", 12.0), (3, 3.0), (None, 0.0), ("", 0.0), ("nan", 0.0), ("abc", 0.0)])
def test_numero(valor, esperado):
    assert triple_whale.numero(valor) == esperado


# ------------------------------------------------------------- conexión ---

@pytest.fixture()
def base(base_temporal, monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "test_secret_key_12345678")
    return base_temporal


def test_conectar_cifra_la_llave_y_obtener_no_la_devuelve(base):
    tw_id = triple_whale_tiendas.conectar("test", "tw_1234567890", "https://Test.myshopify.com/", moneda="usd",
                                          modelo_atribucion="Triple Attribution", ventana_atribucion="lifetime")
    assert tw_id > 0
    config = triple_whale_tiendas.obtener("test")
    assert config["dominio_tienda"] == "test.myshopify.com" and config["moneda"] == "USD"
    assert config["estado"] == "conectada" and config["error"] is None and config["extra"] == {}
    assert "llave" not in config
    assert triple_whale_tiendas.obtener_llave("test") == "tw_1234567890"
    import sqlalchemy as sa
    with db.conectar() as con:
        cruda = con.execute(sa.select(db.triple_whale.c.llave)).scalar()
    assert "tw_1234567890" not in cruda and cifrado.descifrar(cruda) == "tw_1234567890"


def test_obtener_traduce_valores_viejos_guardados(base):
    triple_whale_tiendas.conectar("viejo", "tw_x", "v.myshopify.com")
    triple_whale_tiendas.actualizar("viejo", modelo_atribucion="First Touch", ventana_atribucion="7")
    c = triple_whale_tiendas.obtener("viejo")
    assert (c["modelo_atribucion"], c["ventana_atribucion"]) == ("First Click", "7_days")


def _copiar_algo(cliente):
    from triple_whale import datos
    datos.reemplazar_tienda(cliente, "2026-09-01", "2026-09-01", [{"fecha": "2026-09-01", "ingresos": 5}])
    datos.reemplazar_anuncios_canal(cliente, "2026-09-01", "2026-09-01",
                                    [{"canal": "facebook-ads", "ad_id": "1", "fecha": "2026-09-01", "gasto": 3}])


def test_reconectar_con_otra_atribucion_borra_lo_copiado(base):
    from triple_whale import datos
    triple_whale_tiendas.conectar("c", "tw_x", "c.myshopify.com")
    _copiar_algo("c")
    triple_whale_tiendas.conectar("c", "tw_nueva", "c.myshopify.com")   # misma atribución: se conserva
    assert datos.hay_tienda("c") and datos.rango("c")["filas"] == 1
    triple_whale_tiendas.conectar("c", "tw_nueva", "c.myshopify.com", modelo_atribucion="Last Click")
    assert not datos.hay_tienda("c") and datos.rango("c")["filas"] == 0


def test_cambiar_ajustes_solo_borra_si_algo_cambio(base):
    from triple_whale import datos
    triple_whale_tiendas.conectar("c", "tw_x", "c.myshopify.com")
    triple_whale_tiendas.actualizar_extra("c", {"backfill_desde": "2026-07-01"})
    _copiar_algo("c")
    assert triple_whale_tiendas.cambiar_ajustes("c", moneda="USD") is False
    assert datos.hay_tienda("c")
    assert triple_whale_tiendas.cambiar_ajustes("c", ventana_atribucion="7_days") is True
    c = triple_whale_tiendas.obtener("c")
    assert c["ventana_atribucion"] == "7_days" and c["extra"] == {} and not datos.hay_tienda("c")
    assert triple_whale_tiendas.cambiar_ajustes("nadie", moneda="EUR") is False


def test_desconectar_borra_copias_y_conserva_evaluaciones(base):
    from triple_whale import datos
    triple_whale_tiendas.conectar("c", "tw_x", "c.myshopify.com")
    _copiar_algo("c")
    eid = datos.crear_evaluacion("c", "2026-09-01", "2026-09-30", "USD", [{"ref": "A1"}])
    triple_whale_tiendas.desconectar("c")
    assert triple_whale_tiendas.obtener("c") is None and datos.rango("c")["filas"] == 0
    assert datos.evaluacion("c", eid) is not None


def test_conectados_lista_solo_proyectos_con_llave(base):
    triple_whale_tiendas.conectar("b", "tw_x", "b.myshopify.com")
    triple_whale_tiendas.conectar("a", "tw_y", "a.myshopify.com")
    assert triple_whale_tiendas.conectados() == ["a", "b"]
