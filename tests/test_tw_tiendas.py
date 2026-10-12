"""Conexión de Triple Whale por tiendas (spec 2026-10-08 §4.1): varias tiendas por proyecto, una por país."""
import pytest
import sqlalchemy as sa

import cifrado
import db
import triple_whale
import triple_whale_tiendas as tt


@pytest.fixture()
def base(base_temporal, monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "test_secret_key_12345678")
    return base_temporal


def _copia(tabla, cliente, tienda_id, **extra):
    """Una fila a mano en una de las tres copias."""
    valores = {"cliente": cliente, "tienda_id": tienda_id, "fecha": "2026-09-01",
               "creado_en": db.ahora(), "actualizado_en": db.ahora(), **extra}
    valores = {k: v for k, v in valores.items() if k in tabla.c}
    with db.conectar() as con:
        con.execute(tabla.insert().values(**valores))


def _llenar(cliente, tienda_id):
    _copia(db.tw_anuncio_dia, cliente, tienda_id, canal="facebook-ads", ad_id="1", gasto=3.0)
    _copia(db.tw_tienda_dia, cliente, tienda_id, ingresos=5.0)
    _copia(db.tw_producto_dia, cliente, tienda_id, producto_id="p1")


def _contar(tabla, cliente, tienda_id=None):
    q = sa.select(sa.func.count()).select_from(tabla).where(tabla.c.cliente == cliente)
    if tienda_id is not None:
        q = q.where(tabla.c.tienda_id == tienda_id)
    with db.conectar() as con:
        return con.execute(q).scalar()


def _copias(cliente, tienda_id=None):
    return [_contar(t, cliente, tienda_id) for t in (db.tw_anuncio_dia, db.tw_tienda_dia, db.tw_producto_dia)]


def _dos(cliente="acme"):
    no = tt.agregar(cliente, "tw_no", "https://Happyflops-Norge.myshopify.com/", pais="NO", moneda="usd")
    se = tt.agregar(cliente, "tw_se", "happyflops-se.myshopify.com", pais="SE")
    return no, se


def test_dos_tiendas_comparten_ajustes_y_la_primera_manda(base):
    no, se = _dos()
    assert no != se
    assert [t["pais"] for t in tt.tiendas("acme")] == ["NO", "SE"]
    assert tt.tiendas("acme")[0]["dominio"] == "happyflops-norge.myshopify.com"
    a = tt.ajustes("acme")
    assert a["moneda"] == "USD" and a["id"] and a["extra"] == {} and a["actualizado_en"]
    # una tercera llamada con otra moneda no cambia la del proyecto
    tt.agregar("acme", "tw_dk", "happyflops-dk.myshopify.com", pais="DK", moneda="EUR",
               modelo_atribucion="Last Click", ventana_atribucion="7_days")
    a = tt.ajustes("acme")
    assert a["moneda"] == "USD" and a["modelo_atribucion"] == triple_whale.MODELO_DEFECTO
    assert len(tt.tiendas("acme")) == 3


def test_tiendas_no_trae_llave_y_va_ordenada_con_las_sin_pais_al_final(base):
    tt.agregar("acme", "tw_x", "sinpais.myshopify.com", pais=None)       # sin pista: queda sin país
    tt.agregar("acme", "tw_se", "a.myshopify.com", pais="SE")
    tt.agregar("acme", "tw_no", "b.myshopify.com", pais="NO")
    lista = tt.tiendas("acme")
    assert [t["pais"] for t in lista] == ["NO", "SE", None]
    assert all("llave" not in t for t in lista)
    assert set(lista[0]) == {"id", "cliente", "pais", "dominio", "zona_horaria", "estado", "error",
                             "ultima_sincronizacion", "extra", "creado_en", "actualizado_en"}


def test_el_pais_se_adivina_por_el_dominio_si_no_llega(base):
    i = tt.agregar("acme", "tw_x", "happyflops-norge.myshopify.com")
    assert tt.tienda("acme", i)["pais"] == "NO"


def test_la_llave_va_cifrada_y_cada_tienda_tiene_la_suya(base):
    no, se = _dos()
    assert tt.obtener_llave("acme", no) == "tw_no" and tt.obtener_llave("acme", se) == "tw_se"
    assert tt.obtener_llave("otro", no) is None and tt.obtener_llave("acme", 999) is None
    with db.conectar() as con:
        cruda = con.execute(sa.select(db.tw_tienda.c.llave).where(db.tw_tienda.c.id == no)).scalar()
    assert "tw_no" not in cruda and cifrado.descifrar(cruda) == "tw_no"


def test_reconectar_el_mismo_dominio_cambia_la_llave_y_conserva_el_id(base):
    no, _ = _dos()
    tt.actualizar_tienda("acme", no, estado="error", error="llave mala")
    _llenar("acme", no)
    otra = tt.agregar("acme", "tw_nueva", "happyflops-norge.myshopify.com", pais="NO")
    assert otra == no
    t = tt.tienda("acme", no)
    assert t["estado"] == "conectada" and t["error"] is None
    assert tt.obtener_llave("acme", no) == "tw_nueva"
    assert len(tt.tiendas("acme")) == 2
    assert _copias("acme", no) == [1, 1, 1]            # reconectar no borra las cifras


def test_reconectar_sin_pais_conserva_el_que_tenia(base):
    no, _ = _dos()
    tt.agregar("acme", "tw_otra", "happyflops-norge.myshopify.com")   # el dominio se adivina como NO
    assert tt.tienda("acme", no)["pais"] == "NO"
    i = tt.agregar("acme", "tw_z", "z.myshopify.com", pais="DK")
    tt.agregar("acme", "tw_z2", "z.myshopify.com")                    # sin pista: no pierde DK
    assert tt.tienda("acme", i)["pais"] == "DK"


def test_pais_ocupado_lanza_y_lleva_el_codigo(base):
    _dos()
    with pytest.raises(tt.PaisOcupado) as e:
        tt.agregar("acme", "tw_otra", "otra.myshopify.com", pais="no")
    assert isinstance(e.value, ValueError) and e.value.pais == "NO" and str(e.value) == "NO"
    assert len(tt.tiendas("acme")) == 2 and tt.tienda_de_pais("acme", "NO")["dominio"].startswith("happyflops-norge")


def test_pais_ocupado_tambien_al_reconectar_con_otro_pais(base):
    _, se = _dos()
    with pytest.raises(tt.PaisOcupado):
        tt.agregar("acme", "tw_se", "happyflops-se.myshopify.com", pais="NO")
    assert tt.tienda("acme", se)["pais"] == "SE"


def test_el_mismo_pais_en_otro_proyecto_no_choca(base):
    tt.agregar("acme", "tw_a", "a.myshopify.com", pais="NO")
    tt.agregar("otro", "tw_b", "b.myshopify.com", pais="NO")
    assert tt.tienda_de_pais("otro", "NO")["dominio"] == "b.myshopify.com"
    assert tt.tienda_de_pais("acme", "SE") is None


def test_cambiar_pais_no_toca_las_copias_y_controla_ocupado(base):
    no, se = _dos()
    _llenar("acme", no)
    tt.cambiar_pais("acme", no, "dk")
    assert tt.tienda("acme", no)["pais"] == "DK"
    assert _copias("acme", no) == [1, 1, 1]
    with pytest.raises(tt.PaisOcupado):
        tt.cambiar_pais("acme", no, "SE")
    assert tt.tienda("acme", no)["pais"] == "DK"
    tt.cambiar_pais("acme", no, "DK")                  # el suyo no es «ocupado»
    tt.cambiar_pais("acme", no, "")                    # vacío = sin país
    assert tt.tienda("acme", no)["pais"] is None
    tt.cambiar_pais("otro", se, "FI")                  # de otro proyecto: no hace nada
    assert tt.tienda("acme", se)["pais"] == "SE"


def test_tienda_verifica_el_cliente(base):
    no, _ = _dos()
    assert tt.tienda("acme", no)["id"] == no
    assert tt.tienda("otro", no) is None


def test_quitar_una_borra_sus_copias_y_deja_las_de_la_otra(base):
    no, se = _dos()
    _llenar("acme", no)
    _llenar("acme", se)
    assert tt.quitar("otro", no) is False and tt.quitar("acme", 999) is False
    assert tt.quitar("acme", no) is True
    assert _copias("acme", no) == [0, 0, 0]          # incluye tw_producto_dia
    assert _copias("acme", se) == [1, 1, 1]
    assert [t["id"] for t in tt.tiendas("acme")] == [se]
    assert tt.ajustes("acme") is not None


def test_quitar_la_ultima_borra_los_ajustes(base):
    no, se = _dos()
    tt.quitar("acme", no)
    tt.quitar("acme", se)
    assert tt.ajustes("acme") is None and tt.obtener("acme") is None and tt.tiendas("acme") == []


def test_obtener_es_ajustes_mas_tiendas_o_none(base):
    assert tt.obtener("acme") is None
    _dos()
    o = tt.obtener("acme")
    assert o["moneda"] == "USD" and len(o["tiendas"]) == 2 and "llave" not in o["tiendas"][0]


def test_obtener_normaliza_valores_viejos(base):
    tt.agregar("acme", "tw_x", "v.myshopify.com", pais="NO")
    with db.conectar() as con:
        con.execute(db.triple_whale.update().values(modelo_atribucion="First Touch", ventana_atribucion="7"))
    a = tt.ajustes("acme")
    assert (a["modelo_atribucion"], a["ventana_atribucion"]) == ("First Click", "7_days")


def test_cambiar_ajustes_borra_las_copias_de_todas_y_vacia_el_backfill(base):
    no, se = _dos()
    for i in (no, se):
        _llenar("acme", i)
        tt.actualizar_extra_tienda("acme", i, {"backfill_desde": "2026-07-01", "gasto_7d": 3})
    tt.actualizar_extra("acme", {"avisados": ["x"]})
    assert tt.cambiar_ajustes("acme", moneda="USD") is False
    assert _copias("acme") == [2, 2, 2]
    assert tt.cambiar_ajustes("acme", ventana_atribucion="7_days") is True
    assert _copias("acme") == [0, 0, 0]
    assert all("backfill_desde" not in t["extra"] for t in tt.tiendas("acme"))
    assert tt.ajustes("acme")["ventana_atribucion"] == "7_days"
    assert tt.ajustes("acme")["extra"] == {"avisados": ["x"]}      # los avisos son del proyecto
    assert tt.cambiar_ajustes("nadie", moneda="EUR") is False


def test_cambiar_ajustes_no_toca_a_otro_proyecto(base):
    no, _ = _dos()
    otra = tt.agregar("otro", "tw_o", "o.myshopify.com", pais="NO")
    _llenar("acme", no)
    _llenar("otro", otra)
    tt.cambiar_ajustes("acme", moneda="EUR")
    assert _copias("acme") == [0, 0, 0] and _copias("otro") == [1, 1, 1]
    assert tt.ajustes("otro")["moneda"] == "USD"


def test_actualizar_tienda_y_extra_solo_de_esa_tienda_del_cliente(base):
    no, se = _dos()
    tt.actualizar_tienda("acme", no, estado="error", error="mala", ultima_sincronizacion="2026-10-08T10:00:00")
    t = tt.tienda("acme", no)
    assert (t["estado"], t["error"], t["ultima_sincronizacion"]) == ("error", "mala", "2026-10-08T10:00:00")
    assert tt.tienda("acme", se)["estado"] == "conectada"
    tt.actualizar_tienda("otro", no, estado="error")
    assert tt.tienda("acme", no)["error"] == "mala" and tt.tienda("acme", no)["estado"] == "error"
    tt.actualizar_extra_tienda("acme", no, {"backfill_desde": "2026-07-01"})
    tt.actualizar_extra_tienda("acme", no, {"gasto_7d": 9})
    assert tt.tienda("acme", no)["extra"] == {"backfill_desde": "2026-07-01", "gasto_7d": 9}
    tt.actualizar_extra_tienda("otro", no, {"x": 1})
    assert "x" not in tt.tienda("acme", no)["extra"]
    with pytest.raises(ValueError):
        tt.actualizar_tienda("acme", no, llave="robada")


def test_conectadas_lista_cliente_y_tienda_con_llave(base):
    b = tt.agregar("b", "tw_x", "b.myshopify.com", pais="NO")
    a1 = tt.agregar("a", "tw_y", "a1.myshopify.com", pais="NO")
    a2 = tt.agregar("a", "tw_z", "a2.myshopify.com", pais="SE")
    assert tt.conectadas() == [("a", a1), ("a", a2), ("b", b)]


def test_firma_cambia_con_la_tienda_y_con_los_ajustes(base):
    assert tt.firma("acme") == (0, None)
    no, _ = _dos()
    f1 = tt.firma("acme")
    assert f1[0] == 2 and f1[1]
    with db.conectar() as con:
        con.execute(db.tw_tienda.update().values(actualizado_en="2000-01-01T00:00:00"))
        con.execute(db.triple_whale.update().values(actualizado_en="2000-01-01T00:00:00"))
    f0 = tt.firma("acme")
    tt.actualizar_tienda("acme", no, estado="error")
    assert tt.firma("acme") != f0
    f2 = tt.firma("acme")
    tt.actualizar_extra("acme", {"avisados": []})
    assert tt.firma("acme")[1] >= f2[1]
    tt.cambiar_ajustes("acme", moneda="EUR")
    assert tt.firma("acme") != f0


def test_desconectar_quita_todo_y_conserva_evaluaciones(base):
    no, se = _dos()
    _llenar("acme", no)
    _llenar("acme", se)
    with db.conectar() as con:
        con.execute(db.tw_evaluacion.insert().values(cliente="acme", creado_en=db.ahora(), actualizado_en=db.ahora()))
    tt.desconectar("acme")
    assert tt.obtener("acme") is None and tt.tiendas("acme") == [] and _copias("acme") == [0, 0, 0]
    with db.conectar() as con:
        assert con.execute(sa.select(sa.func.count()).select_from(db.tw_evaluacion)).scalar() == 1


def test_url_tags_si_hay_al_menos_una_tienda(base):
    assert tt.url_tags("acme") is None and tt.kw_url_tags("acme") == {}
    i = tt.agregar("acme", "tw_x", "a.myshopify.com", pais="NO")
    assert tt.url_tags("acme") == triple_whale.URL_TAGS and tt.kw_url_tags("acme") == {"url_tags": triple_whale.URL_TAGS}
    tt.quitar("acme", i)
    assert tt.url_tags("acme") is None


def test_conectar_es_el_agregar_de_la_firma_vieja(base):
    i = tt.conectar("acme", "tw_x", "https://Acme.myshopify.com/", moneda="usd", modelo_atribucion="Last Click",
                    ventana_atribucion="7_days", zona_horaria="America/Bogota")
    assert tt.tienda("acme", i)["zona_horaria"] == "America/Bogota"
    assert tt.ajustes("acme")["modelo_atribucion"] == "Last Click"


def _fila_vieja(cliente):
    a = db.triple_whale
    with db.conectar() as con:
        return con.execute(sa.select(a.c.llave, a.c.dominio_tienda, a.c.moneda, a.c.extra)
                           .where(a.c.cliente == cliente)).first()


def _con_fila_vieja(cliente, llave, dominio):
    """Como quedó un proyecto tras la migración 0032: la fila de ajustes con las columnas viejas de conexión
    (la llave cifrada y el dominio de la tienda que estaba conectada) todavía llenas."""
    a = db.triple_whale
    with db.conectar() as con:
        con.execute(a.update().where(a.c.cliente == cliente).values(
            llave=cifrado.cifrar(llave), dominio_tienda=dominio, extra={"avisados": {"g1": "ganador"}}))


def test_quitar_o_reconectar_con_otra_llave_vacia_la_llave_vieja_de_los_ajustes(base):
    """Auditoría de seguridad (2026-10-08): la fila `triple_whale` guardaba la llave de antes de 0032. Si se
    quita esa tienda o se reconecta con otra llave, la copia vieja se vacía (llave y dominio_tienda en None)
    sin borrar la fila: sus ajustes y avisos siguen."""
    no = tt.agregar("acme", "llave-vieja-no", "happyflops-norge.myshopify.com", moneda="USD")
    se = tt.agregar("acme", "llave-se-1234", "happyflops-sverige.myshopify.com")
    _con_fila_vieja("acme", "llave-vieja-no", "happyflops-norge.myshopify.com")

    tt.quitar("acme", se)                                     # otra tienda: la fila vieja no se toca
    assert _fila_vieja("acme").dominio_tienda == "happyflops-norge.myshopify.com"
    tt.agregar("acme", "llave-vieja-no", "happyflops-norge.myshopify.com")   # la misma llave: tampoco
    assert cifrado.descifrar(_fila_vieja("acme").llave) == "llave-vieja-no"

    tt.agregar("acme", "llave-nueva-no", "happyflops-norge.myshopify.com")   # otra llave: se vacía
    fila = _fila_vieja("acme")
    assert (fila.llave, fila.dominio_tienda) == (None, None)
    assert fila.moneda == "USD" and fila.extra == {"avisados": {"g1": "ganador"}}
    assert tt.obtener_llave("acme", no) == "llave-nueva-no"


def test_quitar_la_tienda_de_la_fila_vieja_la_vacia_y_conserva_los_ajustes(base):
    no = tt.agregar("acme", "llave-vieja-no", "happyflops-norge.myshopify.com", moneda="EUR")
    tt.agregar("acme", "llave-se-1234", "happyflops-sverige.myshopify.com")
    _con_fila_vieja("acme", "llave-vieja-no", "https://HappyFlops-Norge.myshopify.com/")   # sin normalizar
    _con_fila_vieja("otro", "x", "y")                                                      # otro proyecto: nada
    tt.quitar("acme", no)
    fila = _fila_vieja("acme")
    assert (fila.llave, fila.dominio_tienda) == (None, None)
    assert fila.moneda == "EUR" and fila.extra == {"avisados": {"g1": "ganador"}}


def test_una_tienda_quitada_no_deja_su_id_a_la_siguiente(base):
    """Auditoría de seguridad (2026-10-08): con AUTOINCREMENT el id de una tienda quitada no se reusa, así
    una evaluación vieja que guarda `tienda_id` no toma el nombre de la tienda conectada después."""
    tt.agregar("acme", "llave-no-1234", "happyflops-norge.myshopify.com")
    se = tt.agregar("acme", "llave-se-1234", "happyflops-sverige.myshopify.com")
    tt.quitar("acme", se)
    dk = tt.agregar("acme", "llave-dk-1234", "happyflops-danmark.myshopify.com")
    assert dk > se
