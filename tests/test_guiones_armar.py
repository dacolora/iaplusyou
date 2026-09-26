"""Armar clips de punta a punta con Claude falso: prompts al chat, rearmar, versiones."""
import copy

import pytest
import sqlalchemy as sa

from guiones import refinador
from tests.fixtures_guiones import BLOQUE, CONFIG, PLAN, fake, video_nuevo


@pytest.fixture()
def proyecto(base_temporal, tmp_path, monkeypatch):
    import proyectos
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    return base_temporal


def _armando(config=CONFIG):
    from guiones import datos
    gid, vid = video_nuevo(config=config)
    datos.empezar("acme", vid, "armando", ("configurando",))
    return gid, vid


def test_armar_deja_los_prompts_en_el_chat(proyecto):
    from guiones import clips, datos
    _, vid = _armando()
    clips.armar(vid, llamar=fake(PLAN))
    v = datos.video("acme", vid)
    assert v["estado"] == "armado", v["validaciones"]
    assert all(x["ok"] for x in v["validaciones"])
    prompts = datos.prompts_de_video(vid)
    assert [p["extra"]["variante"] for p in prompts] == ["principal", "principal", "hook:hook_2", "hook:hook_3"]
    for p in prompts:
        d = refinador.obtener("acme", p["id"])
        assert d["origen"] == "pipeline" and d["tipo"] == "clip" and d["texto_fijo"]
        assert d["problemas"] == []
    with proyecto.conectar() as con:
        tipos = [r[0] for r in con.execute(sa.select(proyecto.gasto.c.tipo))]
    assert "guion_clips" in tipos


def test_plan_invalido_no_crea_prompts_y_rearmar_manda_las_fallas(proyecto):
    from guiones import clips, datos
    _, vid = _armando()
    malo = copy.deepcopy(PLAN)
    malo["clips"][1]["momentos"][2]["aire"] = 5.0
    clips.armar(vid, llamar=fake(malo))
    v = datos.video("acme", vid)
    assert v["estado"] == "invalido" and datos.prompts_de_video(vid) == []
    datos.empezar("acme", vid, "armando", ("configurando", "invalido", "error"))
    registro = []
    clips.armar(vid, llamar=fake(PLAN, registro=registro))
    contenido = registro[0]["messages"][0]["content"]
    assert "<fallas>" in contenido and "clip 2" in contenido and "<plan_anterior>" in contenido
    assert datos.video("acme", vid)["estado"] == "armado"


def test_plan_sin_clips_queda_en_error(proyecto):
    from guiones import clips, datos
    _, vid = _armando()
    clips.armar(vid, llamar=fake({"clips": []}))
    v = datos.video("acme", vid)
    assert v["estado"] == "error" and "incompleto" in v["aviso"]


def test_version_con_bloque_no_llama_a_claude(proyecto, monkeypatch):
    from guiones import claude, clips, datos
    _, vid = _armando()
    clips.armar(vid, llamar=fake(PLAN))

    def prohibido(*_):
        raise AssertionError("no debía llamar a Claude")
    monkeypatch.setattr(claude, "llamar", prohibido)
    nuevo = clips.version_con_bloque("acme", vid, dict(BLOQUE, conteo_objetos="Exactly TWO flip-flops."))
    v2 = datos.video("acme", nuevo)
    assert v2["version_n"] == 2 and v2["estado"] == "armado"
    textos = [refinador.obtener("acme", p["id"])["texto_vigente"] for p in datos.prompts_de_video(nuevo)]
    assert textos and all("Exactly TWO flip-flops." in t for t in textos)
    assert len(datos.prompts_de_video(vid)) == 4


def test_nueva_version_con_otra_config(proyecto):
    from guiones import datos
    _, vid = video_nuevo(config=dict(CONFIG, duracion_objetivo=20))
    datos.guardar_quitadas("acme", vid, [4])
    igual = datos.nueva_version("acme", vid, config=dict(CONFIG, duracion_objetivo=20, modo="voiceover"))
    otra = datos.nueva_version("acme", vid, config=dict(CONFIG, duracion_objetivo=30))
    assert datos.video("acme", igual)["recorte"]["quitadas"] == [4]
    assert datos.video("acme", otra)["recorte"] == {}
    assert datos.video("acme", otra)["estado"] == "configurando"
