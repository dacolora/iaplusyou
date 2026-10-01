"""
Referencias desde un link (FlowPlus): TrendTrack, TikTok, Instagram, YouTube…

- TrendTrack (app.trendtrack.io/…/share/ads/…): la página compartida es pública y
  trae dentro la URL del .mp4 en medias.trendtrack.io — se lee con requests, sin
  navegador. Verificado el 2026-09-12.
- Todo lo demás: yt-dlp (TikTok, Instagram, YouTube, Facebook…). Hay que tenerlo
  en requirements y actualizarlo cuando las plataformas cambian algo.

El video se recorta a 15 s como máximo (Wan 3.0 acepta videos de referencia de
1-15 s) y se le sacan fotogramas para la miniatura y para describirlo con IA.
Nunca se publica ni se re-sube el video ajeno: solo sirve como referencia de
movimiento/estructura para generar uno nuevo con el producto del cliente.
"""
import base64
import io
import os
import re
import subprocess
import tempfile
from urllib.parse import urlparse

import requests
from flask_babel import gettext

import idiomas
from conectores import ErrorConector
from conectores import url as conector_url

MAX_SEGUNDOS = 15
# Tope de lo que se baja de un link (el mismo que yt-dlp, `max_filesize`) y de
# la página de TrendTrack que se lee buscando el .mp4.
MAX_BYTES_VIDEO = 200 * 1024 * 1024
MAX_BYTES_PAGINA = 5 * 1024 * 1024
_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/128 Safari/537.36"}


class LinkError(RuntimeError):
    """Error legible para el usuario."""


def _es_trendtrack(url):
    # Por el host, no por el texto: «http://169.254.169.254/?trendtrack.io»
    # también contiene la palabra (auditoría de seguridad 2026-10-01).
    host = (urlparse(url).hostname or "").lower()
    return host == "trendtrack.io" or host.endswith(".trendtrack.io")


def _bajar_limitado(url, f, tope, timeout):
    """Copia `url` en el archivo abierto `f` sin pasar de `tope` bytes y sin
    salir de hosts públicos, tampoco en una redirección (conectores.url.abrir:
    antes un requests.get seguía cualquier redirección y leía sin tope)."""
    try:
        r = conector_url.abrir(url, cabeceras=_UA, timeout=timeout)
    except ErrorConector:
        raise LinkError(gettext("Ese link no está permitido (apunta a una red interna o local).")) from None
    try:
        if not r.ok:
            raise LinkError(gettext("TrendTrack no dejó descargar el video (%(codigo)s).", codigo=r.status_code))
        total = 0
        for chunk in r.iter_content(1 << 16):
            total += len(chunk)
            if total > tope:
                raise LinkError(gettext("El video del link pesa demasiado."))
            f.write(chunk)
    finally:
        r.close()


def _descargar_trendtrack(url, destino):
    pagina = io.BytesIO()
    try:
        _bajar_limitado(url, pagina, MAX_BYTES_PAGINA, 30)
    except requests.RequestException as e:
        raise LinkError(gettext("No pude abrir el link de TrendTrack (%(tipo)s).", tipo=type(e).__name__)) from None
    html = pagina.getvalue().decode("utf-8", errors="replace")
    m = re.search(r'https://medias\.trendtrack\.io/[^"\'\\\s<>]+\.mp4', html)
    if not m:
        raise LinkError(gettext("En ese link de TrendTrack no encontré el video (¿es un anuncio de imagen, o el link no es público?)."))
    video_url = m.group(0)
    try:
        with open(destino, "wb") as f:
            _bajar_limitado(video_url, f, MAX_BYTES_VIDEO, 120)
    except requests.RequestException as e:
        raise LinkError(gettext("Falló la descarga del video de TrendTrack (%(tipo)s).", tipo=type(e).__name__)) from None
    return {"fuente": "trendtrack", "titulo": None}


def _descargar_ytdlp(url, destino):
    try:
        import yt_dlp
    except ImportError:
        raise LinkError(gettext("Falta yt-dlp en el servidor para descargar de TikTok/Instagram/YouTube.")) from None
    opts = {
        "outtmpl": destino, "format": "mp4/bestvideo*+bestaudio/best", "merge_output_format": "mp4",
        "quiet": True, "no_warnings": True, "noplaylist": True, "max_filesize": MAX_BYTES_VIDEO,
        # Solo los extractores de cada red (TikTok, Instagram, YouTube…): el
        # «genérico» abre cualquier URL y sigue sus redirecciones, que es
        # justo lo que no debe hacer el servidor con un link ajeno (SSRF).
        "allowed_extractors": ["default", "-generic"],
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as e:
        raise LinkError(gettext("No pude descargar ese link (%(tipo)s): puede ser privado, requerir inicio de sesión o no ser un video.", tipo=type(e).__name__)) from None
    return {"fuente": info.get("extractor_key", "").lower() or "link", "titulo": info.get("title")}


def descargar(url, carpeta, nombre_base):
    """Descarga el video del link a carpeta/nombre_base.mp4, recortado a
    MAX_SEGUNDOS. Devuelve (ruta_mp4, meta)."""
    url = url.strip()
    if not re.match(r"^https?://", url):
        raise LinkError(gettext("Eso no parece un link (tiene que empezar por http:// o https://)."))
    try:
        publico = conector_url.host_permitido(url)
    except ErrorConector:
        publico = False
    if not publico:
        raise LinkError(gettext("Ese link no está permitido (apunta a una red interna o local)."))
    os.makedirs(carpeta, exist_ok=True)
    bruto = os.path.join(carpeta, nombre_base + ".orig.mp4")
    final = os.path.join(carpeta, nombre_base + ".mp4")
    meta = _descargar_trendtrack(url, bruto) if _es_trendtrack(url) else _descargar_ytdlp(url, bruto)
    if not os.path.exists(bruto) or os.path.getsize(bruto) == 0:
        raise LinkError(gettext("La descarga terminó vacía."))
    # Recorte a 15 s + re-encode a H.264 (los modelos exigen mp4 estándar).
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", bruto, "-t", str(MAX_SEGUNDOS),
             "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-an", final],
            check=True, capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        raise LinkError(gettext("No pude preparar el video descargado: %(detalle)s",
                                detalle=e.stderr.decode(errors="ignore")[-200:])) from None
    finally:
        try:
            os.remove(bruto)
        except OSError:
            pass
    meta["url_origen"] = url
    return final, meta


def fotogramas(video_path, n=4):
    """n fotogramas repartidos en el video, como bytes JPEG (para describir con IA)."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video_path],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        dur = float(out or 0) or MAX_SEGUNDOS
    except Exception:
        dur = MAX_SEGUNDOS
    imgs = []
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(n):
            t = max(0.0, dur * (i + 0.5) / n)
            p = os.path.join(tmp, f"f{i}.jpg")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", video_path,
                            "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "4", p], capture_output=True)
            if os.path.exists(p):
                imgs.append(open(p, "rb").read())
    return imgs


DESCRIPCION_PROMPT = """Eres director creativo de anuncios cortos para redes. Vas a ver fotogramas de uno o varios videos/imágenes de referencia, en orden. Describe en __IDIOMA__, en un solo párrafo de máximo 90 palabras y en segunda persona (como instrucción para un generador de video), lo que habría que recrear:
- qué producto aparece y cómo se muestra (encuadre, ángulo, distancia),
- si hay una persona y qué hace con el producto (o si no hay nadie),
- el movimiento de cámara y el ritmo (lento, rápido, cortes, zoom),
- la escena, la luz y el ambiente.
No inventes marcas ni textos. No menciones "fotograma" ni "imagen": describe la escena directamente. Si son varias referencias, nómbralas como @Video 1, @Imagen 1, etc. en el orden dado."""


def describir(referencias, cliente_hint="", idioma="es"):
    """referencias: [{etiqueta, tipo, ruta_local?, url?}]. Usa Claude con visión
    sobre fotogramas/imágenes. Devuelve el texto en el idioma pedido (el del
    proyecto: la sugerencia cae en el cuadro de la persona, que la edita)."""
    import anthropic
    from generador_prompts import _api_key, MODEL
    orden = idiomas.orden_idioma(idioma)
    pista = f"\nContexto del cliente: {cliente_hint}" if cliente_hint else ""
    instrucciones = DESCRIPCION_PROMPT.replace("__IDIOMA__", idiomas.nombre_para_claude(idioma))
    content = [{"type": "text", "text": f"{orden}\n\n{instrucciones}{pista}\n\n{orden}"}]
    total = 0
    for r in referencias:
        content.append({"type": "text", "text": f"--- {r['etiqueta']} ({r['tipo']}) ---"})
        if r["tipo"] == "video" and r.get("ruta_local") and os.path.exists(r["ruta_local"]):
            for b in fotogramas(r["ruta_local"], n=4):
                content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                            "data": base64.b64encode(b).decode()}})
                total += 1
        elif r.get("url"):
            content.append({"type": "image", "source": {"type": "url", "url": r["url"]}})
            total += 1
        if total >= 16:
            break
    if total == 0:
        raise LinkError(gettext("No hay imágenes ni videos que describir."))
    client = anthropic.Anthropic(api_key=_api_key())
    resp = client.messages.create(model=MODEL, max_tokens=300, messages=[{"role": "user", "content": content}])
    return "".join(b.text for b in resp.content if b.type == "text").strip()
