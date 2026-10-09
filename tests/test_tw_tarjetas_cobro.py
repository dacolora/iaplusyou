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


# ------------------------------------------------------------------- A2: todos los análisis del anuncio ---

def test_ida_y_vuelta_entre_periodos_no_vuelve_a_ofrecer(app):  # noqa: F811
    """7 días → 30 días → 7 días: el de 30 (más nuevo) no esconde el de 7, que sigue fresco."""
    _conectar()
    _sembrar_con_snapchat()
    _analizar(app, "p1", dias="7")
    _el_worker_termino("La de siete días.")
    _analizar(app, "p1", dias="30")                       # «Analizar con estos datos» en 30 días
    _el_worker_termino("La de treinta días.")
    assert _n_filas() == 2
    html = _tarjeta(app, "p1", dias="7")
    assert "La de siete días." in html and "La de treinta días." not in html
    assert "Analizado con los datos del" not in html and "Analizar con estos datos" not in html
    assert "Cómo mejorarlo" not in html and "Analizar otra vez" not in html
    alc = panel.alcance("acme", 7)
    assert ("facebook-ads", "p1") not in panel.galeria("acme", alc["ev"], alcance=alc)["lote"]["elegibles"]
    d = _analizar(app, "p1", dias="7", json=True).get_json()
    assert d["ok"] is False and _n_filas() == 2
    assert "La de treinta días." in _tarjeta(app, "p1", dias="30")


def test_el_error_de_otro_alcance_no_ofrece_intentar_otra_vez(app):  # noqa: F811
    """Uno fresco de 7 días y uno de 30 que falló después: en 7 se ve el de 7, sin «Intentar otra vez» ni lote."""
    _conectar()
    _sembrar_con_snapchat()
    _analizar(app, "p1", dias="7")
    _el_worker_termino("La de siete días.")
    alc30 = panel.alcance("acme", 30)
    error = datos.crear_analisis("acme", alc30["tienda_id"], "facebook-ads", "p1", alc30["desde"], alc30["hasta"],
                                 "USD", {})
    datos.actualizar_analisis(error, estado="error", error="Claude no respondió a tiempo.")
    html = _tarjeta(app, "p1", dias="7")
    assert "La de siete días." in html and "Intentar otra vez" not in html and "Claude no respondió" not in html
    alc7 = panel.alcance("acme", 7)
    assert ("facebook-ads", "p1") not in panel.galeria("acme", alc7["ev"], alcance=alc7)["lote"]["elegibles"]
    # En 30 días ese error sí es el suyo.
    assert "Intentar otra vez" in _tarjeta(app, "p1", dias="30")
    # Y un anuncio cuyo único análisis es un error de otro alcance se ve como nuevo: «Cómo mejorarlo».
    solo_error = datos.crear_analisis("acme", alc30["tienda_id"], "facebook-ads", "p2", alc30["desde"],
                                      alc30["hasta"], "USD", {})
    datos.actualizar_analisis(solo_error, estado="error", error="Claude no respondió a tiempo.")
    html = _tarjeta(app, "p2", dias="7")
    assert "Cómo mejorarlo" in html and "Intentar otra vez" not in html and "Claude no respondió" not in html
    assert ("facebook-ads", "p2") in panel.galeria("acme", alc7["ev"], alcance=alc7)["lote"]["elegibles"]


def test_elegir_analisis():
    a = {"veredicto": "perdedor", "m": {"gasto": 100.0}}
    alc = {"tienda_id": 1, "canal": None, "desde": "2026-09-24", "hasta": "2026-09-30"}

    def fila(i, estado, desde="2026-09-24", hasta="2026-09-30", veredicto="perdedor"):
        return {"id": i, "estado": estado, "tienda_id": 1, "desde": desde, "hasta": hasta,
                "foto": {"veredicto": veredicto, "m": {"gasto": 100.0}}}
    fresco7, error30 = fila(1, "lista"), fila(2, "error", desde="2026-09-01")
    lista30 = fila(3, "lista", desde="2026-09-01")
    e = panel.elegir_analisis(a, [error30, fresco7], alc)
    assert e["fila"] is fresco7 and e["fresco"] and not e["ofrecer"] and not e["otro_alcance"]
    e = panel.elegir_analisis(a, [lista30, error30], alc)
    assert e["fila"] is lista30 and e["otro_alcance"] and not e["ofrecer"]
    e = panel.elegir_analisis(a, [error30], alc)
    assert e["fila"] is None and e["ofrecer"]
    viejo = fila(4, "lista", veredicto="ganador")
    e = panel.elegir_analisis(a, [lista30, viejo], alc)
    assert e["fila"] is viejo and e["viejo"] and e["ofrecer"]
    e = panel.elegir_analisis(a, [], alc, vivo=True)
    assert not e["ofrecer"] and e["vivo"]
    assert not panel.elegir_analisis(dict(a, veredicto="sin_datos"), [], alc)["ofrecer"]


# ------------------------------------------------------------------- A4: una fila colgada no bloquea ---

def test_una_fila_colgada_sin_tarea_no_bloquea_el_anuncio(app):  # noqa: F811
    """Una fila en_cola cuya tarea ya no existe (murió antes de su try, un reinicio): la tarjeta la muestra como error
    con «Intentar otra vez · US$», entra al lote, y el POST la cierra en error antes de crear la nueva."""
    _conectar()
    _sembrar_con_snapchat()
    alc = panel.alcance("acme", 30)
    colgada = datos.crear_analisis("acme", alc["tienda_id"], "facebook-ads", "p1", alc["desde"], alc["hasta"], "USD", {})
    html = _tarjeta(app, "p1")
    assert "Se interrumpió antes de terminar." in html and "Intentar otra vez · US$" in html and "data-poll-job" not in html
    assert ("facebook-ads", "p1") in panel.galeria("acme", alc["ev"], alcance=alc)["lote"]["elegibles"]
    d = _analizar(app, "p1", json=True).get_json()
    assert d["ok"] and 'data-poll-job="acme__tw_anuncio__facebook-ads__p1"' in d["html"]
    vieja = datos.analisis_anuncio("acme", colgada)
    assert vieja["estado"] == "error" and vieja["error"] == "Se interrumpió antes de terminar."
    assert _n_filas() == 2 and [t["payload"]["analisis_id"] for t in _tareas("tw_analizar_anuncio")] != [colgada]


def test_con_la_tarea_viva_no_se_crea_otra_fila(app):  # noqa: F811
    _conectar()
    _sembrar_con_snapchat()
    assert _analizar(app, "p1", json=True).get_json()["ok"]
    d = _analizar(app, "p1", json=True).get_json()
    assert d["ok"] is False and "ya se está analizando" in d["mensaje"] and _n_filas() == 1
    assert datos.analisis_de_anuncios("acme", [("facebook-ads", "p1")])[("facebook-ads", "p1")][0]["estado"] == "en_cola"


def test_una_tarea_que_falla_al_leer_su_fila_deja_el_anuncio_analizable(app, monkeypatch):  # noqa: F811
    """La tarea muere antes de llegar a analizar (la base no deja leer la fila): la fila queda en error o, si ni eso se
    pudo escribir, colgada sin tarea viva; en los dos casos el anuncio se puede volver a pedir."""
    from tareas import triple_whale as t
    _conectar()
    _sembrar_con_snapchat()
    assert _analizar(app, "p1", json=True).get_json()["ok"]
    [fila] = _filas("p1")
    leer = datos.analisis_anuncio

    def bloqueada(cliente, aid):
        raise RuntimeError("database is locked")
    monkeypatch.setattr(datos, "analisis_anuncio", bloqueada)
    with pytest.raises(RuntimeError):
        t.tw_analizar_anuncio({"id": 1, "job_id": t.job_id_analisis("acme", "facebook-ads", "p1"),
                               "payload": {"cliente": "acme", "analisis_id": fila["id"]}})
    monkeypatch.setattr(datos, "analisis_anuncio", leer)
    assert datos.analisis_anuncio("acme", fila["id"])["estado"] == "error"
    with db.conectar() as con:                                       # el worker cierra la tarea en error
        con.execute(db.tarea.update().values(estado="error"))
    assert "Intentar otra vez · US$" in _tarjeta(app, "p1")
    assert _analizar(app, "p1", json=True).get_json()["ok"] and _n_filas() == 2


# ------------------------------------------------------------------- A5: el precio del lote ---

def _con_duraciones(duraciones):
    datos.reemplazar_creativos("acme", _tienda(), [{"canal": "facebook-ads", "ad_id": ad, "tipo": "video",
                                                    "duracion_s": s} for ad, s in duraciones.items()])


def test_el_precio_del_lote_es_la_suma_de_las_tarjetas(app):  # noqa: F811
    """Cada tarjeta cobra por la duración de su video: el total del lote es la suma de esas tarjetas, no 30 s × N."""
    _conectar()
    _sembrar_con_snapchat()
    _con_duraciones({"g1": 600, "p1": 15, "p2": 120})
    alc = panel.alcance("acme", 30)
    g = panel.galeria("acme", alc["ev"], alcance=alc)
    claves = set(g["lote"]["claves"])
    assert {("facebook-ads", "g1"), ("facebook-ads", "p1"), ("facebook-ads", "p2")} <= claves
    por_tarjeta = {(a["canal"], a["ad_id"]): a["precio_analisis"]["usd"] for a in g["tarjetas"]}
    assert set(por_tarjeta) >= claves
    total = sum(por_tarjeta[k] for k in claves)
    assert g["lote"]["precio"]["usd"] == pytest.approx(total, abs=1e-4)
    treinta = panel.precio_analisis({})["usd"]
    assert g["lote"]["precio"]["usd"] != pytest.approx(treinta * len(claves), abs=1e-4)
    html = app["c"].get("/cliente/acme/triple-whale/galeria?entera=1&dias=30").data.decode()
    assert f"Analizar los {len(claves)} que más gastaron · {g['lote']['precio']['texto']}" in html


def test_sin_precio_el_lote_dice_precio_no_disponible(app, monkeypatch):  # noqa: F811
    import gastos
    _conectar()
    _sembrar_con_snapchat()
    monkeypatch.setattr(gastos, "_ESTIMADORES", dict(gastos._ESTIMADORES, analisis_anuncio_tw=lambda **_: (None, "")))
    alc = panel.alcance("acme", 30)
    g = panel.galeria("acme", alc["ev"], alcance=alc)
    assert g["lote"]["n"] and g["lote"]["precio"]["usd"] is None
    html = app["c"].get("/cliente/acme/triple-whale/galeria?entera=1&dias=30").data.decode()
    assert "que más gastaron · precio no disponible" in html and "Costo total: precio no disponible" in html
    assert "US$ 0" not in html
