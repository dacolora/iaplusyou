"""La pantalla de los ganchos (spec 2026-10-09 §4.1, §4.3, §5, §6 y §7): la ruta que pide la tanda y el detalle que
la muestra. Nada se genera: la tarea de preparar solo queda en la cola."""
import re

import pytest
import sqlalchemy as sa
from sqlalchemy import event

import db
import proyectos
import trabajos
from tests.test_rutas_configuracion import app  # noqa: F401  (fixture)
from tests.test_tw_mejorar import COPY_NUEVO, GANCHOS, respuesta
from triple_whale import datos, mejorar
from triple_whale import ganchos as ganchos_tw


@pytest.fixture(autouse=True)
def _proyecto_aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))


def _analisis(cliente="acme", lista_ganchos=None, video=True, duracion=20.0, copy_nuevo=True, estado="lista"):
    foto = {"nombre": "Anuncio p1", "ad_id": "p1", "canal": "facebook-ads",
            "creativo": {"tipo": "video", "video_url": "https://files.triplewhale.com/v/p1.mp4" if video else None,
                         "imagen_url": "https://files.triplewhale.com/t/p1.jpg", "duracion_s": duracion,
                         "titulo": "Título", "copy": "Copy"}}
    aid = datos.crear_analisis(cliente, None, "facebook-ads", "p1", "2026-09-01", "2026-09-30", "USD", foto)
    cambios = {"ganchos": GANCHOS if lista_ganchos is None else lista_ganchos}
    if copy_nuevo:
        cambios["copy_nuevo"] = COPY_NUEVO
    datos.actualizar_analisis(aid, estado=estado, usd=0.08,
                              resultado=mejorar.parsear(respuesta(**cambios), "datos", duracion_s=duracion),
                              medios={"visual": "fotogramas", "fotogramas": 6, "copy": True})
    return aid


def _detalle(app, aid):  # noqa: F811
    return app["c"].get(f"/cliente/acme/triple-whale/analisis/{aid}").data.decode()


def _probar(app, aid, precio="1.008", json=True, **headers):  # noqa: F811
    h = dict(headers)
    if json:
        h["Accept"] = "application/json"
    return app["c"].post(f"/cliente/acme/triple-whale/analisis/{aid}/ganchos", data={"precio_visto": precio}, headers=h)


def _preparaciones():
    with db.conectar() as con:
        return [dict(f._mapping) for f in con.execute(
            sa.select(db.tarea).where(db.tarea.c.tipo == "tw_ganchos_preparar"))]


def _generables(aid):
    return ganchos_tw.ganchos_generables(datos.analisis_anuncio("acme", aid)["resultado"])


def _cobra(milesimas=0):
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    if milesimas:
        with db.conectar() as con:
            libro.acreditar(con, "acme", "ajuste", milesimas, "ajuste", usuario="admin", detalle="prueba")
    return libro


# --------------------------------------------------------------------------------------------------- detalle ---

def test_el_detalle_muestra_copy_ganchos_y_el_boton_con_su_precio(app):  # noqa: F811
    aid = _analisis()
    html = _detalle(app, aid)
    assert "Copy nuevo para Meta" in html and "Descanso para tus pies" in html
    assert html.index("Copy nuevo para Meta") < html.index("Versión mejorada")
    assert html.count('onclick="navigator.clipboard && navigator.clipboard.writeText(this.dataset.copiar)"') == 2
    assert "Ganchos nuevos (primeros 3 s)" in html and "«¿Te duelen los pies al final del día?»" in html
    assert "Slow push-in on a tired foot" in html                                 # el prompt, en un <details>
    assert "Probar los 3 ganchos · US$ 1,01" in html and "data-tw-ganchos" in html
    assert "¿Generar 3 clips de 3 s con Kling y armar sus videos? Costo: US$ 1,01" in html
    assert re.search(r'name="precio_visto" value="1\.008"', html)
    assert f'action="/cliente/acme/triple-whale/analisis/{aid}/ganchos"' in html
    assert "<script" not in html


def test_un_gancho_con_cifras_no_se_genera_ni_entra_al_precio(app):  # noqa: F811
    lista = [GANCHOS[0], dict(GANCHOS[1], texto="50 % menos dolor"), GANCHOS[2]]
    aid = _analisis(lista_ganchos=lista)
    html = _detalle(app, aid)
    assert "No se genera: cita cifras que no están en los datos (50 %)." in html
    assert "Probar los 2 ganchos · US$ 0,67" in html
    r = _probar(app, aid, precio="0.672")
    assert r.status_code == 200 and r.get_json()["ok"]
    assert [f["n"] for f in datos.ganchos_de_analisis("acme", aid)] == [1, 3]


def test_un_analisis_viejo_sin_ganchos_lo_dice_y_no_ofrece_nada(app):  # noqa: F811
    aid = _analisis()
    datos.actualizar_analisis(aid, resultado={"frase": "Pierde porque arranca con el logo."})
    html = _detalle(app, aid)
    assert "Este análisis es de antes de los ganchos." in html and "data-tw-ganchos" not in html
    assert "Copy nuevo para Meta" not in html
    r = _probar(app, aid)
    assert r.status_code == 409 and r.get_json()["mensaje"] == "Este análisis es de antes de los ganchos."


@pytest.mark.parametrize("kw, motivo", [({"video": False}, "Sin video que se pueda bajar"),
                                         ({"duracion": 4.0}, "El video es muy corto")])
def test_sin_video_o_con_video_corto_dice_por_que_y_no_cobra(app, kw, motivo):  # noqa: F811
    aid = _analisis(**kw)
    html = _detalle(app, aid)
    assert motivo in html and 'name="precio_visto"' not in html
    r = _probar(app, aid)
    assert r.status_code == 409 and motivo in r.get_json()["mensaje"]
    assert datos.ganchos_de_analisis("acme", aid) == [] and _preparaciones() == []


def test_el_detalle_muestra_cada_variante_segun_su_estado(app):  # noqa: F811
    aid = _analisis()
    f1, f2, f3 = datos.crear_tanda("acme", aid, _generables(aid), pedido_por="admin")
    assert datos.mover(f1["id"], "preparando", "lista", cf_id="cf_x", edicion_id=5,
                       url_final="https://r2.test/final.mp4")
    assert datos.mover(f2["id"], "preparando", "error", error="Kling: contenido sensible")
    trabajos.encolar("acme__cf_y__creative_flow", "flowplus_video", {"cliente": "acme", "cf_id": "cf_y"},
                     cliente="acme", max_intentos=1)
    assert datos.mover(f3["id"], "preparando", "generando", cf_id="cf_y", job_id="acme__cf_y__creative_flow")
    html = _detalle(app, aid)
    assert '<video controls preload="none" data-precarga src="https://r2.test/final.mp4"' in html
    assert f"CV{f1['id']}" in html and f"CV{f3['id']}" in html and f'data-copiar="CV{f1["id"]}"' in html
    assert "/cliente/acme/ediciones/5" in html and "#creativeflowplus?cf=cf_x" in html
    assert 'href="https://r2.test/final.mp4" download' in html
    assert "Kling: contenido sensible" in html
    assert f'id="tw-gancho-{f3["id"]}" data-poll-job="acme__cf_y__creative_flow" data-poll-al-terminar="evento"' in html
    assert "Generando el clip" in html and "Pon este código en el nombre del anuncio en Meta" in html
    assert "Hay una tanda en curso" in html and 'name="precio_visto"' not in html      # sin botón mientras vive
    assert "data-tw-ganchos-esperan" not in html and "<script" not in html


def test_una_variante_viva_sin_trabajo_vivo_no_pinta_barra_y_pide_esperar(app):  # noqa: F811
    """Ruling 4: una barra sobre un trabajo ya terminado avisaría al instante y la pestaña pediría el detalle en
    bucle. Sin trabajo vivo (el clip terminó y el vigilante todavía no pasó) va el estado sin barra y el marcador."""
    aid = _analisis()
    f1, _f2, _f3 = datos.crear_tanda("acme", aid, _generables(aid))
    assert datos.mover(f1["id"], "preparando", "generando", cf_id="cf_z", job_id="acme__cf_z__creative_flow")
    html = _detalle(app, aid)
    assert "data-poll-job" not in html and "data-tw-ganchos-esperan" in html and "Generando el clip" in html


def test_el_detalle_lee_las_variantes_en_una_consulta_y_resume_las_tandas_viejas(app):  # noqa: F811
    aid = _analisis()
    for _ in range(2):
        for f in datos.crear_tanda("acme", aid, _generables(aid)):
            datos.mover(f["id"], "preparando", "lista", cf_id="cf", edicion_id=1, url_final="https://r2.test/x.mp4")
    vistas = []
    contar = lambda conn, cursor, statement, *a: vistas.append(statement)  # noqa: E731
    event.listen(sa.engine.Engine, "before_cursor_execute", contar)
    try:
        html = _detalle(app, aid)
    finally:
        event.remove(sa.engine.Engine, "before_cursor_execute", contar)
    assert sum(1 for s in vistas if "tw_gancho" in s) == 1
    assert "Antes: 1 tanda · ver" in html and html.count("<video") == 3


# ------------------------------------------------------------------------------------------------------ ruta ---

def test_probar_crea_la_tanda_y_encola_la_preparacion_una_vez(app):  # noqa: F811
    aid = _analisis()
    r = _probar(app, aid)
    assert r.status_code == 200 and r.get_json() == {"ok": True, "mensaje": "Generando 3 ganchos…"}
    filas = datos.ganchos_de_analisis("acme", aid)
    job = f"acme__tw_ganchos_{aid}_t1"
    assert [(f["tanda"], f["n"], f["estado"]) for f in filas] == [(1, 1, "preparando"), (1, 2, "preparando"),
                                                                   (1, 3, "preparando")]
    assert {f["job_id"] for f in filas} == {job} and {f["pedido_por"] for f in filas} == {"admin"}
    assert filas[0]["texto"] == GANCHOS[0]["texto"] and filas[0]["prompt"] == GANCHOS[0]["prompt"]
    [t] = _preparaciones()
    assert t["job_id"] == job and t["max_intentos"] == 1 and t["prioridad"] == 3 and t["cliente"] == "acme"
    assert t["payload"] == {"cliente": "acme", "analisis_id": aid, "tanda": 1}
    r = _probar(app, aid)                                            # segundo clic: tanda viva, nada nuevo
    assert r.status_code == 409 and "Hay una tanda en curso" in r.get_json()["mensaje"]
    assert len(_preparaciones()) == 1 and len(datos.ganchos_de_analisis("acme", aid)) == 3


def test_probar_por_formulario_vuelve_a_la_pestana(app):  # noqa: F811
    aid = _analisis()
    r = _probar(app, aid, json=False)
    assert r.status_code == 302 and r.headers["Location"].endswith("#triplewhale")
    assert len(_preparaciones()) == 1


def test_probar_rechaza_otro_origen_otro_proyecto_e_ids_raros(app):  # noqa: F811
    aid = _analisis()
    assert _probar(app, aid, **{"Sec-Fetch-Site": "cross-site"}).status_code == 403
    ajeno = _analisis(cliente="otro")
    assert _probar(app, ajeno).status_code == 404
    assert app["c"].post("/cliente/acme/triple-whale/analisis/99999999999999999999/ganchos").status_code == 404
    assert datos.ganchos_de_analisis("otro", ajeno) == [] and _preparaciones() == []


@pytest.mark.parametrize("precio", ["0.50", "", "abc", "1e9"])
def test_si_el_precio_cambio_no_crea_ni_encola_nada(app, precio):  # noqa: F811
    aid = _analisis()
    r = _probar(app, aid, precio=precio)
    assert r.status_code == 409 and r.get_json()["mensaje"].startswith("El precio cambió: ahora es US$ 1,01.")
    assert datos.ganchos_de_analisis("acme", aid) == [] and _preparaciones() == []


def test_sin_saldo_no_guarda_nada_y_el_fetch_recibe_402(app):  # noqa: F811
    aid = _analisis()
    _cobra()
    visto = re.search(r'name="precio_visto" value="([^"]+)"', _detalle(app, aid)).group(1)  # el precio con margen
    r = _probar(app, aid, precio=visto)
    assert r.status_code == 402 and r.get_json()["saldo_insuficiente"] is True
    assert datos.ganchos_de_analisis("acme", aid) == [] and _preparaciones() == []


def test_con_saldo_pide_el_total_y_no_reserva_hasta_lanzar_cada_clip(app):  # noqa: F811
    aid = _analisis()
    _cobra(milesimas=5000)
    visto = re.search(r'name="precio_visto" value="([^"]+)"', _detalle(app, aid)).group(1)
    assert _probar(app, aid, precio=visto).get_json()["ok"]
    with db.conectar() as con:
        assert con.execute(sa.select(sa.func.count()).select_from(db.reserva_saldo)).scalar() == 0
    assert len(_preparaciones()) == 1


def test_una_tanda_que_se_cuela_entre_la_revision_y_el_insert_es_409(app, monkeypatch):  # noqa: F811
    aid = _analisis()

    def _viva(*a, **k):
        raise datos.TandaViva()
    monkeypatch.setattr(datos, "crear_tanda", _viva)
    r = _probar(app, aid)
    assert r.status_code == 409 and "Ya hay una tanda de ganchos en curso" in r.get_json()["mensaje"]
    assert _preparaciones() == []


def test_si_no_se_puede_encolar_la_tanda_queda_en_error_y_el_boton_vuelve(app, monkeypatch):  # noqa: F811
    from tareas import triple_whale as tareas_tw
    aid = _analisis()
    monkeypatch.setattr(tareas_tw, "encolar_preparar", lambda *a, **k: False)
    r = _probar(app, aid)
    assert r.status_code == 409 and "vuelve a intentarlo" in r.get_json()["mensaje"]
    filas = datos.ganchos_de_analisis("acme", aid)
    assert {f["estado"] for f in filas} == {"error"} and filas[0]["error"] == "No se pudo poner la preparación en la cola."
    assert "Probar los 3 ganchos" in _detalle(app, aid)


def test_la_hoja_tiene_las_reglas_de_los_ganchos():
    with open("static/style.css", encoding="utf-8") as f:
        css = f.read()
    assert ".tw-variantes { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 12rem), 1fr))" in css
    assert ".tw-copy-texto { margin: 0; white-space: pre-line; }" in css
