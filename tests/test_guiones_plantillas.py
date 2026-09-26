"""Plantillas: formato exacto del spec del cliente §2.4 y el invariante con refinador.validar."""
from guiones import duracion, plantillas, refinador
from tests.fixtures_guiones import BLOQUE, CLIP1, CLIP2, CONFIG, LINEAS

TEXTOS = {i: t for i, t in enumerate(LINEAS, 1)}


def _calc(c, indice, total):
    t = duracion.calcular_clip(c["momentos"], TEXTOS, 2.4)
    return dict(t, indice=indice, total=total, titulo=c["titulo"], lineas=c["lineas"], estado_inicio=c["estado_inicio"],
                estado_fin=c["estado_fin"], entornos=c["entornos"], es_final=indice == total)


def _fijos(c):
    return [t for m in c["momentos"] for t in m["textos"]]


ESPERADO_CLIP2 = """CLIP 2 of 2 — 13 seconds — 9:16 — The thin sole
Start image = last frame of Clip 1.
START STATE: Hands empty.
DIALOGUE (exact words, natural unhurried pace, lip-sync exactly):
"Flip-flops are the first ones. The sole is paper thin. So what do I recommend instead? A cushioned slipper you can wear all day."
TIMED SCRIPT
0.0–2.4s  [SAY: "Flip-flops are the first ones."]  He lifts ONE flip-flop.
2.4–4.8s  [SAY: "The sole is paper thin."]  Insert macro: the paper-thin edge.
4.8–11.1s  [SAY: "So what do I recommend instead? A cushioned slipper you can wear all day."]  He smiles.
11.1–13.0s  Held frame: the flip-flop in his hand.
END STATE: Holding ONE flip-flop.
FINAL CLIP: end on the held frame described in the last beat. HARD CUT, no logo, no fade."""


def test_bloque_clip_formato_exacto():
    assert plantillas.bloque_clip(_calc(CLIP2, 2, 2), CONFIG) == ESPERADO_CLIP2


def test_clip_1_sin_start_image_ni_final():
    txt = plantillas.bloque_clip(_calc(CLIP1, 1, 2), CONFIG)
    assert txt.startswith("CLIP 1 of 2 — 10 seconds — 9:16 — The hook\nSTART STATE: Hands empty.")
    assert "Start image" not in txt and "FINAL CLIP" not in txt


def test_voz_en_off():
    cfg = dict(CONFIG, modo="voiceover")
    txt = plantillas.bloque_clip(_calc(CLIP1, 1, 2), cfg)
    assert plantillas.ENCABEZADO_VOZ_OFF in txt and plantillas.ENCABEZADO_DIALOGO not in txt
    bv = plantillas.bloque_video(cfg, BLOQUE)
    assert "AUDIO\nNo speech is generated" in bv and "VOICE & AUDIO" not in bv


def test_bloque_video():
    cfg = dict(CONFIG, referencias=CONFIG["referencias"] + [
        {"tipo": "producto", "activo_id": "hf", "nombre": "HappyFlops Original", "descripcion": "EVA slipper",
         "casting": {}, "fotos": 2}])
    bv = plantillas.bloque_video(cfg, BLOQUE)
    assert bv.startswith("REFERENCE MAP\nImage 1 = character — the AI podiatrist, adult British man (~45). "
                         "Casting: age 45; wardrobe: white clinic coat; palette: white, navy. "
                         "Do not copy the background of Image 1.\n"
                         "Image 2 = environment — modern bright podiatry clinic. Do not copy the background of Image 2.\n"
                         "Image 3 = hero object — HappyFlops Original: EVA slipper. Preserve its exact geometry")
    assert "FORMAT & STYLE\nAspect ratio 9:16. ultra-photorealistic live-action" in bv
    assert "STARTING LAYOUT" not in bv
    assert bv.endswith("VOICE & AUDIO\nCalm British English male voice. The SAME voice in every clip, lip-sync exactly.")
    assert "STARTING LAYOUT\nHe stands left." in plantillas.bloque_video(cfg, dict(BLOQUE, disposicion_inicial="He stands left."))


def test_linea_referencia_producto_con_regla_propia():
    ref = {"tipo": "producto", "activo_id": "hf", "nombre": "HappyFlops Original", "descripcion": "EVA slipper",
           "casting": {}, "fotos": 2, "regla": "Logo en el talón."}
    assert plantillas.linea_referencia(3, ref) == (
        "Image 3 = hero object — HappyFlops Original: EVA slipper. Preserve its exact geometry, proportions, "
        "materials and construction; never redesign it. Catalog fidelity rule: Logo en el talón.")


def test_linea_referencia_producto_sin_regla_no_cambia():
    ref = {"tipo": "producto", "activo_id": "hf", "nombre": "HappyFlops Original", "descripcion": "EVA slipper",
           "casting": {}, "fotos": 2, "regla": ""}
    assert plantillas.linea_referencia(3, ref) == (
        "Image 3 = hero object — HappyFlops Original: EVA slipper. Preserve its exact geometry, proportions, "
        "materials and construction; never redesign it.")
    ref_sin_clave = {k: v for k, v in ref.items() if k != "regla"}
    assert plantillas.linea_referencia(3, ref_sin_clave) == plantillas.linea_referencia(3, ref)


def test_todo_prompt_de_fabrica_pasa_el_validador_del_chat():
    assert refinador.validar(plantillas.BLOQUE_GLOBAL_FABRICA, (), "clip") == []
    bv = plantillas.bloque_video(CONFIG, BLOQUE)
    for c in (_calc(CLIP1, 1, 2), _calc(CLIP2, 2, 2)):
        prompt = plantillas.prompt_clip(bv, c, CONFIG, plantillas.BLOQUE_GLOBAL_FABRICA)
        assert refinador.validar(prompt, _fijos(c), "clip") == [], prompt


def test_bloque_global_del_proyecto(tmp_path, monkeypatch):
    import proyectos
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    assert plantillas.bloque_global("acme") == plantillas.BLOQUE_GLOBAL_FABRICA
    proyectos.guardar_bloque_global_flowplus("acme", "  CLOSING RULES\nThe final clip ends with a HARD CUT.  ")
    assert plantillas.bloque_global("acme") == "CLOSING RULES\nThe final clip ends with a HARD CUT."
    proyectos.guardar_bloque_global_flowplus("acme", "")
    assert plantillas.bloque_global("acme") == plantillas.BLOQUE_GLOBAL_FABRICA
