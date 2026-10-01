"""Lo que la página de vista previa del editor necesita (spec editor §3,
capa 3): los materiales del documento con sus URL (original y proxy), cuáles
faltan por preparar, los destinos que el documento sabe resolver y la
configuración que el motor del navegador comparte con el de ffmpeg — sacada
de los módulos de Python, nunca copiada a mano. Solo lectura: no cambia el
documento ni paga nada; encolar proxies es gratis (edicion_proxy)."""
import copy
import glob
import os
import re

import audios
import idiomas
import materiales
import trabajos
from final_edition import estimar, mezcla
from final_edition.documento import FORMATOS
from final_edition.motor import compilador, subtitulos
from tareas import edicion as tareas_edicion

VENTANA_PICOS_MS = 50   # tareas.edicion._picos(ventana_ms=50): un pico cada 50 ms
_FUENTES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "fonts")


def fuentes():
    """Nombres de las TTF de static/fonts (sin extensión): son los nombres
    que usan `estilo.fuente` y las @font-face de la página."""
    return sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(_FUENTES_DIR, "*.ttf")))


def config_navegador():
    return {
        "formatos": {k: list(v) for k, v in FORMATOS.items()},
        "fps": 30,
        "ventana_picos_ms": VENTANA_PICOS_MS,
        "fuentes": fuentes(),
        "mezcla": {
            "presets": mezcla.PRESETS,
            "preset_defecto": mezcla.PRESET_DEFECTO,
            "vol_musica_sola": mezcla.VOL_MUSICA_SOLA,
            "vol_musica_con_sonido": mezcla.VOL_MUSICA_CON_SONIDO,
            "ducking_musica": mezcla.DUCKING_VOZ_SOBRE_MUSICA,
            "ducking_sonido": mezcla.DUCKING_VOZ_SOBRE_SONIDO,
        },
        "subtitulos": {"estilos": subtitulos.ESTILOS_ASS, "em_por_tam": subtitulos.escala_libass()},
    }


_IDIOMA_RE = re.compile(r"^[a-z]{2}$")


def material_para(m, con_palabras=False):
    """La forma que el navegador necesita de UN material: original + proxy +
    lo medido + lo derivado del proxy (picos, tira), más lo que la
    biblioteca (spec editor capa 4b, Task 1) necesita para mostrarlo sin
    volver a tocar la base: `tiene_audio`, `nombre` y `origen`; y
    `mi_musica` (capa 4c): una canción de Mi música — también con origen
    `subida` si se subió — que se borra solo en Crear, nunca desde el editor
    (`mi_musica.py` le pone `extra.fuente`). Capa 5a: `tiene_palabras` va
    siempre (si ya se transcribió); `palabras` solo con `con_palabras=True`
    (la biblioteca general no las manda: 200 materiales con sus palabras
    pesarían cientos de KB — spec riesgo 6)."""
    extra = m.get("extra") or {}
    d = {"id": m["id"], "tipo": m["tipo"], "url": m["url"], "url_proxy": m.get("url_proxy"),
         "duracion_ms": m.get("duracion_ms"), "ancho": m.get("ancho"), "alto": m.get("alto"),
         "picos": extra.get("picos"), "proxy_version": extra.get("proxy_version"),
         "tira_url": extra.get("tira_url"), "tiene_audio": extra.get("tiene_audio"),
         "nombre": extra.get("nombre"), "origen": m["origen"], "mi_musica": es_de_mi_musica(m),
         "tiene_palabras": isinstance(extra.get("palabras"), list),
         # capa 5a (Task 8, fix round 1): el idioma que habla una voz con IA o
         # una locución, para decidir con qué idioma entra al agregarla
         "idioma": extra["idioma"] if _IDIOMA_RE.fullmatch(str(extra.get("idioma") or "")) else None}
    if con_palabras:
        d["palabras"] = extra.get("palabras")
    return d


def es_de_mi_musica(m):
    """Una canción de Mi música (subida o creada con ElevenLabs): `mi_musica.py`
    guarda `extra.fuente` en todas; ninguna otra subida lo lleva."""
    return bool((m.get("extra") or {}).get("fuente"))


def materiales_para(cliente, doc):
    """{material_id: material_para(m)} de los materiales del documento que
    existen para ESTE cliente (un id ajeno no aparece). Con sus palabras
    (capa 5a): la página del editor las necesita para derivar los
    subtítulos (`subtitulos_fuente.aplicar`) sin otra vuelta al servidor."""
    out = {}
    for mid in doc.get("materiales") or []:
        m = materiales.obtener(cliente, int(mid))
        if not m:
            continue
        out[int(mid)] = material_para(m, con_palabras=True)
    return out


def faltantes(doc, mats):
    return sorted(int(m) for m in doc.get("materiales") or [] if int(m) not in mats)


def pendientes(mats):
    """Videos sin proxy o con proxy de una receta anterior, y audios sin
    picos (el agache de la música los necesita)."""
    out = []
    for mid, m in mats.items():
        if m["tipo"] == "video":
            if not m.get("url_proxy") or (m.get("proxy_version") or 1) < tareas_edicion.PROXY_VERSION:
                out.append(mid)
        elif m["tipo"] == "audio" and m.get("picos") is None:
            out.append(mid)
    return sorted(out)


def encolar_proxies(cliente, ids):
    """Una tarea edicion_proxy por material (gratis, max_intentos=3); un
    job_id que ya está vivo no se repite. Devuelve cuántas encoló."""
    n = 0
    for mid in ids:
        if trabajos.encolar(tareas_edicion.job_id_proxy(cliente, mid), "edicion_proxy",
                            {"cliente": cliente, "material_id": int(mid)},
                            duracion_estimada=60, cliente=cliente, max_intentos=3):
            n += 1
    return n


def destinos(doc):
    """Destinos (`<idioma>_<PAIS>`) que el documento menciona en textos,
    voces, precios, subtítulos o voces por destino; el del guion base
    primero. Sin ninguno: el idioma base con el país del guion, o el de
    `origen.pais` (la edición armada desde el clon lleva el del proyecto),
    o CO."""
    claves = set()
    var = doc.get("variables") or {}
    for grupo in ("textos", "voz"):
        for valores in (var.get(grupo) or {}).values():
            claves.update(k for k in (valores or {}) if "_" in k)
    claves.update(var.get("precios") or {})
    claves.update(k for k in ((doc.get("subtitulos") or {}).get("palabras") or {}) if "_" in k)
    for p in doc.get("pistas") or []:
        for c in p.get("clips") or []:
            claves.update(k for k in (c.get("por_destino") or {}) if "_" in k)
    pais = (doc.get("guion") or {}).get("pais") or (doc.get("origen") or {}).get("pais") or "CO"
    base = f"{doc.get('idioma_base') or 'es'}_{pais}"
    if not claves:
        claves.add(base)
    return sorted(claves, key=lambda k: (k != base, k))


def documento_para_vista(doc, mats):
    """Copia del documento con los recortes que el render de verdad usa:
    `compilador.verificar_recortes`, con las duraciones medidas de los
    materiales, acorta o quita una transición cuya cola no cabe en el
    material — así la vista previa no muestra un fundido donde el video final
    hace corte seco. Si un clip pide más material del que hay (el render
    fallaría), devuelve el documento tal cual y el aviso en vez de lanzar."""
    copia = copy.deepcopy(doc)
    duraciones = {mid: m["duracion_ms"] for mid, m in mats.items() if m.get("duracion_ms")}
    try:
        compilador.verificar_recortes(copia, duraciones)
    except ValueError as e:
        return doc, str(e)
    return copia, None


def _voces_traducidas():
    """`audios.fichas_voces()` con `genero_nombre` y `tono` traducidos (son
    msgids N_): la galería de voces del editor (D9/D12) no tiene plantilla
    Jinja que los traduzca sola, a diferencia de Crear › Audios."""
    salida = []
    for ficha in audios.fichas_voces():
        salida.append({**ficha, "genero_nombre": idiomas.traducir(ficha["genero_nombre"]),
                       "tono": idiomas.traducir(ficha["tono"])})
    return salida


def datos_pagina(cliente, edicion, urls):
    from final_edition import biblioteca   # import tardío: biblioteca importa este módulo
    mats = materiales_para(cliente, edicion["documento"])
    doc, aviso = documento_para_vista(edicion["documento"], mats)
    job_subtitulos = tareas_edicion.job_id_transcribir(cliente, edicion["id"])
    job_voz = tareas_edicion.job_id_voz(cliente, edicion["id"])
    return {
        "edicion": {"id": edicion["id"], "nombre": edicion["nombre"], "version_n": edicion["version_n"]},
        "documento": doc,
        "aviso_recortes": aviso,
        "materiales": {str(k): v for k, v in mats.items()},
        "pendientes": pendientes(mats),
        "faltantes": faltantes(doc, mats),
        "destinos": destinos(doc),
        "config": config_navegador(),
        "estimado_s": estimar.segundos(doc),
        "cf_id": edicion.get("cf_id"),
        # Capa 5a: idiomas disponibles para transcribir y si ya hay una
        # transcripción corriendo en esta edición (la barra sigue viva si la
        # página se recarga mientras tanto).
        "subtitulos": {"idiomas": list(audios.IDIOMAS), "nombres_idioma": audios.NOMBRES_IDIOMA},
        # Task 6: voz con IA (la galería de Crear › Audios) y grabación con el micrófono.
        "voces": _voces_traducidas(),
        "voz": {"idiomas": list(audios.IDIOMAS), "nombres_idioma": audios.NOMBRES_IDIOMA,
               "velocidades": {k: idiomas.traducir(v) for k, v in audios.NOMBRES_VELOCIDAD.items()},
               "max_caracteres": audios.MAX_CARACTERES, "idioma_defecto": audios.idioma_defecto(cliente)},
        "grabacion": {"max_ms": biblioteca.MAX_GRABACION_MS, "max_bytes": materiales.LIMITES["audio"][0]},
        "trabajos_vivos": {"subtitulos": job_subtitulos if trabajos.en_curso(job_subtitulos) else None,
                           "voz": job_voz if trabajos.en_curso(job_voz) else None},
        "urls": urls,
    }
