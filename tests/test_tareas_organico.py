"""Tarea del worker `organico_publicar` (Bloque 7): cablea organico.publicar
con las etapas de la barra y el aviso `publicado`; hook de interrupción.
Sin red: organico.publicar es un fake que solo mueve filas."""
import pytest

from tests.test_experimentos_db import _pieza


@pytest.fixture()
def ent(base_temporal, monkeypatch):
    import organico
    import tareas
    from tareas import organico as to
    tareas.cargar_todas()
    etapas, avisos = [], []
    monkeypatch.setattr(to.trabajos, "reportar", lambda job_id, etapa=None, **kw: etapas.append((job_id, etapa)))
    monkeypatch.setattr(to.notificaciones, "avisar",
                        lambda c, tipo, asunto, cuerpo: (avisos.append((tipo, asunto, cuerpo)), True)[1])
    pid = _pieza(base_temporal)
    ids = {p: organico.crear("acme", pid, p, f"texto {p} #a #b #c", titulo=f"T {p}")
           for p in ("instagram", "facebook")}
    return {"organico": organico, "to": to, "pid": pid, "ids": ids, "etapas": etapas, "avisos": avisos}


def test_registro_y_job_id(ent):
    import tareas
    to = ent["to"]
    assert tareas.REGISTRO["organico_publicar"] is to.publicar
    assert tareas.AL_INTERRUMPIR["organico_publicar"] is to.interrumpida
    assert to.job_id_publicar("acme", 7) == "acme__pieza7__organico"
    assert to.ETAPAS_PUBLICAR == [("Descargando", 15), ("Publicando", 85)]


def test_tarea_publica_reporta_etapas_y_avisa_con_urls(ent, monkeypatch):
    organico, to, ids = ent["organico"], ent["to"], ent["ids"]
    llamadas = []

    def publicar(cliente, pub_ids, on_etapa=None):
        llamadas.append((cliente, list(pub_ids)))
        on_etapa("Descargando")
        on_etapa("Publicando")
        organico.actualizar(cliente, ids["instagram"], estado="publicada", id_externo="abc123",
                            url="https://www.instagram.com/p/abc123")
        organico.actualizar(cliente, ids["facebook"], estado="error", error="token vencido")
        return {"ok": [ids["instagram"]], "error": [ids["facebook"]]}

    monkeypatch.setattr(to.organico, "publicar", publicar)
    job_id = to.job_id_publicar("acme", ent["pid"])
    msg = to.publicar({"payload": {"cliente": "acme", "pub_ids": [ids["instagram"], ids["facebook"]]}, "job_id": job_id})
    assert llamadas == [("acme", [ids["instagram"], ids["facebook"]])]
    assert ent["etapas"] == [(job_id, "Descargando"), (job_id, "Publicando")]
    assert msg == "Publicada en Instagram Reels; falló en Facebook (Página)."
    assert len(ent["avisos"]) == 1
    tipo, asunto, cuerpo = ent["avisos"][0]
    assert tipo == "publicado" and asunto.startswith("Publicación orgánica con errores")
    assert "https://www.instagram.com/p/abc123" in cuerpo and "Facebook (Página): NO se publicó — token vencido" in cuerpo


def test_tarea_sin_job_id_usa_el_de_la_pieza_y_todo_ok(ent, monkeypatch):
    organico, to, ids = ent["organico"], ent["to"], ent["ids"]

    def publicar(cliente, pub_ids, on_etapa=None):
        on_etapa("Descargando")
        for i in pub_ids:
            organico.actualizar(cliente, i, estado="publicada", id_externo="x1", url="https://youtu.be/x1")
        return {"ok": list(pub_ids), "error": []}

    monkeypatch.setattr(to.organico, "publicar", publicar)
    msg = to.publicar({"payload": {"cliente": "acme", "pub_ids": [ids["facebook"]]}})
    assert ent["etapas"] == [(to.job_id_publicar("acme", ent["pid"]), "Descargando")]
    assert msg == "Publicada en Facebook (Página)."
    assert ent["avisos"][0][1].startswith("Publicación orgánica lista")


def test_tarea_falla_si_ninguna_salio_pero_igual_avisa(ent, monkeypatch):
    organico, to, ids = ent["organico"], ent["to"], ent["ids"]

    def publicar(cliente, pub_ids, on_etapa=None):
        for i in pub_ids:
            organico.actualizar(cliente, i, estado="error", error="No pude descargar el video")
        return {"ok": [], "error": list(pub_ids)}

    monkeypatch.setattr(to.organico, "publicar", publicar)
    with pytest.raises(RuntimeError, match="No se pudo publicar en Instagram Reels, Facebook"):
        to.publicar({"payload": {"cliente": "acme", "pub_ids": list(ids.values())}})
    assert ent["avisos"][0][0] == "publicado" and ent["avisos"][0][1].startswith("No se pudo publicar")
    assert "No pude descargar el video" in ent["avisos"][0][2]


def test_tarea_sin_publicaciones_no_hace_nada(ent, monkeypatch):
    to = ent["to"]
    monkeypatch.setattr(to.organico, "publicar", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debe publicar")))
    assert to.publicar({"payload": {"cliente": "acme", "pub_ids": []}}) == "No había publicaciones pendientes."
    assert to.publicar({"payload": {"cliente": "otro", "pub_ids": list(ent["ids"].values())}}) == \
        "No había publicaciones pendientes."   # ids de otro cliente: no se ven
    assert ent["avisos"] == [] and ent["etapas"] == []


def test_tarea_limpia_lo_vivo_si_organico_publicar_revienta(ent, monkeypatch):
    """I-1: una excepción de organico.publicar que no sea un fallo por
    plataforma (p.ej. "database is locked" al actualizar una fila) no debe
    dejar las publicaciones atascadas en `publicando`/`en_cola` para
    siempre — la tarea corre la misma limpieza que `interrumpida` antes de
    re-lanzar."""
    organico, to, ids = ent["organico"], ent["to"], ent["ids"]
    organico.actualizar("acme", ids["instagram"], estado="publicando")

    def publicar(cliente, pub_ids, on_etapa=None):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(to.organico, "publicar", publicar)
    with pytest.raises(RuntimeError, match="database is locked"):
        to.publicar({"payload": {"cliente": "acme", "pub_ids": list(ids.values())}})
    pubs = {p["plataforma"]: p for p in organico.listar("acme", pieza_id=ent["pid"])}
    assert pubs["instagram"]["estado"] == "error" and "interrumpió" in pubs["instagram"]["error"]
    assert pubs["facebook"]["estado"] == "error" and "antes de llegar a esta plataforma" in pubs["facebook"]["error"]
    assert ent["avisos"] == []   # revienta antes de poder avisar nada
    # La unicidad viva ya no bloquea: se puede volver a crear/publicar.
    nuevo = organico.crear("acme", ent["pid"], "instagram", "reintento #a #b #c")
    assert nuevo


def test_interrumpida_deja_en_error_lo_publicando_y_lo_en_cola_sin_tocar_lo_publicado(ent):
    organico, to, ids, pid = ent["organico"], ent["to"], ent["ids"], ent["pid"]
    ids["youtube"] = organico.crear("acme", pid, "youtube", "texto yt #a #b #c")
    organico.actualizar("acme", ids["instagram"], estado="publicando")
    organico.actualizar("acme", ids["facebook"], estado="publicada", url="https://www.facebook.com/1")
    to.interrumpida({"payload": {"cliente": "acme", "pub_ids": list(ids.values())}}, "Se interrumpió.")
    pubs = {p["plataforma"]: p for p in organico.listar("acme", pieza_id=pid)}
    assert pubs["instagram"]["estado"] == "error" and "se interrumpió" in pubs["instagram"]["error"]
    assert pubs["youtube"]["estado"] == "error" and "antes de llegar a esta plataforma" in pubs["youtube"]["error"]
    assert pubs["facebook"]["estado"] == "publicada" and pubs["facebook"]["url"] == "https://www.facebook.com/1"
