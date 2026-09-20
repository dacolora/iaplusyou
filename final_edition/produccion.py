"""Producción de una final por la vía del editor (spec §2.4, §5, §7.2): el
`final_producir` de siempre pasa a ser guion → borrador (una edición
reutilizable por receta) → traducción del destino → versión → render del
motor → final. Mismo contrato que tenía `final_edition.producir` (firma,
`final_id`, `capas`, `pieza.guion`, gasto `final:<id>:t<tarea>`, estados
listo / degradada / error) para que dashboard, derivaciones y la tarjeta de
la final no cambien. Nada se paga dos veces: clon, voz y música son
materiales con caché por hash (insumos.py); el borrador de una receta se
hace una vez y cada destino nuevo solo paga su localización y su voz.

Etapas reportadas: las 5 de ETAPAS_FINAL, en orden. La traducción del
destino corre bajo «Música» (sin etapa propia: la barra no retrocede).
Las carpetas de trabajo del borrador no se borran (ver insumos)."""
import copy
import os

import cola
import creative_flow
import ediciones
import final_edition
from final_edition import ETAPAS_FINAL, borrador, cortes, guion as guion_mod, insumos, mezcla, musica as musica_mod, tipos
from final_edition import voz as voz_mod
from providers import fal_audio
from tareas import edicion as tareas_ed

_ORDEN_CAPAS = ("guion", "cortes", "sonido", "voz", "musica", "texto", "render")


class VozIncompleta(Exception):
    """Falló la voz de un bloque que no es el primero: la pieza sale sin
    voz (degradada) y lo pagado hasta ahí cuenta."""

    def __init__(self, mensaje, costo):
        super().__init__(mensaje)
        self.costo = costo


def _mensaje(e):
    return cola.recortar(cola.sin_token(str(e)), 500)


def _capa(capas, nombre, proveedor, parametros, costo=0.0, estado="ok", error=None):
    capas[nombre] = {"proveedor": proveedor, "parametros": parametros, "costo_usd": round(float(costo or 0.0), 4),
                     "estado": estado, "error": error}


def _ordenar(capas):
    """Las capas en el orden de siempre (guion → render): la tarjeta y el
    detalle del gasto las listan en orden de inserción."""
    return {k: capas[k] for k in _ORDEN_CAPAS if k in capas}


def _carpeta_borrador(cliente, cf_id):
    c = os.path.join(final_edition._carpeta_salidas(), cliente, "ediciones", f"borrador_{cf_id}")
    os.makedirs(c, exist_ok=True)
    return c


def _voces_bloques(cliente, guion, nombre_voz, carpeta):
    """{rol: {material_id, duracion_ms, extra}} y el costo nuevo. Un fallo
    en el PRIMER bloque es fatal (voz.ErrorPrimerBloque: casi siempre es
    determinístico —voz inválida, texto vacío— y fallaría igual en todos);
    en otro bloque → VozIncompleta con lo ya pagado."""
    voces, costo = {}, 0.0
    idioma = guion.get("idioma") or "es"
    for i, bl in enumerate(guion.get("bloques") or []):
        ventana_ms = max(1, borrador.ms(bl.get("fin_s")) - borrador.ms(bl.get("inicio_s")))
        try:
            mat, c = insumos.voz_bloque(cliente, bl.get("texto_voz") or "", nombre_voz, idioma, ventana_ms, carpeta)
        except Exception as e:
            if i == 0:
                raise voz_mod.ErrorPrimerBloque(str(e)) from e
            raise VozIncompleta(str(e), round(costo, 4)) from e
        voces[bl["rol"]] = {"material_id": mat["id"], "duracion_ms": int(mat["duracion_ms"] or 0),
                            "extra": mat.get("extra") or {}}
        costo += float(c or 0.0)
    return voces, round(costo, 4)


def asegurar_borrador(cliente, cf_id, entry, guion_base, guion, o, avisar):
    """La edición-borrador de la sesión para esta receta: la reutiliza si
    existe (y no quedó degradada) o la crea pagando solo lo que falte.
    `guion` es el base o el variado (variante); la receta se calcula con el
    BASE + las opciones (`borrador.receta`). Devuelve (edicion, capas,
    costo_nuevo, creada). Reporta «Cortes», «Voz» y «Música» solo al crear."""
    formato = borrador.formato_de(entry.get("aspect_ratio"))
    rec = borrador.receta(guion_base, o, formato)
    existente = ediciones.buscar_origen(cliente, cf_id, rec)
    if existente:
        capas = copy.deepcopy(((existente["documento"].get("origen") or {}).get("capas")) or {})
        for c in capas.values():
            c["costo_usd"] = 0.0
        return existente, capas, 0.0, False

    capas, costo, degradada = {}, 0.0, False
    carpeta = _carpeta_borrador(cliente, cf_id)
    # 1. clon como material + cortes → segmentos
    avisar(ETAPAS_FINAL[1][0])
    clon_local = final_edition._clon_local(cliente, cf_id, entry)
    clon_mat, _ = insumos.clon(cliente, cf_id, entry, clon_local)
    extra_clon = clon_mat.get("extra") or {}
    cortes_s = [c / 1000.0 for c in extra_clon.get("cortes_ms") or []]
    duracion_clon = int(clon_mat["duracion_ms"] or 0) / 1000.0
    fin_guion = (guion.get("bloques") or [{}])[-1].get("fin_s") or duracion_clon
    segmentos = cortes.planificar_segmentos(duracion_clon, cortes_s, float(fin_guion))
    if not segmentos:
        raise RuntimeError("El clon no da para ningún segmento.")
    _capa(capas, "cortes", "ffmpeg", {"cortes": cortes_s, "segmentos": len(segmentos)})
    duracion_final = float(segmentos[-1]["fin"])
    # 1b. sonido de la escena (gratis; el clon mudo no degrada la pieza)
    pedir_sonido = bool(o.get("con_sonido", True)) and o.get("sonido") == "nativo"
    params_sonido = {"sonido": o.get("sonido"), "mezcla": o.get("mezcla") or mezcla.PRESET_DEFECTO,
                     "volumenes": mezcla.volumenes_para(o.get("mezcla"), o.get("volumenes"))}
    if not pedir_sonido:
        _capa(capas, "sonido", "nativo", params_sonido, estado="omitida")
    elif extra_clon.get("tiene_audio") is True:
        _capa(capas, "sonido", "nativo", params_sonido, estado="ok")
    else:
        _capa(capas, "sonido", "nativo", params_sonido, estado="ausente")
    # 2. voz por bloque (degradable, salvo el primer bloque)
    avisar(ETAPAS_FINAL[2][0])
    voces = None
    if not o.get("con_voz", True):
        _capa(capas, "voz", "fal/elevenlabs", {"voz": o.get("voz")}, estado="omitida")
    else:
        try:
            voces, c = _voces_bloques(cliente, guion, o.get("voz"), carpeta)
            costo += c
            _capa(capas, "voz", "fal/elevenlabs", {"voz": o.get("voz")}, c)
        except voz_mod.ErrorPrimerBloque as e:
            _capa(capas, "voz", "fal/elevenlabs", {"voz": o.get("voz")}, estado="error", error=_mensaje(e))
            raise ValueError(f"No se pudo generar la voz (revisa la voz elegida, '{o.get('voz')}'): {e}") from e
        except VozIncompleta as e:
            degradada, voces = True, None
            costo += e.costo
            _capa(capas, "voz", "fal/elevenlabs", {"voz": o.get("voz")}, e.costo, estado="error", error=_mensaje(e))
    # 3. música (degradable)
    avisar(ETAPAS_FINAL[3][0])
    musica = None
    if not o.get("con_musica", True):
        _capa(capas, "musica", "fal/stable-audio", {"estilo": o.get("estilo_musica")}, estado="omitida")
    else:
        try:
            mat, c = insumos.musica(cliente, o.get("estilo_musica"), duracion_final)
            musica = {"id": mat["id"]}
            costo += c
            _capa(capas, "musica", "fal/stable-audio", {"estilo": o.get("estilo_musica"), "url": mat.get("url")}, c)
        except Exception as e:
            degradada = True
            _capa(capas, "musica", "fal/stable-audio", {"estilo": o.get("estilo_musica")}, estado="error", error=_mensaje(e))
    # 4. el documento
    logo = insumos.logo(cliente)
    marca = {"color": final_edition._color_acento(cliente),
             "logo": ({"id": logo["id"], "ancho": logo["ancho"], "alto": logo["alto"]}
                      if logo and logo.get("ancho") and logo.get("alto") else None)}
    _capa(capas, "texto", "pillow", {"formato": formato, "logo": bool(marca["logo"])})
    origen = {"tipo": "borrador", "cf_id": cf_id, "variante": o.get("variante"), "variante_tipo": o.get("variante_tipo"),
              "receta": rec, "degradada": degradada, "capas": copy.deepcopy(capas)}
    clon = {"id": clon_mat["id"], "duracion_ms": clon_mat["duracion_ms"], "ancho": clon_mat.get("ancho"),
            "alto": clon_mat.get("alto"), "tiene_audio": extra_clon.get("tiene_audio")}
    doc = borrador.armar_documento(guion, segmentos, clon, voces, musica, marca, formato,
                                   {"con_sonido": pedir_sonido, "mezcla": o.get("mezcla"), "volumenes": o.get("volumenes")},
                                   origen=origen)
    nombre = "Borrador" if o.get("variante") is None else f"Variante {int(o['variante'])} ({o.get('variante_tipo')})"
    nombre += " · " + (entry.get("accion_central") or cf_id)[:60]
    edicion = ediciones.crear(cliente, "video", nombre, doc, cf_id=cf_id, creada_por="final_edition")
    return edicion, capas, round(costo, 4), True


def traducir(cliente, edicion, idioma, pais, precio, nombre_voz, con_voz):
    """Asegura el destino en la edición: localiza el guion (Claude; nada si
    el destino ya está — el base siempre lo está), sintetiza la voz de cada
    bloque (caché) y fija el precio del destino (None = sin badge). Guarda
    con CAS (sin reintento: en esta capa solo el worker escribe borradores).
    Devuelve (edicion recargada, capas, costo_nuevo). `capas["guion"]`
    siempre; `capas["voz"]` solo si sintetizó (o falló) voz nueva."""
    doc = edicion["documento"]
    capas, costo = {}, 0.0
    params = {"idioma": idioma, "pais": pais, "precio": precio}
    if borrador.tiene_destino(doc, idioma, pais):
        _capa(capas, "guion", "anthropic", params, 0.0)
        nuevo = borrador.fijar_precio(doc, idioma, pais, precio)
    else:
        g, c = guion_mod.localizar_guion(doc.get("guion") or {}, idioma, pais, precio)
        costo += float(c or 0.0)
        _capa(capas, "guion", "anthropic", params, c)
        voces = None
        hay_pista_voz = any(p["tipo"] == "audio" and any(cl.get("rol_audio") == "voz" for cl in p["clips"]) for p in doc["pistas"])
        if con_voz and hay_pista_voz:
            carpeta = _carpeta_borrador(cliente, edicion.get("cf_id") or f"ed{edicion['id']}")
            try:
                voces, cv = _voces_bloques(cliente, g, nombre_voz, carpeta)
                costo += cv
                _capa(capas, "voz", "fal/elevenlabs", {"voz": nombre_voz}, cv)
            except voz_mod.ErrorPrimerBloque as e:
                _capa(capas, "voz", "fal/elevenlabs", {"voz": nombre_voz}, estado="error", error=_mensaje(e))
                raise ValueError(f"No se pudo generar la voz (revisa la voz elegida, '{nombre_voz}'): {e}") from e
            except VozIncompleta as e:
                costo += e.costo
                _capa(capas, "voz", "fal/elevenlabs", {"voz": nombre_voz}, e.costo, estado="error", error=_mensaje(e))
        nuevo = borrador.agregar_destino(doc, g, voces, precio)
    ediciones.guardar(cliente, edicion["id"], nuevo, edicion["version_n"])
    return ediciones.cargar(cliente, edicion["id"]), capas, round(costo, 4)
