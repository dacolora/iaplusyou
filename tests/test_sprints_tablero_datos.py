"""sprints.datos para el tablero (spec 2026-09-26): mercado, marcas y momento
del sprint; enfoque de la campaña; herencia sprint → campaña; campañas
repetidas permitidas con aviso."""
import pytest


def _persona(datos, **kw):
    return datos.crear_persona("acme", "Premium", resumen="Busca calidad", **kw)


def _familia(nombre="Antes y después"):
    from referentes import datos as rdatos
    rdatos.familia_asegurar(nombre, "Muestra el cambio")
    return nombre


def test_crear_sprint_guarda_mercado_marcas_y_momento(base_temporal):
    from sprints import datos
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31", pais="mx", idioma="es",
                             marcas="Crocs\nSkechers https://www.facebook.com/ads/library/?view_all_page_id=123456",
                             momento={"clave": "dia_madre", "nombre": "Día de la madre", "contexto": "regalos",
                                      "inicio": "2026-05-01", "fin": "2026-05-10",
                                      "mood_visual": {"paleta": ["#fff", "rojo"]}})
    s = datos.sprint("acme", sid)
    assert s["pais"] == "MX" and s["idioma"] == "es"
    assert s["marcas"] == [{"nombre": "Crocs"}, {"nombre": "Skechers", "pagina_id": "123456"}]
    assert s["momento"]["nombre"] == "Día de la madre" and s["momento"]["clave"] == "dia_madre"
    assert s["momento"]["mood_visual"]["paleta"] == ["#fff"]


def test_crear_sprint_sin_mercado_queda_para_todos_los_paises_en_ingles(base_temporal):
    """Desde 2026-09-27 el sprint no lleva país: se trabaja en inglés y cada país
    se resuelve en la edición final."""
    from sprints import datos
    s = datos.sprint("acme", datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31"))
    assert s["pais"] is None and s["idioma"] == "en" and s["marcas"] == [] and s["momento"] is None


@pytest.mark.parametrize("campos", [dict(pais="Colombia"), dict(idioma="xx"), dict(marcas=5),
                                    dict(marcas=[{"nombre": "X", "pagina_id": "abc"}]),
                                    dict(momento={"nombre": "X", "inicio": "mañana"})])
def test_crear_sprint_valida_los_campos_nuevos(base_temporal, campos):
    from sprints import datos
    with pytest.raises(datos.ErrorDatos):
        datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31", **campos)
    assert datos.sprints("acme") == []


def test_normalizar_marcas_acepta_texto_links_e_ids(base_temporal):
    from sprints import datos
    texto = ("Crocs, crocs\nhttps://www.facebook.com/ads/library/?active_status=all&view_all_page_id=987654\n"
             "Hoka 1234567")
    assert datos.normalizar_marcas(texto) == [{"nombre": "Crocs"},
                                             {"nombre": "Página 987654", "pagina_id": "987654"},
                                             {"nombre": "Hoka", "pagina_id": "1234567"}]
    assert datos.normalizar_marcas("") == [] and datos.normalizar_marcas(None) == []
    with pytest.raises(datos.ErrorDatos):
        datos.normalizar_marcas(",".join(f"Marca{i}" for i in range(datos.MAX_MARCAS + 1)))


def test_actualizar_sprint_valida_nombre_y_campos_nuevos(base_temporal):
    from sprints import datos
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31")
    datos.actualizar_sprint("acme", sid, pais="co", idioma="en", marcas="Nike", momento="Hot Sale")
    s = datos.sprint("acme", sid)
    assert (s["pais"], s["idioma"], s["marcas"], s["momento"]) == ("CO", "en", [{"nombre": "Nike"}], {"nombre": "Hot Sale"})
    datos.actualizar_sprint("acme", sid, momento="")
    assert datos.sprint("acme", sid)["momento"] is None
    for malo in (dict(nombre="  "), dict(pais="COL"), dict(idioma="klingon")):
        with pytest.raises(datos.ErrorDatos):
            datos.actualizar_sprint("acme", sid, **malo)


def test_agregar_campana_con_enfoque(base_temporal):
    from sprints import datos
    pid = _persona(datos)
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31")
    fam = _familia()
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", None, 2, 1, funnel="mof",
                                consciencia="consciente del problema", dolor="pies fríos", familias=[fam, fam])
    c = datos.campana("acme", cid)
    assert (c["funnel"], c["consciencia"], c["dolor"], c["familias"]) == ("mof", "consciente_del_problema", "pies fríos", [fam])
    assert c["pais"] is None and c["idioma"] is None and c["marcas"] is None


def test_agregar_campana_precarga_la_consciencia_de_la_persona_de_nicho(base_temporal):
    from sprints import datos
    pid = datos.crear_persona("acme", "Melissa", origen="investigada",
                              extra={"conciencia": {"nivel": "Consciente del problema", "detalle": "lo sufre"}})
    otra = datos.crear_persona("acme", "Manual")
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31")
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", None, 1, 0)
    assert datos.campana("acme", cid)["consciencia"] == "consciente_del_problema"
    datos.actualizar_campana("acme", cid, consciencia=None)
    datos.actualizar_campana("acme", cid, persona_id=pid)          # vacía: vuelve a precargar
    assert datos.campana("acme", cid)["consciencia"] == "consciente_del_problema"
    datos.actualizar_campana("acme", cid, persona_id=otra)         # la que ya tiene se respeta
    assert datos.campana("acme", cid)["consciencia"] == "consciente_del_problema"
    assert datos.campana("acme", cid)["persona_id"] == otra


@pytest.mark.parametrize("campos", [dict(consciencia="despistado"), dict(dolor="x" * 301),
                                    dict(familias=["No existe"]), dict(familias="Antes y después"),
                                    dict(pais="Colombia"), dict(idioma="xx"), dict(funnel="tofu"),
                                    dict(persona_id=999), dict(persona_id="abc"), dict(catalogo_id="  "),
                                    dict(marcas=[{"nombre": "X", "pagina_id": "abc"}])])
def test_actualizar_campana_valida_cada_campo(base_temporal, campos):
    from sprints import datos
    pid = _persona(datos)
    _familia()
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31")
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", None, 1, 0)
    with pytest.raises(datos.ErrorDatos):
        datos.actualizar_campana("acme", cid, **campos)


def test_efectivos_hereda_del_sprint_y_cambia_solo_aqui(base_temporal):
    from sprints import datos
    pid = _persona(datos)
    # Un sprint viejo, con país e idioma (los nuevos no llevan país y van en inglés).
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31", pais="CO", idioma="es", marcas="Crocs",
                             momento="Hot Sale")
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", None, 1, 0)
    ef = datos.efectivos_de("acme", datos.campana("acme", cid))
    assert (ef["pais"], ef["idioma"], ef["marcas"], ef["momento"]) == ("CO", "es", [{"nombre": "Crocs"}], {"nombre": "Hot Sale"})
    assert ef["hereda"] == {"pais": True, "idioma": True, "marcas": True}
    datos.actualizar_campana("acme", cid, pais="us", idioma="en", marcas="Hoka")
    ef = datos.efectivos_de("acme", datos.campana("acme", cid))
    assert (ef["pais"], ef["idioma"], ef["marcas"]) == ("US", "en", [{"nombre": "Hoka"}])
    assert ef["hereda"] == {"pais": False, "idioma": False, "marcas": False}
    datos.actualizar_campana("acme", cid, pais="", idioma="", marcas="")        # vacío = vuelve a heredar
    ef = datos.efectivos_de("acme", datos.campana("acme", cid))
    assert ef["pais"] == "CO" and ef["marcas"] == [{"nombre": "Crocs"}] and all(ef["hereda"].values())
    assert datos.sprint("acme", sid)["campanas"][0]["efectivos"]["pais"] == "CO"


def test_campanas_identicas_se_permiten_con_aviso(base_temporal):
    from sprints import datos
    pid = _persona(datos)
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31")
    c1 = datos.agregar_campana("acme", sid, pid, "espejo_led", None, 1, 0)
    c2 = datos.agregar_campana("acme", sid, pid, "espejo_led", None, 1, 0)
    c3 = datos.agregar_campana("acme", sid, pid, "espejo_led", None, 1, 0, funnel="bof")
    assert datos.campanas_identicas("acme", c2) == [1]
    assert datos.campanas_identicas("acme", c1) == [2]
    assert datos.campanas_identicas("acme", c3) == []
    assert len(datos.campanas("acme", sid)) == 3


def test_ya_no_hay_personas_genericas(base_temporal):
    from sprints import datos
    assert not hasattr(datos, "asegurar_personajes_predeterminados")
    assert not hasattr(datos, "CampanaDuplicada")
