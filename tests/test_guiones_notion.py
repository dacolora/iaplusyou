"""Notion: id desde el link, texto desde bloques anidados y paginados, errores sin filtrar la llave."""
import pytest

from guiones import notion

LLAVE = "ntn_SECRETO123"
PID = "1a2b3c4d5e6f47a8b9c0d1e2f3a4b5c6"


class _Resp:
    def __init__(self, status, data):
        self.status_code, self._d, self.ok = status, data, 200 <= status < 300

    def json(self):
        return self._d


class _Http:
    def __init__(self, rutas):
        self.rutas, self.llamadas = rutas, []

    def get(self, url, headers=None, params=None, timeout=None):
        self.llamadas.append((url, headers, params))
        clave = url.replace(notion.API, "") + (f"?{params['start_cursor']}" if params and params.get("start_cursor") else "")
        return _Resp(*self.rutas[clave])


def _bloque(bid, tipo, texto, hijos=False):
    return {"id": bid, "type": tipo, "has_children": hijos, tipo: {"rich_text": [{"plain_text": texto}]}}


def test_extraer_id():
    assert notion.extraer_id(f"https://www.notion.so/equipo/ORIGINALS-AI-RISKY-BATCH-{PID}?pvs=4") == PID
    assert notion.extraer_id("https://www.notion.so/1a2b3c4d-5e6f-47a8-b9c0-d1e2f3a4b5c6") == PID
    assert notion.extraer_id(PID.upper()) == PID
    assert notion.extraer_id("https://example.com/nada") is None
    assert notion.extraer_id("") is None


def test_leer_pagina_con_hijos_y_paginas():
    rutas = {
        f"/pages/{PID}": (200, {"properties": {"Name": {"type": "title", "title": [{"plain_text": "AI RISKY BATCH"}]}}}),
        f"/blocks/{PID}/children": (200, {"results": [_bloque("b1", "heading_2", "Script 1"),
                                                     _bloque("b2", "toggle", "Hooks", hijos=True)],
                                          "has_more": True, "next_cursor": "c2"}),
        f"/blocks/{PID}/children?c2": (200, {"results": [_bloque("b4", "paragraph", "Fin.")], "has_more": False}),
        "/blocks/b2/children": (200, {"results": [_bloque("b3", "bulleted_list_item", "Hook 2: otra frase")],
                                      "has_more": False}),
    }
    http = _Http(rutas)
    titulo, texto = notion.leer_pagina(LLAVE, PID, http=http)
    assert titulo == "AI RISKY BATCH"
    assert texto == "Script 1\nHooks\n- Hook 2: otra frase\nFin."
    assert all(h["Authorization"] == f"Bearer {LLAVE}" and h["Notion-Version"] for _, h, _ in http.llamadas)
    assert all(u.startswith("https://api.notion.com/v1/") for u, _, _ in http.llamadas)


@pytest.mark.parametrize("status, palabra", [(401, "llave"), (404, "compartida"), (429, "esperar"), (500, "500")])
def test_errores_en_llano_sin_la_llave(status, palabra):
    http = _Http({f"/pages/{PID}": (status, {"message": LLAVE})})
    with pytest.raises(notion.ErrorNotion) as e:
        notion.leer_pagina(LLAVE, PID, http=http)
    assert palabra in str(e.value) and LLAVE not in str(e.value)


def test_pagina_vacia():
    http = _Http({f"/pages/{PID}": (200, {"properties": {}}),
                  f"/blocks/{PID}/children": (200, {"results": [], "has_more": False})})
    with pytest.raises(notion.ErrorNotion):
        notion.leer_pagina(LLAVE, PID, http=http)


def test_llave_cifrada_en_kv(base_temporal, monkeypatch):
    import sqlalchemy as sa
    monkeypatch.setenv("FLASK_SECRET_KEY", "clave-de-prueba-larga-1234567890")
    assert not notion.conectado("acme") and notion.llave("acme") is None
    notion.guardar_llave("acme", LLAVE)
    notion.guardar_llave("acme", LLAVE + "b")
    assert notion.conectado("acme") and notion.llave("acme") == LLAVE + "b"
    with base_temporal.conectar() as con:
        crudo = con.execute(sa.select(base_temporal.kv.c.valor).where(base_temporal.kv.c.clave == "notion:acme")).scalar()
    assert LLAVE not in crudo
    notion.borrar("acme")
    assert not notion.conectado("acme")


def test_leer_lote_de_notion_trae_la_pagina(base_temporal, monkeypatch):
    from guiones import datos, lectura
    from tests.fixtures_guiones import GUION_CRUDO, TEXTO, fake
    monkeypatch.setattr(notion, "llave", lambda c: LLAVE)
    monkeypatch.setattr(notion, "leer_pagina", lambda llave, pid, http=None: ("Batch", TEXTO))
    lid = datos.crear_lote("acme", "", fuente="notion", notion_page_id=PID)
    lectura.leer_lote(lid, llamar=fake({"guiones": [GUION_CRUDO]}))
    [lote] = datos.lotes("acme")
    assert lote["estado"] == "leido" and lote["titulo"] == "Batch" and lote["guiones"]


def test_leer_lote_de_notion_con_error(base_temporal, monkeypatch):
    from guiones import datos, lectura
    from tests.fixtures_guiones import fake

    def falla(llave, pid, http=None):
        raise notion.ErrorNotion("Esa página no está compartida con tu integración de Notion.")
    monkeypatch.setattr(notion, "llave", lambda c: LLAVE)
    monkeypatch.setattr(notion, "leer_pagina", falla)
    lid = datos.crear_lote("acme", "", fuente="notion", notion_page_id=PID)
    lectura.leer_lote(lid, llamar=fake({}))
    assert "compartida" in datos.lotes("acme")[0]["aviso"]
