"""
Compara Seedance 2.5 con su acceso Turbo de WaveSpeed antes de cambiar el modelo
de Crear (US$ 0,20/s contra 0,36 a 720p, un 44 % menos; lo verificado y lo que
falta en docs/investigacion/2026-10-01-seedance-turbo.md). Regenera con Turbo
piezas de Seedance que YA existen, con las mismas entradas que usó el worker
(`tareas.flowplus._preparar`: prompt, imagen de arranque, duración, formato y
sonido; solo cambia la ruta), y deja una página con los dos videos lado a lado.
Es una herramienta de investigación aparte, como comparar_modelos.py: no toca
la sesión de Crear ni crea piezas nuevas.

Uso (en el VPS: ahí están las llaves y wavespeed.ai responde):
    venv/bin/python3 comparar_seedance_turbo.py --cliente happyflops
        Gratis: lista las últimas piezas de Seedance con lo que costaría cada una.
    venv/bin/python3 comparar_seedance_turbo.py --cliente happyflops --cf <id> --cf <id>
        Gratis: muestra el precio de esas piezas en Turbo y el total.
    venv/bin/python3 comparar_seedance_turbo.py --cliente happyflops --cf <id> --cf <id> --generar
        Muestra el total y pide escribir «si» antes de cobrar nada.

Gasto: cada video Turbo se anota en `gasto` (tipo `video`, referencia
`turbo:<cf_id>:<marca>`) apenas WaveSpeed lo entrega, o con el detalle «espera
agotada» si se dejó de esperar (WaveSpeed sigue y cobra igual). Un rechazo del
proveedor no se anota: no entregó nada.
"""
import argparse
import html
import os
import sys
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

import creative_flow
import gastos
import idiomas
from providers import flowplus_modelos, wavespeed_common
from storage import r2_uploader

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MODELO = "seedance25"
# Rutas y precio del acceso Turbo (fuentes en el doc de investigación): mismos
# parámetros que la ruta normal salvo 480p, que no tiene; Crear siempre pide 720p.
PATH_TURBO = "bytedance/seedance-2.5/image-to-video-turbo"
PATH_TEXTO_TURBO = "bytedance/seedance-2.5/text-to-video-turbo"
USD_POR_SEGUNDO_TURBO = 0.20
NOMBRE_TURBO = "Seedance 2.5 Turbo"
MAX_PIEZAS = 5


class PiezaNoComparable(ValueError):
    """La pieza no existe, no es un video de Seedance 2.5 terminado o usa algo
    que el acceso Turbo no recibe igual."""


def usd_turbo(duracion):
    return round(USD_POR_SEGUNDO_TURBO * duracion, 3)


def candidatas(cliente, n=10):
    """Las `n` piezas de video de Seedance 2.5 terminadas más recientes."""
    salida = []
    for cf_id, e in creative_flow.cargar(cliente).items():
        if (e.get("modelo") == MODELO and (e.get("tipo") or "video") == "video"
                and e.get("estado") == "video_listo" and e.get("video_url")):
            duracion = flowplus_modelos.ajustar_duracion(MODELO, e.get("duracion_objetivo") or 0)
            salida.append({"cf_id": cf_id, "creado_en": e.get("creado_en"), "duracion": duracion,
                           "prompt": e.get("prompt_relleno") or e.get("accion_central") or "",
                           "con_imagen": bool(e.get("referencias_urls")), "usd_turbo": usd_turbo(duracion)})
    # El id lleva la hora con microsegundos: desempata dos del mismo segundo.
    salida.sort(key=lambda c: (str(c["creado_en"] or ""), c["cf_id"]), reverse=True)
    return salida[:n]


def entradas(cliente, cf_id):
    """Lo que se le manda a Turbo para regenerar `cf_id`: exactamente lo que
    `flowplus_modelos.generar_video` le mandó a Seedance 2.5 (mismo prompt,
    misma imagen, misma duración, formato y sonido), con la ruta Turbo."""
    from tareas import flowplus
    try:
        entry, referencias, _videos, duracion, prompt, _plat, aspect_ratio, modelo, _cal = \
            flowplus._preparar(cliente, cf_id)
    except flowplus.SesionDescartada:
        raise PiezaNoComparable(f"{cf_id}: no existe en {cliente}.") from None
    if (entry.get("tipo") or "video") != "video" or entry.get("estado") != "video_listo" or not entry.get("video_url"):
        raise PiezaNoComparable(f"{cf_id}: no es un video terminado (estado {entry.get('estado')}).")
    if entry.get("modelo") != MODELO or modelo != MODELO:
        raise PiezaNoComparable(f"{cf_id}: no es de Seedance 2.5 (modelo {entry.get('modelo')}).")
    if entry.get("imagen_inicial") or entry.get("elementos"):
        raise PiezaNoComparable(f"{cf_id}: es una escena de una cadena; no se compara.")
    con_sonido = entry.get("con_sonido", True) is not False
    payload = {"prompt": prompt, "duration": int(duracion), "resolution": "720p", "generate_audio": bool(con_sonido)}
    if referencias:
        payload["image"] = referencias[0]
        path = PATH_TURBO
    else:
        if aspect_ratio:
            payload["aspect_ratio"] = aspect_ratio
        path = PATH_TEXTO_TURBO
    usd_original = entry.get("usd")
    if usd_original is None:
        usd_original = flowplus_modelos.estimate_video(MODELO, duracion, con_sonido=con_sonido)["usd"]
    return {"cf_id": cf_id, "path": path, "payload": payload, "duracion": int(duracion),
            "usd_turbo": usd_turbo(int(duracion)), "usd_original": usd_original, "video_url": entry["video_url"]}


def _bajar(url, destino):
    with requests.get(url, stream=True, timeout=180) as r:
        r.raise_for_status()
        with open(destino, "wb") as f:
            for trozo in r.iter_content(1 << 20):
                f.write(trozo)


def generar(cliente, e, marca, avisar=print):
    """Genera UNA pieza con Turbo, la sube a R2 y anota el gasto. Nunca lanza:
    devuelve el resultado con `url` o con `error`."""
    resultado = dict(e, segundos=None, url=None, error=None, prediction_id=None)
    ref = f"turbo:{e['cf_id']}:{marca}"

    def _progreso(p):
        resultado["prediction_id"] = p.get("prediction_id") or resultado["prediction_id"]
        if p.get("fase") == "created":
            avisar(f"  {e['cf_id']}: lanzada (predicción {resultado['prediction_id']})")

    inicio = time.time()
    try:
        url_ws = flowplus_modelos._lanzar(e["path"], e["payload"], NOMBRE_TURBO, on_progreso=_progreso)
    except wavespeed_common.EsperaAgotada as err:
        resultado["prediction_id"] = err.prediction_id or resultado["prediction_id"]
        resultado["error"] = f"se dejó de esperar; WaveSpeed sigue (predicción {resultado['prediction_id']})"
        gastos.registrar_seguro(cliente, "video", e["usd_turbo"], ref, proveedor="wavespeed",
                                detalle=f"{NOMBRE_TURBO} (comparación): espera agotada, "
                                        f"predicción {resultado['prediction_id']}")
        return resultado
    except Exception as err:  # noqa: BLE001 — una pieza que falla no frena a las demás
        resultado["error"] = str(err)[:300]
        return resultado
    resultado["segundos"] = round(time.time() - inicio)
    gastos.registrar_seguro(cliente, "video", e["usd_turbo"], ref, proveedor="wavespeed",
                            detalle=f"{NOMBRE_TURBO} (comparación con {e['cf_id']}), {e['duracion']} s")
    try:
        carpeta = os.path.join(BASE_DIR, "salidas", cliente, "comparacion_turbo", marca)
        os.makedirs(carpeta, exist_ok=True)
        local = os.path.join(carpeta, f"{e['cf_id']}.mp4")
        _bajar(url_ws, local)
        resultado["url"] = r2_uploader.upload_file(
            local, f"clientes/{cliente}/comparaciones/seedance_turbo/{marca}/{e['cf_id']}.mp4", "video/mp4")
    except Exception as err:  # noqa: BLE001 — ya está pagado: queda el enlace de WaveSpeed
        resultado["url"] = url_ws
        resultado["error"] = f"no se pudo copiar a R2 ({str(err)[:200]}); el enlace de WaveSpeed vence"
    return resultado


def pagina(cliente, marca, resultados):
    """HTML con el original y el Turbo de cada pieza, lado a lado."""
    filas = []
    for r in resultados:
        turbo = (f'<video src="{html.escape(r["url"])}" controls playsinline preload="metadata"></video>'
                 if r.get("url") else f'<p class="error">{html.escape(r.get("error") or "sin video")}</p>')
        nota = f' · {html.escape(r["error"])}' if r.get("url") and r.get("error") else ""
        tiempo = f' · tardó {r["segundos"]} s' if r.get("segundos") is not None else ""
        filas.append(f"""<section>
  <h2>{html.escape(r["cf_id"])} · {r["duracion"]} s</h2>
  <p class="prompt">{html.escape(r["payload"]["prompt"])}</p>
  <div class="par">
    <figure><video src="{html.escape(r["video_url"])}" controls playsinline preload="metadata"></video>
      <figcaption>Seedance 2.5 · US$ {r["usd_original"]:.2f}</figcaption></figure>
    <figure>{turbo}<figcaption>Turbo · US$ {r["usd_turbo"]:.2f}{tiempo}{nota}</figcaption></figure>
  </div>
</section>""")
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Seedance 2.5 contra Turbo · {html.escape(cliente)}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 0 auto; max-width: 960px; padding: 16px; background: #fafafa; color: #222; }}
  h1 {{ font-size: 22px; }}
  h2 {{ font-size: 16px; overflow-wrap: anywhere; }}
  section {{ margin-bottom: 32px; }}
  .par {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
  figure {{ margin: 0; }}
  video {{ width: 100%; border-radius: 6px; background: #000; }}
  .prompt {{ font-size: 13px; color: #555; white-space: pre-wrap; max-height: 6em; overflow: auto; }}
  .error {{ color: #a30000; }}
  @media (prefers-color-scheme: dark) {{ body {{ background: #161616; color: #eee; }} .prompt {{ color: #aaa; }} }}
</style></head><body>
<h1>Seedance 2.5 contra Turbo</h1>
<p>{html.escape(cliente)} · {html.escape(marca)} · mismas entradas, solo cambia la ruta. Mira sobre todo caras,
manos, el producto y si el movimiento se sostiene.</p>
{"".join(filas)}
</body></html>
"""


def _tabla(lista, columnas):
    """Columnas alineadas; `tope` corta solo los textos largos (None = nunca)."""
    anchos = {c: max(len(str(f[c])) for f in lista) for c, _ in columnas}
    anchos = {c: min(anchos[c], tope) if tope else anchos[c] for c, tope in columnas}
    for fila in lista:
        print("  " + "  ".join(str(fila[c])[:anchos[c]].ljust(anchos[c]) for c, _ in columnas).rstrip())


def main(argv=None, preguntar=input):
    parser = argparse.ArgumentParser(description="Regenera piezas de Seedance 2.5 con Turbo para compararlas.")
    parser.add_argument("--cliente", required=True)
    parser.add_argument("--cf", action="append", default=[], help="id de la pieza de Crear (se repite)")
    parser.add_argument("--ultimas", type=int, default=10, help="cuántas candidatas listar (sin --cf)")
    parser.add_argument("--generar", action="store_true", help="generar de verdad (pide confirmación)")
    args = parser.parse_args(argv)
    cliente = args.cliente
    load_dotenv(os.path.join(BASE_DIR, ".env"))

    with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
        if not args.cf:
            lista = candidatas(cliente, args.ultimas)
            if not lista:
                print(f"{cliente} no tiene videos de Seedance 2.5 terminados.")
                return 0
            print(f"Últimos videos de Seedance 2.5 de {cliente} (nada se cobra al listar):")
            for c in lista:
                c["usd"] = f"US$ {c['usd_turbo']:.2f}"
                c["fecha"] = str(c["creado_en"] or "")[:16]
                c["imagen"] = "imagen" if c["con_imagen"] else "solo texto"
                c["texto"] = " ".join(c["prompt"].split())
            _tabla(lista, (("cf_id", None), ("fecha", None), ("duracion", None), ("imagen", None), ("usd", None),
                           ("texto", 60)))
            print("\nElige 2 o 3 y repite con --cf <id> --cf <id> para ver el total (y --generar para generarlas).")
            return 0

        ids = list(dict.fromkeys(args.cf))
        if len(ids) > MAX_PIEZAS:
            print(f"Como mucho {MAX_PIEZAS} piezas por corrida.")
            return 2
        try:
            lista = [entradas(cliente, cf_id) for cf_id in ids]
        except PiezaNoComparable as err:
            print(f"No se puede comparar {err}")
            return 2
        total = round(sum(e["usd_turbo"] for e in lista), 3)
        print(f"Se regenerarían con {NOMBRE_TURBO} (US$ {USD_POR_SEGUNDO_TURBO:.2f}/s a 720p):")
        for e in lista:
            e["s"] = f"{e['duracion']} s"
            e["orig"] = f"original US$ {e['usd_original']:.2f}"
            e["turbo"] = f"Turbo US$ {e['usd_turbo']:.2f}"
            e["ruta"] = "imagen" if e["path"] == PATH_TURBO else "solo texto"
        _tabla(lista, (("cf_id", None), ("s", None), ("ruta", None), ("orig", None), ("turbo", None)))
        print(f"Total: US$ {total:.2f}")
        if not args.generar:
            print("Nada se generó. Agrega --generar para generarlas.")
            return 0
        respuesta = preguntar(f"Esto cobra ≈ US$ {total:.2f} en WaveSpeed. Escribe «si» para generar: ")
        if respuesta.strip().lower() not in ("si", "sí"):
            print("Cancelado: no se cobró nada.")
            return 1

        marca = datetime.now().strftime("%Y%m%d-%H%M%S")
        resultados = []
        for e in lista:
            print(f"Generando {e['cf_id']} ({e['duracion']} s)…")
            r = generar(cliente, e, marca)
            print(f"  {'listo' if r['url'] else 'falló'}: {r['url'] or r['error']}")
            resultados.append(r)

        carpeta = os.path.join(BASE_DIR, "salidas", cliente, "comparacion_turbo", marca)
        os.makedirs(carpeta, exist_ok=True)
        ruta_html = os.path.join(carpeta, "index.html")
        with open(ruta_html, "w", encoding="utf-8") as f:
            f.write(pagina(cliente, marca, resultados))
        try:
            url = r2_uploader.upload_file(
                ruta_html, f"clientes/{cliente}/comparaciones/seedance_turbo/{marca}/index.html",
                "text/html; charset=utf-8")
            print(f"\nComparación lado a lado: {url}")
        except Exception as err:  # noqa: BLE001 — la página local sigue ahí
            print(f"\nNo pude subir la página ({err}); está en {ruta_html}")
        return 0 if all(r["url"] for r in resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
