"""Rutas del pipeline de Flow Plus: panel como fragmento, acciones JSON, aislamiento."""
import pytest

from tests.fixtures_guiones import GUION_CRUDO, LINEAS, TEXTO, fake

BASE = "/cliente/acme/guiones"


@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import proyectos
    import trabajos
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    for c in ("acme", "otro"):
        (tmp_path / "clientes" / c).mkdir(parents=True)
    iniciados = []
    monkeypatch.setattr(trabajos, "iniciar",
                        lambda job_id, fn, duracion_estimada=60, etapas=None: iniciados.append((job_id, fn)) or True)
    dashboard.app.config["TESTING"] = True
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "admin"; s["rol"] = "admin"; s["cliente"] = None
    return {"c": c, "iniciados": iniciados}


def _leido(app, crudo=GUION_CRUDO):
    from guiones import datos, lectura
    r = app["c"].post(f"{BASE}/lotes", json={"texto": TEXTO})
    assert r.status_code == 202
    lid = r.get_json()["lote_id"]
    lectura.leer_lote(lid, llamar=fake({"guiones": [crudo]}))
    return datos.lotes("acme")[0]["guiones"][0]["id"]


def test_crear_lote_lanza_la_lectura(app):
    r = app["c"].post(f"{BASE}/lotes", json={"texto": TEXTO})
    assert r.status_code == 202
    assert app["iniciados"][0][0] == f"guion_leer_{r.get_json()['lote_id']}"
    assert app["c"].post(f"{BASE}/lotes", json={"texto": "  "}).status_code == 400


def test_panel_muestra_leyendo_y_pide_sondeo(app):
    app["c"].post(f"{BASE}/lotes", json={"texto": TEXTO})
    html = app["c"].get(f"{BASE}/panel").get_data(as_text=True)
    assert "Leyendo…" in html and 'data-trabajando="1"' in html


def test_panel_escapa_la_lectura(app):
    gid = _leido(app, dict(GUION_CRUDO, lineas=LINEAS + ["<script>alert(1)</script>"]))
    html = app["c"].get(f"{BASE}/panel?guion={gid}").get_data(as_text=True)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html and "<script>alert(1)" not in html
    assert "no aparece tal cual en el guion" in html
    assert 'data-trabajando="0"' in html


def test_editar_confirmar_y_duplicar(app):
    from guiones import datos
    gid = _leido(app)
    r = app["c"].post(f"{BASE}/guiones/{gid}/lectura", json={"titulo": "Otro", "lineas": "\n".join(LINEAS[:3]),
                                                             "hooks": "", "personajes": "", "notas_estilo": ""})
    assert r.status_code == 200 and len(datos.guion("acme", gid)["lectura"]["lineas"]) == 3
    assert app["c"].post(f"{BASE}/guiones/{gid}/confirmar", json={}).status_code == 200
    assert app["c"].post(f"{BASE}/guiones/{gid}/lectura", json={"lineas": "x"}).status_code == 409
    r = app["c"].post(f"{BASE}/guiones/{gid}/duplicar", json={})
    assert r.status_code == 201 and datos.guion("acme", r.get_json()["guion_id"])["estado"] == "leido"


def test_reintentar_lote(app):
    from guiones import datos
    lid = app["c"].post(f"{BASE}/lotes", json={"texto": TEXTO}).get_json()["lote_id"]
    datos.fallar_lote(lid, "falló")
    assert app["c"].post(f"{BASE}/lotes/{lid}/reintentar", json={}).status_code == 202
    assert app["iniciados"][-1][0] == f"guion_leer_{lid}"


def test_otro_proyecto_no_ve_ni_toca(app):
    from guiones import datos
    gid = _leido(app)
    assert datos.guion("otro", gid) is None
    r = app["c"].post(f"/cliente/otro/guiones/guiones/{gid}/confirmar", json={})
    assert r.status_code == 404
    html = app["c"].get(f"/cliente/otro/guiones/panel?guion={gid}").get_data(as_text=True)
    assert 'data-guion=""' in html


def test_post_de_otro_sitio_se_rechaza(app):
    r = app["c"].post(f"{BASE}/lotes", json={"texto": TEXTO}, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    assert app["c"].post(f"{BASE}/lotes", data="no json", content_type="text/plain").status_code == 400
