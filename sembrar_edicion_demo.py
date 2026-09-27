"""Edición de demostración para probar la vista previa del editor (capa 3)
sin gastar ni tocar R2: un clon sintético de 8 s (barras de colores con un
tono), una «voz» (tono cortado en sílabas) y una «música» que son tonos, un
logo, y el documento que arma el borrador de producción (hook, precio, CTA,
logo, voz, música, sonido de la escena, subtítulos) con un fundido entre los
dos cortes. Los archivos quedan en static/editor_demo/<cliente>/ (fuera de
git) y los sirve la misma app: mismo origen, así el navegador no necesita
CORS. `extra.local` deja que preparar_rutas también la renderice.

    venv/bin/python3 sembrar_edicion_demo.py --cliente <proyecto>

Usa la base de CREATV_DB_URL (o data/creatv.db). Cada corrida crea una
edición nueva; los materiales se reutilizan por hash."""
import argparse
import os
import subprocess

from PIL import Image

import ediciones
import materiales
from final_edition import borrador, cortes
from tareas import edicion as tareas_edicion

BASE = os.path.dirname(os.path.abspath(__file__))
DURACION_S = 8
PALABRAS = [{"t_ms": 0, "dur_ms": 400, "texto": "¿Tu"}, {"t_ms": 450, "dur_ms": 350, "texto": "piel"},
            {"t_ms": 850, "dur_ms": 300, "texto": "se"}, {"t_ms": 1200, "dur_ms": 300, "texto": "ve"},
            {"t_ms": 1550, "dur_ms": 700, "texto": "apagada?"}]
GUION = {"idioma": "es", "pais": "CO", "bloques": [
    {"rol": "hook", "inicio_s": 0, "fin_s": 2.5, "texto_pantalla": "¿Tu piel se ve apagada?", "texto_voz": "¿Tu piel se ve apagada?"},
    {"rol": "producto", "inicio_s": 2.5, "fin_s": 5, "texto_pantalla": "Sérum de vitamina C", "texto_voz": "Sérum de vitamina C."},
    {"rol": "prueba", "inicio_s": 5, "fin_s": 6.5, "texto_pantalla": "Resultados en 7 días", "texto_voz": "En siete días."},
    {"rol": "cta", "inicio_s": 6.5, "fin_s": 8, "texto_pantalla": "Pídelo hoy con envío gratis", "texto_voz": "Pídelo hoy."},
]}


def _ffmpeg(*args):
    subprocess.run([cortes.FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def _medios(carpeta):
    os.makedirs(carpeta, exist_ok=True)
    r = {k: os.path.join(carpeta, n) for k, n in (("clon", "clon.mp4"), ("voz", "voz.wav"), ("musica", "musica.wav"),
                                                   ("logo", "logo.png"), ("proxy", "clon_proxy.mp4"))}
    if not os.path.exists(r["clon"]):
        _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30", "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000",
                "-t", str(DURACION_S), "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", "-shortest", r["clon"])
    if not os.path.exists(r["voz"]):
        # ganancia 8 (≈ +18 dB): en ffmpeg 9.x la fuente `sine` sin `amplitude`
        # (el parámetro ya no existe) sale a pico ≈ -18 dB (≈0.125), muy por
        # debajo de lo que _picos necesita para que el agache se note.
        _ffmpeg("-f", "lavfi", "-i", "sine=frequency=660:sample_rate=48000",
                "-af", "volume='if(lt(mod(t,0.5),0.3),8,0)':eval=frame", "-t", "3", r["voz"])
    if not os.path.exists(r["musica"]):
        _ffmpeg("-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000", "-t", str(DURACION_S), r["musica"])
    if not os.path.exists(r["logo"]):
        Image.new("RGBA", (300, 120), (124, 58, 237, 255)).save(r["logo"])
    if not os.path.exists(r["proxy"]):
        tareas_edicion.generar_proxy(r["clon"], r["proxy"])
    return r


def _registrar(cliente, ruta, url, tipo, origen, extra=None, **campos):
    ya = materiales.buscar_hash(cliente, materiales.hash_archivo(ruta))
    if ya:
        return ya
    return materiales.registrar(cliente, tipo=tipo, origen=origen, url=url, hash=materiales.hash_archivo(ruta),
                                bytes=os.path.getsize(ruta), extra={"local": ruta, **(extra or {})}, **campos)


def sembrar(cliente, carpeta=None, url_base=None, cf_id=None):
    carpeta = carpeta or os.path.join(BASE, "static", "editor_demo", cliente)
    url_base = (url_base or f"/static/editor_demo/{cliente}").rstrip("/")
    r = _medios(carpeta)
    url = lambda k: f"{url_base}/{os.path.basename(r[k])}"   # noqa: E731
    clon = _registrar(cliente, r["clon"], url("clon"), "video", "crear", duracion_ms=DURACION_S * 1000, ancho=1080, alto=1920,
                      url_proxy=url("proxy"), extra={"proxy_version": tareas_edicion.PROXY_VERSION})
    voz = _registrar(cliente, r["voz"], url("voz"), "audio", "voz", duracion_ms=3000,
                     extra={"picos": tareas_edicion._picos(r["voz"]), "palabras": PALABRAS})
    musica = _registrar(cliente, r["musica"], url("musica"), "audio", "musica", duracion_ms=DURACION_S * 1000,
                        extra={"picos": tareas_edicion._picos(r["musica"])})
    logo = _registrar(cliente, r["logo"], url("logo"), "imagen", "marca", ancho=300, alto=120)
    voces = {"hook": {"material_id": voz["id"], "duracion_ms": 3000, "extra": voz["extra"]}}
    doc = borrador.armar_documento(GUION, [{"inicio": 0, "fin": 4}, {"inicio": 4, "fin": DURACION_S}],
                                   {"id": clon["id"], "tiene_audio": True}, voces, {"id": musica["id"]},
                                   {"color": "#7c3aed", "logo": {"id": logo["id"], "ancho": 300, "alto": 120}},
                                   "9:16", {"con_sonido": True})
    doc = borrador.fijar_precio(doc, "es", "CO", 89900)
    # un fundido entre los dos cortes: la cola de 500 ms sale del clon (el
    # primer corte termina a los 4 s de un clon de 8 s)
    doc["pistas"][0]["clips"][0]["transicion"] = {"tipo": "fundido", "duracion_ms": 500}
    return ediciones.crear(cliente, "video", "Demo de la vista previa", doc, cf_id=cf_id)["id"]


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Crea una edición de demostración para la vista previa del editor.")
    p.add_argument("--cliente", required=True, help="proyecto donde crearla (carpeta de clientes/)")
    p.add_argument("--cf", default=None, help="sesión de Crear a la que cuelga (opcional)")
    a = p.parse_args()
    eid = sembrar(a.cliente, cf_id=a.cf)
    print(f"Edición {eid}: http://127.0.0.1:5050/cliente/{a.cliente}/ediciones/{eid}")
