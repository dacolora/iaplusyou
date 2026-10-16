"""PND-300 (decisión 2026-10-13, lote 1): lo que llama al proveedor DENTRO de la petición (o en un hilo de
`trabajos.iniciar`) reserva con un id propio por pedido. Antes `libro.exigir` sin `job_id` no reservaba: todos los
pedidos veían el mismo saldo libre hasta que el primero anotaba su gasto (con US$ 10 pasaban 50 «Armar» seguidos y el
saldo quedaba negativo). La reserva vive mientras corre el pedido y se suelta (o se cobra: el gasto se anota al
precio reservado) al terminar; uno que se cuelga vence solo a los `libro.VIDA_PEDIDO_MIN` minutos."""
from datetime import datetime, timedelta

import pytest
import sqlalchemy as sa

from tests.test_rutas_guiones_pipeline import app as app_pipeline  # noqa: F401 — fixture
from tests.test_rutas_guiones_pipeline import catalogo_vacio  # noqa: F401 — fixture
from tests.test_rutas_organico import app as app_organico  # noqa: F401 — fixture
from tests.test_rutas_referentes import app as app_referentes  # noqa: F401 — fixture
from tests.test_voces_propias import fal, r2  # noqa: F401 — fixtures


@pytest.fixture()
def libro(margen_1_5):
    from cobros import libro as mod
    return mod


def _cobra(libro, cliente="acme", milesimas=0):
    import db
    libro.configurar(cliente, usuario="admin", cobrar=True)
    if milesimas:
        with db.conectar() as con:
            libro.acreditar(con, cliente, "ajuste", milesimas, "ajuste", usuario="admin", detalle="prueba")


def _reservas(cliente="acme"):
    import db
    r = db.reserva_saldo
    with db.conectar() as con:
        return [dict(x._mapping) for x in con.execute(sa.select(r).where(r.c.cliente == cliente)).all()]


def _movimientos(cliente="acme"):
    import db
    m = db.movimiento_saldo
    with db.conectar() as con:
        return [dict(x._mapping) for x in con.execute(sa.select(m).where(m.c.cliente == cliente)
                                                      .order_by(m.c.id)).all()]


# --- el libro ---------------------------------------------------------------------------------

def test_dos_pedidos_seguidos_no_ven_el_mismo_saldo_libre(libro):
    from cobros import SaldoInsuficiente
    _cobra(libro, milesimas=1_000)
    pid = libro.reservar_pedido("acme", 0.5)                     # 0,50 × 1,5 = 750
    assert pid.startswith(libro.PREFIJO_PEDIDO) and libro.disponible("acme") == 250
    with pytest.raises(SaldoInsuficiente):
        libro.reservar_pedido("acme", 0.5)                       # el segundo ya no ve los 1 000
    libro.soltar_pedido("acme", pid)
    assert libro.disponible("acme") == 1_000 and _reservas() == []


def test_en_pedido_cobra_al_precio_reservado_y_suelta_la_reserva(libro):
    import gastos
    _cobra(libro, milesimas=2_000)
    with libro.pedido("acme", 0.5) as pid:
        assert [r["job_id"] for r in _reservas()] == [pid]
        libro.guardar_margen_global(3.0, "admin")                 # el margen cambia mientras corre
        gastos.registrar("acme", "guion_clips", 0.4, "pedido:prueba:1")
    assert _reservas() == []
    cobro, = [m for m in _movimientos() if m["tipo"] == "cobro"]
    assert cobro["milesimas"] == -600 and cobro["job_id"] == pid   # 0,40 × 1,5 (lo visto), no × 3
    assert libro.disponible("acme") == 2_000 - 600


def test_la_reserva_se_suelta_aunque_el_pedido_falle(libro):
    _cobra(libro, milesimas=2_000)
    with pytest.raises(RuntimeError):
        with libro.pedido("acme", 0.5):
            raise RuntimeError("Claude caído")
    assert _reservas() == [] and libro.disponible("acme") == 2_000


def test_dentro_del_pedido_su_propia_reserva_no_frena_al_que_pide_otra_vez(libro):
    """Una función que también pide saldo (organico.redactar dentro de «Escribir con IA») no se frena con la
    reserva de su propio pedido."""
    _cobra(libro, milesimas=750)
    with libro.pedido("acme", 0.5):
        assert libro.exigir("acme", 0.5) == 750                  # sin el pedido, el libre sería 0


def test_un_pedido_colgado_vence_solo(libro):
    import db
    _cobra(libro, milesimas=1_000)
    libro.reservar_pedido("acme", 0.5)
    viejo = (datetime.now() - timedelta(minutes=libro.VIDA_PEDIDO_MIN + 1)).isoformat(timespec="seconds")
    with db.conectar() as con:
        con.execute(db.reserva_saldo.update().values(creada_en=viejo))
    assert libro.disponible("acme") == 1_000                     # ya no cuenta
    assert libro.limpiar_reservas_muertas() == 1 and _reservas() == []


def test_un_proyecto_que_no_cobra_no_reserva_nada(libro):
    with libro.pedido("acme", 5.0) as pid:
        assert pid and _reservas() == []
    libro.soltar_pedido("acme", "acme__otro_trabajo")             # solo suelta reservas de pedidos
    assert _reservas() == []


def test_soltar_no_toca_la_reserva_de_un_trabajo_del_worker(libro):
    import db
    _cobra(libro, milesimas=5_000)
    with db.conectar() as con:
        con.execute(db.tarea.insert().values(tipo="flowplus_video", estado="pendiente", job_id="acme__v1",
                                             payload={}, creada_en=db.ahora(), ejecutar_desde=db.ahora(),
                                             intentos=0, max_intentos=1))
    libro.exigir("acme", 1.0, job_id="acme__v1")
    libro.soltar_pedido("acme", "acme__v1")
    assert [r["job_id"] for r in _reservas()] == ["acme__v1"]


# --- las rutas ----------------------------------------------------------------------------------

def test_leer_referente_reserva_mientras_llama_a_claude_y_la_suelta(app_referentes, monkeypatch, libro):
    from referentes import lectura
    from tests.test_rutas_referentes import _sembrar
    monkeypatch.setattr("proyectos.referentes_copycoders", lambda cliente: True)
    ids = _sembrar()
    vistas = []
    monkeypatch.setattr(lectura, "leer", lambda r: vistas.append(libro.reservado("acme")) or ({}, 1000, 100))
    monkeypatch.setattr(lectura, "medir", lambda url: (1, 1))
    _cobra(libro, milesimas=5_000)
    r = app_referentes["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/leer",
                                 headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200 and vistas and vistas[0] > 0
    assert _reservas() == [] and any(m["tipo"] == "cobro" for m in _movimientos())


def test_adaptar_referente_reserva_mientras_llama_a_claude(app_referentes, monkeypatch, libro):
    from referentes import recrear
    from tests.test_rutas_referentes import _sembrar
    monkeypatch.setattr("proyectos.referentes_copycoders", lambda cliente: True)
    ids = _sembrar()
    vistas = []
    monkeypatch.setattr(recrear, "adaptar", lambda *a, **k: vistas.append(libro.reservado("acme")) or ({"ok": 1}, 10, 10))
    _cobra(libro, milesimas=5_000)
    r = app_referentes["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/adaptar",
                                 json={"producto_id": "espejo_led"}, headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200 and vistas and vistas[0] > 0
    assert _reservas() == []


def _dos_videos(app):
    from tests.test_rutas_guiones_pipeline import BASE, FORM_VIDEO, _confirmado
    gid = _confirmado(app)
    v1 = app["c"].post(f"{BASE}/guiones/{gid}/videos", json=FORM_VIDEO).get_json()["video_id"]
    v2 = app["c"].post(f"{BASE}/guiones/{gid}/videos", json=FORM_VIDEO).get_json()["video_id"]
    return BASE, v1, v2


def test_dos_armar_seguidos_no_pasan_con_saldo_para_uno(app_pipeline, catalogo_vacio, libro):
    """El caso de PND-300: «Armar» abre un hilo por video; el segundo clic ya ve lo que reservó el primero."""
    import gastos
    from guiones import datos
    from guiones.rutas_pipeline import _palabras
    base, v1, v2 = _dos_videos(app_pipeline)
    costo = gastos.estimar("guion_clips", paso="armar", palabras=_palabras(datos.video("acme", v1)))["usd"]
    _cobra(libro, milesimas=libro.precio_milesimas(costo, 1.5) + 1)   # alcanza para uno
    antes = len(app_pipeline["iniciados"])
    assert app_pipeline["c"].post(f"{base}/videos/{v1}/armar", json={}).status_code == 202
    r = app_pipeline["c"].post(f"{base}/videos/{v2}/armar", json={})
    assert r.status_code == 402 and r.get_json()["saldo_insuficiente"] is True
    assert len(app_pipeline["iniciados"]) == antes + 1 and len(_reservas()) == 1
    # El hilo corre (aquí sin Claude: falla) y al terminar suelta la reserva.
    job, fn = app_pipeline["iniciados"][-1]
    assert job == f"guion_armar_{v1}"
    try:
        fn()
    except Exception:  # noqa: BLE001 — sin Claude de verdad el armado falla; lo que importa es la reserva
        pass
    assert _reservas() == []


def test_si_el_hilo_ya_corria_la_reserva_se_suelta(app_pipeline, catalogo_vacio, libro, monkeypatch):
    import trabajos
    base, v1, _v2 = _dos_videos(app_pipeline)
    monkeypatch.setattr(trabajos, "iniciar", lambda *a, **k: False)
    _cobra(libro, milesimas=50_000)
    app_pipeline["c"].post(f"{base}/videos/{v1}/armar", json={})
    assert _reservas() == []


def test_un_error_antes_de_lanzar_suelta_la_reserva(app_pipeline, catalogo_vacio, libro):
    """`datos.empezar` rechaza un video que no está para armarse: no queda una reserva de 10 minutos colgada."""
    from guiones import datos
    base, v1, _v2 = _dos_videos(app_pipeline)
    _cobra(libro, milesimas=50_000)
    datos.empezar("acme", v1, "armando", ("configurando",))
    assert app_pipeline["c"].post(f"{base}/videos/{v1}/armar", json={}).status_code == 409
    assert _reservas() == []


def test_mensaje_del_chat_reserva_hasta_que_responde(app_pipeline, libro):
    from guiones import refinador
    _cobra(libro, milesimas=50_000)
    r = app_pipeline["c"].post("/cliente/acme/guiones/prompts", json={"texto": "Una mujer camina", "tipo": "libre"})
    pid = r.get_json()["prompt"]["id"]
    r = app_pipeline["c"].post(f"/cliente/acme/guiones/prompts/{pid}/mensajes", json={"mensaje": "más luz"})
    assert r.status_code == 202 and len(_reservas()) == 1
    _job, fn = app_pipeline["iniciados"][-1]
    try:
        fn()
    except refinador.ErrorRefinador:
        pass
    except Exception:  # noqa: BLE001 — sin Claude de verdad
        pass
    assert _reservas() == []


def test_escribir_con_ia_reserva_mientras_redacta(app_organico, base_temporal, monkeypatch, libro):
    from tests.test_experimentos_db import _pieza
    pid = _pieza(base_temporal)
    vistas = []
    monkeypatch.setattr(app_organico["dashboard"].organico, "redactar",
                        lambda *a: vistas.append(libro.reservado("acme")) or {})
    _cobra(libro, milesimas=5_000)
    r = app_organico["c"].post("/cliente/acme/organico/redactar",
                               data={"pieza_id": str(pid), "plataformas": ["instagram"]},
                               headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200 and vistas and vistas[0] > 0
    assert _reservas() == []


def test_muestra_de_voz_propia_reserva_mientras_sintetiza(base_temporal, r2, fal, libro, monkeypatch):
    import voces_propias
    from tests.test_voces_propias import _voz
    v = _voz(idioma="es", estrenada=True)
    _cobra(libro, milesimas=50_000)
    original = voces_propias.sintetizar
    vistas = []

    def _sintetizar(*a, **k):
        vistas.append(libro.reservado("acme"))
        return original(*a, **k)
    monkeypatch.setattr(voces_propias, "sintetizar", _sintetizar)
    voces_propias.muestra("acme", f"vp:{v['id']}", "fi")
    assert vistas and vistas[0] > 0 and _reservas() == []
