"""PND-175: detalles de texto y de código de Cobros. El rango del margen con el separador de quien lee, «se acredita
sola en unos minutos» solo los primeros minutos, las ramas que fallan cerrado dejan su línea en el log y el CSV del
gasto no responde 500 si no se sabe si el proyecto cobra (el 402 por XMLHttpRequest y el global de cobros.js se
prueban en tests/js/cobros.test.mjs)."""
import logging

import pytest

AHORA = "2026-10-08T12:00:00"
HACE_20_MIN = "2026-10-08T11:40:00"
HACE_2_HORAS = "2026-10-08T10:00:00"


@pytest.fixture()
def libro(base_temporal, monkeypatch, tmp_path):
    import proyectos
    from cobros import libro as mod
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    monkeypatch.delenv("BOLD_LLAVE_IDENTIDAD", raising=False)
    return mod


@pytest.fixture()
def pagina(libro, monkeypatch):
    import dashboard
    import referencias_flowplus
    monkeypatch.setattr(referencias_flowplus, "listar", lambda c: [])
    dashboard.app.config["TESTING"] = True

    def cliente_como(usuario="user_acme", rol="cliente", proyecto="acme"):
        c = dashboard.app.test_client()
        with c.session_transaction() as s:
            s["usuario"] = usuario; s["rol"] = rol; s["cliente"] = proyecto
        return c
    return cliente_como


def _recarga(creada_en, medio="wompi", milesimas=20_000, ref="r1"):
    import db
    with db.conectar() as con:
        return int(con.execute(db.recarga.insert().values(
            cliente="acme", creada_en=creada_en, medio=medio, estado="pendiente", milesimas=milesimas,
            referencia=ref, usuario="admin")).inserted_primary_key[0])


# --- el rango del margen -----------------------------------------------------------------------------------

def test_el_rango_del_margen_va_con_el_separador_de_quien_lee(libro):
    import dashboard
    import idiomas
    with dashboard.app.test_request_context("/"):
        with pytest.raises(ValueError) as e:
            libro._validar_margen(6)
        assert str(e.value) == "El margen va de 1,00 a 5,00."
        with idiomas.en_idioma("en"), pytest.raises(ValueError) as e:
            libro._validar_margen(0.5)
        assert str(e.value) == "The markup ranges from 1.00 to 5.00."
    with pytest.raises(ValueError, match="1,00 a 5,00"):                   # también fuera de una petición
        libro.configurar("acme", usuario="admin", cobrar=True, margen=9)


# --- «se acredita sola» solo los primeros minutos -----------------------------------------------------------

def test_la_recarga_pendiente_solo_dice_que_se_acredita_sola_la_primera_hora(libro):
    import alertas
    import db
    libro.configurar("acme", usuario="admin", cobrar=True, margen=1.5)
    with db.conectar() as con:
        libro.acreditar(con, "acme", "ajuste", 50_000, "ajuste", usuario="admin", detalle="prueba")
    nueva = _recarga(HACE_20_MIN, ref="r_nueva")
    vieja = _recarga(HACE_2_HORAS, medio="bold", ref="r_vieja")
    por_id = {a["entidad"]: a for a in alertas._fuente_cobros("acme", AHORA)}
    assert "se acredita sola en unos minutos" in por_id[nueva]["detalle"] and "Wompi" in por_id[nueva]["detalle"]
    assert "se acredita sola" not in por_id[vieja]["detalle"]
    assert "más de una hora" in por_id[vieja]["detalle"] and "Bold" in por_id[vieja]["detalle"]
    assert "20,00" in por_id[vieja]["detalle"]
    # La huella no sigue al texto: el descarte de la de 20 min vale cuando ya pasó la hora.
    despues = {a["entidad"]: a for a in alertas._fuente_cobros("acme", "2026-10-08T13:00:00")}
    assert "más de una hora" in despues[nueva]["detalle"] and despues[nueva]["huella"] == por_id[nueva]["huella"]


def test_la_recarga_de_mas_de_una_hora_tambien_sale_en_ingles(libro):
    import alertas
    import dashboard
    import idiomas
    import db
    libro.configurar("acme", usuario="admin", cobrar=True, margen=1.5)
    with db.conectar() as con:
        libro.acreditar(con, "acme", "ajuste", 50_000, "ajuste", usuario="admin", detalle="prueba")
    _recarga(HACE_2_HORAS)
    with dashboard.app.test_request_context("/"), idiomas.en_idioma("en"):
        a, = alertas._fuente_cobros("acme", AHORA)
    assert "more than an hour" in a["detalle"] and "Wompi" in a["detalle"]


# --- falla cerrado con su línea en el log ------------------------------------------------------------------

def test_puede_ver_costo_cerrado_deja_su_linea_sin_el_texto_del_error(libro, monkeypatch, caplog):
    from cobros import vista

    def roto(cliente):
        raise RuntimeError("token=secreto123")
    monkeypatch.setattr(vista.libro, "cuenta", roto)
    with caplog.at_level(logging.WARNING, logger="cobros.vista"):
        assert vista.puede_ver_costo("acme", es_admin=False) is False
    lineas = [r.getMessage() for r in caplog.records if r.name == "cobros.vista"]
    assert any("acme" in l and "RuntimeError" in l for l in lineas), lineas
    assert not any("secreto123" in l for l in lineas)
    assert vista.puede_ver_costo("acme", es_admin=True) is True               # el admin no pasa por ahí


def test_el_filtro_cobrado_y_ver_cobrado_dejan_su_linea_al_fallar_cerrado(libro, monkeypatch, capsys):
    import dashboard
    from cobros import vista
    from flask import g, session

    def roto(*a, **k):
        raise RuntimeError("se cayó")
    monkeypatch.setattr(vista, "visto", roto)
    monkeypatch.setattr(vista, "ver_cobrado_aqui", roto)
    monkeypatch.setattr(vista, "puede_ver_costo", lambda cliente, es_admin: False)
    with dashboard.app.test_request_context("/cliente/acme"):
        g.cliente_precio = "acme"
        session["rol"] = "cliente"
        assert dashboard._filtro_cobrado({}, 1.0, "video:1") is None
        assert dashboard._ver_cobrado() is True
    salida = capsys.readouterr().out
    assert salida.count("[aviso] cobros:") == 2 and "RuntimeError" in salida


# --- el CSV del gasto sin saber si el proyecto cobra --------------------------------------------------------

def test_el_csv_del_gasto_no_da_500_si_no_se_sabe_si_el_proyecto_cobra(libro, pagina, monkeypatch):
    import gastos
    from cobros import vista
    libro.configurar("acme", usuario="admin", cobrar=True, margen=1.5)
    gastos.registrar("acme", "video", 1.0, "video:cf1:t1")

    def roto(*a, **k):
        raise RuntimeError("base ocupada")
    monkeypatch.setattr(vista, "gasto_para", roto)
    monkeypatch.setattr(vista, "cobra", roto)                                # tampoco se sabe si cobra
    for ruta in ("/cliente/acme/gasto/mes.csv", "/cliente/acme/gasto/todo.csv"):
        r = pagina().get(ruta)
        assert r.status_code == 302 and "/cliente/acme" in r.headers["Location"], ruta
        assert "1,0000" not in r.get_data(as_text=True)                      # ninguna cifra, menos el costo
    c = pagina()
    c.get("/cliente/acme/gasto/todo.csv")
    with c.session_transaction() as s:
        flashes = [m for _, m in s.get("_flashes", [])]
    assert any("No pudimos leer el gasto" in m for m in flashes)
    # El admin sí puede ver el costo: baja su CSV aunque la cuenta no se lea.
    admin = pagina("admin", "admin", None).get("/cliente/acme/gasto/todo.csv")
    assert admin.status_code == 200 and "1,0000" in admin.get_data(as_text=True)
