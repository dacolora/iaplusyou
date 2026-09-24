import referentes.sugerir as sugerir


def _cand(id, familia, variantes=1, dias=1, dolor="d", firma="f"):
    return {"id": id, "familia": familia, "variantes": variantes, "dias": dias, "dolor": dolor, "firma": firma,
            "clasificacion": "fuente", "etapa": "TOF", "titular": f"T{id}", "imagen_url": f"https://cdn/{id}.jpg"}


def test_elegir_una_familia_distinta_por_sugerencia():
    cands = [
        _cand(1, "ugc", variantes=1, dias=10),   # score 10
        _cand(2, "ugc", variantes=5, dias=10),   # score 50, misma familia que #1 — se salta si #1 ya entró
        _cand(3, "unboxing", variantes=2, dias=3),  # score 6
        _cand(4, "comparacion", variantes=1, dias=1),  # score 1
    ]
    elegidos = sugerir.elegir(cands, objetivo=2)
    familias = [c["familia"] for c in elegidos]
    assert len(elegidos) == 2
    assert len(set(familias)) == len(familias)
    # Orden por score desc dentro de "una familia distinta a la vez": la familia con mayor score
    # de cada grupo entra primero.
    assert elegidos[0]["id"] == 2  # ugc con mayor score gana sobre ugc#1
    assert elegidos[1]["id"] == 3  # unboxing es la siguiente familia distinta por score


def test_elegir_minimo_uno_aunque_objetivo_sea_cero_o_negativo():
    cands = [_cand(1, "ugc")]
    assert len(sugerir.elegir(cands, objetivo=0)) == 1
    assert len(sugerir.elegir(cands, objetivo=-3)) == 1


def test_elegir_lista_vacia():
    assert sugerir.elegir([], objetivo=5) == []


def test_candidatos_filtra_clasificacion_y_excluidos(monkeypatch):
    filas = [
        {"id": 1, "clasificacion": "fuente", "variantes": 1, "dias": 1, "familia": "a", "dolor": "", "firma": "",
         "etapa": "TOF", "titular": "", "imagen_url": ""},
        {"id": 2, "clasificacion": "pendiente", "variantes": 9, "dias": 9, "familia": "b", "dolor": "", "firma": "",
         "etapa": "TOF", "titular": "", "imagen_url": ""},
        {"id": 3, "clasificacion": "claude", "variantes": 2, "dias": 2, "familia": "c", "dolor": "", "firma": "",
         "etapa": "TOF", "titular": "", "imagen_url": ""},
    ]
    import referentes.datos as referentes_datos
    monkeypatch.setattr(referentes_datos, "listar", lambda cliente, filtros, pagina, por_pagina: {"items": filas})
    out = sugerir.candidatos("cliente-x", "TOF", excluir_ids={3}, limite=50)
    ids = [c["id"] for c in out]
    assert ids == [1]  # #2 fuera por clasificacion=pendiente, #3 fuera por excluir_ids


def test_sugerir_combina_candidatos_y_elegir(monkeypatch):
    filas = [
        {"id": 1, "clasificacion": "fuente", "variantes": 3, "dias": 3, "familia": "a", "dolor": "", "firma": "",
         "etapa": "TOF", "titular": "", "imagen_url": ""},
        {"id": 2, "clasificacion": "fuente", "variantes": 1, "dias": 1, "familia": "b", "dolor": "", "firma": "",
         "etapa": "TOF", "titular": "", "imagen_url": ""},
    ]
    import referentes.datos as referentes_datos
    monkeypatch.setattr(referentes_datos, "listar", lambda cliente, filtros, pagina, por_pagina: {"items": filas})
    out = sugerir.sugerir("cliente-x", "TOF", excluir_ids=set(), objetivo=1)
    assert len(out) == 1 and out[0]["id"] == 1
