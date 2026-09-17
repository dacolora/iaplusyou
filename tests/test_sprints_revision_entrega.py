import io
import os
import zipfile

import pytest


def _sprint_en_revision(datos, creative_flow, monkeypatch, tmp_path):
    import estado as estado_videos
    monkeypatch.setattr(estado_videos, "_path", lambda c: str(tmp_path / f"{c}_videos.json"))
    pid = datos.crear_persona("acme", "Premium")
    tid = datos.crear_temporada("acme", "Navidad", "2026-11-15", "2026-12-31")
    sid = datos.crear_sprint("acme", "Sprint octubre", "2026-10-01", "2026-10-31")
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 2, 1)
    piezas = []
    for n, (tipo, est, qa) in enumerate([("video", "video_listo", {"veredicto": "pasa", "score": 90}),
                                         ("video", "video_listo", {"veredicto": "revisar", "score": 60}),
                                         ("imagen", "error", None)]):
        cp = datos.crear_idea("acme", cid, tipo, f"Pieza {n}", "x", estado_idea="aprobada")
        cf = creative_flow.crear("acme", [], ["E"], [], "x", 8, "", "A")
        creative_flow.actualizar("acme", cf, tipo=tipo, estado=est, video_url=f"https://r2/{n}.{'mp4' if tipo == 'video' else 'png'}", usd=0.5)
        datos.actualizar_idea("acme", cp, cf_id=cf, qa=qa)
        if est == "video_listo":
            ev = estado_videos.cargar("acme"); ev[cf] = {"estado": "pendiente"}; estado_videos.guardar("acme", ev)
        piezas.append((cp, cf))
    return sid, cid, piezas


def test_aprobar_rechazar_y_aprobar_qa(base_temporal, monkeypatch, tmp_path):
    import creative_flow
    import estado as estado_videos
    from sprints import datos, estado, revision
    sid, cid, piezas = _sprint_en_revision(datos, creative_flow, monkeypatch, tmp_path)
    (cp0, cf0), (cp1, cf1), (cp2, cf2) = piezas
    assert revision.aprobar("acme", cp0) is True and datos.idea("acme", cp0)["revision"] == "aprobada"
    with pytest.raises(datos.ErrorDatos):
        revision.rechazar("acme", cp1, "")
    assert revision.rechazar("acme", cp1, "mal encuadre") is True
    i1 = datos.idea("acme", cp1)
    assert i1["revision"] == "rechazada" and i1["revision_motivo"] == "mal encuadre"
    assert cf1 not in estado_videos.cargar("acme") and cf0 in estado_videos.cargar("acme")
    assert revision.aprobar("acme", cp2) is False        # en error, no se puede aprobar
    datos.actualizar_idea("acme", cp1, revision="pendiente")
    assert revision.aprobar_pasaron_qa("acme", sid) == 0   # cp0 ya aprobada, cp1 es "revisar"
    datos.actualizar_idea("acme", cp1, qa={"veredicto": "error", "score": None, "checks": {}, "nota": "ffprobe"})
    assert revision.aprobar_pasaron_qa("acme", sid) == 0   # F5: un QA fallido no es un QA pasado
    datos.actualizar_idea("acme", cp1, qa={"veredicto": "pasa", "score": 80})
    assert revision.aprobar_pasaron_qa("acme", sid) == 1
    tipos = [e["tipo"] for e in datos.eventos("acme", sid)]
    assert "pieza_aprobada" in tipos and "pieza_rechazada" in tipos


def test_resumen_cerrar_reabrir(base_temporal, monkeypatch, tmp_path):
    import creative_flow
    from sprints import datos, estado, revision
    sid, cid, piezas = _sprint_en_revision(datos, creative_flow, monkeypatch, tmp_path)
    datos.actualizar_sprint("acme", sid, extra={"costo_estimado_usd": 1.2})
    # Con una pieza todavía generando, el sprint NO está en revisión y no se puede cerrar:
    creative_flow.actualizar("acme", piezas[2][1], estado="video_generando")
    assert estado.recalcular("acme", sid)["estado"] == "generando"
    with pytest.raises(datos.ErrorDatos):
        revision.cerrar("acme", sid)
    creative_flow.actualizar("acme", piezas[2][1], estado="error", error="x")
    # Con todas las piezas terminadas (listo/error) el sprint está en revisión:
    assert estado.recalcular("acme", sid)["estado"] == "revision"
    revision.aprobar("acme", piezas[0][0]); revision.rechazar("acme", piezas[1][0], "no")
    r = revision.resumen("acme", sid)
    assert r == {"planeadas": 3, "terminadas": 2, "aprobadas": 1, "rechazadas": 1, "sin_revisar": 0, "error": 1,
                 "costo_usd": 1.5, "costo_estimado_usd": 1.2, "dias": 30}
    r2 = revision.cerrar("acme", sid)
    assert r2["aprobadas"] == 1 and datos.sprint("acme", sid)["estado"] == "completado"
    assert estado.recalcular("acme", sid)["estado"] == "completado"
    assert revision.reabrir("acme", sid) is True and estado.recalcular("acme", sid)["estado"] == "revision"
    tipos = [e["tipo"] for e in datos.eventos("acme", sid)]
    assert tipos[0] == "sprint_reabierto" and "sprint_cerrado" in tipos


def test_enlaces_y_empaquetar(base_temporal, monkeypatch, tmp_path):
    import creative_flow
    from sprints import datos, entrega, revision
    from storage import r2_uploader
    sid, cid, piezas = _sprint_en_revision(datos, creative_flow, monkeypatch, tmp_path)
    revision.aprobar("acme", piezas[0][0])
    lista = entrega.enlaces("acme", sid)
    assert len(lista) == 1 and lista[0]["url"] == "https://r2/0.mp4" and lista[0]["campana_n"] == 1 and lista[0]["persona"] == "Premium"
    assert entrega.nombre_archivo(lista[0], ".mp4") == "campana1_video_Pieza-0.mp4"
    subidas = []
    monkeypatch.setattr(r2_uploader, "upload_file", lambda ruta, key, ct: subidas.append((ruta, key, ct)) or f"https://r2/{key}")
    monkeypatch.setattr(entrega, "BASE_DIR", str(tmp_path))
    r = entrega.empaquetar("acme", sid, descargar=lambda url: b"contenido-" + url.encode())
    assert r["n"] == 1 and r["url"].startswith("https://r2/clientes/acme/sprints/") and r["url"].endswith(".zip")
    ruta, key, ct = subidas[0]
    assert ct == "application/zip" and os.path.exists(ruta)
    with zipfile.ZipFile(ruta) as z:
        assert z.namelist() == ["campana1_video_Pieza-0.mp4"] and z.read("campana1_video_Pieza-0.mp4") == b"contenido-https://r2/0.mp4"
    assert datos.sprint("acme", sid)["extra"]["zip"]["url"] == r["url"]
    with pytest.raises(datos.ErrorDatos):
        entrega.empaquetar("acme", 999)


def test_rechazar_conserva_registro_de_publicacion(base_temporal, monkeypatch, tmp_path):
    """Fix round 1, hallazgo 1: si la pieza ya se publicó (estado distinto de
    "pendiente" en la cola de estado_videos.json), rechazarla no debe borrar
    ese registro — no hay nada que deshacer. Solo se retira de la cola la
    que sigue pendiente de publicar, y el evento de la ya publicada queda
    marcado con datos["ya_publicada"]."""
    import creative_flow
    import estado as estado_videos
    from sprints import datos, revision
    sid, cid, piezas = _sprint_en_revision(datos, creative_flow, monkeypatch, tmp_path)
    (cp0, cf0), (cp1, cf1), (cp2, cf2) = piezas
    cola = estado_videos.cargar("acme")
    cola[cf0] = {"estado": "publicado", "publicado_en": "x"}
    estado_videos.guardar("acme", cola)
    assert revision.rechazar("acme", cp0, "motivo publicada") is True
    assert revision.rechazar("acme", cp1, "motivo pendiente") is True
    cola = estado_videos.cargar("acme")
    assert cola[cf0] == {"estado": "publicado", "publicado_en": "x"}
    assert cf1 not in cola
    eventos = {e["datos"]["cp_id"]: e for e in datos.eventos("acme", sid) if e["tipo"] == "pieza_rechazada"}
    assert eventos[cp0]["datos"]["ya_publicada"] is True
    assert "ya estaba publicada" in eventos[cp0]["mensaje"]
    assert "ya_publicada" not in eventos[cp1]["datos"]


def test_nombre_archivo_normaliza_acentos():
    """Fold-in: _slug no debe tragarse la letra base al quitar acentos."""
    from sprints import entrega
    assert entrega.nombre_archivo({"campana_n": 1, "tipo": "video", "titulo": "Árbol de Año Nuevo"},
                                  ".mp4") == "campana1_video_Arbol-de-Ano-Nuevo.mp4"
