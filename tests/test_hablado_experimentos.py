"""Experimentos y un anuncio hablado (spec 2026-10-01 §6): como una imagen, no
se deriva ni se rescata (una re-edición le pondría otra voz encima): ganadora
solo escala (y sí sale en orgánico, es un video); perdedora solo se pausa."""
import pytest

import creative_flow
from tests.test_experimentos_db import PAISES, _pieza, _pieza_imagen
from tests.test_tareas_experimentos import (_decisor_fijo, _experimento_activo, _pedidas,  # noqa: F401
                                            _sin_diagnostico_real)


def _pieza_hablada(db):
    with db.conectar() as con:
        ahora = db.ahora()
        cid = con.execute(db.concepto.insert().values(
            cliente="acme", creado_en=ahora, actualizado_en=ahora, origen="manual", legado_id="cf_hablado",
            extra={"accion_central": "Estas chanclas son una nube.", "modo_crear": "hablado"})).inserted_primary_key[0]
        return con.execute(db.pieza.insert().values(
            cliente="acme", creado_en=ahora, actualizado_en=ahora, concepto_id=cid, tipo="video", estado="listo",
            url_video="https://r2/hablado.mp4", modelo="p_video_avatar", legado_id="cf_hablado",
            extra={})).inserted_primary_key[0]


def test_la_pieza_del_experimento_sabe_que_no_se_deriva(base_temporal):
    import experimentos as ex
    hablada, img = _pieza_hablada(base_temporal), _pieza_imagen(base_temporal)
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_2")
    eid = ex.crear("acme", "Prueba", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    for p in (hablada, img, clon):
        ex.agregar_pieza("acme", eid, p, "CO")
    por_id = {p["pieza_id"]: p for p in ex.piezas("acme", eid)}
    assert por_id[hablada]["sin_derivar"] is True and por_id[hablada]["es_imagen"] is False
    assert por_id[img]["sin_derivar"] is True and por_id[clon]["sin_derivar"] is False
    galeria = {e["pieza_id"]: e for e in ex.elegibles("acme")}
    assert galeria[hablada]["sin_derivar"] is True and galeria[clon]["sin_derivar"] is False


def test_ganadora_hablada_escala_sin_derivar(base_temporal, monkeypatch):
    import experimentos as ex
    import organico
    import tareas
    from tareas import experimentos as te
    tareas.cargar_todas()
    eid, _ep = _experimento_activo(ex, _pieza_hablada(base_temporal))
    _decisor_fijo(monkeypatch, te, "ganador", "escalar_y_derivar")
    monkeypatch.setattr(organico, "disponibles", lambda c: ["instagram"])
    pedidas = _pedidas(monkeypatch, te)
    te.exp_decidir({"payload": {"cliente": "acme", "experimento_id": eid}})
    assert pedidas == ["escalar", "publicar_organico"]
    assert any("Anuncio hablado: sin rescate/derivación" in e["mensaje"] for e in ex.eventos("acme", eid))


def test_perdedora_hablada_solo_se_pausa(base_temporal, monkeypatch):
    import experimentos as ex
    import tareas
    from tareas import experimentos as te
    tareas.cargar_todas()
    eid, _ep = _experimento_activo(ex, _pieza_hablada(base_temporal))
    _decisor_fijo(monkeypatch, te, "perdedor", "rescatar")
    pedidas = _pedidas(monkeypatch, te)
    te.exp_decidir({"payload": {"cliente": "acme", "experimento_id": eid}})
    assert pedidas == ["pausar"]


def test_derivaciones_rechaza_un_anuncio_hablado(base_temporal):
    import derivaciones
    cf = creative_flow.crear("acme", [], [], [], "Hola", 8, "", "A", referencias_urls=["https://r2/f.jpg"])
    creative_flow.actualizar("acme", cf, tipo="video", estado="video_listo", modelo="p_video_avatar",
                             modo_crear="hablado", video_url="https://r2/h.mp4")
    with pytest.raises(ValueError, match="anuncio hablado"):
        derivaciones._rechazar_imagen("acme", cf)
    normal = creative_flow.crear("acme", [], [], [], "gira", 8, "", "A", referencias_urls=["https://x/1.png"])
    creative_flow.actualizar("acme", normal, tipo="video", estado="video_listo", modelo="wan3", video_url="https://r2/v.mp4")
    derivaciones._rechazar_imagen("acme", normal)          # un video normal se sigue derivando
