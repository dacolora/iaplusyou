"""Tokens de referencia (spec director §5): los modelos documentan `Image N` /
`Video N` por orden de subida; `@Imagen N` / `@Logo N` eran nuestros."""
import flowplus_prompt


def _refs():
    return [
        {"tipo": "imagen", "etiqueta": "@Imagen 1", "url": "https://x/1.png", "frame_url": "https://x/1.png"},
        {"tipo": "video", "etiqueta": "@Video 1", "url": "https://x/v.mp4", "frame_url": "https://x/v.jpg"},
        {"tipo": "imagen", "etiqueta": "Personaje 1", "url": "https://x/a.png", "frame_url": "https://x/a.png",
         "categoria": "personaje", "activo": "Ana", "regla": "Misma cara."},
        {"tipo": "imagen", "etiqueta": "Personaje 1 (vista 2)", "url": "https://x/b.png", "frame_url": "https://x/b.png",
         "categoria": "personaje", "activo": "Ana", "regla": "Misma cara."},
        {"tipo": "imagen", "etiqueta": "@Logo 1", "url": "https://x/l.png", "frame_url": "https://x/l.png", "logo": True},
    ]


def test_wan_numera_imagenes_y_videos_aparte():
    refs = flowplus_prompt.asignar_tokens(_refs(), "wan3")
    assert [r["token"] for r in refs] == ["Image 1", "Video 1", "Image 2", "Image 3", "Image 4"]


def test_otros_modelos_cuentan_el_fotograma_del_video_como_imagen():
    for modelo in ("kling_o3_pro", "seedance25"):
        refs = flowplus_prompt.asignar_tokens(_refs(), modelo)
        assert [r["token"] for r in refs] == ["Image 1", "Image 2", "Image 3", "Image 4", "Image 5"]


def test_sustituir_tokens_en_el_texto_de_la_persona():
    refs = flowplus_prompt.asignar_tokens(_refs(), "wan3")
    texto = "@Imagen 1 es el producto; Ana lo toma como en @Video 1, con @Logo 1 al fondo"
    assert flowplus_prompt.sustituir_tokens(texto, refs) == \
        "Image 1 es el producto; Ana lo toma como en Video 1, con Image 4 al fondo"
    # menciones que no existen se dejan tal cual (no se inventan referencias)
    assert flowplus_prompt.sustituir_tokens("@Imagen 9 gira", refs) == "@Imagen 9 gira"
    # un activo del catálogo (etiqueta "Personaje 1") nunca se mostró como @Imagen N en la UI: esa mención no le pertenece
    assert flowplus_prompt.sustituir_tokens("@Imagen 2 sonríe", refs) == "@Imagen 2 sonríe"


def test_sustituir_tokens_respeta_la_etiqueta_no_el_orden_en_sprints():
    """En Sprints el producto del catálogo va primero en `referencias` pero se
    menciona `@Producto 1`; la imagen de campaña que sigue es `@Imagen 1`. Si
    se numerara por posición dentro de `referencias` en vez de por etiqueta,
    `@Imagen 1` apuntaría al producto en lugar de a la imagen de campaña."""
    refs = [
        {"tipo": "imagen", "etiqueta": "@Producto 1", "categoria": "producto", "activo": "Espejo", "producto": "Espejo"},
        {"tipo": "imagen", "etiqueta": "@Imagen 1"},
    ]
    flowplus_prompt.asignar_tokens(refs, "wan3")
    assert flowplus_prompt.sustituir_tokens("@Imagen 1 al fondo", refs) == "Image 2 al fondo"


def test_armar_usa_los_tokens_en_activos_logos_y_videos():
    refs = flowplus_prompt.asignar_tokens(_refs(), "wan3")
    p = flowplus_prompt.armar("Ana camina con @Imagen 1", refs, logos=[r for r in refs if r.get("logo")], enfoque="persona")
    assert 'PERSONAJE: Ana (Image 2, Image 3: la misma persona). Misma cara.' in p
    assert "LOGO OFICIAL: Image 4 muestra el logotipo real de la marca." in p
    assert "Video 1: referencia de movimiento, ritmo y encuadre de cámara" in p
    assert "ESCENA: Ana camina con Image 1" in p
    assert "@Imagen" not in p and "@Logo" not in p and "@Video" not in p


def test_sesiones_viejas_sin_token_siguen_usando_la_etiqueta():
    refs = [{"tipo": "imagen", "etiqueta": "@Producto 1", "categoria": "producto", "activo": "Espejo", "regla": "Idéntico.", "producto": "Espejo"}]
    p = flowplus_prompt.armar("gira", refs, enfoque="producto")
    assert 'PRODUCTO EXACTO: @Producto 1 es el producto "Espejo". Idéntico.' in p


def test_evitar_ya_no_lleva_deformaciones():
    p = flowplus_prompt.armar("gira", [{"tipo": "imagen", "etiqueta": "@Imagen 1", "token": "Image 1"}], enfoque="producto")
    linea = next(l for l in p.split("\n") if l.startswith("EVITAR: "))
    assert linea == "EVITAR: personas, pies, manos, texto inventado, logos inventados, marcas de agua, subtítulos."


PLANOS = [
    {"n": 1, "inicio_s": 0, "fin_s": 4, "plano": "primer plano", "camara": "dolly_in",
     "accion": "la sandalia (Image 1) reposa sobre la piedra; una brisa mueve la correa", "sonido": "brisa, roce de la correa"},
    {"n": 2, "inicio_s": 4, "fin_s": 8, "plano": "plano medio", "camara": "orbita_corta",
     "accion": "la cámara rodea la sandalia y revela la playa", "sonido": "olas lejanas"},
]
REF = [{"tipo": "imagen", "etiqueta": "@Imagen 1", "token": "Image 1"}]


def test_con_planos_el_bloque_shot_reemplaza_a_escena_y_cierra_con_la_frase_oficial():
    p = flowplus_prompt.armar("gira", REF, enfoque="producto", con_sonido=True, planos=PLANOS,
                              cierre_sonido="No dialogue. No background music.")
    lineas = p.split("\n")
    assert not any(l.startswith("ESCENA: ") for l in lineas) and not any(l.startswith("SONIDO: ") for l in lineas)
    i1 = lineas.index("Shot 1 (0-4s): primer plano, la cámara avanza en línea recta hacia el sujeto, despacio y a velocidad constante, sin zoom. "
                      "La sandalia (Image 1) reposa sobre la piedra; una brisa mueve la correa. Sonido: brisa, roce de la correa.")
    i2 = lineas.index("Shot 2 (4-8s): Hard cut. plano medio, la cámara rodea al sujeto en un arco corto de menos de 45 grados. "
                      "La cámara rodea la sandalia y revela la playa. Sonido: olas lejanas.")
    i_cierre = lineas.index("No dialogue. No background music.")
    i_evitar = next(i for i, l in enumerate(lineas) if l.startswith("EVITAR: "))
    assert i1 < i2 < i_cierre < i_evitar


def test_sesion_muda_con_planos_no_lleva_sonido_ni_cierre():
    p = flowplus_prompt.armar("gira", REF, enfoque="producto", con_sonido=False, planos=PLANOS,
                              cierre_sonido="No dialogue. No background music.")
    assert "Sonido:" not in p and "No dialogue" not in p and "Shot 1 (0-4s)" in p


def test_sin_planos_la_linea_sonido_de_siempre_gana_el_cierre_oficial():
    p = flowplus_prompt.armar("gira", REF, enfoque="producto", con_sonido=True, cierre_sonido="No dialogue. No music.")
    assert "SONIDO: ambiente natural de la escena. Sin diálogo hablado ni música de fondo. No dialogue. No music." in p
    # sin cierre, el prompt es exactamente el de antes (sesiones viejas)
    assert "No dialogue" not in flowplus_prompt.armar("gira", REF, enfoque="producto", con_sonido=True)


def test_camara_desconocida_en_un_plano_lanza():
    import pytest
    malo = [dict(PLANOS[0], camara="grua_lunar")]
    with pytest.raises(ValueError):
        flowplus_prompt.armar("gira", REF, enfoque="producto", planos=malo)


def test_el_primer_plano_no_lleva_corte_y_los_siguientes_si():
    """Prueba real 2026-09-20: sin decir cómo pasar de un plano a otro, Wan improvisó
    un fundido con la sandalia semitransparente. La guía multi-shot de Wan escribe
    «Hard cut transition» al abrir el segundo plano: se antepone la frase literal
    a cada Shot a partir del segundo, nunca al primero."""
    tres = PLANOS + [{"n": 3, "inicio_s": 8, "fin_s": 12, "plano": "plano general", "camara": "estatico",
                      "accion": "la sandalia queda sola en la piedra", "sonido": "olas"}]
    p = flowplus_prompt.armar("gira", REF, enfoque="producto", con_sonido=False, planos=tres)
    lineas = [l for l in p.split("\n") if l.startswith("Shot ")]
    assert lineas[0].startswith("Shot 1 (0-4s): primer plano,") and "Hard cut" not in lineas[0]
    assert lineas[1].startswith("Shot 2 (4-8s): Hard cut. plano medio,")
    assert lineas[2].startswith("Shot 3 (8-12s): Hard cut. plano general,")
