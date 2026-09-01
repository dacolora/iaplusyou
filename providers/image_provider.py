"""
Capa única de generación de imagen. El resto del programa nunca habla directo con
Higgsfield ni con Nano Banana — solo pide "generame una imagen con este proveedor" y
esta capa decide cómo hacerlo. Agregar un proveedor nuevo mañana no debería requerir
tocar dashboard.py ni ningún otro módulo que consuma imágenes.
"""
import higgsfield_client
from providers import nano_banana_client

PROVEEDORES_VALIDOS = ("higgsfield", "nano_banana")


def generar_imagen(proveedor, referencia_url, prompt, local_path, negative_prompt=None, extra_params=None):
    """Genera una imagen y la guarda en local_path. Devuelve {"credits", "usd"} — para
    Nano Banana "credits" siempre es None (esa API no usa créditos, cobra directo en USD)."""
    if proveedor == "nano_banana":
        img_bytes = nano_banana_client.generate_image(
            referencia_url,
            prompt,
            negative_prompt=negative_prompt,
            extra_params=extra_params,
        )
        with open(local_path, "wb") as f:
            f.write(img_bytes)
        return nano_banana_client.estimate_image()

    if proveedor == "higgsfield":
        launch = higgsfield_client.generate_image(referencia_url, prompt, extra_params=extra_params)
        result = higgsfield_client.poll_until_done(launch["status_url"])
        higgsfield_client.download_image_result(result, local_path)
        return higgsfield_client.estimate_image(referencia_url, prompt, extra_params=extra_params)

    raise ValueError(f"Proveedor de imagen desconocido: {proveedor}. Opciones: {PROVEEDORES_VALIDOS}")
