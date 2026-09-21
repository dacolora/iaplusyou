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


class VozFatal(ValueError):
    """Falló la voz del PRIMER bloque (voz.ErrorPrimerBloque): fatal, pero lo
    que ya se pagó y las capas ya construidas viajan con la excepción para
    que quien produce las registre (gasto y `capas` de la final). `.costo`/
    `.capas` quedan para las pruebas de Task 7; `.costo_pagado`/
    `.capas_pagadas` son el mismo par bajo el nombre genérico que `producir`
    lee de CUALQUIER excepción pagada (ver `asegurar_borrador`/`traducir`)."""

    def __init__(self, mensaje, costo, capas):
        super().__init__(mensaje)
        self.costo = costo
        self.capas = capas
        self.costo_pagado = costo
        self.capas_pagadas = capas


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
    try:
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
                raise VozFatal(f"No se pudo generar la voz (revisa la voz elegida, '{o.get('voz')}'): {e}",
                              round(costo, 4), capas) from e
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
    except VozFatal:
        raise
    except Exception as e:
        # Lo pagado y las capas construidas viajan con cualquier fallo (un
        # Conflicto al guardar, un proveedor caído) para que `producir` lo registre.
        e.costo_pagado = round(costo, 4)
        e.capas_pagadas = capas
        raise


def traducir(cliente, edicion, idioma, pais, precio, nombre_voz, con_voz):
    """Asegura el destino en la edición: localiza el guion (Claude) SOLO si
    ese destino no tiene textos todavía (`borrador.tiene_textos`) — un
    destino cuyos textos ya se localizaron pero cuya voz degradó
    (`VozIncompleta`) reusa esos textos (`borrador.guion_destino`) en vez de
    volver a pagarle a Claude; nada si el destino ya está completo del todo
    (`borrador.tiene_destino`) — el base siempre lo está. Sintetiza la voz
    de cada bloque (caché) y fija el precio del destino (None = sin badge).
    Guarda con CAS (sin reintento: en esta capa solo el worker escribe
    borradores). Devuelve (edicion recargada, capas, costo_nuevo).
    `capas["guion"]` siempre; `capas["voz"]` solo si sintetizó (o falló) voz
    nueva. Un fallo en el bloque 0 de la voz es fatal (`VozFatal`, con lo ya
    pagado y las capas construidas hasta ahí) y la edición no se guarda."""
    doc = edicion["documento"]
    capas, costo = {}, 0.0
    try:
        params = {"idioma": idioma, "pais": pais, "precio": precio}
        if borrador.tiene_destino(doc, idioma, pais):
            _capa(capas, "guion", "anthropic", params, 0.0)
            nuevo = borrador.fijar_precio(doc, idioma, pais, precio)
        else:
            if borrador.tiene_textos(doc, idioma, pais):
                g, c = borrador.guion_destino(doc, idioma, pais), 0.0
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
                    raise VozFatal(f"No se pudo generar la voz (revisa la voz elegida, '{nombre_voz}'): {e}",
                                  round(costo, 4), capas) from e
                except VozIncompleta as e:
                    costo += e.costo
                    _capa(capas, "voz", "fal/elevenlabs", {"voz": nombre_voz}, e.costo, estado="error", error=_mensaje(e))
            nuevo = borrador.agregar_destino(doc, g, voces, precio)
        ediciones.guardar(cliente, edicion["id"], nuevo, edicion["version_n"])
        return ediciones.cargar(cliente, edicion["id"]), capas, round(costo, 4)
    except VozFatal:
        raise
    except Exception as e:
        # Lo pagado y las capas construidas viajan con cualquier fallo (un
        # Conflicto al guardar, un proveedor caído) para que `producir` lo registre.
        e.costo_pagado = round(costo, 4)
        e.capas_pagadas = capas
        raise


def producir(cliente, cf_id, idioma, pais, opciones=None, on_etapa=None, ref_sufijo=""):
    """Vía del editor de `final_edition.producir` (misma firma y contrato;
    ver el docstring del módulo). Devuelve (final_id, resumen)."""
    o = final_edition._opciones(opciones)
    entry = final_edition._sesion(cliente, cf_id)
    avisar = on_etapa or (lambda nombre: None)
    variante_tipo = o.get("variante_tipo")
    # Validaciones ANTES de tocar la fila final (como siempre).
    if bool(variante_tipo) != (o.get("variante") is not None):
        raise ValueError("Para producir una variante hay que indicar `variante` (número) y "
                         "`variante_tipo` (hook | estructura) a la vez.")
    if variante_tipo and variante_tipo not in guion_mod.VARIANTES_GUION:
        raise ValueError(
            f"Tipo de variante no soportado: {variante_tipo}. Opciones: {sorted(guion_mod.VARIANTES_GUION)}")
    if o.get("sonido") not in final_edition.SONIDOS_VALIDOS:
        raise ValueError(f"Capa de sonido no soportada: {o.get('sonido')}. Opciones: {final_edition.SONIDOS_VALIDOS}")
    mezcla.volumenes_para(o.get("mezcla"), o.get("volumenes"))   # ValueError si el preset no existe
    if pais not in tipos.PAISES:
        raise ValueError(f"País no soportado: {pais}. Opciones: {sorted(tipos.PAISES)}")

    final_id = creative_flow.crear_final(cliente, cf_id, idioma, pais, variante=o.get("variante"))
    costo, costo_base, costo_variante = 0.0, 0.0, 0.0
    capas, guion = {}, None
    formato = borrador.formato_de(entry.get("aspect_ratio"))

    avisar(ETAPAS_FINAL[0][0])
    try:
        # Guion base (una vez por sesión): si aún no existe se escribe aquí
        # y su cobro queda aparte (`guion:<cf_id>`), como siempre.
        guion_base = creative_flow.guion_base(cliente, cf_id)
        if not guion_base:
            guion_base, costo_base = final_edition.preparar_guion(cliente, cf_id, o, ref_sufijo=ref_sufijo)
            costo += costo_base
        # Voz y estilo concretos ANTES de la receta (la receta los incluye).
        lista_voces = fal_audio.VOCES.get(guion_base.get("idioma") or "es") or fal_audio.VOCES["es"]
        if not o.get("voz"):
            o["voz"] = lista_voces[0]
            if variante_tipo == "hook":
                # Otra voz que la de la final original del destino (o la
                # siguiente a la de defecto si no hay original).
                o["voz"] = final_edition._siguiente(
                    lista_voces, final_edition._parametro_capa_original(cliente, cf_id, idioma, pais, "voz", "voz") or lista_voces[0])
        if not o.get("estilo_musica"):
            producto = final_edition._producto(cliente, entry, None)
            estilo = musica_mod.elegir_estilo(producto.get("tipo"), entry.get("enfoque"))
            if variante_tipo == "estructura":
                estilo = final_edition._siguiente(
                    tipos.ESTILOS_MUSICA, final_edition._parametro_capa_original(cliente, cf_id, idioma, pais, "musica", "estilo") or estilo)
            o["estilo_musica"] = estilo
        guion_trabajo = guion_base
        if variante_tipo and ediciones.buscar_origen(cliente, cf_id, borrador.receta(guion_base, o, formato)) is None:
            # La variante se escribe UNA vez por receta: los demás destinos
            # de la misma variante la leen del documento (doc["guion"]).
            guion_trabajo, costo_variante = guion_mod.variar_guion(guion_base, variante_tipo, final_edition._guia_marca(cliente))
            costo += float(costo_variante or 0.0)
            # Capa "guion" desde ya: si el borrador falla más abajo (p. ej.
            # voz fatal), lo que costó variar el guion no debe quedar fuera
            # de `capas` (la sobrescribe la de después con el costo completo).
            _capa(capas, "guion", "anthropic",
                  {"idioma": idioma, "pais": pais, "precio": None, "variante_tipo": variante_tipo}, costo_variante)
    except Exception as e:
        _capa(capas, "guion", "anthropic", {"variante_tipo": variante_tipo} if variante_tipo else {},
              estado="error", error=_mensaje(e))
        creative_flow.actualizar_final(cliente, final_id, estado="error", error=_mensaje(e), capas=_ordenar(capas))
        raise

    try:
        edicion, capas_b, c_b, _ = asegurar_borrador(cliente, cf_id, entry, guion_base, guion_trabajo, o, avisar)
        capas.update(capas_b)
        costo += c_b
        # Precio por destino (I1): el número escrito para ESE país; el atajo
        # `precio` / `precio_base` solo aplica al país base del guion.
        precios = o.get("precios") or {}
        clave = f"{idioma}_{pais}"
        if clave in precios:
            precio = precios[clave]
        elif pais == guion_trabajo.get("pais"):
            precio = o.get("precio") if o.get("precio") is not None else guion_base.get("precio_base")
        else:
            precio = None
        edicion, capas_t, c_t = traducir(cliente, edicion, idioma, pais, precio, o["voz"], bool(o.get("con_voz", True)))
        costo += c_t
        params_guion = {"idioma": idioma, "pais": pais, "precio": precio}
        if variante_tipo:
            params_guion["variante_tipo"] = variante_tipo
        _capa(capas, "guion", "anthropic", params_guion, capas_t["guion"]["costo_usd"] + float(costo_variante or 0.0))
        if "voz" in capas_t:
            previa = capas.get("voz") or {}
            estado = "error" if "error" in (previa.get("estado"), capas_t["voz"]["estado"]) else capas_t["voz"]["estado"]
            _capa(capas, "voz", "fal/elevenlabs", capas_t["voz"]["parametros"],
                  float(previa.get("costo_usd") or 0.0) + capas_t["voz"]["costo_usd"], estado=estado,
                  error=capas_t["voz"].get("error") or previa.get("error"))
        guion = borrador.guion_destino(edicion["documento"], idioma, pais)
        # 5. versión congelada + render del motor + subida (claves versionadas)
        avisar(ETAPAS_FINAL[4][0])
        version = ediciones.versionar(cliente, edicion["id"], "producir")
        res = tareas_ed.renderizar_final(cliente, final_id, version["id"], idioma, pais, avisar)
        _capa(capas, "render", "ffmpeg", {"edicion_id": edicion["id"], "edicion_version_id": version["id"],
                                          "tramos": res["tramos"], "con_ass": res["con_ass"],
                                          "mezcla": o.get("mezcla") or mezcla.PRESET_DEFECTO})
    except Exception as e:
        # Lo pagado y las capas construidas viajan con CUALQUIER excepción
        # pagada (VozFatal u otra: un Conflicto al guardar, un proveedor
        # caído) — no solo VozFatal — para no perder el cobro.
        capas.update(getattr(e, "capas_pagadas", None) or {})
        costo += float(getattr(e, "costo_pagado", 0.0) or 0.0)
        creative_flow.actualizar_final(cliente, final_id, estado="error", error=_mensaje(e), capas=_ordenar(capas),
                                       costo_usd=round(costo, 4), guion=guion)
        final_edition.registrar_gasto_final(cliente, final_id, idioma, pais, costo - costo_base, _ordenar(capas),
                                            fallo=True, ref_sufijo=ref_sufijo)
        raise

    capas = _ordenar(capas)
    degradada = any((capas.get(k) or {}).get("estado") == "error" for k in ("voz", "musica"))
    # La fila la creó `crear_final` al principio: si ya no está, algo la
    # borró en el camino — un error del worker, nada que escribirle. El
    # gasto se registra DESPUÉS de las dos comprobaciones.
    if not creative_flow.actualizar_final(
            cliente, final_id, estado="degradada" if degradada else "listo", url_video=res["url_video"],
            url_miniatura=res["url_miniatura"], duracion_s=float(res["duracion_s"]), capas=capas,
            costo_usd=round(costo, 4), guion=guion, error=None):
        raise RuntimeError(f"La final {final_id} no existe; la ruta debe crearla con creative_flow.crear_final antes de encolar.")
    if not ediciones.apuntar_final(cliente, final_id, version["id"]):
        raise RuntimeError(f"La final {final_id} no existe en pieza; la ruta debe crearla con creative_flow.crear_final antes de encolar.")
    final_edition.registrar_gasto_final(cliente, final_id, idioma, pais, costo - costo_base, capas, ref_sufijo=ref_sufijo)
    return final_id, creative_flow.final_por_legado(cliente, final_id)
