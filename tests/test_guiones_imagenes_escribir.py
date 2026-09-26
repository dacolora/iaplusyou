"""Escribir los prompts de imágenes con Claude falso y pasarlos al chat."""
import pytest

from guiones import refinador
from tests.fixtures_guiones import CONFIG, PLAN, fake, video_nuevo


@pytest.fixture()
def armado(base_temporal, tmp_path, monkeypatch):
    import proyectos
    from guiones import clips, datos
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    _, vid = video_nuevo(config=CONFIG)
    datos.empezar("acme", vid, "armando", ("configurando",))
    clips.armar(vid, llamar=fake(PLAN))
    return vid


RESPUESTA = {"imagenes": [{"id": "img_1", "titulo": "Podólogo", "prompt": "A calm British man in a white coat."},
                          {"id": "img_2", "titulo": "Clínica", "prompt": "A bright modern clinic."}]}


def test_escribir_deja_prompts_de_imagen_en_el_chat(armado):
    from guiones import datos, imagenes
    datos.empezar_imagenes("acme", armado)
    registro = []
    imagenes.escribir(armado, llamar=fake(RESPUESTA, registro=registro))
    v = datos.video("acme", armado)
    assert v["estado_imagenes"] == "listo"
    assert [x["id"] for x in v["imagenes"]["lista"]] == ["img_1", "img_2"]
    assert v["imagenes"]["tabla"][0]["imagenes"] == ["Image 1 · por crear (img_1)", "Image 2 · por crear (img_2)"]
    prompts = [p for p in datos.prompts_de_video(armado) if p["tipo"] == "imagen"]
    assert len(prompts) == 2
    d = refinador.obtener("acme", prompts[0]["id"])
    assert d["texto_fijo"] == [imagenes.CIERRE] and d["problemas"] == []
    assert '<imagen id="img_1" tipo="personaje">' in registro[0]["messages"][0]["content"]


def test_falta_un_prompt_es_error(armado):
    from guiones import datos, imagenes
    datos.empezar_imagenes("acme", armado)
    imagenes.escribir(armado, llamar=fake({"imagenes": RESPUESTA["imagenes"][:1]}))
    v = datos.video("acme", armado)
    assert v["estado_imagenes"] == "error" and "img_2" in v["aviso_imagenes"]


def test_empezar_imagenes_exige_armado_y_no_repite(armado):
    from guiones import datos
    from guiones.refinador import Conflicto
    datos.empezar_imagenes("acme", armado)
    with pytest.raises(Conflicto):
        datos.empezar_imagenes("acme", armado)
    _, otro = video_nuevo(config=CONFIG)
    with pytest.raises(Conflicto):
        datos.empezar_imagenes("acme", otro)


def test_refinador_crear_falla_a_medias_deja_listo_con_aviso(armado, monkeypatch):
    from guiones import datos, imagenes, refinador
    datos.empezar_imagenes("acme", armado)
    original = refinador.crear
    llamadas = []

    def crear_falla(*args, **kwargs):
        llamadas.append(1)
        if len(llamadas) == 2:
            raise RuntimeError("boom")
        return original(*args, **kwargs)

    monkeypatch.setattr(refinador, "crear", crear_falla)
    imagenes.escribir(armado, llamar=fake(RESPUESTA))
    v = datos.video("acme", armado)
    assert v["estado_imagenes"] == "listo"
    assert v["aviso_imagenes"] == ("Los prompts de imágenes quedaron escritos pero no se pudieron pasar todos al "
                                   "chat. Vuelve a escribirlos en una versión nueva.")


def test_sin_imagenes_necesarias_no_llama_a_claude(base_temporal, tmp_path, monkeypatch):
    import proyectos
    from guiones import clips, datos, imagenes
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    cfg = dict(CONFIG, referencias=[dict(r, activo_id=f"a{i}", nombre=f"A{i}") for i, r in enumerate(CONFIG["referencias"])])
    _, vid = video_nuevo(config=cfg)
    datos.empezar("acme", vid, "armando", ("configurando",))
    clips.armar(vid, llamar=fake(PLAN))
    datos.empezar_imagenes("acme", vid)
    registro = []
    imagenes.escribir(vid, llamar=fake(RESPUESTA, registro=registro))
    assert registro == [] and datos.video("acme", vid)["estado_imagenes"] == "listo"
