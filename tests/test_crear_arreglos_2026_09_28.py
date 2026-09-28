"""Dos arreglos de Crear (2026-09-28): el botón «Rearmar con IA» ya no vive
dentro del formulario de «Guardar cambios» (un <form> anidado lo descarta el
navegador y el clic guardaba en vez de rearmar), y una tarea de generación
cuya sesión se descartó termina con un mensaje claro, sin traceback ni gasto."""
from html.parser import HTMLParser

import pytest


def _admin(dashboard):
    dashboard.app.config["TESTING"] = True
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "admin"; s["rol"] = "admin"; s["cliente"] = None
    return c


@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import proyectos
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    return {"dashboard": dashboard, "c": _admin(dashboard)}


class _Formularios(HTMLParser):
    """Anidamiento de <form> y a qué formulario apunta cada botón."""
    def __init__(self):
        super().__init__()
        self.abiertos = 0
        self.anidados = 0
        self.forms = {}          # id -> action
        self.botones = []        # (texto pendiente, form=)
        self._boton = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            if self.abiertos:
                self.anidados += 1
            self.abiertos += 1
            if a.get("id"):
                self.forms[a["id"]] = a.get("action")
        if tag == "button":
            self._boton = {"form": a.get("form"), "texto": ""}

    def handle_data(self, data):
        if self._boton is not None:
            self._boton["texto"] += data

    def handle_endtag(self, tag):
        if tag == "form":
            self.abiertos -= 1
        if tag == "button" and self._boton is not None:
            self.botones.append(self._boton); self._boton = None


def test_rearmar_con_ia_no_vive_dentro_de_guardar_cambios(app):
    import creative_flow
    cf = creative_flow.crear("acme", [], ["prod"], [], "acción", 8, "tono", "A", legado_id="cf_20260928_000000_000001")
    creative_flow.actualizar("acme", cf, estado="prompt_listo", tipo="video", prompt_relleno="Prompt A")
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    tarjeta = html.split('data-cf="%s"' % cf)[1].split('class="generado-pie"')[0]
    p = _Formularios(); p.feed(tarjeta)
    assert p.anidados == 0, "hay un <form> dentro de otro <form>"
    rearmar = next(b for b in p.botones if "Rearmar con IA" in b["texto"])
    assert rearmar["form"] == f"rearmar-{cf}"
    assert p.forms[f"rearmar-{cf}"] == f"/cliente/acme/creative_flow/{cf}/rearmar"
    guardar = next(b for b in p.botones if "Guardar cambios" in b["texto"])
    assert guardar["form"] is None            # sigue en su formulario de siempre


def test_tarea_de_una_sesion_descartada_termina_sin_gasto(base_temporal, monkeypatch, tmp_path):
    import tareas.flowplus as fp
    monkeypatch.setattr(fp, "BASE_DIR", str(tmp_path))
    llamadas = []
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", lambda *a, **k: llamadas.append("video"))
    monkeypatch.setattr(fp.flowplus_modelos, "generar_imagen", lambda *a, **k: llamadas.append("imagen"))
    tarea = {"payload": {"cliente": "acme", "cf_id": "cf_20260928_133953_734527"}, "job_id": "j", "id": 5618}
    mensaje = fp.ejecutar_video(tarea)
    assert "se descartó antes de generar" in mensaje and "no se cobró" in mensaje
    assert fp.ejecutar_imagen(tarea) == mensaje
    assert llamadas == []


def test_preparar_avisa_que_la_sesion_no_existe(base_temporal):
    import tareas.flowplus as fp
    with pytest.raises(fp.SesionDescartada):
        fp._preparar("acme", "cf_no_existe")
