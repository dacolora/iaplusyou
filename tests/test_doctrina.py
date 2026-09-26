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
