"""Rutas del centro de resultados (E2, spec 2026-10-02 §2 y §4): el fragmento `exp_resultados`, el panel de
una pieza `exp_pieza`, «Nuevo experimento» en su propia ruta (`exp_nuevo`) y las redirecciones de las acciones
de un experimento a `#experimentos?exp=<id>`. Todo GET: nada gasta ni publica."""
import pytest
import sqlalchemy as sa
from sqlalchemy import event

from tests.test_experimentos_db import PAISES, _pieza
from tests.test_rutas_experimentos import FORM_PROBAR, app  # noqa: F401  (fixture `app`)

AJAX = {"X-Requested-With": "fetch"}   # lo que manda static/exp_resultados.js: sin sidebar ni alertas de la página


@pytest.fixture(autouse=True)
def _proyectos_en_tmp(monkeypatch, tmp_path):
    """proyecto.json de cada cliente en una carpeta temporal: cfg_reglas escribe las reglas del proyecto y no debe
    dejar nada en clientes/acme/ del repo."""
    import proyectos
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))


def _experimento(nombre="Prueba", cliente="acme", **campos):
    import experimentos as ex
    eid = ex.crear(cliente, nombre, PAISES, "OUTCOME_TRAFFIC", 7, 500000.0, "https://t.co/p", "COP")
    if campos:
        ex.actualizar(cliente, eid, **campos)
    return eid


def _pieza_en(base_temporal, eid, cliente="acme", pais="CO", n=1):
    """Una pieza de video lista metida en el experimento, con un snapshot (así tiene dinero que mostrar)."""
    import experimentos as ex
    pid = _pieza(base_temporal, cliente=cliente, tipo="video", estado="listo", pais=None, idioma=None, legado=f"cf_{n}")
    ep = ex.agregar_pieza(cliente, eid, pid, pais)
    ex.snapshot(ep, {"impresiones": 1000, "clics_enlace": 20, "gasto": 100.0, "ctr": 2.0, "cpc": 5.0})
    return pid, ep


def _usuario(dashboard, usuario, cliente):
    """Sesión de un usuario de un proyecto (los de tests/conftest.py: «otro» es del proyecto «otro»)."""
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = usuario; s["rol"] = "cliente"; s["cliente"] = cliente
    return c


# ---------- exp_resultados ----------

def test_resultados_pinta_las_secciones_y_lo_que_necesita_decision(app, base_temporal):
    r = app["c"].get("/cliente/acme/experimentos/resultados", headers=AJAX)
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "cr-resultados-fragmento" in html and "Necesita tu decisión" in html
    for n in range(1, 8):
        assert f">{n:02d}<" in html
    assert "cr-resultados-fragmento" in app["c"].get("/cliente/acme/experimentos/resultados").get_data(as_text=True)


def test_resultados_con_experimento_trae_su_gestion(app, base_temporal):
    eid = _experimento("Cojín armando")
    otro = _experimento("Colcha corriendo", estado="corriendo", meta_campaign_id="cam_2")
    _pieza_en(base_temporal, eid)
    sin_exp = app["c"].get("/cliente/acme/experimentos/resultados", headers=AJAX).get_data(as_text=True)
    assert f'id="exp-{eid}"' not in sin_exp
    html = app["c"].get(f"/cliente/acme/experimentos/resultados?exp={eid}", headers=AJAX).get_data(as_text=True)
    assert f'id="exp-{eid}"' in html and "Cojín armando" in html
    assert f"/cliente/acme/experimentos/{eid}/lanzar" in html and "Lanzar a Meta (en pausa)" in html
    assert f"/cliente/acme/experimentos/{eid}/modo" in html and f"/cliente/acme/experimentos/{eid}/reglas" in html
    # En armado se pueden agregar piezas: el formulario trae las elegibles (que salen de ex.elegibles, no de la página).
    assert f"/cliente/acme/experimentos/{eid}/piezas" in html and "Agregar pieza" in html
    # Un experimento corriendo no acepta piezas nuevas ni trae el formulario.
    corriendo = app["c"].get(f"/cliente/acme/experimentos/resultados?exp={otro}", headers=AJAX).get_data(as_text=True)
    assert f'id="exp-{otro}"' in corriendo and "Pausar todo" in corriendo and "Agregar pieza" not in corriendo


def test_resultados_no_filtra_el_experimento_de_otro_proyecto(app, base_temporal):
    ajeno = _experimento("Ajeno secreto", cliente="otro")
    html = app["c"].get(f"/cliente/acme/experimentos/resultados?exp={ajeno}", headers=AJAX).get_data(as_text=True)
    assert "Ajeno secreto" not in html and f'id="exp-{ajeno}"' not in html
    assert f"/experimentos/{ajeno}/" not in html


def test_resultados_pieza_y_nuevo_piden_acceso_al_proyecto(app, base_temporal):
    """El guard por <cliente> de la app: alguien de «otro» no entra a acme (302 a su propio proyecto)."""
    eid = _experimento()
    _pid, ep = _pieza_en(base_temporal, eid)
    c = _usuario(app["dashboard"], "otro", "otro")
    for ruta in ("/cliente/acme/experimentos/resultados", f"/cliente/acme/experimentos/pieza/{ep}",
                 "/cliente/acme/experimentos/nuevo"):
        r = c.get(ruta, headers=AJAX)
        assert r.status_code == 302 and "/cliente/otro" in r.headers["Location"], ruta
        assert b"cr-resultados-fragmento" not in r.data
    # Sin sesión: al login.
    anonimo = app["dashboard"].app.test_client()
    assert anonimo.get("/cliente/acme/experimentos/resultados").status_code == 302


# ---------- exp_pieza ----------

def test_pieza_de_acme_200_y_la_ajena_404(app, base_temporal):
    eid = _experimento()
    _pid, ep = _pieza_en(base_temporal, eid)
    ajeno = _experimento("Ajeno", cliente="otro")
    _pid_o, ep_o = _pieza_en(base_temporal, ajeno, cliente="otro", n=2)
    r = app["c"].get(f"/cliente/acme/experimentos/pieza/{ep}?dias=30", headers=AJAX)
    assert r.status_code == 200 and "Retención" in r.get_data(as_text=True)
    assert app["c"].get(f"/cliente/acme/experimentos/pieza/{ep_o}", headers=AJAX).status_code == 404
    assert app["c"].get("/cliente/acme/experimentos/pieza/999999", headers=AJAX).status_code == 404
    # El proyecto dueño sí la ve.
    assert app["c"].get(f"/cliente/otro/experimentos/pieza/{ep_o}", headers=AJAX).status_code == 200


# ---------- exp_nuevo ----------

def test_nuevo_experimento_tiene_su_ruta_con_la_galeria_y_los_tres_pasos(app, base_temporal):
    import experimentos as ex
    pid = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_2")
    r = app["c"].get("/cliente/acme/experimentos/nuevo?piezas=%d" % pid)
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'id="exp-galeria"' in html and 'id="exp-probar"' in html
    assert 'action="/cliente/acme/experimentos/probar"' in html and f'name="piezas" value="{pid}"' in html
    assert 'data-paso="1"' in html and 'data-paso="3"' in html and 'id="exp-cuadricula"' in html
    assert "panel-cabecera" in html and "zona-exp" in html and "Nuevo experimento" in html
    assert 'href="/cliente/acme#experimentos"' in html and "Volver a resultados" in html
    # La llegada con piezas marcadas lee ?piezas= de la query (antes, del hash).
    assert "location.search" in html
    # Es la misma URL que el POST de exp_crear, con otro método: el GET no crea nada.
    assert ex.cargar("acme") == []


def test_nuevo_experimento_sin_meta_ofrece_conectar_y_no_deja_probar(app, monkeypatch, base_temporal):
    _pieza(base_temporal)
    monkeypatch.setattr(app["dashboard"].meta_conexion, "estado",
                        lambda c: {"estado": "sin_conectar", "verificado": False, "detalle": {}})
    html = app["c"].get("/cliente/acme/experimentos/nuevo").get_data(as_text=True)
    assert 'id="exp-galeria"' in html and "Conecta Meta arriba para probar" in html
    assert "¿Cómo quieres conectar Meta?" in html     # la tarjeta de _meta_conectar.html, ahora también en esta ruta
    assert 'action="/cliente/acme/experimentos/probar"' not in html


def test_nuevo_experimento_prellena_nombre_y_destino_del_catalogo(app, base_temporal):
    _pieza(base_temporal)
    html = app["c"].get("/cliente/acme/experimentos/nuevo?exp_nombre=Cojín&exp_destino=https://t.co/cojin").get_data(as_text=True)
    assert 'value="Cojín"' in html and 'value="https://t.co/cojin"' in html and 'data-tocado="1"' in html


def test_catalogo_crear_experimento_manda_a_la_ruta_nueva(app, base_temporal, monkeypatch):
    import tiendas
    monkeypatch.setattr(tiendas, "producto", lambda c, pid: {"nombre": "Cojín", "url_compra": "https://t.co/cojin"})
    r = app["c"].post("/cliente/acme/productos/7/experimento")
    assert r.status_code == 302
    destino = r.headers["Location"]
    assert destino.startswith("/cliente/acme/experimentos/nuevo?") and "exp_nombre=Coj" in destino
    assert "exp_destino=https://t.co/cojin" in destino and "#" not in destino


def test_crear_enlaza_a_la_ruta_nueva_con_la_pieza(app, base_temporal):
    import creative_flow as cf
    cid = cf.crear("acme", [], ["P"], [], "gira", 5, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", cid, estado="video_listo", tipo="video", modelo="wan3", video_url="https://r2/v.mp4")
    pieza_id = cf.pieza_id_por_legado("acme", cid)
    detalle = app["c"].get(f"/cliente/acme/creative_flow/{cid}/detalle").get_data(as_text=True)
    assert f'href="/cliente/acme/experimentos/nuevo?piezas={pieza_id}"' in detalle
    assert "#experimentos?piezas=" not in detalle


# ---------- redirecciones: de vuelta a ESE experimento ----------

def test_las_acciones_de_un_experimento_vuelven_a_el(app, base_temporal, monkeypatch):
    import experimentos as ex
    import propuestas
    d = app["dashboard"]
    monkeypatch.setattr(d.lanzador, "cambiar_estado", lambda *a, **k: None)
    monkeypatch.setattr(d.lanzador, "cambiar_presupuesto_pais", lambda *a, **k: None)
    monkeypatch.setattr(d.lanzador, "cerrar", lambda *a, **k: None)
    monkeypatch.setattr(d.acciones, "ejecutar", lambda *a, **k: "hecho.")
    eid = _experimento("Uno", estado="pausado", meta_campaign_id="cam_1")
    _pid, ep = _pieza_en(base_temporal, eid)
    c = app["c"]
    meta = "#experimentos?exp=%d" % eid
    assert c.post(f"/cliente/acme/experimentos/{eid}/estado", data={"estado": "ACTIVE"}).headers["Location"].endswith(meta)
    assert c.post(f"/cliente/acme/experimentos/{eid}/estado", data={"estado": "NADA"}).headers["Location"].endswith(meta)
    assert c.post(f"/cliente/acme/experimentos/{eid}/presupuesto",
                  data={"pais": "CO", "presupuesto_dia": "30000"}).headers["Location"].endswith(meta)
    assert c.post(f"/cliente/acme/experimentos/{eid}/modo", data={"modo": "semi"}).headers["Location"].endswith(meta)
    assert c.post(f"/cliente/acme/experimentos/{eid}/reglas", data={"ctr_min": "1.5"}).headers["Location"].endswith(meta)
    assert c.post(f"/cliente/acme/experimentos/{eid}/refrescar").headers["Location"].endswith(meta)
    assert c.post(f"/cliente/acme/experimentos/{eid}/decidir").headers["Location"].endswith(meta)
    assert c.post(f"/cliente/acme/experimentos/{eid}/cerrar").headers["Location"].endswith(meta)
    pid = propuestas.crear("acme", eid, "pausar", {"ep_id": ep}, "CTR bajo")
    assert c.post(f"/cliente/acme/propuestas/{pid}/aprobar").headers["Location"].endswith(meta)
    # Ya resuelta: el aviso de siempre, pero el clic vuelve al mismo experimento.
    assert c.post(f"/cliente/acme/propuestas/{pid}/aprobar").headers["Location"].endswith(meta)
    pid2 = propuestas.crear("acme", eid, "pausar", {"ep_id": ep}, "CTR bajo")
    assert c.post(f"/cliente/acme/propuestas/{pid2}/rechazar").headers["Location"].endswith(meta)
    propuestas.crear("acme", eid, "pausar", {"ep_id": ep}, "otra")
    assert c.post(f"/cliente/acme/experimentos/{eid}/propuestas/aprobar_todas").headers["Location"].endswith(meta)
    # Una propuesta que no existe no sabe de qué experimento era: a la pestaña.
    assert c.post("/cliente/acme/propuestas/999999/rechazar").headers["Location"].endswith("#experimentos")
    # La URL no queda con el «?» ni el «=» escapados.
    assert "%3F" not in c.post(f"/cliente/acme/experimentos/{eid}/estado", data={"estado": "PAUSED"}).headers["Location"]


def test_agregar_quitar_lanzar_y_meter_vuelven_al_experimento(app, base_temporal):
    import experimentos as ex
    eid = _experimento("Armando")
    pid = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_9")
    c = app["c"]
    meta = "#experimentos?exp=%d" % eid
    assert c.post(f"/cliente/acme/experimentos/{eid}/piezas", data={"pieza_id": str(pid), "pais": "CO"}).headers["Location"].endswith(meta)
    ep = ex.piezas("acme", eid)[0]["id"]
    assert c.post(f"/cliente/acme/experimentos/{eid}/piezas/{ep}/quitar").headers["Location"].endswith(meta)
    assert c.post(f"/cliente/acme/experimentos/{eid}/lanzar").headers["Location"].endswith(meta)   # sin piezas: avisa, vuelve
    r = c.post("/cliente/acme/experimentos/meter",
               data={"legado_id": "cf_9", "experimento_id": str(eid), "pais": "CO", "volver": "experimentos"})
    assert r.headers["Location"].endswith(meta)
    r = c.post("/cliente/acme/experimentos/meter",
               data={"legado_id": "cf_9", "experimento_id": str(eid), "pais": "MX", "volver": "creativeflowplus"})
    assert r.headers["Location"].endswith("#creativeflowplus")


def test_probar_vuelve_al_experimento_nuevo_y_los_errores_a_la_pagina_del_formulario(app, base_temporal):
    import experimentos as ex
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_2")
    data = dict(FORM_PROBAR, piezas=[str(clon)], combinaciones=[f"{clon}:CO", f"{clon}:MX"])
    r = app["c"].post("/cliente/acme/experimentos/probar", data=data)
    (e,) = ex.cargar("acme")
    assert r.status_code == 302 and r.headers["Location"].endswith("#experimentos?exp=%d" % e["id"])
    # Un error de validación no crea nada y deja a la persona donde está el formulario, con su pieza marcada.
    malo = dict(data, tope_total="0")
    r = app["c"].post("/cliente/acme/experimentos/probar", data=malo)
    assert r.status_code == 302 and r.headers["Location"] == "/cliente/acme/experimentos/nuevo?piezas=%d" % clon
    assert len(ex.cargar("acme")) == 1


def test_crear_y_reglas_por_defecto_vuelven_a_la_pestana(app, base_temporal):
    import experimentos as ex
    from tests.test_rutas_experimentos import FORM
    r = app["c"].post("/cliente/acme/experimentos/nuevo", data=FORM)
    (e,) = ex.cargar("acme")
    assert r.headers["Location"].endswith("#experimentos?exp=%d" % e["id"])
    assert app["c"].post("/cliente/acme/experimentos/nuevo", data=dict(FORM, nombre="")).headers["Location"].endswith("#experimentos")
    assert app["c"].post("/cliente/acme/config/reglas", data={"roas_min": "3"}).headers["Location"].endswith("#experimentos")


# ---------- consultas: el fragmento no crece con las piezas ----------

class _Contador:
    def __init__(self):
        self.n = 0

    def __enter__(self):
        def cuenta(conn, cursor, statement, parameters, context, executemany):
            self.n += 1
        self._f = cuenta
        event.listen(sa.engine.Engine, "before_cursor_execute", cuenta)
        return self

    def __exit__(self, *a):
        event.remove(sa.engine.Engine, "before_cursor_execute", self._f)


def _dia(db, ep, fecha):
    with db.conectar() as con:
        con.execute(db.metrica_dia.insert().values(
            experimento_pieza_id=ep, fecha=fecha, actualizado_en=fecha + "T12:00:00", impresiones=500, alcance=400,
            frecuencia=1.2, clics=12, clics_enlace=10, gasto=5.0, cpm=10.0, vistas_3s=100, reproducciones=300, p25=90,
            p50=60, p75=40, p95=20, p100=10, thruplay=30, tiempo_medio_s=3.0, visitas_pagina=6, carrito=2,
            pago_iniciado=1, compras_meta=1, ingresos_meta=30.0))


def _sembrar_piezas(base_temporal, eid, desde, hasta):
    import db
    import experimentos as ex
    for i in range(desde, hasta):
        pid = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado=f"cf_{100 + i}")
        ep = ex.agregar_pieza("acme", eid, pid, "CO" if i % 2 else "MX")
        for k, f in enumerate(("2026-09-29T23:00:00", "2026-10-01T23:00:00")):
            ex.snapshot(ep, {"impresiones": 1000 * (k + 1), "gasto": 10.0 * (k + 1), "clics_enlace": 10 * (k + 1),
                             "frecuencia": 1.4}, tomado_en=f)
        for f in ("2026-09-30", "2026-10-01"):
            _dia(db, ep, f)


def _lecturas(app, base_temporal, eid):
    import experimentos as ex
    d = app["dashboard"]

    def fragmento():
        d._TABLERO_CACHE.clear()      # frío cada vez: lo que se mide es el cálculo, no la caché de 60 s
        d.invalidar_alertas("acme")
        r = app["c"].get(f"/cliente/acme/experimentos/resultados?exp={eid}", headers=AJAX)
        assert r.status_code == 200
    with _Contador() as solo:
        ex.cargar("acme")
    with _Contador() as frag:
        fragmento()
    return solo.n, frag.n


def test_el_fragmento_no_hace_mas_consultas_por_pieza_que_experimentos_cargar(app, base_temporal):
    """`experimentos.cargar` tiene un N+1 por pieza (la última métrica) que ya existía y que se acepta; el fragmento
    puede crecer SOLO lo que crece esa lectura —una sola vez por petición—, no una por tarjeta ni por sección."""
    eid = _experimento("Muchas piezas", estado="corriendo", meta_campaign_id="cam_1")
    _sembrar_piezas(base_temporal, eid, 0, 3)
    solo3, frag3 = _lecturas(app, base_temporal, eid)
    _sembrar_piezas(base_temporal, eid, 3, 15)
    solo15, frag15 = _lecturas(app, base_temporal, eid)
    assert solo15 > solo3, "la prueba no mide nada si cargar() no crece con las piezas"
    assert frag15 - frag3 <= solo15 - solo3, (solo3, solo15, frag3, frag15)


def test_experimentos_cargar_memorizado_lee_una_vez_por_peticion(base_temporal):
    import experimentos as ex
    eid = _experimento("Uno")
    _pieza_en(base_temporal, eid)
    with _Contador() as normal:
        ex.cargar("acme"); ex.cargar("acme")
    with ex.lecturas_memorizadas():
        with _Contador() as primera:
            a = ex.cargar("acme")
        with _Contador() as segunda:
            b = ex.cargar("acme")
        a[0]["nombre"] = "tocado"                       # quien la modifique no le cambia nada al siguiente
        c = ex.cargar("acme")
    assert primera.n * 2 == normal.n and segunda.n == 0
    assert b == c and b[0]["nombre"] == "Uno" and a is not b
    # Fuera del bloque no se memoriza nada.
    with _Contador() as despues:
        ex.cargar("acme")
    assert despues.n == primera.n
    assert ex.cargar("otro") == []


# ---------- la pantalla (R2, 2026-10-03): fragmento, panel de la pieza y JS ----------

import re
from datetime import datetime, timedelta


def _hoy(atras=0):
    return (datetime.now() - timedelta(days=atras)).date().isoformat()


def _scripts(html):
    return re.findall(r"<script\b[^>]*>", html)


def test_fragmento_trae_cada_seccion_y_solo_el_json_de_las_graficas(app, base_temporal):
    import db
    import propuestas
    eid = _experimento("Con datos", estado="corriendo", meta_campaign_id="cam_1")
    _pid, ep = _pieza_en(base_temporal, eid)
    _dia(db, ep, _hoy())
    pid = propuestas.crear("acme", eid, "pausar", {"ep_id": ep}, "CTR bajo")
    html = app["c"].get("/cliente/acme/experimentos/resultados", headers=AJAX).get_data(as_text=True)
    assert html.count('<li class="cr-kpi') == 12 and html.count("data-cr-spark=") == 12
    assert 'data-cr-grafico="dia"' in html and 'data-cr-metrica="roas"' in html and 'class="cr-embudo"' in html
    assert html.count("--alto:") == 6
    assert f'data-cr-pieza="/cliente/acme/experimentos/pieza/{ep}?' in html and "data-cr-evolucion=" in html
    assert 'class="cr-ranking cr-tabla tabla-apilada"' in html and "data-cr-dona-pct=" in html
    assert f'href="#experimentos?exp={eid}"' in html and "data-cr-filtro" in html
    # «Necesita tu decisión»: los mismos formularios POST de siempre, con su confirmación
    assert f'action="/cliente/acme/propuestas/{pid}/aprobar"' in html and f'action="/cliente/acme/propuestas/{pid}/rechazar"' in html
    assert f'action="/cliente/acme/experimentos/{eid}/propuestas/aprobar_todas"' in html and "confirm(" in html
    # el único <script> del fragmento es el JSON de las gráficas (innerHTML no ejecuta scripts)
    assert _scripts(html) == ['<script type="application/json" id="cr-datos">']


def test_fragmento_sin_pixel_atenua_cada_paso_que_sigue(app, base_temporal):
    """Sin el Pixel, «Agregaron al carrito» llega en 0 (sin_datos) y los pasos que siguen llegan en 0 con pct None y
    sin_datos=False: los tres se atenúan y dicen «requiere el Pixel» (revisión de la tarea 3)."""
    import db
    eid = _experimento("Sin pixel", estado="corriendo", meta_campaign_id="cam_1")
    _pid, ep = _pieza_en(base_temporal, eid)
    with db.conectar() as con:
        con.execute(db.metrica_dia.insert().values(
            experimento_pieza_id=ep, fecha=_hoy(), actualizado_en=db.ahora(), impresiones=500, alcance=400, frecuencia=1.2,
            clics=12, clics_enlace=10, gasto=5.0, cpm=10.0, vistas_3s=100, reproducciones=300, p25=90, p50=60, p75=40,
            p95=20, p100=10, thruplay=30, tiempo_medio_s=3.0, visitas_pagina=6, carrito=0, pago_iniciado=0,
            compras_meta=0, ingresos_meta=0.0))
    html = app["c"].get("/cliente/acme/experimentos/resultados", headers=AJAX).get_data(as_text=True)
    embudo = html[html.index('class="cr-embudo"'):html.index("</ol>", html.index('class="cr-embudo"'))]
    assert embudo.count("cr-sin-pixel") == 3 and embudo.count("requiere el Pixel") == 3
    assert "cr-caida" not in embudo


def test_fragmento_errores_del_detalle_de_meta_en_palabras_y_escapados(app, base_temporal):
    import db
    import experimentos as ex
    eid = _experimento("Con error", estado="corriendo", meta_campaign_id="cam_1")
    _pieza_en(base_temporal, eid)
    ex.actualizar_extra("acme", eid, lambda x: dict(x, detalle_meta={
        "actualizado_en": db.ahora(), "errores": {"diario": "<img src=x onerror=alert(1)> se cayó"},
        "limite": False, "cortado": False}))
    html = app["c"].get("/cliente/acme/experimentos/resultados", headers=AJAX).get_data(as_text=True)
    assert "Detalle de Meta al día hace menos de 1 h" in html
    assert "&lt;img src=x onerror=alert(1)&gt; se cayó" in html and "<img src=x" not in html
    assert "{&#39;diario&#39;" not in html and "{'diario'" not in html        # el motivo, no el diccionario


def test_panel_de_la_pieza_completo_y_con_autoescape(app, base_temporal):
    import db
    import experimentos as ex
    eid = _experimento("Panel", estado="corriendo", meta_campaign_id="cam_1")
    pid, ep = _pieza_en(base_temporal, eid)
    ex.actualizar_pais("acme", eid, "CO", meta_adset_id="adset_1", estado="activo")
    ex.marcar_pieza("acme", ep, rankings_meta={"calidad": "ABOVE_AVERAGE", "interaccion": None, "conversion": "BELOW_AVERAGE_35"},
                    diagnostico={"causas": [{"codigo": "gancho", "detalle": "<b>detalle</b>"}],
                                 "siguiente": {"que": "gancho", "porque": "<script>alert(2)</script>"}})
    with db.conectar() as con:
        con.execute(db.evento.insert().values(cliente="acme", experimento_id=eid, experimento_pieza_id=ep, tipo="accion",
                                              mensaje="<script>alert(3)</script> pausa", datos={}, creado_en=db.ahora()))
    html = app["c"].get(f"/cliente/acme/experimentos/pieza/{ep}?dias=14", headers=AJAX).get_data(as_text=True)
    assert "cr-pieza-fragmento" in html and "Retención" in html and 'data-cr-grafico="pieza"' in html
    assert html.count('<li class="cr-kpi') == 12
    assert "Superior al promedio" in html and "Inferior al promedio" in html
    assert "<script>alert" not in html and "&lt;script&gt;alert(2)&lt;/script&gt;" in html and "<b>detalle</b>" not in html
    assert f'href="/cliente/acme/experimentos/nuevo?piezas={pid}"' in html and 'href="#creativeflowplus"' in html
    assert f'action="/cliente/acme/experimentos/{eid}/estado"' in html and 'name="estado" value="PAUSED"' in html
    assert 'preload="none" data-precarga' in html
    assert _scripts(html) == ['<script type="application/json" class="cr-datos-pieza">']
    # el JSON de la gráfica escapa lo que podría cerrar el <script>
    datos = html[html.index('class="cr-datos-pieza">'):]
    assert "</script> pausa" not in datos.split("</script>", 1)[0]


def test_armazon_y_js_del_centro_de_resultados(app):
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    tab = html[html.index('<section id="tab-experimentos"'):html.index('<section id="tab-alertas"')]
    assert re.search(r'src="/static/exp_resultados\.js\?v=\w+" defer', tab)
    assert 'id="cr-textos"' in tab and 'id="cr-resultados"' in tab and '<dialog id="cr-panel"' in tab
    assert "panel-cabecera cr-cabecera" in tab and "Centro de resultados" in tab
    js = open("static/exp_resultados.js", encoding="utf-8").read()
    assert "getElementById(id)" in js and "textosDe('cr-textos')" in js and "dataset.crTextos" not in js
    assert "r.redirected" in js                         # sesión vencida: el login no entra a la pestaña
    assert not re.search(r"position\s*[:=]\s*['\"]?fixed", js)
    # innerHTML solo con los fragmentos del servidor; los datos van con textContent
    asignaciones = re.findall(r"(\w+)\.innerHTML\s*=\s*([^;]+);", js)
    assert asignaciones and all(valor.strip() == "html" for _el, valor in asignaciones), asignaciones
    assert "textContent" in js


# ---------- revisión de R2 (2026-10-03) ----------

import shutil
import subprocess

_ARNES_JS = r"""
const fs = require('fs');
const g = globalThis; g.window = g;
const oyentes = {};
g.addEventListener = (t, f) => { (oyentes[t] = oyentes[t] || []).push(f); };
g.innerWidth = 1280;
const ubic = {pathname: '/cliente/acme', search: '?exp=7', hash: '#experimentos', replace: (u) => pedidos.push('replace:' + u)};
g.location = ubic;
const reemplazos = [], pedidos = [];
function ir(url) {
  const m = url.match(/^([^?#]*)(\?[^#]*)?(#.*)?$/);
  ubic.pathname = m[1] || ubic.pathname; ubic.search = m[2] || ''; ubic.hash = m[3] || '';
}
g.history = {replaceState: (s, t, u) => { reemplazos.push(u); ir(u); }, pushState: (s, t, u) => ir(u)};
function nodo(atributos) {
  return {atributos: atributos || {}, firstChild: null, classList: {add() {}, remove() {}, toggle() {}, contains: () => true},
          getAttribute(n) { return this.atributos[n] === undefined ? null : this.atributos[n]; },
          setAttribute(n, v) { this.atributos[n] = v; }, querySelector: () => null, querySelectorAll: () => [],
          addEventListener() {}, appendChild() {}, scrollIntoView() {}, set innerHTML(v) { this.html = v; }};
}
const raiz = nodo({'data-url': '/cliente/acme/experimentos/resultados', 'data-url-nuevo': '/cliente/acme/experimentos/nuevo'});
const pestana = nodo();
g.document = {readyState: 'complete', documentElement: {lang: 'es'}, addEventListener() {},
  createElement: () => nodo(), createElementNS: () => nodo(),
  getElementById: (id) => id === 'cr-resultados' ? raiz : id === 'tab-experimentos' ? pestana :
                          id === 'cr-textos' ? {textContent: '{}'} : null};
g.fetch = (url) => { pedidos.push(url); return Promise.resolve({ok: true, redirected: false,
  text: () => Promise.resolve('<div class="cr-resultados-fragmento"></div>')}); };
eval(fs.readFileSync('static/exp_resultados.js', 'utf8'));
setTimeout(() => {
  // La persona quita el filtro («×» o «Todos los experimentos»): el hash queda sin exp.
  g.history.pushState(null, '', '#experimentos');
  (oyentes.hashchange || []).forEach((f) => f());
  setTimeout(() => console.log(JSON.stringify({reemplazos, pedidos, search: ubic.search, hash: ubic.hash})), 20);
}, 20);
"""


@pytest.mark.skipif(not shutil.which("node"), reason="sin Node no se corre el JS (el VPS no lo tiene)")
def test_el_exp_de_un_enlace_viejo_se_consume_una_vez_y_se_puede_quitar():
    """`?exp=<id>#experimentos` (el enlace viejo de _tw_panel.html) se pasa UNA vez al hash y sale de la dirección;
    después, quitar el filtro de verdad lo quita (antes navegar() lo volvía a leer de location.search)."""
    import json
    r = subprocess.run([shutil.which("node"), "-e", _ARNES_JS], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    salida = json.loads(r.stdout.strip().splitlines()[-1])
    assert salida["reemplazos"] == ["/cliente/acme#experimentos?exp=7"] and salida["search"] == ""
    assert salida["pedidos"] == ["/cliente/acme/experimentos/resultados?exp=7", "/cliente/acme/experimentos/resultados"]
    js = open("static/exp_resultados.js", encoding="utf-8").read()
    navegar = js[js.index("function navegar()"):js.index("function consumirExpViejo()")]
    assert "location.search" not in re.sub(r"//[^\n]*", "", navegar)          # sin contar los comentarios


def test_la_barra_de_un_anuncio_suelto_avanza_dentro_del_fragmento(app, base_temporal, monkeypatch):
    """Revisión de R2: la barra de un anuncio suelto con trabajo vivo traía un <script>iniciarPolling…</script>, que
    dentro del fragmento (innerHTML) nunca corre: ahora lleva data-poll-job y arrancarSondeos la arranca."""
    import ads
    aid = ads.crear("acme", "flowplus", "cf_9", "https://r2/suelto.mp4", "video", "Anuncio viejo")
    ads.actualizar("acme", aid, estado="activo", meta_ids={"campaign_id": "c1", "adset_id": "s1", "ad_id": "a1"})
    jid = f"acme__{aid}__metricas"
    monkeypatch.setattr(app["dashboard"].trabajos, "en_curso", lambda job_id: job_id == jid)
    html = app["c"].get("/cliente/acme/experimentos/resultados", headers=AJAX).get_data(as_text=True)
    assert "Anuncio viejo" in html
    assert f'<div class="barra-progreso" id="trabajo-{jid}" data-poll-job="{jid}">' in html
    assert "iniciarPolling" not in html
    assert all("application/json" in s for s in _scripts(html)), _scripts(html)
