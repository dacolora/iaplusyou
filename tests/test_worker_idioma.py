"""El worker corre cada tarea en el idioma de su proyecto (spec 2026-09-26 §B8):
lo que la tarea guarda o manda sale en ese idioma sin que cada tarea repita
el `with idiomas.en_idioma(...)`."""
from flask_babel import gettext

import idiomas
import tareas
import worker


def test_tarea_con_proyecto_corre_en_su_idioma(tmp_path, monkeypatch):
    import proyectos
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    idiomas.guardar_de_proyecto("acme", "en")
    monkeypatch.setitem(tareas.REGISTRO, "prueba_idioma", lambda tarea: gettext("Idioma guardado."))
    assert worker.ejecutar({"tipo": "prueba_idioma", "cliente": "acme", "payload": {}}) == "Language saved."
    assert worker.ejecutar({"tipo": "prueba_idioma", "cliente": None, "payload": {}}) == "Idioma guardado."


def test_idioma_de_tarea(tmp_path, monkeypatch):
    import proyectos
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    idiomas.guardar_de_proyecto("acme", "en")
    assert worker.idioma_de_tarea({"cliente": "acme"}) == "en"
    assert worker.idioma_de_tarea({"cliente": None, "payload": {"cliente": "acme"}}) == "en"
    assert worker.idioma_de_tarea({"cliente": "_creatv"}) == "es"      # global de Creatv: DEFECTO
    assert worker.idioma_de_tarea({"cliente": None, "payload": {}}) == "es"
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: (_ for _ in ()).throw(OSError("disco")))
    assert worker.idioma_de_tarea({"cliente": "acme"}) == "es"          # leer el idioma nunca tumba una tarea
