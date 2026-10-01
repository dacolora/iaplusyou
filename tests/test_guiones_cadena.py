"""Cadena de escenas de Flow Plus (spec 2026-09-30): lógica pura, sin base ni red."""
from guiones import cadena, escenas
from providers import flowplus_modelos
from tests.test_guiones_escenas import CFG, CLIPS, FOTO

TEXTO = ("REFERENCE MAP\nImage 1 = hero object — HappyFlops Original: EVA slipper.\n"
         "Image 2 = character — the AI podiatrist. Do not copy the background of Image 2.\n\n"
         "FORMAT & STYLE\nAspect ratio 9:16.\n\nCLIP 2 of 2 — 12 seconds — 9:16 — B\n"
         "Start image = last frame of Clip 1.\nTIMED SCRIPT\n0.0–3.0s  Image 2 lifts Image 1 near Image 3.")
PROMPTS = {f"principal:{c['indice']}": {"id": c["indice"], "texto_vigente": TEXTO} for c in CLIPS}


def _video(est=None, cad=None, clips=CLIPS, estado="armado"):
    extra = {}
    if est is not None:
        extra["imagenes_escenas"] = est
    if cad is not None:
        extra["cadena"] = cad
    return {"config": CFG, "clips": clips, "estado": estado, "extra": extra}


def _completo():
    v = _video()
    est = escenas.poner_ref(escenas.estado(v), v, 2, FOTO)
    est = escenas.poner_ref(est, _video(est), 3, dict(FOTO, material_id=8, url="https://r2/c.jpg", nombre="clinica"))
    return _video(est)


def test_revisar_pide_imagenes_prompts_y_version_armada():
    motivos = cadena.revisar(_video(), PROMPTS)
    assert any(m["indice"] == 1 and "Image 2" in m["motivo"] for m in motivos)
    sin_prompts = cadena.revisar(_completo(), {})
    assert {m["indice"] for m in sin_prompts} == {1, 2}
    assert cadena.revisar(_completo(), PROMPTS) == []
    assert cadena.revisar(dict(_completo(), estado="invalido"), PROMPTS)[0]["indice"] is None


def test_revisar_limite_de_elementos_en_escenas_siguientes():
    v = _completo()
    est = escenas.estado(v)
    for n in range(2):
        est = escenas.agregar_extra(est, _video(est), dict(FOTO, material_id=50 + n, url=f"https://r2/x{n}.jpg"),
                                    escena=2)
    motivos = cadena.revisar(_video(est), PROMPTS)
    # escena 2: producto + personaje + 2 extras = 4 elementos (el entorno no cuenta)
    assert [m["indice"] for m in motivos] == [2] and "4" in motivos[0]["motivo"]
    # desde la escena 1, la 1 no tiene tope de elementos (va por referencias, hasta 7)
    assert all(m["indice"] != 1 for m in motivos)


def test_revisar_con_la_cadena_corriendo():
    v = _completo()
    v = dict(v, extra=dict(v["extra"], cadena=cadena.aprobar(v, 1, 1.0, "admin", "t")))
    assert any(m["indice"] is None for m in cadena.revisar(v, PROMPTS))


def test_avisos_de_cambio_de_lugar():
    # escena 1 en Image 3 (clínica), escena 2 en Image 4 (sala): cambia de lugar
    avisos = cadena.avisos(_completo())
    assert [a["indice"] for a in avisos] == [2]


def test_elementos_necesarios_y_nombres():
    v = _completo()
    els = cadena.elementos_necesarios(v, 1)
    assert [e["nombre"] for e in els] == ["HappyFlops Original", "the AI podiatrist,"]
    assert all(len(e["nombre"]) <= 20 for e in els)
    assert els[0]["id"] == "catalogo:producto:hf" and els[1]["id"] == "https://r2/x.jpg"
    assert els[0]["imagen"] == {"activo_id": "hf", "categoria": "producto", "nombre": "HappyFlops Original"}


def test_precio():
    v = _completo()
    escenas_usd = sum(flowplus_modelos.estimate_video("kling_o3_pro", c["duracion"], True)["usd"] for c in CLIPS)
    assert cadena.precio(v) == round(escenas_usd + 0.01 * 2, 2)
    ya = {e["id"] for e in cadena.elementos_necesarios(v, 1)}
    assert cadena.precio(v, conocidos=ya) == round(escenas_usd, 2)
    solo_2 = flowplus_modelos.estimate_video("kling_o3_pro", CLIPS[1]["duracion"], True)["usd"]
    assert cadena.precio(v, desde=2, conocidos=ya) == round(solo_2, 2)


def test_transiciones_de_punta_a_punta():
    v = _completo()
    ks = [1, 2]
    est = cadena.aprobar(v, 1, 3.5, "admin", "2026-10-01T00:00:00")
    assert est["estado"] == "corriendo" and cadena.siguiente(est, ks) == 1
    est = cadena.lanzada(est, 1, "cf_1")
    assert cadena.siguiente(est, ks) is None  # la 1 está generando
    est = cadena.lista(est, 1, "https://f1.jpg")
    assert cadena.siguiente(est, ks) == 2 and cadena.frame_anterior(est, 2) == "https://f1.jpg"
    est = cadena.lanzada(est, 2, "cf_2")
    est = cadena.lista(est, 2, "https://f2.jpg")
    assert cadena.siguiente(est, ks) is None and cadena.todas_listas(est, ks)
    est = cadena.con_edicion(cadena.terminada(est), 7)
    assert est["estado"] == "terminada" and est["edicion_id"] == 7


def test_fallo_detiene_y_rehacer_conserva_lo_anterior():
    v = _completo()
    est = cadena.lista(cadena.lanzada(cadena.aprobar(v, 1, 3.5, "admin", "t"), 1, "cf_1"), 1, "https://f1.jpg")
    est = cadena.fallo(cadena.lanzada(est, 2, "cf_2"), 2, "Kling 1200")
    assert est["estado"] == "detenida" and est["escenas"]["2"] == {"cf_id": "cf_2", "estado": "fallo",
                                                                   "frame_url": None, "error": "Kling 1200"}
    assert cadena.puede_rehacer(est, 2) and not cadena.puede_rehacer(est, 3)
    est2 = cadena.aprobar(v, 2, 1.0, "admin", "t2", previo=est)
    assert est2["escenas"] == {"1": est["escenas"]["1"]} and est2["desde"] == 2
    assert cadena.siguiente(est2, [1, 2]) == 2


def test_detener():
    v = _completo()
    est = cadena.pedir_detener(cadena.lanzada(cadena.aprobar(v, 1, 3.5, "admin", "t"), 1, "cf_1"))
    assert est["detener"] and est["estado"] == "corriendo"
    est = cadena.lista(est, 1, "https://f1.jpg")
    assert cadena.siguiente(est, [1, 2]) is None
    assert cadena.detenida(est)["estado"] == "detenida"


def test_estado_ignora_basura():
    assert cadena.estado(_video(cad={"estado": "raro"})) is None
    assert cadena.estado(_video(cad="x")) is None
    assert cadena.estado(_video()) is None


def test_prompt_escena_1_es_el_de_llevar_a_crear():
    v = _completo()
    imgs = escenas.imagenes_para_crear(v, 1)
    assert cadena.prompt_escena(TEXTO, v, 1, imgs) == escenas.prompt_para_crear(TEXTO, v, imgs)


def test_prompt_escena_siguiente_arranca_en_el_fotograma_y_nombra_elementos():
    v = _completo()
    p = cadena.prompt_escena(TEXTO, v, 2, escenas.imagenes_para_crear(v, 2))
    assert "Start image" not in p and "REFERENCE MAP" not in p and "Image " not in p
    assert p.startswith("The video starts exactly on the provided first frame.")
    assert "Characters and objects: HappyFlops Original, the AI podiatrist,." in p
    # Image 2 es un elemento: su nombre; Image 3 (la clínica) no es elemento: su nombre en palabras
    assert "the AI podiatrist, lifts HappyFlops Original near modern bright podiatry clinic." in p
