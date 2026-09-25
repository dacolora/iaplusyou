"""Documento .md del spec del cliente §2.7 con el texto vigente del chat."""
import pytest

from tests.fixtures_guiones import CONFIG, PLAN, fake, video_nuevo


@pytest.fixture()
def armado(base_temporal, tmp_path, monkeypatch):
    import proyectos
    from guiones import clips, datos
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    _, vid = video_nuevo(config=dict(CONFIG, duracion_objetivo=30))
    datos.guardar_quitadas("acme", vid, [])
    datos.empezar("acme", vid, "armando", ("configurando",))
    clips.armar(vid, llamar=fake(PLAN))
    return vid


def test_documento_trae_todo_y_el_texto_vigente(armado):
    from guiones import datos, plantillas, refinador
    v = datos.video("acme", armado)
    prompts = datos.prompts_de_video(armado)
    p1 = refinador.obtener("acme", prompts[0]["id"])
    refinador.editar("acme", p1["id"], p1["texto_vigente"].replace("Medium shot", "Wide shot"), p1["version_n"])
    md = plantillas.documento_md(v, datos.prompts_de_video(armado))
    for titulo in ("## Cómo funciona esto", "## Frases quitadas", "## Bloque del video", "## Hooks alternativos",
                   "## Clips", "## Resumen de clips"):
        assert titulo in md
    assert "Wide shot" in md and "| 1 | 10 s |" in md and "hook_2" in md
    assert "Ninguna: se usa el guion completo." in md
    assert plantillas.nombre_documento(v) == f"batch-{v['guion']['lote_id']}-videos-prompts-30s-v1.md"
