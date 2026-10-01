"""Precalienta las muestras de voz de la galería de Audios (Crear › Audios):
sintetiza una vez, con fal (ElevenLabs), la frase corta de cada voz en cada
idioma y la deja en R2 bajo el cliente interno `_creatv` (audios.muestra: lo que
ya existe no se vuelve a pagar). Así la primera persona que toca ▶ no espera.

Uso, con el .env de la raíz cargado (en el VPS, como deploy):
    TZ=America/Bogota venv/bin/python3 precalentar_muestras.py            # todas
    TZ=America/Bogota venv/bin/python3 precalentar_muestras.py es en      # solo esos idiomas
Costo: unos US$ 0,005 por muestra nueva (22 voces × 10 idiomas; el noruego va por Turbo y cuesta la mitad)."""
import os
import sys
import time

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

import audios  # noqa: E402
import materiales  # noqa: E402


def main(idiomas_pedidos):
    idiomas_ = [i for i in idiomas_pedidos if i in audios.IDIOMAS] or list(audios.IDIOMAS)
    nuevas = existentes = fallidas = 0
    for idioma in idiomas_:
        for voz in audios.voces():
            ya = materiales.buscar_hash(audios.CLIENTE_MUESTRAS, audios.hash_muestra(voz, idioma))
            if ya:
                existentes += 1
                continue
            t0 = time.time()
            try:
                url = audios.muestra(voz, idioma)
            except Exception as e:  # noqa: BLE001 — una voz caída no para las demás
                fallidas += 1
                print(f"[{idioma}] {voz}: FALLÓ {type(e).__name__}: {e}")
                continue
            nuevas += 1
            print(f"[{idioma}] {voz}: lista en {time.time() - t0:.1f} s → {url}")
    print(f"nuevas {nuevas} · ya existían {existentes} · fallidas {fallidas}")
    return 1 if fallidas else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
