"""PND-339 (decisión 2026-10-15, lote 2): si la tarea que pagó una voz propia falló después (el worker devolvió el
cobro), Mis voces la recuperaba gratis al abrirse (PND-012) y un GET nunca cobra: la voz se usaba sin pagarla. Ahora
se recupera igual (no se pierde) pero queda «pagada y sin cobrar»: no se puede usar hasta «Usar esta voz (se cobra ≈
X)», que pasa por el freno de saldo y le cobra al proyecto lo que fal cobró, una sola vez
(`gastos.registrar_trasladando`). Un proyecto que no cobra sigue como antes."""
import pytest
import sqlalchemy as sa

import db
import gastos
import materiales
import voces_propias as vp
from tests.test_voces_propias import fal, r2  # noqa: F401  (fixtures)

pytestmark = pytest.mark.usefixtures("margen_1_5")

REF = "voz_propia:disenar:t12"


def _cobrar(saldo=10000):
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    if saldo:
        with db.conectar() as con:
            libro.acreditar(con, "acme", "ajuste", saldo, "ajuste", usuario="admin", detalle="prueba")
    return libro


def _voz_pagada_y_fallida():
    """La tarea pagó la voz en fal y falló después: el worker le devolvió el cobro (cobro + reverso)."""
    from cobros import libro
    payload = vp.validar_disenar({"nombre": "Ana", "descripcion": "Mujer cálida, de 30", "idioma": "es"})

    def falla(etapa):
        raise RuntimeError("se cortó después de pagar")
    with libro.en_trabajo(12, "acme__voz_propia"):
        with pytest.raises(RuntimeError):
            vp.crear("acme", payload, ref_sufijo=":t12", reportar=falla)
    libro.revertir_trabajo("acme", "acme__voz_propia", "falló", desde_tarea=12)


def _movimientos(ref):
    g, m = db.gasto, db.movimiento_saldo
    with db.conectar() as con:
        gid = con.execute(sa.select(g.c.id).where(g.c.cliente == "acme", g.c.referencia == ref)).scalar()
        return sorted(r.tipo for r in con.execute(sa.select(m.c.tipo).where(m.c.gasto_id == gid))) if gid else None


def test_el_get_la_recupera_pero_no_se_usa_ni_se_cobra(base_temporal, fal, r2):
    libro = _cobrar()
    _voz_pagada_y_fallida()
    saldo = libro.saldo("acme")
    voz, = vp.listar("acme")
    assert voz["por_cobrar"] == pytest.approx(3.0004) and voz["voice_id"] == "mmx_dis"
    assert vp.resolver("acme", voz["valor"]) is None                       # no se puede usar todavía
    assert vp.listar("acme", usables=True) == []                           # ni aparece en los selectores
    assert libro.saldo("acme") == saldo and _movimientos(f"{REF}:recuperada") is None   # un GET no cobra


def test_usar_esta_voz_la_cobra_una_vez_y_la_libera(base_temporal, fal, r2):
    libro = _cobrar()
    _voz_pagada_y_fallida()
    voz, = vp.listar("acme")
    saldo = libro.saldo("acme")
    vp.cobrar_recuperada("acme", voz["id"])
    assert libro.saldo("acme") == saldo - libro.precio_milesimas(3.0004, 1.5)
    assert _movimientos(f"{REF}:recuperada") == ["cobro"]
    assert gastos.por_referencia("acme", REF)["usd"] == 0                   # el costo pasó a la fila de la entrega
    assert vp.resolver("acme", voz["valor"])["voice_id"] == "mmx_dis" and not vp.listar("acme")[0].get("por_cobrar")
    vp.cobrar_recuperada("acme", voz["id"])                                 # un segundo clic no cobra otra vez
    assert libro.saldo("acme") == saldo - libro.precio_milesimas(3.0004, 1.5)


def test_sin_saldo_no_cobra_ni_la_libera(base_temporal, fal, r2):
    from cobros import SaldoInsuficiente
    libro = _cobrar()
    _voz_pagada_y_fallida()
    voz, = vp.listar("acme")
    with db.conectar() as con:                                              # gastó todo en otra cosa
        libro.acreditar(con, "acme", "ajuste", -libro.saldo("acme"), "ajuste", usuario="admin", detalle="prueba")
    with pytest.raises(SaldoInsuficiente):
        vp.cobrar_recuperada("acme", voz["id"])
    assert vp.resolver("acme", voz["valor"]) is None and _movimientos(f"{REF}:recuperada") is None


def test_un_proyecto_que_no_cobra_la_recupera_y_la_usa_como_antes(base_temporal, fal, r2):
    payload = vp.validar_disenar({"nombre": "Ana", "descripcion": "Mujer cálida, de 30", "idioma": "es"})
    with pytest.raises(RuntimeError):
        vp.crear("acme", payload, ref_sufijo=":t12", reportar=lambda e: (_ for _ in ()).throw(RuntimeError("x")))
    voz, = vp.listar("acme")
    assert not voz.get("por_cobrar") and vp.resolver("acme", voz["valor"])


# --- la pantalla y la ruta ----------------------------------------------------------------------

@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import proyectos
    from tests.test_rutas_experimentos import _cliente_admin
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard)}


def test_mis_voces_la_muestra_con_su_precio_y_la_ruta_la_cobra(app, fal, r2):
    libro = _cobrar()
    _voz_pagada_y_fallida()
    r = app["c"].get("/cliente/acme/audios/voces", headers={"X-Requested-With": "fetch"})
    d = r.get_json()
    assert "Usar esta voz (se cobra ≈" in d["html"] and "pagada y sin cobrar" in d["html"]
    assert d["voces"] == []                                                # nada que elegir todavía
    voz_id = vp.listar("acme")[0]["id"]
    assert f"/audios/voces/{voz_id}/cobrar" in d["html"]
    r = app["c"].post(f"/cliente/acme/audios/voces/{voz_id}/cobrar", headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200 and r.get_json()["ok"] and _movimientos(f"{REF}:recuperada") == ["cobro"]
    assert "Usar esta voz" not in r.get_json()["html"] and r.get_json()["voces"][0]["id"] == voz_id
    assert libro.saldo("acme") < 10000
