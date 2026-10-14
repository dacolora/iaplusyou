"""Lo usado antes de cobrar, uno por uno en Configuración › Gasto (pedido de Daniel, 2026-10-13: «en Spend,
History solo saca lo último; la idea es que también vea todos los 900 que ha gastado»).

El pospago de happyflops (2026-10-12) cargó lo usado antes como UN ajuste de −US$ 948,63 en el libro. Lo
cobrado que ve el cliente sale de los movimientos atados a un gasto, así que esos 1 164 gastos no aparecían en
su gasto: ni en el historial, ni en el total, ni por tipo, ni en el CSV. `libro.detallar_uso_previo` anota en
el ajuste qué gastos paga y a qué margen, y la vista los cuenta como cobrados a ese margen. El saldo no cambia."""
import re

import pytest
import sqlalchemy as sa


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


def _seccion(html, ident):
    m = re.search(r'<section class="config-apartado" id="%s".*?</section>' % re.escape(ident), html, re.S)
    assert m, f"no está la sección {ident}"
    return m.group(0)


def _fechar(gasto_id, creado_en):
    import db
    with db.conectar() as con:
        con.execute(db.gasto.update().where(db.gasto.c.id == gasto_id).values(creado_en=creado_en))


def _historia(libro, cliente="acme"):
    """Como happyflops: tres gastos sin cobrar, el pospago ×3 con lo usado antes como un ajuste y,
    después, un cobro nuevo. Devuelve (ids viejos, id del ajuste, id del gasto nuevo)."""
    import db
    import gastos
    viejos = [gastos.registrar(cliente, "video", 0.8, f"video:cf{i}:t{i}", detalle=f"wan · {i}")
              for i in (1, 2)]
    viejos.append(gastos.registrar(cliente, "imagen", 0.05, "imagen:cf3:t3"))
    for i, gid in enumerate(viejos):
        _fechar(gid, f"2026-09-0{i + 1}T10:00:00")
    libro.configurar(cliente, usuario="admin", cobrar=True, margen=3.0, pospago=True)
    with db.conectar() as con:                                       # (0,80 + 0,80 + 0,05) × 3 = 4,95
        ajuste = libro.acreditar(con, cliente, "ajuste", -4_950, "ajuste", usuario="admin",
                                 detalle="Creatv usage before postpaid billing")
        con.execute(db.movimiento_saldo.update().where(db.movimiento_saldo.c.id == ajuste)
                    .values(creado_en="2026-10-12T18:32:59"))
    nuevo = gastos.registrar(cliente, "guion", 0.1, "guion:cf1:t4")  # cobro −300
    _fechar(nuevo, "2026-10-12T21:00:00")
    return viejos, ajuste, nuevo


# --- el libro anota qué paga el ajuste ------------------------------------------------------

def test_detallar_anota_los_gastos_que_paga_el_ajuste_y_no_toca_el_saldo(libro):
    import db
    viejos, ajuste, _nuevo = _historia(libro)
    saldo = libro.saldo("acme")
    uso = libro.detallar_uso_previo("acme", ajuste, 3)
    assert uso == {"desde_gasto": 0, "hasta_gasto": max(viejos), "margen": 3.0, "n": 3, "costo": 1.65}
    assert libro.saldo("acme") == saldo == -4_950 - 300
    with db.conectar() as con:
        extra = con.execute(sa.select(db.movimiento_saldo.c.extra)
                            .where(db.movimiento_saldo.c.id == ajuste)).scalar()
    assert extra["uso_previo"] == uso
    assert libro.detallar_uso_previo("acme", ajuste, 3.0) == uso           # dos veces, lo mismo


def test_detallar_no_escribe_si_el_ajuste_no_cuadra_con_el_margen(libro):
    import db
    _viejos, ajuste, _nuevo = _historia(libro)
    with pytest.raises(ValueError, match="no cuadra"):
        libro.detallar_uso_previo("acme", ajuste, 2)                       # 1,65 × 2 = 3,30 ≠ 4,95
    with db.conectar() as con:
        extra = con.execute(sa.select(db.movimiento_saldo.c.extra)
                            .where(db.movimiento_saldo.c.id == ajuste)).scalar()
    assert "uso_previo" not in (extra or {})


def test_detallar_solo_un_ajuste_negativo_del_mismo_proyecto(libro):
    import db
    _viejos, ajuste, nuevo = _historia(libro)
    libro.configurar("otro", usuario="admin", cobrar=True)
    with db.conectar() as con:
        recarga = libro.acreditar(con, "acme", "recarga", 1_000, "recarga_manual", usuario="admin")
        cobro = con.execute(sa.select(db.movimiento_saldo.c.id)
                            .where(db.movimiento_saldo.c.gasto_id == nuevo)).scalar()
    for cliente, mov in (("otro", ajuste), ("acme", recarga), ("acme", cobro), ("acme", 9_999)):
        with pytest.raises(ValueError, match="no es un ajuste negativo"):
            libro.detallar_uso_previo(cliente, mov, 3)
    libro.detallar_uso_previo("acme", ajuste, 3)
    with pytest.raises(ValueError, match="ya"):
        libro.detallar_uso_previo("acme", ajuste, 1.5)                     # ya detallado con otro margen


# --- lo que ve el cliente ---------------------------------------------------------------------

def test_sin_detallar_el_cliente_solo_ve_lo_cobrado_despues(libro):
    from cobros import vista
    _historia(libro)
    assert [f["usd"] for f in vista.historial_cobrado("acme")] == [0.3]
    assert vista.resumen_total_cobrado("acme")["total"] == 0.3


def test_detallado_el_cliente_ve_todo_lo_usado_a_su_margen(libro):
    from cobros import vista
    viejos, ajuste, nuevo = _historia(libro)
    libro.detallar_uso_previo("acme", ajuste, 3)
    h = vista.historial_cobrado("acme")
    assert [(f["id"], f["usd"]) for f in h] == [(nuevo, 0.3), (viejos[2], 0.15), (viejos[1], 2.4), (viejos[0], 2.4)]
    assert h[-1]["detalle"] == "wan · 1" and h[-1]["tipo"] == "video"
    assert [f["id"] for f in vista.historial_cobrado("acme", limite=2, desplazamiento=1)] == [viejos[2], viejos[1]]
    t = vista.resumen_total_cobrado("acme")
    assert t == {"total": 5.25, "n": 4, "desde": "2026-09-01T10:00:00"}   # = lo que debe: 4,95 + 0,30
    assert -0.01 < t["total"] + libro.saldo("acme") / 1000 < 0.01
    r = vista.resumen_todo_cobrado("acme")
    assert r["por_tipo"] == {"video": {"usd": 4.8, "n": 2}, "imagen": {"usd": 0.15, "n": 1},
                             "guion": {"usd": 0.3, "n": 1}}
    assert vista.por_mes_cobrado("acme") == {"2026-09": {"usd": 4.95, "n": 3}, "2026-10": {"usd": 0.3, "n": 1}}
    assert vista.total_entre_cobrado("acme", "2026-09-01T00:00:00", "2026-09-02T00:00:00") == {"usd": 2.4, "n": 1}
    assert vista.cobrado_por_gasto("acme", viejos + [nuevo]) == {viejos[0]: 2.4, viejos[1]: 2.4, viejos[2]: 0.15,
                                                                 nuevo: 0.3}
    assert vista.cobrado_clave("acme", "video:cf1") == 2.4                 # la tarjeta de la pieza vieja
    assert vista.cobrado_donde("acme", prefijos=("video:",)) == 4.8


def test_un_gasto_sin_cobro_posterior_al_ajuste_no_entra(libro):
    """Lo que el ajuste paga es lo que había hasta su fecha; un gasto de después que quedó sin cobro (con
    «Cobrar» apagado un rato) no se cuela como cobrado."""
    import gastos
    from cobros import vista
    _viejos, ajuste, _nuevo = _historia(libro)
    libro.detallar_uso_previo("acme", ajuste, 3)
    libro.configurar("acme", usuario="admin", cobrar=False)
    tarde = gastos.registrar("acme", "video", 1.0, "video:cf9:t9")
    libro.configurar("acme", usuario="admin", cobrar=True)
    assert tarde not in [f["id"] for f in vista.historial_cobrado("acme")]
    assert vista.resumen_total_cobrado("acme")["total"] == 5.25


def test_lo_ya_cobrado_no_se_cuenta_dos_veces_y_dos_ajustes_no_se_pisan(libro):
    """Un gasto con su cobro dentro del rango del ajuste ya está en el libro: no se suma otra vez. Un segundo
    ajuste detallado paga solo lo que vino después del primero."""
    import db
    import gastos
    from cobros import vista
    a = gastos.registrar("acme", "video", 1.0, "video:cfa:t1")                 # antes de cobrar
    libro.configurar("acme", usuario="admin", cobrar=True, margen=3.0, pospago=True)
    b = gastos.registrar("acme", "video", 0.5, "video:cfb:t2")                 # cobrado: −1 500
    libro.configurar("acme", usuario="admin", cobrar=False)
    c = gastos.registrar("acme", "imagen", 0.2, "imagen:cfc:t3")               # otro rato sin cobrar
    libro.configurar("acme", usuario="admin", cobrar=True)
    for gid, fecha in ((a, "2026-09-01T10:00:00"), (b, "2026-09-02T10:00:00"), (c, "2026-09-04T10:00:00")):
        _fechar(gid, fecha)
    m = db.movimiento_saldo
    with db.conectar() as con:
        primero = libro.acreditar(con, "acme", "ajuste", -3_000, "ajuste", usuario="admin", detalle="a")
        segundo = libro.acreditar(con, "acme", "ajuste", -600, "ajuste", usuario="admin", detalle="c")
        con.execute(m.update().where(m.c.id == primero).values(creado_en="2026-09-03T10:00:00"))
        con.execute(m.update().where(m.c.id == segundo).values(creado_en="2026-09-05T10:00:00"))
    assert libro.detallar_uso_previo("acme", primero, 3)["n"] == 1             # a; b ya tiene su cobro
    assert libro.detallar_uso_previo("acme", segundo, 3)["desde_gasto"] == b
    assert sorted((f["id"], f["usd"]) for f in vista.historial_cobrado("acme")) == [(a, 3.0), (b, 1.5), (c, 0.6)]
    assert vista.resumen_total_cobrado("acme")["total"] == 5.1 == -libro.saldo("acme") / 1000


def test_otro_proyecto_no_ve_nada_del_detalle(libro):
    """El detalle es del ajuste de ESE proyecto: otro con gastos sin cobro en el mismo rango de ids no los ve
    como cobrados."""
    import gastos
    from cobros import vista
    suelto = gastos.registrar("otro", "video", 1.0, "video:cfx:t1")          # id 1, sin cobro
    viejos, ajuste, _nuevo = _historia(libro)
    assert suelto < max(viejos)
    libro.detallar_uso_previo("acme", ajuste, 3)
    libro.configurar("otro", usuario="admin", cobrar=True)
    assert vista.historial_cobrado("otro") == []
    assert vista.resumen_total_cobrado("otro")["total"] == 0
    gastos.registrar("otro", "video", 1.0, "video:cfy:t2")
    assert [f["usd"] for f in vista.historial_cobrado("otro")] == [2.0]


def test_el_precio_de_cada_fila_redondea_y_no_trunca(libro, pagina):
    """0,70 × 3 en coma flotante es 2,0999999…: la fila dice 2,10, no 2,099."""
    import db
    import gastos
    from cobros import vista
    gid = gastos.registrar("acme", "video", 0.7, "video:cf1:t1")
    _fechar(gid, "2026-09-01T10:00:00")
    libro.configurar("acme", usuario="admin", cobrar=True, margen=3.0, pospago=True)
    with db.conectar() as con:
        ajuste = libro.acreditar(con, "acme", "ajuste", -2_100, "ajuste", usuario="admin", detalle="antes")
    libro.detallar_uso_previo("acme", ajuste, 3)
    assert [f["usd"] for f in vista.historial_cobrado("acme")] == [2.1]
    assert vista.cobrado_por_gasto("acme", [gid]) == {gid: 2.1}
    assert "2,1000" in pagina().get("/cliente/acme/gasto/todo.csv").get_data(as_text=True)


def test_la_pantalla_de_gasto_del_cliente_y_el_csv_traen_lo_viejo(libro, pagina):
    _viejos, ajuste, _nuevo = _historia(libro)
    libro.detallar_uso_previo("acme", ajuste, 3)
    html = _seccion(pagina().get("/cliente/acme").get_data(as_text=True), "config-ap-gasto")
    assert "US$ 5,25" in html                                             # «Generación total»
    assert "wan · 1" in html and "US$ 2,40" in html and "US$ 0,80" not in html
    csv_todo = pagina().get("/cliente/acme/gasto/todo.csv").get_data(as_text=True)
    assert csv_todo.count("\n") == 5 and "2,4000" in csv_todo and "0,8000" not in csv_todo
    admin = _seccion(pagina("admin", "admin", None).get("/cliente/acme").get_data(as_text=True), "config-ap-gasto")
    assert "US$ 5,25" in admin and "US$ 0,80" in admin                    # «Cobrado total» y el costo


# --- History entero, sin clics (Daniel 2026-10-13: «la idea es que salga todo») ---------------

def _boton_mas(html):
    m = re.search(r'<button[^>]*data-lista-mas="gasto-filas"[^>]*>', html)
    return m and m.group(0)


def test_history_llega_liviano_y_el_resto_se_pide_solo_de_una_vez(libro, pagina, monkeypatch):
    """La página trae 24 filas (pintar 1 181 le sumaba ~400 KB a cada carga del proyecto); el botón «Ver todo»
    lleva data-auto (base.html lo pulsa al entrar en pantalla) y UN pedido trae todas las filas que faltan."""
    import dashboard
    import gastos
    for i in range(60):
        gastos.registrar("acme", "imagen", 0.01 * (i + 1), f"imagen:cf{i}:t{i}")
    html = pagina().get("/cliente/acme").get_data(as_text=True)
    sec = _seccion(html, "config-ap-gasto")
    tbody = re.search(r'<tbody id="gasto-filas">(.*?)</tbody>', sec, re.S).group(1)
    assert tbody.count("<tr") == 24
    boton = _boton_mas(sec)
    url = re.search(r'data-url="([^"]+)"', boton).group(1).replace("&amp;", "&")
    assert " data-auto" in boton and "todo=1" in url and "desde=24" in url
    assert "'[data-lista-mas][data-auto]'" in html                       # el script que lo pulsa solo
    resto = pagina().get(url).get_data(as_text=True)
    assert resto.count("<tr") == 36 and _boton_mas(resto) is None
    # Sin `todo`, la página siguiente sigue de a 24.
    assert pagina().get("/cliente/acme/gasto/lista?desde=24").get_data(as_text=True).count("<tr") == 24
    monkeypatch.setattr(dashboard, "GASTO_TODO_MAX", 10)                 # el tope corta y deja otro «Ver todo»
    corto = pagina().get(url).get_data(as_text=True)
    assert corto.count("<tr") == 10
    otro = _boton_mas(corto)
    assert " data-auto" in otro and "desde=34" in otro and "todo=1" in otro
