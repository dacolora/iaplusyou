"""Rutas de la pestaña Rendimiento: el panel por fetch y «Actualizar ahora»."""
import pytest
import sqlalchemy as sa

import db
from tests.test_rendimiento_resumen import _sembrar
from tests.test_rutas_configuracion import app  # noqa: F401  (fixture)


@pytest.fixture()
def meta_on(app, monkeypatch):  # noqa: F811
    monkeypatch.setattr(app["dashboard"].meta_conexion, "cargar",
                        lambda c: {"token": "t-llave-de-prueba", "page_id": None})  # llave-de-prueba
    return app


def _con_anuncios():
    """`_sembrar` + anuncios en las dos fuentes (la galería de Triple Whale y la tabla de campañas de Meta solo
    existen con anuncios copiados)."""
    from datetime import date, timedelta

    from meta_rendimiento import datos as mdatos
    from tests.test_rutas_meta_rendimiento import _ad
    from triple_whale import datos as twdatos
    tid = _sembrar()
    for n in range(5):
        f = (date.today() - timedelta(days=n)).isoformat()
        twdatos.reemplazar_anuncios_canal("acme", tid, f, f, [{"canal": "facebook-ads", "ad_id": "n1", "fecha": f,
                                                               "gasto": 10, "impresiones": 2000, "valor_canal": 25,
                                                               "anuncio": "Anuncio Noruega"}])
        twdatos.reemplazar_anuncios_pixel("acme", tid, f, f, [{"canal": "facebook-ads", "ad_id": "n1", "fecha": f,
                                                               "pedidos": 1, "ingresos": 30}])
        mdatos.reemplazar_anuncio_dias("acme", "act_se", f, f, [_ad(f, "se1", 60, 90, compras=1, campaign="cse")])
    return tid


def test_el_panel_pinta_los_dos_bloques_y_el_selector(meta_on):
    _con_anuncios()
    html = meta_on["c"].get("/cliente/acme/rendimiento/panel").data.decode()
    assert 'data-rend-param="entrada"' in html and "Noruega" in html and "Suecia" in html
    assert "Resultados de todos tus países" in html and 'id="tw-galeria"' in html
    assert "t-llave-de-prueba" not in html


def test_el_panel_de_otro_proyecto_no_se_ve(meta_on):
    r = meta_on["c"].get("/cliente/otro/rendimiento/panel")
    assert r.status_code in (302, 403, 404) or "Noruega" not in r.data.decode()


def test_actualizar_encola_las_dos_fuentes_y_vuelve_a_rendimiento(meta_on):
    _sembrar()
    r = meta_on["c"].post("/cliente/acme/rendimiento/actualizar", data={"entrada": ""},
                          headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 302 and r.headers["Location"].endswith("#rendimiento")
    with db.conectar() as con:
        tipos = {t for (t,) in con.execute(sa.select(db.tarea.c.tipo))}
    assert {"tw_sincronizar", "meta_rend_sincronizar"} <= tipos


def test_actualizar_de_otro_sitio_es_403(meta_on):
    r = meta_on["c"].post("/cliente/acme/rendimiento/actualizar", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


# ---- más allá del brief: «Ver más», «Actualizar» por entrada y quién puede ----------------------------------------

def _jobs():
    with db.conectar() as con:
        return sorted(j for (j,) in con.execute(sa.select(db.tarea.c.job_id)))


def test_ver_mas_de_conjuntos_va_a_la_ruta_de_rendimiento(meta_on):
    from datetime import date, timedelta

    from meta_rendimiento import datos as mdatos
    from tests.test_rutas_meta_rendimiento import _ad
    _sembrar()
    f = (date.today() - timedelta(days=1)).isoformat()
    mdatos.reemplazar_anuncio_dias("acme", "act_se", f, f, [_ad(f, f"a{i:02d}", 100 - i, 50, adset=f"s{i:02d}")
                                                            for i in range(25)])
    c = meta_on["c"]
    html = c.get("/cliente/acme/rendimiento/conjuntos?entrada=SE&dias=0&pagina=0").data.decode()
    assert html.count("<tr>") == 24 and "/cliente/acme/rendimiento/conjuntos?" in html and "entrada=SE" in html
    assert "/meta-rendimiento/" not in html
    siguiente = c.get("/cliente/acme/rendimiento/conjuntos?entrada=SE&dias=0&pagina=1").data.decode()
    assert siguiente.count("<tr>") == 1 and "s24" in siguiente


def test_la_galeria_de_una_entrada_solo_trae_los_anuncios_de_su_fuente(meta_on):
    """Desde E2 tarea 4 los anuncios de fuente Meta están en la galería única (`/rendimiento/galeria`): una entrada de
    Meta trae los suyos; Noruega tiene tienda y sus ventas salen de Triple Whale (ningún anuncio de fuente Meta)."""
    _con_anuncios()
    c = meta_on["c"]
    r = c.get("/cliente/acme/rendimiento/galeria?entrada=SE&pagina=1")
    assert r.status_code == 200 and 'id="tw-tarjeta-meta-facebook-ads-se1"' in r.data.decode()
    # Una página rara es la primera.
    r = c.get("/cliente/acme/rendimiento/galeria?entrada=NO&pagina=abc")
    assert r.status_code == 200 and "se1" not in r.data.decode() and 'id="tw-tarjeta-facebook-ads-n1"' in r.data.decode()


def test_actualizar_una_entrada_solo_pide_sus_copias(meta_on):
    tid = _sembrar()
    c = meta_on["c"]
    c.post("/cliente/acme/rendimiento/actualizar", data={"entrada": "SE"}, headers={"Sec-Fetch-Site": "same-origin"})
    assert _jobs() == ["acme__meta_rend__act_se"]
    c.post("/cliente/acme/rendimiento/actualizar", data={"entrada": "NO"}, headers={"Sec-Fetch-Site": "same-origin"})
    assert _jobs() == sorted(["acme__meta_rend__act_se", "acme__meta_rend__act_no", f"acme__tw_sync__{tid}"])


def test_actualizar_dice_cada_mensaje_una_vez(meta_on):
    from tests.test_rutas_productos import _flashes
    _sembrar()
    c = meta_on["c"]
    c.post("/cliente/acme/rendimiento/actualizar", data={"entrada": ""}, headers={"Sec-Fetch-Site": "same-origin"})
    mensajes = _flashes(c)
    assert len(mensajes) == len(set(mensajes)) and any("Triple Whale" in m for m in mensajes)


def test_actualizar_sin_nada_conectado_lo_dice(app):  # noqa: F811
    from tests.test_rutas_productos import _flashes
    c = app["c"]
    r = c.post("/cliente/acme/rendimiento/actualizar", headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 302 and r.headers["Location"].endswith("#rendimiento") and _jobs() == []
    assert any("Conecta Triple Whale o Meta" in m for m in _flashes(c))


def test_sin_correo_verificado_un_cliente_no_pide_copias(meta_on):
    import usuarios
    from tests.test_rutas_meta_rendimiento import _como_cliente
    _sembrar()
    usuarios.actualizar("user_acme", correo_verificado=False)
    c = _como_cliente(meta_on)
    r = c.post("/cliente/acme/rendimiento/actualizar", data={"entrada": ""}, headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/cliente/acme#settings") and _jobs() == []
    assert c.get("/cliente/acme/rendimiento/panel").status_code == 200       # leer no es escribir


def test_un_cliente_de_otro_proyecto_no_ve_ni_actualiza(meta_on):
    from tests.test_rutas_meta_rendimiento import _como_cliente
    _con_anuncios()
    c = _como_cliente(meta_on, usuario="otro", cliente="otro")
    r = c.get("/cliente/acme/rendimiento/panel")
    assert r.status_code == 302 and "Noruega" not in r.data.decode()
    r = c.post("/cliente/acme/rendimiento/actualizar", headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 302 and _jobs() == []


def test_una_entrada_que_ya_no_existe_no_encola_nada(meta_on):
    """Revisión de la tarea 8: solo la entrada vacía es «Todas». Una pestaña vieja (un país que se quitó, una tienda
    de otro proyecto, texto raro) no ensancha la copia a todo: ensanchada gastaría el límite de uso de Meta que
    necesitan los lanzamientos. Dice que hay que recargar y no encola nada."""
    from tests.test_rutas_productos import _flashes
    _sembrar()
    c = meta_on["c"]
    for valor in ("DK", "cuenta:act_de_otro", "tienda:99999", "x y", "act_se"):
        r = c.post("/cliente/acme/rendimiento/actualizar", data={"entrada": valor},
                   headers={"Sec-Fetch-Site": "same-origin"})
        assert r.status_code == 302 and r.headers["Location"].endswith("#rendimiento"), valor
        assert _jobs() == [], valor
        assert "Esa vista ya no existe: recarga la pestaña." in _flashes(c), valor
    # La vacía sigue siendo «Todas» y una clave de verdad, su entrada.
    c.post("/cliente/acme/rendimiento/actualizar", data={"entrada": "SE"}, headers={"Sec-Fetch-Site": "same-origin"})
    assert _jobs() == ["acme__meta_rend__act_se"]


def test_con_una_sola_entrada_una_clave_vieja_tampoco_encola(app):  # noqa: F811
    """Con una sola entrada `entradas.elegir` siempre la devuelve: igual una clave que no es la suya no encola nada."""
    from tests.test_rutas_productos import _flashes
    from tests.test_rutas_triple_whale import _conectar
    tid = _conectar()                                      # una tienda sin país: la entrada «tienda:<id>»
    c = app["c"]
    c.post("/cliente/acme/rendimiento/actualizar", data={"entrada": "NO"}, headers={"Sec-Fetch-Site": "same-origin"})
    assert _jobs() == [] and "Esa vista ya no existe: recarga la pestaña." in _flashes(c)
    c.post("/cliente/acme/rendimiento/actualizar", data={"entrada": f"tienda:{tid}"},
           headers={"Sec-Fetch-Site": "same-origin"})
    assert _jobs() == [f"acme__tw_sync__{tid}"]
