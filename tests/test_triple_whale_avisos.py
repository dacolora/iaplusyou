"""Avisos por correo tras cada copia de Triple Whale (spec 2026-09-28 §12)."""
import pytest

import triple_whale_tiendas
from tests.test_triple_whale_evaluacion import REGLAS, anuncio
from triple_whale import avisos, evaluacion


def _ev(*lista):
    return evaluacion.evaluar(list(lista), reglas=REGLAS)


def test_cambios_es_pura_y_solo_cuenta_lo_nuevo():
    ev = _ev(anuncio("g", pedidos=5, ingresos=400), anuncio("p", gasto=400), anuncio("n", impresiones=10))
    c = avisos.cambios({}, ev)
    assert [a["ad_id"] for a in c["ganadores"]] == ["g"] and [a["ad_id"] for a in c["perdedores"]] == ["p"]
    assert c["cansados"] == [] and c["estado"]["g"]["veredicto"] == "ganador"
    # La misma evaluación contra su propio estado: nada nuevo.
    c2 = avisos.cambios(c["estado"], ev)
    assert c2["ganadores"] == [] and c2["perdedores"] == []
    # Un ganador que se cansa (ev con fatiga) sale una sola vez.
    con_fatiga = _ev(anuncio("g", pedidos=5, ingresos=400))
    con_fatiga["anuncios"][0]["fatiga"] = True
    assert [a["ad_id"] for a in avisos.cambios(c["estado"], con_fatiga)["cansados"]] == ["g"]
    estado = avisos.cambios(c["estado"], con_fatiga)["estado"]
    assert avisos.cambios(estado, con_fatiga)["cansados"] == []


def test_cuerpo_lista_cada_bloque_y_vacio_sin_cambios():
    c = {"ganadores": [{"ad_id": "1", "nombre": "Caja", "roas": 4.2, "pedidos": 7, "gasto": 120}],
         "cansados": [], "perdedores": []}
    texto = avisos.cuerpo("acme", c, "USD")
    assert "Nuevos ganadores:" in texto and "- Caja (ROAS 4,2×, 7 pedidos, gasto 120 USD)" in texto
    assert "Triple Whale del proyecto acme" in texto
    assert avisos.cuerpo("acme", {"ganadores": [], "cansados": [], "perdedores": []}, "USD") == ""
    assert "tw_source" in avisos.cuerpo("acme", {}, "USD", sin_ventas=True)


@pytest.fixture()
def conectado(base_temporal, monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "test_secret_key_12345678")
    triple_whale_tiendas.conectar("acme", "tw_x", "acme.myshopify.com", moneda="USD")
    enviados = []
    monkeypatch.setattr(avisos.notificaciones, "avisar", lambda cliente, tipo, asunto, cuerpo:
                        enviados.append((tipo, asunto, cuerpo)) or True)
    return enviados


def test_primera_copia_solo_guarda_la_base_y_la_segunda_avisa(conectado):
    enviados = conectado
    ev1 = _ev(anuncio("g1", pedidos=5, ingresos=400), anuncio("p1", gasto=400))
    assert avisos.revisar_y_avisar("acme", ev=ev1) is None
    assert enviados == []
    assert set(triple_whale_tiendas.obtener("acme")["extra"]["avisados"]) == {"g1", "p1"}

    ev2 = _ev(anuncio("g1", pedidos=5, ingresos=400), anuncio("p1", gasto=400), anuncio("g2", pedidos=4, ingresos=300))
    c = avisos.revisar_y_avisar("acme", ev=ev2)
    assert c["avisado"] and [a["ad_id"] for a in c["ganadores"]] == ["g2"]
    tipo, asunto, cuerpo = enviados[-1]
    assert tipo == "tw_evaluacion" and "1 cambio" in asunto and "Anuncio g2" in cuerpo and "Anuncio p1" not in cuerpo
    # Sin cambios, sin correo.
    assert avisos.revisar_y_avisar("acme", ev=ev2)["avisado"] is False and len(enviados) == 1


def test_sin_ventas_atribuidas_avisa_una_sola_vez_y_se_rearma_cuando_vuelven(conectado):
    enviados = conectado
    sin = _ev(anuncio("a", gasto=300), anuncio("b", gasto=200))
    avisos.revisar_y_avisar("acme", ev=sin)           # base
    c = avisos.revisar_y_avisar("acme", ev=sin)
    assert c["avisado"] and "sin ventas atribuidas" in enviados[-1][1] and "tw_source" in enviados[-1][2]
    assert triple_whale_tiendas.obtener("acme")["extra"]["aviso_sin_ventas"]
    assert avisos.revisar_y_avisar("acme", ev=sin)["avisado"] is False    # no repite
    con = _ev(anuncio("a", gasto=300, pedidos=5, ingresos=900), anuncio("b", gasto=200))
    avisos.revisar_y_avisar("acme", ev=con)
    assert not triple_whale_tiendas.obtener("acme")["extra"].get("aviso_sin_ventas")


def test_sin_conexion_no_hace_nada(base_temporal):
    assert avisos.revisar_y_avisar("nadie") is None


def test_revisar_evalua_todas_las_tiendas(conectado, monkeypatch):
    """Evaluar por tienda daría perdedores falsos con una cuenta compartida: los avisos miran «Todas»."""
    from triple_whale import panel
    pedidos = []

    def evaluar(cliente, dias=30, canal=None, tienda_id="no se pasó", hoy=None):
        pedidos.append((cliente, dias, tienda_id))
        return _ev(anuncio("g1", pedidos=5, ingresos=400)), "2026-09-01", "2026-09-30"
    monkeypatch.setattr(panel, "evaluar_periodo", evaluar)
    assert avisos.revisar_y_avisar("acme") is None
    assert pedidos == [("acme", avisos.DIAS, None)]
    # La base queda en los ajustes del proyecto, no en una tienda.
    assert set(triple_whale_tiendas.ajustes("acme")["extra"]["avisados"]) == {"g1"}
    assert "avisados" not in triple_whale_tiendas.tiendas("acme")[0]["extra"]


def test_con_varias_tiendas_manda_un_solo_correo(conectado, monkeypatch):
    enviados = conectado
    triple_whale_tiendas.agregar("acme", "tw_y", "no-acme.myshopify.com", "NO")
    avisos.revisar_y_avisar("acme", ev=_ev(anuncio("p1", gasto=400)))
    c = avisos.revisar_y_avisar("acme", ev=_ev(anuncio("p1", gasto=400), anuncio("g2", pedidos=4, ingresos=300)))
    assert c["avisado"] and len(enviados) == 1
