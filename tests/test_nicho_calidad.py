"""Qué es un avatar completo y cómo se funde lo que completa Claude (spec 2026-09-29 §2)."""

COMPLETO = {"nombre": "Ana / La que carga", "deseo": "Quiero lavar sin cargar", "demografia": "Mujer 35-45, ciudad, dos hijos",
            "edad_rango": "35-45", "emocion": "Cansancio", "identidad": {"quiere_que_vean": "organizada", "cree_de_si": "práctica", "quiere_lograr": "una casa que funcione"},
            "encaje_producto": "Cápsulas: nada que cargar", "soluciones_previas": [{"que": "Líquido de marca", "por_que_fallo": ["pesa"]}],
            "situaciones": ["Cargando garrafas", "Limpiando el goteo"], "comportamiento": "Sigue con el líquido",
            "conciencia": {"nivel": "consciente_del_problema", "detalle": "sabe que pesa"}, "tono": "Directo",
            "palabras_clave": ["garrafa", "peso", "goteo"], "evidencia": [{"comentario_id": 1, "cita": "pesa demasiado"}, {"comentario_id": 2, "cita": "gotea todo"}]}


def test_completo_y_faltantes():
    from nicho import calidad
    assert calidad.faltantes(COMPLETO) == []
    vacio = {"nombre": "X"}
    assert calidad.faltantes(vacio) == ["deseo", "demografia", "edad_rango", "emocion", "identidad", "encaje_producto", "soluciones_previas",
                                        "situaciones", "comportamiento", "conciencia", "tono", "palabras_clave", "evidencia"]
    assert "evidencia" not in calidad.faltantes(vacio, con_evidencia=False)
    casi = dict(COMPLETO, situaciones=["una"], palabras_clave=["a", "b"], evidencia=COMPLETO["evidencia"][:1],
                soluciones_previas=[{"que": "Líquido", "por_que_fallo": []}], identidad={**COMPLETO["identidad"], "cree_de_si": " "},
                conciencia={"nivel": "", "detalle": "x"})
    assert calidad.faltantes(casi) == ["identidad", "soluciones_previas", "situaciones", "conciencia", "palabras_clave", "evidencia"]
    assert set(calidad.ETIQUETAS) == set(calidad.faltantes({"nombre": ""})) | {"nombre"}


def test_fundir_no_pisa_lo_lleno():
    from nicho import calidad
    sub = dict(COMPLETO, demografia="", situaciones=["Cargando garrafas"], palabras_clave=["garrafa"], identidad={"quiere_que_vean": "organizada"},
               conciencia={"nivel": "", "detalle": ""}, soluciones_previas=[])
    nuevos = {"demografia": "Mujer 30-40 (inferido)", "emocion": "OTRA", "situaciones": ["cargando garrafas", "En el súper"],
              "palabras_clave": ["peso", "garrafa", "goteo"], "identidad": {"quiere_que_vean": "OTRA", "cree_de_si": "práctica", "quiere_lograr": "orden"},
              "conciencia": {"nivel": "consciente_del_problema", "detalle": "sabe"}, "soluciones_previas": [{"que": "Polvo", "por_que_fallo": ["se apelmaza"]}]}
    f = calidad.fundir(sub, nuevos)
    assert f["demografia"] == "Mujer 30-40 (inferido)" and f["emocion"] == "Cansancio"                     # lo lleno se queda
    assert f["situaciones"] == ["Cargando garrafas", "En el súper"] and f["palabras_clave"] == ["garrafa", "peso", "goteo"]
    assert f["identidad"] == {"quiere_que_vean": "organizada", "cree_de_si": "práctica", "quiere_lograr": "orden"}
    assert f["conciencia"]["nivel"] == "consciente_del_problema" and f["soluciones_previas"] == [{"que": "Polvo", "por_que_fallo": ["se apelmaza"]}]
    assert f["evidencia"] == COMPLETO["evidencia"] and sub["demografia"] == ""                             # no toca la evidencia ni el original


def test_fundir_conserva_las_soluciones_que_ya_tenia():
    """Ruling 20 (1): `fundir` nunca descarta ni reescribe lo que el avatar ya
    tenía en `soluciones_previas` -- válida o no (una persona pudo escribir
    una solución sin "por qué falló"); solo agrega las nuevas válidas cuyo
    "que" no repite una ya existente (sin distinguir mayúsculas ni espacios)."""
    from nicho import calidad
    sub = {"soluciones_previas": [{"que": "Plantillas", "por_que_fallo": []}]}
    nuevos = {"soluciones_previas": [{"que": "plantillas", "por_que_fallo": ["x"]}, {"que": "Crema", "por_que_fallo": ["y"]}]}
    f = calidad.fundir(sub, nuevos)
    assert f["soluciones_previas"] == [{"que": "Plantillas", "por_que_fallo": []}, {"que": "Crema", "por_que_fallo": ["y"]}]
