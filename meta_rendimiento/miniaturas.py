"""Copia a R2 de las miniaturas de los anuncios de Meta (PND-194, decisión 2026-10-13: «copiar a R2 las miniaturas
de los anuncios de Meta sin análisis, como ya hace Triple Whale»).

Las tarjetas de los anuncios de Meta de la galería de Rendimiento enlazaban la miniatura firmada de Meta, que caduca: la
imagen se rompía hasta la siguiente copia. Los anuncios analizados ya mostraban su copia en R2
(`pestana_rendimiento.galeria.medio_meta`); ahora la copia diaria de la cuenta (la corrida del listado completo, después
de pedir las miniaturas: `sync._miniaturas`) copia también la de los anuncios con gasto en los últimos 30 días, fuera
del camino de pintar.

- UNA vez por anuncio y creativo: la clave es `clientes/<c>/meta_rendimiento/miniaturas/<ad_id>.jpg` y `meta_objeto.extra`
  guarda `miniatura_r2` (la URL) y `miniatura_r2_de` (el `creative_id` copiado); solo se vuelve a copiar si el
  creativo cambió. La URL firmada de Meta cambia en cada lectura; la imagen de un creativo, no.
- Como mucho `TOPE_POR_CORRIDA` por cuenta y corrida, las de más gasto primero: la primera vez hay miles y la copia
  corre en el carril de lectura (un hilo).
- Se baja con `conectores.url.descargar_archivo` (SSRF en cada redirección, tope de tamaño y de tiempo) solo una URL que
  pasa `datos.miniatura_valida`, Pillow la abre solo como JPEG/PNG/WEBP/GIF y se sube como JPEG.
- Es lo copiado de Meta: soltar la cuenta (`cuentas.elegir`, también al desconectar) la borra de R2 después de las
  filas (`borrar`; lo que R2 no borra se anota en `storage.r2_pendientes`). Si la cuenta se suelta mientras se copia,
  la escritura en la base lo nota (`datos.CuentaSoltada`) y la copia recién subida se borra.
- Nunca tumba la copia de la cuenta: un fallo se anota con el tipo del error (el texto de una excepción de red puede
  traer la URL firmada) y se sigue con la siguiente; solo `CuentaSoltada` sube.
"""
import logging
import os
import tempfile

from conectores import url as conector_url
from meta_rendimiento import datos
from storage import r2_uploader

log = logging.getLogger("creatv.meta_rendimiento.miniaturas")

TOPE_POR_CORRIDA = 200
MAX_BYTES = 2 * 1024 * 1024
FORMATOS = ("JPEG", "PNG", "WEBP", "GIF")
LADO_MAXIMO = 600


def clave(cliente, ad_id):
    return f"clientes/{cliente}/meta_rendimiento/miniaturas/{ad_id}.jpg"


def _subir(url, destino):
    """Baja la miniatura (con la guarda de SSRF), la pasa a JPEG y la sube a R2 en `destino`. Devuelve la URL pública.
    Lanza si algo falla; los temporales se borran siempre."""
    from PIL import Image  # noqa: PLC0415 — Pillow solo en este paso diario
    fd, crudo = tempfile.mkstemp(prefix="meta_mini_", suffix=".img")
    os.close(fd)
    try:
        conector_url.descargar_archivo(url, crudo, max_bytes=MAX_BYTES, tipos=("image/",))
        with tempfile.TemporaryDirectory(prefix="meta_mini_") as carpeta:
            local = os.path.join(carpeta, "miniatura.jpg")
            with Image.open(crudo, formats=FORMATOS) as im:
                im = im.convert("RGB")
                im.thumbnail((LADO_MAXIMO, LADO_MAXIMO))
                im.save(local, format="JPEG", quality=85)
            return r2_uploader.upload_file(local, destino, content_type="image/jpeg")
    finally:
        try:
            os.remove(crudo)
        except OSError:
            pass


def copiar(cliente, act, desde):
    """Copia a R2 las miniaturas de los anuncios de la cuenta `act` con gasto desde `desde` (AAAA-MM-DD) que todavía
    no tienen copia de su creativo actual, como mucho `TOPE_POR_CORRIDA`. Devuelve cuántas copió. Solo lanza
    `datos.CuentaSoltada` (la cuenta se soltó en medio; lo recién subido ya se borró)."""
    try:
        pendientes = datos.miniaturas_por_copiar(cliente, act, desde, TOPE_POR_CORRIDA)
    except Exception as e:  # noqa: BLE001 — sin la lista no se copia nada hoy; la copia de la cuenta sigue
        log.warning("meta miniaturas a R2 %s: no se pudo calcular qué copiar (%s)", act, type(e).__name__)
        return 0
    n, fallos = 0, 0
    for ad_id, url, creative_id in pendientes:
        if not str(ad_id).isdigit() or not datos.miniatura_valida(url):
            continue
        destino = clave(cliente, ad_id)
        try:
            publica = _subir(url, destino)
        except Exception as e:  # noqa: BLE001 — esa miniatura queda para mañana
            fallos += 1
            log.info("meta miniaturas a R2 %s: una no se copió (%s)", act, type(e).__name__)
            continue
        try:
            datos.guardar_objetos(cliente, act, [{"nivel": "anuncio", "objeto_id": str(ad_id), "extra": {
                "miniatura_r2": publica, "miniatura_r2_de": str(creative_id or "")}}], exigir_cuenta=True)
        except datos.CuentaSoltada:
            borrar(cliente, [ad_id])     # se soltó en medio: lo recién subido no se queda en R2
            raise
        except Exception as e:  # noqa: BLE001 — sin la fila que la nombre, la copia no se quedaría huérfana en R2
            borrar(cliente, [ad_id])
            log.warning("meta miniaturas a R2 %s: no se guardó una copia (%s)", act, type(e).__name__)
            continue
        n += 1
    if fallos:
        log.warning("meta miniaturas a R2 %s: %s de %s no se copiaron", act, fallos, len(pendientes))
    return n


def borrar(cliente, ad_ids):
    """Borra de R2 las copias de esas miniaturas (un solo cliente; lo que R2 no borra queda en `r2_pendientes` para el
    reintento diario). Nunca lanza: devuelve el tipo de cada error."""
    claves = [clave(cliente, a) for a in ad_ids or [] if str(a).isdigit()]
    if not claves:
        return []
    from meta_rendimiento import analisis  # noqa: PLC0415 — tardío: analisis carga Claude y Triple Whale
    _, fallos = analisis.borrar_claves(claves)
    return fallos
