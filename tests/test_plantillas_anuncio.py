"""Recetas de tomas del director (spec 2026-09-18 §9, Etapa 3): datos puros,
actos en segundos y número de planos."""
import pytest

import flowplus_prompt
import plantillas_anuncio as pa


def test_ocho_recetas_con_ids_unicos_y_datos_completos():
    ids = [p["id"] for p in pa.PLANTILLAS]
    assert ids == ["antes_despues", "producto_estudio", "producto_entorno", "con_modelo", "ugc_sin_cara",
                   "ugc_silencioso", "unboxing", "recrear_referencia"]
    for p in pa.PLANTILLAS:
        assert p["nombre"].strip() and p["descripcion"].strip(), p["id"]
        assert p["enfoque"] is None or p["enfoque"] in flowplus_prompt.ENFOQUES, p["id"]
        assert p["enfoque"] != "libre", p["id"]
        assert p["camara_inicial"] is None or p["camara_inicial"] in flowplus_prompt.CAMARAS, p["id"]
        assert pa.por_id(p["id"]) is p


@pytest.mark.parametrize("p", [p for p in pa.PLANTILLAS if p["actos"]], ids=lambda p: p["id"])
def test_los_actos_cubren_de_0_a_100_sin_huecos(p):
    actos = p["actos"]
    assert actos[0]["desde_pct"] == 0 and actos[-1]["hasta_pct"] == 100
    for a, b in zip(actos, actos[1:]):
        assert a["hasta_pct"] == b["desde_pct"], p["id"]
    for a in actos:
        assert a["hasta_pct"] > a["desde_pct"] and a["nombre"].strip() and a["que_se_ve"].strip()


def test_recrear_referencia_no_tiene_actos_y_pide_video():
    p = pa.por_id("recrear_referencia")
    assert p["actos"] == () and p["requiere_video"] and "{video}" in p["instruccion"]
    assert not any(q["requiere_video"] for q in pa.PLANTILLAS if q["id"] != "recrear_referencia")


def test_ninguna_receta_obliga_a_quedarse_sin_nadie():
    """Regla de Daniel (2026-09-22): nada de «solo producto, sin nadie» por defecto."""
    for p in pa.PLANTILLAS:
        texto = " ".join(a["que_se_ve"] for a in p["actos"]) + " " + (p.get("instruccion") or "")
        assert "sin nadie" not in texto and "producto quieto" not in texto, p["id"]


def test_por_id_ignora_lo_desconocido():
    assert pa.por_id("no_existe") is None and pa.por_id(None) is None and pa.por_id(3) is None


@pytest.mark.parametrize("duracion", range(1, 31))
@pytest.mark.parametrize("pid", [p["id"] for p in pa.PLANTILLAS if p["actos"]])
def test_actos_en_segundos_contiguos_para_cualquier_duracion(pid, duracion):
    p = pa.por_id(pid)
    actos = pa.actos_en_segundos(p, duracion)
    assert actos and actos[0]["desde_s"] == 0 and actos[-1]["hasta_s"] == duracion
    for a, b in zip(actos, actos[1:]):
        assert a["hasta_s"] == b["desde_s"]
    assert all(a["hasta_s"] > a["desde_s"] for a in actos)
    assert len(actos) <= len(p["actos"])
    # Ningún acto se pierde: si una duración corta deja uno sin segundos, se suma a otro.
    juntos = " ".join(a["que_se_ve"] for a in actos)
    assert all(a["que_se_ve"] in juntos for a in p["actos"])


def test_actos_en_segundos_ejemplo_de_8_s():
    actos = pa.actos_en_segundos(pa.por_id("antes_despues"), 8)
    assert [(a["desde_s"], a["hasta_s"]) for a in actos] == [(0, 2), (2, 5), (5, 8)]


def test_n_planos_con_receta():
    p = pa.por_id("antes_despues")                 # 3 actos
    assert pa.n_planos(p, 8, base=2) == 3          # un plano por acto
    assert pa.n_planos(p, 30, base=5) == 5         # más planos que actos: se reparten dentro
    assert pa.n_planos(p, 5, base=1) == 2          # cada plano de al menos 2 s
    assert pa.n_planos(p, 2, base=1) == 1
    assert pa.n_planos(pa.por_id("recrear_referencia"), 8, base=2) == 2   # sin actos: la tabla de siempre


def test_bloque_para_el_director():
    lineas = pa.bloque_director(pa.por_id("antes_despues"), 8)
    texto = "\n".join(lineas)
    assert lineas[0].startswith("PLANTILLA: «Antes y después»")
    assert "- Acto 1 · 0-2 s · " in texto and "- Acto 3 · 5-8 s · " in texto
    assert "dolly_in" in texto and "La IDEA manda" in texto
    refs = [{"tipo": "video", "token": "Video 1"}, {"tipo": "imagen", "token": "Image 1"}]
    recrear = "\n".join(pa.bloque_director(pa.por_id("recrear_referencia"), 8, refs))
    assert "Video 1" in recrear and "Acto" not in recrear
