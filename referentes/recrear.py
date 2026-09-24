"""
«Recrear con mi producto» (spec 2026-09-23 §9): un referente de la biblioteca
se convierte en imagen o video del producto del cliente sobre el pipeline de
Crear que ya existe. `armar_prompt` es determinista (nunca llama a Claude) —
«Adaptar con IA» es un paso aparte, opcional, que solo propone (`adaptar`).
"""

SIN_VOZ_NI_MUSICA = "Sin diálogo hablado ni música de fondo."
SONIDO_AMBIENTE = "ambiente natural de la escena"


def _linea_sonido(sonido_texto, con_sonido):
    texto = (sonido_texto or "").strip().rstrip(".")
    if texto:
        return f"SONIDO: {texto}. {SIN_VOZ_NI_MUSICA}"
    if con_sonido:
        return f"SONIDO: {SONIDO_AMBIENTE}. {SIN_VOZ_NI_MUSICA}"
    return None


def armar_prompt(referente, familia, producto, guia, titular, formato, tipo="imagen", sonido_texto="", con_sonido=True):
    n_fotos = max(1, min(2, len(producto.get("referencias") or [1])))
    ref_producto = "Image 2 y 3" if n_fotos == 2 else "Image 2"
    desc_familia = (familia or {}).get("descripcion") or ""
    partes = [
        (f"Anuncio estático para redes, formato {formato}. Sigue la ESTRUCTURA y la COMPOSICIÓN de Image 1 "
         f"(referencia de formato «{referente.get('familia') or ''}»: {desc_familia}).").strip(),
    ]
    if referente.get("firma"):
        partes.append(f"Funciona porque: {referente['firma']}.")
    dolor = referente.get("dolor") or ""
    if dolor and not dolor.startswith("ninguno-"):
        partes.append(f"Dolor que ataca: {dolor}.")
    partes.append(
        (f"Producto: el de {ref_producto}: {producto.get('nombre') or ''}. {producto.get('descripcion') or ''} "
         f"{producto.get('regla') or ''}").strip()
    )
    partes.append("Sustituye por completo el producto y la marca de la referencia.")
    if titular:
        partes.append(f"Texto en la imagen: titular «{titular}» con el mismo peso y ubicación que en la referencia; ningún otro texto.")
    if guia:
        partes.append(f"Guía de estilo de la marca: {guia}.")
    partes.append("Sin logos ni nombres de otras marcas. Sin marcas de agua.")
    if tipo == "video":
        partes.append("Cámara fija con leve acercamiento al producto; el titular aparece en los primeros 2 segundos.")
        linea = _linea_sonido(sonido_texto, con_sonido)
        if linea:
            partes.append(linea)
    return " ".join(partes)
