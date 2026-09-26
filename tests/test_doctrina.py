"""Doctrina de venta (spec 2026-09-25): vocabulario, textos, ángulo y verificador de cifras."""
import pytest


def test_vocabulario_es_el_del_spec():
    import doctrina
    assert doctrina.CONSCIENCIAS == ("inconsciente", "consciente_del_problema", "consciente_de_la_solucion",
                                     "consciente_del_producto", "muy_consciente")
    assert doctrina.LEADS == ("oferta", "promesa", "problema_solucion", "secreto", "proclamacion", "historia")
    assert set(doctrina.SOFISTICACIONES) == {1, 2, 3, 4, 5}
    assert doctrina.SOFISTICACIONES[3] == "mecanismo" and doctrina.SOFISTICACIONES[5] == "identificacion"
    assert doctrina.FUENTES_PRUEBA == ("ficha", "comentarios", "demostracion")
    assert doctrina.REBANADAS == ("base", "investigar", "angulo", "gancho", "guion", "video", "caption",
                                  "clasificar", "revisar")
    assert doctrina.ANGULO_VERSION == 1


def test_normalizar_consciencia_acepta_espanol_ingles_y_variantes():
    import doctrina
    assert doctrina.normalizar_consciencia("consciente_del_problema") == "consciente_del_problema"
    assert doctrina.normalizar_consciencia("Consciente del problema") == "consciente_del_problema"
    assert doctrina.normalizar_consciencia("problem-aware") == "consciente_del_problema"
    assert doctrina.normalizar_consciencia("Most Aware") == "muy_consciente"
    assert doctrina.normalizar_consciencia("unaware") == "inconsciente"
    assert doctrina.normalizar_consciencia("solution-aware") == "consciente_de_la_solucion"
    assert doctrina.normalizar_consciencia("product-aware") == "consciente_del_producto"
    assert doctrina.normalizar_consciencia("dormido") is None
    assert doctrina.normalizar_consciencia(None) is None
    assert doctrina.normalizar_consciencia("") is None


def test_lead_por_consciencia_sigue_la_tabla_de_great_leads():
    import doctrina
    assert doctrina.lead_por_consciencia("muy_consciente") == ("oferta",)
    assert doctrina.lead_por_consciencia("consciente_del_producto")[0] == "promesa"
    assert doctrina.lead_por_consciencia("consciente_del_problema")[0] == "problema_solucion"
    inconsciente = doctrina.lead_por_consciencia("inconsciente")
    assert "oferta" not in inconsciente and "promesa" not in inconsciente and "historia" in inconsciente
    # acepta el inglés de referentes y devuelve vacío ante lo desconocido
    assert doctrina.lead_por_consciencia("problem-aware") == doctrina.lead_por_consciencia("consciente_del_problema")
    assert doctrina.lead_por_consciencia("rara") == ()
    assert doctrina.lead_por_consciencia(None) == ()


def test_cada_rebanada_existe_y_respeta_su_presupuesto():
    import doctrina
    for nombre in doctrina.REBANADAS:
        t = doctrina._cargar(nombre)
        assert t.strip(), nombre
        assert "TODO" not in t and "TBD" not in t, nombre
        assert doctrina.palabras(nombre) <= doctrina.PRESUPUESTO[nombre], (nombre, doctrina.palabras(nombre))
    for combo, rebanadas in doctrina.COMBINACIONES.items():
        total = len(doctrina.texto(*rebanadas).split())
        assert total <= doctrina.TOPE_COMBINACION, (combo, total)


def test_texto_pone_base_primero_y_no_la_repite():
    import doctrina
    t = doctrina.texto("gancho", "base", "angulo")
    assert t.startswith(doctrina.ENCABEZADO)
    base = doctrina._cargar("base").strip()
    assert t.count(base) == 1
    assert t.index(base) < t.index(doctrina._cargar("angulo").strip())
    assert t.index(doctrina._cargar("angulo").strip()) > t.index(doctrina._cargar("gancho").strip())
    with pytest.raises(ValueError):
        doctrina.texto("inventada")


def test_bloque_system_lleva_cache_y_extra_aparte():
    import doctrina
    bloques = doctrina.bloque_system("caption", extra="INSTRUCCIONES DEL SITIO")
    assert len(bloques) == 2
    assert bloques[0]["type"] == "text" and bloques[0]["cache_control"] == {"type": "ephemeral"}
    assert bloques[0]["text"] == doctrina.texto("caption")
    assert bloques[1] == {"type": "text", "text": "INSTRUCCIONES DEL SITIO"}
    assert len(doctrina.bloque_system("video")) == 1


def test_cada_principio_cita_su_fuente():
    """Cada rebanada nombra al menos dos de los autores entre paréntesis: así
    quien lea el .md puede ir al libro (spec §3.1)."""
    import doctrina
    autores = ("Kennedy", "Hopkins", "Ogilvy", "Great Leads", "Schwartz", "Theriot")
    for nombre in doctrina.REBANADAS:
        t = doctrina._cargar(nombre)
        assert sum(1 for a in autores if a in t) >= 2, nombre


ANGULO_OK = {
    "audiencia": "mujer 30-45 que ya rompió tres pares de chanclas baratas este verano",
    "consciencia": "consciente_del_problema", "sofisticacion": 3,
    "deseo": "dejar de comprar chanclas cada verano",
    "promesa": "las últimas chanclas que compras este verano",
    "mecanismo": "suela de doble densidad cosida, no pegada",
    "pruebas": [{"texto": "suela cosida a mano, garantía de 2 años", "fuente": "ficha"},
                {"texto": "se ve la suela doblarse y volver sin marca", "fuente": "demostracion"}],
    "lead": "problema_solucion",
    "gancho": "Si ya se te rompió la tercera chancla este verano, mira esto",
    "faltantes": ["no hay ninguna cita de compradores sobre durabilidad"],
}
DATOS = "Chancla Rose. Suela de doble densidad cosida a mano. Garantía de 2 años. Precio 89.900 COP."


def test_validar_angulo_limpia_y_acepta_uno_bueno():
    import doctrina
    limpio, errores = doctrina.validar_angulo(dict(ANGULO_OK, consciencia="Problem-aware", sofisticacion="3"), DATOS)
    assert errores == []
    assert limpio["consciencia"] == "consciente_del_problema" and limpio["sofisticacion"] == 3
    assert limpio["version"] == doctrina.ANGULO_VERSION
    assert len(limpio["pruebas"]) == 2 and limpio["faltantes"] == ANGULO_OK["faltantes"]


def test_validar_angulo_reporta_cada_regla():
    import doctrina
    _, e = doctrina.validar_angulo({k: v for k, v in ANGULO_OK.items() if k != "promesa"})
    assert "campo_faltante:promesa" in e
    _, e = doctrina.validar_angulo(dict(ANGULO_OK, consciencia="dormido", lead="grito", sofisticacion=9))
    assert {"valor_invalido:consciencia", "valor_invalido:lead", "valor_invalido:sofisticacion"} <= set(e)
    _, e = doctrina.validar_angulo(dict(ANGULO_OK, promesa="Dura más. Y además es más cómoda"))
    assert "promesa_multiple" in e
    _, e = doctrina.validar_angulo(dict(ANGULO_OK, sofisticacion=4, mecanismo=""))
    assert "mecanismo_obligatorio" in e
    limpio, e = doctrina.validar_angulo(dict(ANGULO_OK, sofisticacion=2, mecanismo=None))
    assert e == [] and limpio["mecanismo"] is None
    _, e = doctrina.validar_angulo(dict(ANGULO_OK, gancho=" ".join(["palabra"] * 13)))
    assert "gancho_largo" in e


def test_validar_angulo_descarta_pruebas_sin_fuente_y_las_anota():
    import doctrina
    pruebas = [{"texto": "dura 10 años", "fuente": "me lo imagino"}, {"texto": "", "fuente": "ficha"},
               {"texto": "garantía de 2 años", "fuente": "ficha"}]
    limpio, e = doctrina.validar_angulo(dict(ANGULO_OK, pruebas=pruebas))
    assert e == []
    assert limpio["pruebas"] == [{"texto": "garantía de 2 años", "fuente": "ficha"}]
    assert any("prueba sin fuente" in f and "dura 10 años" in f for f in limpio["faltantes"])


def test_validar_angulo_verifica_cifras_contra_los_datos():
    import doctrina
    con_cifra = dict(ANGULO_OK, promesa="47 % menos roturas este verano",
                     pruebas=[{"texto": "el 90 % de las compradoras repite", "fuente": "comentarios"},
                              {"texto": "garantía de 2 años", "fuente": "ficha"}])
    limpio, e = doctrina.validar_angulo(con_cifra, DATOS)
    assert "cifra_no_verificada:47 %" in e or "cifra_no_verificada:47%" in e
    assert limpio["pruebas"] == [{"texto": "garantía de 2 años", "fuente": "ficha"}]
    assert any("90" in f for f in limpio["faltantes"])
    limpio, e = doctrina.validar_angulo(dict(ANGULO_OK, promesa="por 89.900 pesos, las últimas del verano"), DATOS)
    assert e == []


def test_validar_angulo_anota_el_lead_fuera_de_lo_recomendado():
    import doctrina
    limpio, e = doctrina.validar_angulo(dict(ANGULO_OK, lead="oferta"))
    assert e == [] and any("arranque fuera de lo recomendado" in f for f in limpio["faltantes"])


def test_verificar_cifras():
    import doctrina
    assert doctrina.verificar_cifras("baja un 47 % en 3 pasos", DATOS) == ["47 %"]
    assert doctrina.verificar_cifras("garantía de 2 años y 89900 COP", DATOS) == []
    assert doctrina.verificar_cifras("3x más duradera", DATOS) == ["3x"]
    assert doctrina.verificar_cifras("2 de cada 3 repiten", DATOS) == ["2 de cada 3"]
    assert doctrina.verificar_cifras("lista para 2026", "lanzamiento 2026") == []
    assert doctrina.verificar_cifras("$120 hoy", "precio: 120 USD") == []
    assert doctrina.verificar_cifras("sin cifras aquí", "") == []


def test_angulo_a_texto_muestra_los_campos_con_nombre_y_omite_vacios():
    import doctrina
    limpio, _ = doctrina.validar_angulo(dict(ANGULO_OK, mecanismo=None, sofisticacion=2, faltantes=[]))
    t = doctrina.angulo_a_texto(limpio)
    assert t.startswith("ÁNGULO")
    for frag in ("Audiencia:", "consciente del problema", "Sofisticación: 2", "Deseo:", "Promesa única:",
                 "Pruebas:", "[ficha]", "Arranque: problema-solución", "Gancho:"):
        assert frag in t, frag
    assert "Mecanismo" not in t and "Faltantes" not in t
    assert doctrina.angulo_a_texto(None) == ""


def test_angulo_vacio_tiene_todas_las_claves():
    import doctrina
    v = doctrina.angulo_vacio()
    assert set(v) == {"version", "audiencia", "consciencia", "sofisticacion", "deseo", "promesa", "mecanismo",
                      "pruebas", "lead", "gancho", "faltantes"}


def test_validar_angulo_promesa_mas_de_200_caracteres_es_promesa_multiple():
    import doctrina
    # Una promesa de 250 caracteres (una sola frase, sin puntos ni «;»)
    promesa_larga = "Una chancla que durará toda la vida y tu hija la heredará y tal vez la hija de tu hija y es tan resistente que solo la rompes si le das con un martillo desde el espacio exterior " + "z" * 72
    assert len(promesa_larga) > doctrina.MAX_CARACTERES_CAMPO
    limpio, e = doctrina.validar_angulo(dict(ANGULO_OK, promesa=promesa_larga))
    assert "promesa_multiple" in e


def test_validar_angulo_no_lanza_con_angulo_malformado():
    import doctrina
    # No-dict: string
    limpio, e = doctrina.validar_angulo("texto")
    assert isinstance(limpio, dict) and isinstance(e, list)
    assert "campo_faltante:audiencia" in e  # Falta todo
    # No-dict: list
    limpio, e = doctrina.validar_angulo(["a"])
    assert isinstance(limpio, dict) and isinstance(e, list)
    assert "campo_faltante:audiencia" in e
    # pruebas como dict en lugar de list
    limpio, e = doctrina.validar_angulo(dict(ANGULO_OK, pruebas={"texto": "durabilidad", "fuente": "ficha"}))
    assert isinstance(limpio, dict) and isinstance(e, list)
    # La prueba dentro del dict debe ser envuelta como lista
    assert len(limpio["pruebas"]) == 1 and limpio["pruebas"][0]["texto"] == "durabilidad"
    # faltantes como string en lugar de list
    limpio, e = doctrina.validar_angulo(dict(ANGULO_OK, faltantes="algo falta"))
    assert isinstance(limpio, dict) and isinstance(e, list)
    assert "algo falta" in limpio["faltantes"]
    # faltantes como int
    limpio, e = doctrina.validar_angulo(dict(ANGULO_OK, faltantes=42))
    assert isinstance(limpio, dict) and isinstance(e, list)
    assert limpio["faltantes"] == []
    # pruebas como int
    limpio, e = doctrina.validar_angulo(dict(ANGULO_OK, pruebas=42))
    assert isinstance(limpio, dict) and isinstance(e, list)
    assert limpio["pruebas"] == []
