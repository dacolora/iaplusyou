"""«Cómo mejorarlo» no se cobra dos veces por lo mismo (revisión final de tw-tarjetas, sección A): el filtro de canal
es parte del alcance (A3), la ruta rechaza uno fresco del mismo alcance (A1), la tarjeta y el lote eligen entre TODOS
los análisis del anuncio (A2), una fila colgada sin tarea no bloquea (A4) y el precio del lote es la suma de las
tarjetas (A5)."""
import pytest
import sqlalchemy as sa

import db
import proyectos
from tests.test_rutas_configuracion import app  # noqa: F401  (fixture)
from tests.test_rutas_triple_whale import _conectar, _hace, _tareas, _tienda
from triple_whale import datos, panel


@pytest.fixture(autouse=True)
def _proyecto_aislado(tmp_path, monkeypatch):
    """Las preferencias y los aprendizajes viven en clientes/<c>/proyecto.json: que las pruebas no escriban en el repo."""
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))


# Tres anuncios de Meta y tres de Snapchat, 10 días: con el filtro de Snapchat el veredicto se calcula solo contra
# los de Snapchat, con «Todos» contra toda la cuenta.
_ANUNCIOS = (("g1", "facebook-ads", 20, 2000, 1, 120), ("p1", "facebook-ads", 40, 3000, 0, 0),
             ("p2", "facebook-ads", 30, 2500, 0, 0),
             ("s1", "snapchat-ads", 25, 2500, 1, 150), ("s2", "snapchat-ads", 35, 3000, 0, 0),
             ("s3", "snapchat-ads", 15, 1500, 0.5, 40))


def _sembrar_con_snapchat(dias=10):
    tid = _tienda()
    canal, pixel = [], []
    for dia in range(dias):
        for ad, canal_, gasto, imp, pedidos, ingresos in _ANUNCIOS:
            canal.append({"canal": canal_, "ad_id": ad, "fecha": _hace(dia), "anuncio": f"Anuncio {ad}",
                          "campana": "Otoño", "gasto": gasto, "impresiones": imp, "clics": imp // 50,
                          "vistas_3s": imp // 3, "thruplays": imp // 10})
            pixel.append({"canal": canal_, "ad_id": ad, "fecha": _hace(dia), "pedidos": pedidos, "ingresos": ingresos})
    datos.reemplazar_anuncios_canal("acme", tid, _hace(dias - 1), _hace(0), canal)
    datos.reemplazar_anuncios_pixel("acme", tid, _hace(dias - 1), _hace(0), pixel)


def _analizar(app, ad_id, canal="facebook-ads", filtro="", dias="30", json=False):  # noqa: F811
    return app["c"].post(f"/cliente/acme/triple-whale/anuncio/{canal}/{ad_id}/analizar",
                         data={"dias": dias, "canal": filtro, "tienda": ""},
                         headers={"Accept": "application/json"} if json else {})


def _el_worker_termino(frase="Gana por el arranque."):
    """Las tareas se dan por hechas y sus filas quedan listas, como cuando el worker termina de verdad."""
    with db.conectar() as con:
        con.execute(db.tarea.update().values(estado="hecha"))
        con.execute(db.tw_analisis.update().where(db.tw_analisis.c.estado.in_(("en_cola", "analizando")))
                    .values(estado="lista", resultado={"frase": frase}))


def _filas(ad_id, canal="facebook-ads"):
    return datos.analisis_de_anuncios("acme", [(canal, ad_id)]).get((canal, ad_id), [])


def _n_filas():
    with db.conectar() as con:
        return con.execute(sa.select(sa.func.count()).select_from(db.tw_analisis)).scalar()


def _tarjeta(app, ad_id, canal="facebook-ads", filtro="", dias="30"):  # noqa: F811
    return app["c"].get(f"/cliente/acme/triple-whale/tarjeta/{canal}/{ad_id}?dias={dias}&canal={filtro}").data.decode()


def _anuncio(alc, ad_id):
    return next(a for a in alc["ev"]["anuncios"] if a["ad_id"] == ad_id)


# ------------------------------------------------------------------- A3: el filtro de canal es del alcance ---

def test_el_filtro_de_canal_es_parte_del_alcance(app):  # noqa: F811
    """Un anuncio de Snapchat analizado en «Todos» y mirado con el filtro de Snapchat: no es viejo, no entra al lote
    y la tarjeta da la nota neutra (antes el veredicto del filtro lo hacía ver viejo y el lote lo volvía a cobrar)."""
    _conectar()
    _sembrar_con_snapchat()
    assert _analizar(app, "s2", canal="snapchat-ads").status_code == 302
    [fila] = _filas("s2", "snapchat-ads")
    assert fila["foto"]["alcance_canal"] is None                       # pedido en «Todos»
    _el_worker_termino()
    # En «Todos» es su alcance: fresco, nada que ofrecer.
    html = _tarjeta(app, "s2", "snapchat-ads")
    assert "Ver el análisis" in html and "Analizado con los datos del" not in html
    assert "Analizar otra vez" not in html and "Analizar con estos datos" not in html and "Cómo mejorarlo" not in html
    # Con el filtro de Snapchat: otro alcance, nota neutra y solo el botón secundario.
    alc = panel.alcance("acme", 30, "snapchat-ads")
    e = panel.elegir_analisis(_anuncio(alc, "s2"), _filas("s2", "snapchat-ads"), alc)
    assert e["otro_alcance"] and not e["viejo"] and not e["ofrecer"]
    html = _tarjeta(app, "s2", "snapchat-ads", filtro="snapchat-ads")
    assert "Analizado con los datos del" in html and "desde entonces cambió" not in html
    assert "Analizar otra vez" not in html and "Analizar con estos datos" in html
    assert ("snapchat-ads", "s2") not in panel.galeria("acme", alc["ev"], alcance=alc)["lote"]["elegibles"]
    # «Analizar con estos datos» sí cobra uno nuevo, que guarda su filtro.
    assert _analizar(app, "s2", canal="snapchat-ads", filtro="snapchat-ads", json=True).get_json()["ok"]
    assert [f["foto"]["alcance_canal"] for f in _filas("s2", "snapchat-ads")] == ["snapchat-ads", None]


def test_con_otro_veredicto_en_el_filtro_el_lote_no_lo_vuelve_a_cobrar(app):  # noqa: F811
    """La foto de «Todos» con otro veredicto que el del filtro: en el mismo alcance sería viejo (y entraría al lote)."""
    _conectar()
    _sembrar_con_snapchat()
    alc = panel.alcance("acme", 30, "snapchat-ads")
    s3 = _anuncio(alc, "s3")
    aid = datos.crear_analisis("acme", alc["tienda_id"], "snapchat-ads", "s3", alc["desde"], alc["hasta"], "USD",
                               {"veredicto": "ganador" if s3["veredicto"] != "ganador" else "perdedor",
                                "m": {"gasto": s3["m"]["gasto"]}, "alcance_canal": None})
    datos.actualizar_analisis(aid, estado="lista", resultado={"frase": "x"})
    assert ("snapchat-ads", "s3") not in panel.galeria("acme", alc["ev"], alcance=alc)["lote"]["elegibles"]
    todos = panel.alcance("acme", 30)
    assert panel.mismo_alcance(datos.analisis_anuncio("acme", aid), todos)
    assert not panel.mismo_alcance(datos.analisis_anuncio("acme", aid), alc)


def test_mismo_alcance_compara_el_filtro_de_canal():
    alc = {"tienda_id": 3, "canal": "snapchat-ads", "desde": "2026-09-01", "hasta": "2026-09-30"}
    base = {"tienda_id": 3, "desde": "2026-09-01", "hasta": "2026-09-30"}
    assert panel.mismo_alcance(dict(base, foto={"alcance_canal": "snapchat-ads"}), alc)
    assert not panel.mismo_alcance(dict(base, foto={"alcance_canal": "facebook-ads"}), alc)
    assert not panel.mismo_alcance(dict(base, foto={}), alc)                      # sin el dato = «Todos»
    assert panel.mismo_alcance(dict(base, foto={}), dict(alc, canal=None))
    assert panel.mismo_alcance(dict(base, foto={"alcance_canal": None}), dict(alc, canal=""))


# ------------------------------------------------------------------- A1: la ruta no cobra uno fresco ---

def test_una_pestana_vieja_no_paga_otra_vez_un_analisis_fresco(app):  # noqa: F811
    """Dos ventanas: una analiza, termina, y la otra (que todavía muestra «Cómo mejorarlo») manda el POST."""
    _conectar()
    _sembrar_con_snapchat()
    _analizar(app, "p1")
    _el_worker_termino()
    assert _n_filas() == 1 and len(_tareas("tw_analizar_anuncio")) == 1
    r = _analizar(app, "p1")                                                  # la pestaña vieja, sin JS
    assert r.status_code == 302
    d = _analizar(app, "p1", json=True).get_json()                            # y con JS
    assert d["ok"] is False and "ya tiene un análisis con estos datos" in d["mensaje"]
    assert "Ver el análisis" in d["html"] and "Cómo mejorarlo" not in d["html"]
    assert _n_filas() == 1 and len(_tareas("tw_analizar_anuncio")) == 1      # ni fila ni tarea nuevas
    # Viejo (gastó un 50 % más desde entonces) sí se puede pagar otra vez.
    [fila] = _filas("p1")
    datos.actualizar_analisis(fila["id"], foto=dict(fila["foto"], m=dict(fila["foto"]["m"], gasto=1.0)))
    assert _analizar(app, "p1", json=True).get_json()["ok"] and _n_filas() == 2
