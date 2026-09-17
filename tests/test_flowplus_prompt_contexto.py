import flowplus_prompt

REFS = [{"tipo": "imagen", "etiqueta": "@Producto 1", "categoria": "producto", "activo": "Espejo LED",
         "regla": "Idéntico.", "producto": "Espejo LED"}]


def test_sin_contexto_el_prompt_es_identico():
    base = flowplus_prompt.armar("gira despacio", REFS, guia_marca="Luz natural.", enfoque="producto")
    assert flowplus_prompt.armar("gira despacio", REFS, guia_marca="Luz natural.", enfoque="producto", contexto=None) == base
    assert "AUDIENCIA" not in base and "TEMPORADA" not in base


def test_contexto_agrega_audiencia_y_temporada_al_principio():
    ctx = {"persona": {"resumen": "Busca calidad", "descripcion": "Renueva su casa.", "tono": "cercano",
                       "senales_visuales": ["cocina moderna", "luz natural"]},
           "temporada": {"nombre": "Navidad", "contexto": "Regalos y reuniones.",
                         "mood_visual": {"paleta": ["#B3001B", "#0B6E4F"], "luz": "cálida", "elementos": ["luces", "mesa"]}}}
    p = flowplus_prompt.armar("gira despacio", REFS, guia_marca="Luz natural.", enfoque="producto", contexto=ctx)
    lineas = p.split("\n")
    i_aud = next(i for i, l in enumerate(lineas) if l.startswith("AUDIENCIA: "))
    i_tem = next(i for i, l in enumerate(lineas) if l.startswith("TEMPORADA: "))
    i_prod = next(i for i, l in enumerate(lineas) if l.startswith("PRODUCTO EXACTO"))
    assert i_aud < i_tem < i_prod
    assert "Busca calidad" in lineas[i_aud] and "cocina moderna, luz natural" in lineas[i_aud] and "cercano" in lineas[i_aud]
    assert "Navidad" in lineas[i_tem] and "#B3001B" in lineas[i_tem] and "luces, mesa" in lineas[i_tem]
    assert p.endswith("Recordatorio final: el producto permanece solo y sin nadie durante todo el video.")


def test_contexto_parcial_no_rompe():
    p = flowplus_prompt.armar("x", REFS, contexto={"persona": {"resumen": "Joven"}})
    assert "AUDIENCIA: Joven." in p and "TEMPORADA" not in p
    assert flowplus_prompt.armar("x", REFS, contexto={}) == flowplus_prompt.armar("x", REFS)
