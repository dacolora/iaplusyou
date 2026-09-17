"""Bloque 4 — variantes de Final edition (guion hook/estructura, finales
`__v<n>`), duplicar sesión y archivar concepto."""
import shutil

import pytest

from final_edition import cortes

# `entorno_fe` es el fixture `entorno` de test_fe_producir (todas las capas
# falsas); `clip` es su dependencia de módulo. Importarlos al namespace basta
# para que pytest los resuelva.
from tests.test_fe_producir import clip, entorno as entorno_fe  # noqa: F401

_sin_ffmpeg = pytest.mark.skipif(
    shutil.which(cortes.FFMPEG) is None or shutil.which(cortes.FFPROBE) is None,
    reason="ffmpeg/ffprobe no instalados",
)


def test_variar_guion_hook_y_estructura(monkeypatch):
    from final_edition import guion as g
    capturado = {}

    def falso(system, mensaje, duracion, ajustar):
        capturado["system"], capturado["mensaje"] = system, mensaje
        return ajustar({"bloques": [{"rol": "hook", "inicio_s": 0, "fin_s": 3, "texto_pantalla": "X", "texto_voz": "Y"}]}), 0.01
    monkeypatch.setattr(g, "_generar_con_correccion", falso)
    base = {"idioma": "es", "pais": "CO", "precio_base": 100,
            "bloques": [{"rol": "hook", "inicio_s": 0, "fin_s": 3, "texto_pantalla": "A", "texto_voz": "B"}]}
    v, costo = g.variar_guion(base, "hook", "")
    assert v["idioma"] == "es" and v["pais"] == "CO" and v["precio_base"] == 100 and costo == 0.01
    assert "hook" in capturado["mensaje"].lower() and "CTA" in capturado["mensaje"]
    assert base["bloques"][0]["texto_pantalla"] == "A"  # no muta el base
    g.variar_guion(base, "estructura", "")
    m = capturado["mensaje"].lower()
    assert "estructura" in m
    # I3: la variante de estructura NO puede reordenar bloques (validar_guion
    # exige roles fijos en orden): el mensaje pide conservar roles, orden y
    # tiempos y variar el ángulo dentro de cada bloque.
    assert "mismo orden" in m and "hook, problema, producto, prueba, cta" in m
    assert "mismos tiempos" in m and "no agregues, quites ni reordenes" in m
    assert "cta distinto" in m
    with pytest.raises(ValueError):
        g.variar_guion(base, "otra", "")


def test_crear_final_con_variante_y_finales(base_temporal):
    import creative_flow as cf
    cf_id = cf.crear("acme", [], [], [], "acción", 10, "", "A")
    cf.actualizar("acme", cf_id, estado="video_listo", video_url="https://r2/v.mp4")
    f0 = cf.crear_final("acme", cf_id, "es", "CO")
    f1 = cf.crear_final("acme", cf_id, "es", "CO", variante=1)
    assert f0 == f"{cf_id}__es_CO" and f1 == f"{cf_id}__es_CO__v1"
    fs = cf.finales("acme", cf_id)
    assert [(f["id"], f["variante"]) for f in fs] == [(f0, None), (f1, 1)]
    assert cf.final_por_legado("acme", f1)["variante"] == 1
    assert cf.final_por_legado("acme", f0)["variante"] is None
    assert cf.pieza_id_por_legado("acme", f1)
    # Reproducir la variante reinicia la misma fila, no crea otra.
    assert cf.crear_final("acme", cf_id, "es", "CO", variante=1) == f1
    assert len(cf.finales("acme", cf_id)) == 2


def test_duplicar_y_archivar(base_temporal):
    import creative_flow as cf
    import experimentos as ex
    cf_id = cf.crear("acme", [], ["p1"], [], "acción central", 10, "alegre", "A", referencias_urls=["https://r"])
    cf.actualizar("acme", cf_id, estado="video_listo", video_url="https://r2/v.mp4", modelo="wan3")
    nuevo = cf.duplicar("acme", cf_id, modelo="kling_o3", enfoque="persona")
    assert nuevo != cf_id
    e = cf.cargar("acme")[nuevo]
    assert e["accion_central"] == "acción central" and e["modelo"] == "kling_o3" and e["estado"] in ("prompt_listo", "prompt_pendiente")
    assert e.get("derivado_de") == cf_id and e.get("enfoque") == "persona"
    assert e["productos_ids"] == ["p1"] and e["tono"] == "alegre" and e["referencias_urls"] == ["https://r"]
    assert e["video_url"] is None  # el clon no se copia: la copia se genera de nuevo
    # Con enfoque nuevo el prompt se arma como en Crear (marca + enfoque) y el
    # nombre/con_persona reflejan el enfoque nuevo, no el del original.
    assert e["prompt_relleno"] and "acción central" in e["prompt_relleno"]
    assert e["enfoque_nombre"] == "Con persona" and e["con_persona"] is True
    # Sin modelo ni enfoque: conserva los del original.
    otro = cf.duplicar("acme", cf_id)
    e2 = cf.cargar("acme")[otro]
    assert e2["modelo"] == "wan3" and e2.get("enfoque") is None and e2["derivado_de"] == cf_id
    with pytest.raises(ValueError):
        cf.duplicar("acme", cf_id, enfoque="inexistente")
    assert cf.concepto_archivado("acme", cf_id) is False
    cf.archivar_concepto("acme", cf_id, "perdió el escalón 3")
    assert cf.concepto_archivado("acme", cf_id) is True
    assert all(p["legado_id"] != cf_id for p in ex.elegibles("acme"))
    assert cf.concepto_archivado("acme", "cf_inexistente") is False


def test_duplicar_conserva_o_rearma_prompt(base_temporal):
    import creative_flow as cf
    import flowplus_prompt
    cf_id = cf.crear("acme", [], ["p1"], [], "sandalia sobre arena", 10, "", "A", referencias_urls=["https://r"])
    refs = [{"tipo": "imagen", "etiqueta": "@Imagen 1", "url": "https://r", "frame_url": "https://r"}]
    prompt_orig = flowplus_prompt.armar("sandalia sobre arena", refs, enfoque="producto")
    cf.actualizar("acme", cf_id, estado="video_listo", video_url="https://r2/v.mp4", modelo="wan3",
                  prompt_relleno=prompt_orig, referencias=refs, enfoque="producto",
                  enfoque_nombre="Solo producto", con_persona=False)
    # Mismo enfoque (implícito o explícito) y otro modelo: el prompt viaja tal cual.
    n1 = cf.duplicar("acme", cf_id, modelo="kling_o3")
    e = cf.cargar("acme")[n1]
    assert e["prompt_relleno"] == prompt_orig and e["enfoque_nombre"] == "Solo producto" and e["con_persona"] is False
    n2 = cf.duplicar("acme", cf_id, enfoque="producto")
    e = cf.cargar("acme")[n2]
    assert e["prompt_relleno"] == prompt_orig
    # Otro enfoque: se rearma igual que una sesión nueva de Crear (un video
    # pide el sonido de la escena).
    n3 = cf.duplicar("acme", cf_id, enfoque="unboxing")
    e = cf.cargar("acme")[n3]
    esperado = flowplus_prompt.armar("sandalia sobre arena", refs, con_persona=True, enfoque="unboxing", con_sonido=True)
    assert e["prompt_relleno"] == esperado and e["prompt_relleno"] != prompt_orig
    assert e["enfoque_nombre"] == "Unboxing" and e["con_persona"] is True and e["enfoque"] == "unboxing"
    assert e["referencias"] == refs and e["accion_central"] == "sandalia sobre arena"


def test_producir_exige_variante_y_tipo_juntos(entorno_fe, monkeypatch):
    import creative_flow as cf
    import final_edition
    cf_id = entorno_fe["cf_id"]
    llamadas = []
    monkeypatch.setattr(cf, "crear_final", lambda *a, **k: llamadas.append((a, k)))
    with pytest.raises(ValueError, match="variante"):
        final_edition.producir("acme", cf_id, "es", "CO", {"variante_tipo": "hook"})
    with pytest.raises(ValueError, match="variante"):
        final_edition.producir("acme", cf_id, "es", "CO", {"variante": 1})
    assert llamadas == []  # falla antes de tocar ninguna final
    assert cf.finales("acme", cf_id) == []


@_sin_ffmpeg
def test_producir_variante_usa_guion_variante_y_no_pisa_base(entorno_fe, monkeypatch):
    import creative_flow as cf
    import final_edition
    from final_edition import guion as g
    cf_id = entorno_fe["cf_id"]
    base = {"idioma": "es", "pais": "CO",
            "bloques": [{"rol": "hook", "inicio_s": 0, "fin_s": 3, "texto_pantalla": "A", "texto_voz": "B"}]}
    cf.guardar_guion_base("acme", cf_id, base)
    monkeypatch.setattr(g, "variar_guion",
                        lambda gb, tipo, marca: (dict(gb, bloques=[dict(gb["bloques"][0], texto_pantalla="HOOK2")]), 0.02))
    final_id, resumen = final_edition.producir("acme", cf_id, "es", "CO", {"variante": 1, "variante_tipo": "hook"})
    assert final_id.endswith("__v1") and resumen["estado"] in ("listo", "degradada")
    assert resumen["variante"] == 1
    assert resumen["guion"]["bloques"][0]["texto_pantalla"] == "HOOK2"
    assert cf.guion_base("acme", cf_id)["bloques"][0]["texto_pantalla"] == "A"
    assert resumen["capas"]["guion"]["parametros"]["variante_tipo"] == "hook"
    assert resumen["capas"]["guion"]["costo_usd"] == pytest.approx(0.04)  # variar 0.02 + localizar 0.02


@_sin_ffmpeg
def test_producir_variante_cambia_voz_o_musica(entorno_fe, monkeypatch):
    """Sin `voz`/`estilo_musica` en opciones: `hook` toma otra voz distinta de
    la final original; `estructura` otro estilo de música."""
    import final_edition
    from final_edition import guion as g, tipos
    from providers import fal_audio
    import creative_flow as cf
    cf_id = entorno_fe["cf_id"]
    _, original = final_edition.producir("acme", cf_id, "es", "CO", {})
    voz_original = original["capas"]["voz"]["parametros"]["voz"]
    estilo_original = original["capas"]["musica"]["parametros"]["estilo"]

    monkeypatch.setattr(g, "variar_guion", lambda gb, tipo, marca: (dict(gb), 0.0))
    _, v1 = final_edition.producir("acme", cf_id, "es", "CO", {"variante": 1, "variante_tipo": "hook"})
    _, v2 = final_edition.producir("acme", cf_id, "es", "CO", {"variante": 2, "variante_tipo": "estructura"})
    voces = fal_audio.VOCES["es"]
    assert v1["capas"]["voz"]["parametros"]["voz"] == voces[(voces.index(voz_original) + 1) % len(voces)]
    assert v1["capas"]["musica"]["parametros"]["estilo"] == estilo_original
    estilos = list(tipos.ESTILOS_MUSICA)
    assert v2["capas"]["musica"]["parametros"]["estilo"] == estilos[(estilos.index(estilo_original) + 1) % len(estilos)]
    assert v2["capas"]["voz"]["parametros"]["voz"] == voz_original
    assert [f["variante"] for f in cf.finales("acme", cf_id)] == [None, 1, 2]


def test_job_id_final_con_variante():
    from tareas import final_edition as te
    assert te.job_id_final("acme", "cf_1", "es", "CO") == "acme__cf_1__es_CO__final"
    assert te.job_id_final("acme", "cf_1", "es", "CO", variante=2) == "acme__cf_1__es_CO__v2__final"


def test_interrumpida_marca_error_en_la_variante(base_temporal):
    import creative_flow as cf
    from tareas import final_edition as te
    cf_id = cf.crear("acme", [], [], [], "acción", 10, "", "A")
    f0 = cf.crear_final("acme", cf_id, "es", "CO")
    f2 = cf.crear_final("acme", cf_id, "es", "CO", variante=2)
    tarea = {"payload": {"cliente": "acme", "cf_id": cf_id, "idioma": "es", "pais": "CO",
                         "opciones": {"variante": 2, "variante_tipo": "hook"}}}
    te.interrumpida(tarea, "worker caído")
    assert cf.final_por_legado("acme", f2)["estado"] == "error"
    assert cf.final_por_legado("acme", f0)["estado"] == "generando"
