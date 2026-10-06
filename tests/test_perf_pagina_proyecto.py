"""Auditoría de rendimiento 2026-09-28: la página del proyecto hacía una
consulta por tarjeta (1 158 en happyflops, 598 solo para saber si había un
trabajo corriendo). Las lecturas por proyecto (`guiones_base`,
`finales_por_sesion`, `ultimos_captions`, `con_vivos_precargados`) devuelven
lo mismo que las lecturas por pieza, y el total de consultas ya no crece con
el número de piezas."""
import re

import pytest
import sqlalchemy as sa
from sqlalchemy import event


def _admin(dashboard):
    dashboard.app.config["TESTING"] = True
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "admin"; s["rol"] = "admin"; s["cliente"] = None
    return c


@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import proyectos
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    return {"dashboard": dashboard, "c": _admin(dashboard)}


def _sembrar(n, con_final=True, con_caption=True, desde=0):
    import creative_flow
    import organico
    ids = []
    for i in range(desde, desde + n):
        cf_id = creative_flow.crear("acme", [], ["prod"], [], f"acción {i}", 8, "tono", "A",
                                    legado_id=f"cf_2026090{i % 9}_00000{i}_{i:06d}")
        creative_flow.actualizar("acme", cf_id, estado="video_listo", tipo="video",
                                 video_url=f"https://r2/videos/{cf_id}.mp4", guion_base=f"guion {i}" if i % 2 else None)
        if con_final:
            fid = creative_flow.crear_final("acme", cf_id, "es", "CO")
            # Tablero de Final edition (2026-10-02): la mitad lista (Finalizados) y
            # la mitad con error (su video queda en «En edición»), para que las
            # dos columnas tengan tarjetas.
            creative_flow.actualizar_final("acme", fid, estado="listo" if i % 2 == 0 else "error",
                                           url_video=f"https://r2/finales/{fid}.mp4")
        if con_caption:
            pid = creative_flow.pieza_id_por_legado("acme", cf_id)
            organico.crear("acme", pid, "instagram", f"caption viejo {i}")
            organico.crear("acme", pid, "facebook", f"caption nuevo {i}")
        ids.append(cf_id)
    return ids


class _Contador:
    def __init__(self):
        self.total = 0
        self.tarea = 0

    def __enter__(self):
        def _cuenta(conn, cursor, statement, parameters, context, executemany):
            self.total += 1
            if "FROM tarea" in statement:
                self.tarea += 1
        self._f = _cuenta
        event.listen(sa.engine.Engine, "before_cursor_execute", _cuenta)
        return self

    def __exit__(self, *a):
        event.remove(sa.engine.Engine, "before_cursor_execute", self._f)


def test_lecturas_por_proyecto_coinciden_con_las_por_pieza(base_temporal):
    import creative_flow
    from doctrina import revisor
    ids = _sembrar(4)
    assert creative_flow.guiones_base("acme") == {cf: creative_flow.guion_base("acme", cf) for cf in ids}
    por_sesion = creative_flow.finales_por_sesion("acme")
    assert set(por_sesion) == set(ids)
    for cf in ids:
        assert por_sesion[cf] == creative_flow.finales("acme", cf)
        assert len(por_sesion[cf]) == 1 and por_sesion[cf][0]["estado"] in ("listo", "error")
    captions = revisor.ultimos_captions("acme")
    assert captions == {cf: revisor.ultimo_caption("acme", cf) for cf in ids}
    assert all(v.startswith("caption nuevo") for v in captions.values())
    assert creative_flow.guiones_base("otro") == {} and creative_flow.finales_por_sesion("otro") == {}
    assert revisor.ultimos_captions("otro") == {}


def test_sesion_sin_finales_ni_captions(base_temporal):
    import creative_flow
    from doctrina import revisor
    (cf,) = _sembrar(1, con_final=False, con_caption=False)
    assert creative_flow.finales_por_sesion("acme").get(cf, []) == creative_flow.finales("acme", cf) == []
    assert revisor.ultimos_captions("acme").get(cf, "") == revisor.ultimo_caption("acme", cf) == ""


def test_en_curso_precargado_ve_lo_mismo_que_la_consulta_directa(base_temporal):
    import cola
    import trabajos
    cola.encolar("flowplus_video", {"cliente": "acme"}, job_id="acme__vivo", cliente="acme")
    tid = cola.encolar("flowplus_video", {"cliente": "acme"}, job_id="acme__hecho", cliente="acme")
    cola.marcar_terminada(tid, "listo") if hasattr(cola, "marcar_terminada") else None
    with base_temporal.conectar() as con:
        con.execute(base_temporal.tarea.update().where(base_temporal.tarea.c.job_id == "acme__hecho").values(estado="hecha"))
    directo = {j: trabajos.en_curso(j) for j in ("acme__vivo", "acme__hecho", "acme__nunca")}
    assert directo == {"acme__vivo": True, "acme__hecho": False, "acme__nunca": False}

    @trabajos.con_vivos_precargados
    def dentro():
        with _Contador() as c:
            r = {j: trabajos.en_curso(j) for j in ("acme__vivo", "acme__hecho", "acme__nunca")}
        return r, c.tarea
    precargado, consultas = dentro()
    assert precargado == directo and consultas == 0
    # Al salir, el hilo vuelve a consultar la base (gunicorn reutiliza hilos).
    assert getattr(trabajos._PRECARGA, "vivos", None) is None


def test_la_pagina_del_proyecto_no_consulta_por_tarjeta(app):
    c = app["c"]
    _sembrar(3)
    with _Contador() as pocas:
        assert c.get("/cliente/acme").status_code == 200
    _sembrar(12, desde=3)      # 15 piezas en total
    with _Contador() as muchas:
        html = c.get("/cliente/acme").data.decode()
    assert muchas.tarea <= 3, f"{muchas.tarea} consultas a tarea con 15 piezas"
    # 12 piezas más no pueden costar más de un puñado de consultas extra.
    assert muchas.total - pocas.total <= 6, (pocas.total, muchas.total)


def test_la_pagina_no_embebe_detalles_ni_pasa_de_24_tarjetas(app):
    """Tarjetas ligeras (spec 2026-09-28): ningún <template> de detalle en la
    página y, por lista, como mucho TARJETAS_POR_PAGINA tarjetas (el resto
    llega con «Ver más»). Se cuentan las aperturas de tarjeta (`class="generado"`
    o `class="generado generado-final"`), no las clases hijas."""
    _sembrar(40)
    html = app["c"].get("/cliente/acme").data.decode()
    assert '<template class="generado-detalle">' not in html
    # En Crear la cuadrícula cierra antes del modal; en Final edition cada
    # columna del tablero va en su propio <section>.
    cierres = {"crear-generados": '<dialog id="generado-modal"', "fe-editando": "</section>",
               "fe-finalizados": "</section>"}
    for grid, cierre in cierres.items():
        assert f'id="{grid}"' in html
        seg = html.split(f'id="{grid}"')[1].split(cierre)[0]
        tarjetas = re.findall(r'class="generado( generado-final)?"', seg)
        assert 1 <= len(tarjetas) <= 24, (grid, len(tarjetas))


def test_estaticos_versionados_se_guardan_un_ano(app):
    c = app["c"]
    con_v = c.get("/static/style.css?v=123")
    assert con_v.status_code == 200 and con_v.headers["Cache-Control"] == "public, max-age=31536000, immutable"
    sin_v = c.get("/static/style.css")
    assert "immutable" not in (sin_v.headers.get("Cache-Control") or "")
    editor = c.get("/static/editor/geometria.js?v=1")
    assert editor.status_code == 200 and editor.headers["Cache-Control"] == "no-cache"
    html = c.get("/cliente/acme")
    assert html.headers["Cache-Control"] == "no-store, must-revalidate"
