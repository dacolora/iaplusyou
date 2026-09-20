import json
import os

import pytest

import ediciones as e
from final_edition import documento as d

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "documentos", "video_basico.json")


def _doc():
    with open(FIX, encoding="utf-8") as f:
        return json.load(f)


def test_crear_y_cargar_valida_y_normaliza(base_temporal):
    ed = e.crear("acme", "video", "Hook v1", _doc(), cf_id="cf1")
    cargada = e.cargar("acme", ed["id"])
    assert cargada["version_n"] == 0 and cargada["estado"] == "borrador"
    assert d.duracion_ms(cargada["documento"]) == 7000


def test_crear_rechaza_documento_invalido(base_temporal):
    doc = _doc(); doc["formato"] = "x"
    with pytest.raises(d.DocumentoInvalido):
        e.crear("acme", "video", "mal", doc)


def test_guardar_cas_dos_escrituras_una_pierde(base_temporal):
    ed = e.crear("acme", "video", "e", _doc())
    doc_a = _doc(); doc_a["miniatura_ms"] = 1000
    doc_b = _doc(); doc_b["miniatura_ms"] = 2000
    assert e.guardar("acme", ed["id"], doc_a, version_n=0) == 1
    with pytest.raises(e.Conflicto):
        e.guardar("acme", ed["id"], doc_b, version_n=0)
    assert e.cargar("acme", ed["id"])["documento"]["miniatura_ms"] == 1000


def test_guardar_marca_uso_de_materiales(base_temporal, monkeypatch):
    import materiales
    marcados = []
    monkeypatch.setattr(materiales, "marcar_uso", lambda ids: marcados.append(list(ids)))
    ed = e.crear("acme", "video", "e", _doc())
    e.guardar("acme", ed["id"], _doc(), version_n=0)
    assert marcados[-1] == [1, 2, 3]


def test_versionar_y_restaurar(base_temporal):
    ed = e.crear("acme", "video", "e", _doc())
    v1 = e.versionar("acme", ed["id"], "producir")
    assert v1["n"] == 1 and v1["motivo"] == "producir"
    doc2 = _doc(); doc2["miniatura_ms"] = 4200
    e.guardar("acme", ed["id"], doc2, version_n=0)
    assert e.cargar("acme", ed["id"])["documento"]["miniatura_ms"] == 4200
    e.restaurar("acme", ed["id"], 1)
    assert e.cargar("acme", ed["id"])["documento"]["miniatura_ms"] == 3000
    assert [v["n"] for v in e.versiones("acme", ed["id"])] == [1]


def test_versionar_concurrente_no_repite_n(base_temporal):
    import threading
    ed = e.crear("acme", "video", "e", _doc())
    errores = []

    def _trabajo():
        for _ in range(5):
            try:
                e.versionar("acme", ed["id"], "manual")
            except Exception as exc:
                errores.append(exc)

    hilos = [threading.Thread(target=_trabajo) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert errores == []
    assert sorted(v["n"] for v in e.versiones("acme", ed["id"])) == list(range(1, 11))


def test_restaurar_migra_el_documento_congelado(base_temporal, monkeypatch):
    ed = e.crear("acme", "video", "e", _doc())
    v = e.versionar("acme", ed["id"], "producir")
    llamadas = []
    original = e.documento_mod.migrar

    def _wrapper(doc):
        llamadas.append(doc)
        return original(doc)

    monkeypatch.setattr(e.documento_mod, "migrar", _wrapper)
    e.restaurar("acme", ed["id"], v["n"])
    assert len(llamadas) == 1
    assert llamadas[0] == v["documento"]


def test_no_cruza_clientes(base_temporal):
    ed = e.crear("acme", "video", "e", _doc())
    assert e.cargar("otro", ed["id"]) is None
    with pytest.raises(e.Conflicto):
        e.guardar("otro", ed["id"], _doc(), version_n=0)


def test_apuntar_final_escribe_edicion_version_id(base_temporal):
    import db
    import sqlalchemy as sa
    from tests.test_experimentos_db import _pieza
    # _pieza(db, cliente, tipo="final", ..., legado="cf_1__es_CO") inserta una
    # pieza final directa con ese legado_id (sin sesión de Crear).
    _pieza(db, "acme", legado="cf_1__es_CO")
    ed = e.crear("acme", "video", "e", _doc(), cf_id="cf_1")
    v = e.versionar("acme", ed["id"], "producir")
    assert e.apuntar_final("acme", "cf_1__es_CO", v["id"]) == 1
    with db.conectar() as con:
        val = con.execute(sa.select(db.pieza.c.edicion_version_id).where(db.pieza.c.legado_id == "cf_1__es_CO")).scalar()
    assert val == v["id"]
    # I12: devuelve las filas tocadas para que la tarea note una final ausente
    assert e.apuntar_final("acme", "cf_9__es_CO", v["id"]) == 0
    assert e.apuntar_final("otro", "cf_1__es_CO", v["id"]) == 0
