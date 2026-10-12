"""/admin/cobros tras la auditoría de seguridad del 2026-10-12: «Buscar en Wompi» para una recarga sin acreditar (la
salida segura en vez de una recarga manual, que se sumaba otra vez si después llegaba el evento) y los avisos de plata
a la vista (el servidor no manda correos: sin esto, nadie se enteraba). Wompi falso, base temporal."""
import pytest

from tests.test_recargas_wompi import _envejecer, _pendiente, _recarga, _tx, entorno  # noqa: F401 — fixture

MISMO = {"Sec-Fetch-Site": "same-origin"}


@pytest.fixture()
def http(entorno, monkeypatch, tmp_path):  # noqa: F811
    import bitacora
    import dashboard
    import estado
    monkeypatch.setattr(bitacora, "LOG_FILE", str(tmp_path / "registro.csv"))
    monkeypatch.setattr(estado, "listar_clientes", lambda: ["acme", "otro"])
    dashboard.app.config["TESTING"] = True
    c = dashboard.app.test_client()

    def como(usuario):
        from tests.conftest import USUARIOS_PRUEBA
        with c.session_transaction() as s:
            s.clear()
            if usuario:
                s["usuario"] = usuario
                s["rol"] = USUARIOS_PRUEBA[usuario]["rol"]
                s["cliente"] = USUARIOS_PRUEBA[usuario]["cliente"]
                s["sv"] = 1
        return c
    c.como = como
    return c


def _flashes(c):
    with c.session_transaction() as s:
        return [m for _cat, m in s.get("_flashes", [])]


# --- «Buscar en Wompi» ---------------------------------------------------------------------------------------------

def test_buscar_en_wompi_acredita_la_recarga_que_wompi_tiene_aprobada(http, entorno):  # noqa: F811
    rid, ref = _pendiente(entorno)
    entorno["por_ref"][ref] = [_tx(ref)]
    entorno["txs"]["1292-1602113476-10985"] = _tx(ref)
    c = http.como("admin")
    r = c.post(f"/admin/cobros/recarga/{rid}/buscar", headers=MISMO)
    assert r.status_code == 302 and "#cobros-recargas-wompi" in r.headers["Location"]
    assert _recarga(entorno["db"], rid)["estado"] == "aprobada" and entorno["libro"].saldo("acme") == 50000
    assert any("la acreditamos" in m for m in _flashes(c))
    c.post(f"/admin/cobros/recarga/{rid}/buscar", headers=MISMO)            # otra vez: no suma nada
    assert entorno["libro"].saldo("acme") == 50000


def test_buscar_en_wompi_sin_nada_aprobado_lo_dice_y_no_toca_nada(http, entorno):  # noqa: F811
    rid, _ref = _pendiente(entorno)
    c = http.como("admin")
    c.post(f"/admin/cobros/recarga/{rid}/buscar", headers=MISMO)
    assert _recarga(entorno["db"], rid)["estado"] == "pendiente" and entorno["libro"].saldo("acme") == 0
    assert any("no tiene ninguna transacción aprobada" in m for m in _flashes(c))


def test_buscar_en_wompi_con_wompi_caido_lo_dice(http, entorno):  # noqa: F811
    rid, ref = _pendiente(entorno)
    entorno["por_ref"][ref] = entorno["wompi"].ErrorWompi("No se pudo hablar con Wompi (Timeout)", caida=True)
    c = http.como("admin")
    c.post(f"/admin/cobros/recarga/{rid}/buscar", headers=MISMO)
    assert _recarga(entorno["db"], rid)["estado"] == "pendiente"
    assert any("Wompi no respondió" in m for m in _flashes(c))


def test_buscar_en_wompi_es_solo_para_el_admin_y_del_mismo_sitio(http, entorno):  # noqa: F811
    rid, ref = _pendiente(entorno)
    entorno["por_ref"][ref] = [_tx(ref)]
    entorno["txs"]["1292-1602113476-10985"] = _tx(ref)
    r = http.como("user_acme").post(f"/admin/cobros/recarga/{rid}/buscar", headers=MISMO)
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    r = http.como("admin").post(f"/admin/cobros/recarga/{rid}/buscar", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    assert _recarga(entorno["db"], rid)["estado"] == "pendiente" and entorno["busquedas"] == []


def test_buscar_en_wompi_no_toca_una_de_bold_ni_una_ya_aprobada(http, entorno):  # noqa: F811
    import db
    rid, ref = _pendiente(entorno)
    with db.conectar() as con:
        con.execute(db.recarga.update().where(db.recarga.c.id == rid).values(medio="bold"))
    c = http.como("admin")
    c.post(f"/admin/cobros/recarga/{rid}/buscar", headers=MISMO)
    assert entorno["busquedas"] == [] and any("no se puede buscar" in m for m in _flashes(c))
    assert http.como("admin").post("/admin/cobros/recarga/99999/buscar", headers=MISMO).status_code == 404


def test_la_pagina_lista_las_recargas_de_wompi_sin_acreditar_con_su_boton(http, entorno):  # noqa: F811
    rid, ref = _pendiente(entorno)
    html = http.como("admin").get("/admin/cobros").get_data(as_text=True)
    assert 'id="cobros-recargas-wompi"' in html and ref in html
    assert f"/admin/cobros/recarga/{rid}/buscar" in html


# --- los avisos de plata a la vista --------------------------------------------------------------------------------

def test_la_pagina_muestra_los_avisos_de_plata_y_no_los_demas(http, entorno):  # noqa: F811
    import bitacora
    bitacora.registrar("acme", "admin", "wompi_rescatada", "sin_correo", "Una recarga de <b>acme</b> se acreditó")
    bitacora.registrar("acme", "admin", "error_app", "sin_correo", "un error de la app que no es de plata")
    bitacora.registrar("acme", "motor", "plan_renovado", "sin_correo", "al proyecto, no al admin")
    html = http.como("admin").get("/admin/cobros").get_data(as_text=True)
    assert 'id="cobros-avisos"' in html
    assert "Una recarga de &lt;b&gt;acme&lt;/b&gt; se acreditó" in html                  # escapado
    assert "un error de la app que no es de plata" not in html and "al proyecto, no al admin" not in html


def test_sin_correo_en_el_servidor_la_pagina_lo_advierte(http, entorno, monkeypatch):  # noqa: F811
    import cuentas
    monkeypatch.setattr(cuentas, "smtp_configurado", lambda: False)
    html = http.como("admin").get("/admin/cobros").get_data(as_text=True)
    assert 'id="aviso-sin-correo"' in html
    monkeypatch.setattr(cuentas, "smtp_configurado", lambda: True)
    assert 'id="aviso-sin-correo"' not in http.como("admin").get("/admin/cobros").get_data(as_text=True)


def test_los_avisos_de_plata_leen_solo_la_cola_de_la_bitacora(http, entorno, monkeypatch, tmp_path):  # noqa: F811
    import bitacora
    from cobros import vista
    with open(bitacora.LOG_FILE, "w", encoding="utf-8") as f:
        f.write("fecha,cliente,id,etapa,estado,detalle\n")
        f.write(("2026-01-01T00:00:00,acme,motor,x,y," + "z" * 200 + "\n") * 20000)   # ~4 MB viejos
    bitacora.registrar("acme", "admin", "wompi_no_cuadra", "sin_correo", "lo último")
    assert [a["detalle"] for a in vista.avisos_plata()] == ["lo último"]
