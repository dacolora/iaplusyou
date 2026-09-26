"""Final edition: localización, producción y render de piezas finales por
idioma/país a partir de un clon de creative flow. `producir` despacha a la vía
del editor (`produccion.py`); `producir_legado` conserva el pipeline por capas
hasta que `render.py`/`texto.py` se retiren.

Orquestador de las capas (`guion` -> `cortes` -> `sonido` -> `voz` -> `musica`
-> `texto` -> `render`) y del estado en la base (`creative_flow.crear_final` /
`actualizar_final`). Dos entradas:

  preparar_guion(cliente, cf_id, opciones) -> (guion_base, costo_usd)
      Escribe el guion base (idioma base) con lo que hay en la sesión y lo
      guarda en el concepto. Se hace UNA vez por sesión; cada idioma/país
      después solo localiza.

  producir(cliente, cf_id, idioma, pais, opciones, on_etapa) -> (final_id, resumen)
      Produce una pieza final. Voz y música son degradables: si fallan la
      pieza sale igual sin esa capa (`estado="degradada"`). Guion, cortes,
      texto y render no: la pieza queda en `error` y la excepción se relanza.
      La capa `sonido` (spec estudio S2) es el audio nativo del clon: gratis,
      se conserva desde el clon CRUDO (`video_local_crudo`/`video_url_crudo`,
      nunca el mezclado con música, que la pondría dos veces) y se mezcla con
      voz y música según `opciones["mezcla"]` (preset de `mezcla.PRESETS`) y
      `opciones["volumenes"]`; un clon mudo deja la capa `ausente` sin
      degradar la pieza, `con_sonido=False` o `sonido="ninguno"` la omiten.

Las capas se invocan siempre como atributo de su módulo (`voz.sintetizar`,
`render.componer`, ...) para que las pruebas puedan sustituirlas una a una.
"""
import os
import shutil

import requests

import catalogo_productos
import creative_flow
import db
import gastos
import marca
import proyectos
import tiendas
from final_edition import cortes, guion as guion_mod, mezcla, musica, render, texto, tipos, voz
from providers import fal_audio
from storage import r2_uploader

# Monkeypatchable en pruebas: raíz bajo la que viven salidas/ y clientes/.
BASE_DIR = tipos.BASE_DIR

# (nombre, duración estimada en s) — el mismo orden en que se ejecutan.
ETAPAS_FINAL = (
    ("Escribiendo el guion", 10),
    ("Cortes", 5),
    ("Voz", 25),
    ("Música", 15),
    ("Texto y render", 45),
)

COLOR_ACENTO_DEFECTO = texto.COLOR_ACENTO_DEFECTO
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
_TAMANOS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080), "4:5": (1080, 1350)}
_OPCIONES_DEFECTO = {"voz": None, "estilo_musica": None, "precio": None, "precios": None, "con_voz": True,
                     "con_musica": True, "idioma_base": "es", "duracion_s": None,
                     "variante": None, "variante_tipo": None,
                     # Capa "sonido" (spec estudio S2): el audio nativo del clon.
                     "con_sonido": True, "sonido": "nativo", "mezcla": mezcla.PRESET_DEFECTO, "volumenes": None}
SONIDOS_VALIDOS = ("nativo", "ninguno")


# ------------------------------------------------------------------ rutas ---

def _carpeta_salidas():
    return os.environ.get("CREATV_SALIDAS") or os.path.join(BASE_DIR, "salidas")


def _carpeta_final(cliente, final_id):
    return os.path.join(_carpeta_salidas(), cliente, "finales", final_id)


def _clon_local(cliente, cf_id, entry):
    """Ruta local del clon CRUDO (solo sonido nativo): `video_local_crudo` si
    existe; si no, descarga `video_url_crudo` una vez a
    salidas/<cliente>/finales/clones/<cf_id>_crudo.mp4; clones anteriores a la
    capa de sonido usan `video_local`/`video_url` (que en ellos es el mismo
    archivo). El clon mezclado con música NO sirve de fuente: la música se
    pondría dos veces."""
    crudo = entry.get("video_local_crudo")
    if crudo and os.path.exists(crudo):
        return crudo
    local = entry.get("video_local")
    if not entry.get("video_url_crudo") and local and os.path.exists(local):
        return local
    url = entry.get("video_url_crudo") or entry.get("video_url")
    if not url:
        raise ValueError(f"La sesión {cf_id} no tiene video listo para producir.")
    sufijo = "_crudo" if entry.get("video_url_crudo") else ""
    destino = os.path.join(_carpeta_salidas(), cliente, "finales", "clones", f"{cf_id}{sufijo}.mp4")
    if os.path.exists(destino):
        return destino
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    resp = requests.get(url, stream=True, timeout=300)
    resp.raise_for_status()
    tmp = destino + ".parcial"
    with open(tmp, "wb") as f:
        for chunk in resp.iter_content(1024 * 256):
            f.write(chunk)
    os.replace(tmp, destino)
    return destino


def _logo_local(cliente, carpeta):
    """Primer logo del proyecto (clientes/<c>/logos/, misma convención que
    `dashboard._logos` pero sin importar dashboard), copiado a la carpeta de
    trabajo. None si no hay."""
    origen = os.path.join(BASE_DIR, "clientes", cliente, "logos")
    if not os.path.isdir(origen):
        return None
    for nombre in sorted(os.listdir(origen)):
        low = nombre.lower()
        if low.endswith(".frame.jpg") or not low.endswith(IMAGE_EXTS):
            continue
        os.makedirs(carpeta, exist_ok=True)
        destino = os.path.join(carpeta, "logo" + os.path.splitext(nombre)[1].lower())
        shutil.copy(os.path.join(origen, nombre), destino)
        return destino
    return None


def _color_acento(cliente):
    try:
        datos = proyectos.cargar(cliente)
    except Exception:
        return COLOR_ACENTO_DEFECTO
    return datos.get("color_acento") or COLOR_ACENTO_DEFECTO


def _guia_marca(cliente):
    """Guía de estilo efectiva del cliente para inyectar en el prompt del
    guion. Un `root.json` de marca corrupto es un extra, no algo que deba
    tumbar la escritura del guion: se degrada a "" (M6)."""
    try:
        return marca.guia_efectiva(cliente) or ""
    except (OSError, ValueError):
        return ""


# ---------------------------------------------------------------- sesión ---

def _sesion(cliente, cf_id):
    entry = creative_flow.cargar(cliente).get(cf_id)
    if not entry:
        raise ValueError(f"No existe la sesión {cf_id} de {cliente}.")
    return entry


def _fila_producto(cliente, activo_id):
    """Fila `producto` del activo (precio, moneda, url_compra); {} si no hay."""
    try:
        return tiendas.por_activo(cliente).get(activo_id) or {}
    except Exception:  # noqa: BLE001 — precio y URL son un extra del guion, nunca lo tumban
        return {}


def _precio_entero(precio):
    """89900.0 → 89900: el precio escrito (`_precio_form`) y el de la tienda
    (columna Float) llegan como float, y Claude no debe ver «89900.0» — el
    verificador de cifras lo leería como 899000 y el precio real saldría
    «inventado». Un precio con decimales (89.9) queda igual."""
    if isinstance(precio, float) and precio.is_integer():
        return int(precio)
    return precio


def _producto(cliente, entry, precio):
    """{"nombre","descripcion","regla","precio","moneda","url_compra","tipo"}
    desde el catálogo (y su fila de tienda) o desde la acción central.

    `productos_ids` guarda NOMBRES visibles (no ids): se busca cada uno por id
    y luego por nombre (`catalogo_productos.encontrar_por_id_o_nombre`). Si
    nada resuelve, se cae a la primera referencia con categoria=="producto" y
    luego a la acción central. El precio escrito por la persona manda; si no
    hay, el de la tienda con SU moneda (nunca una moneda para un precio escrito).
    Un precio entero va como int (`_precio_entero`), nunca «89900.0»."""
    precio = _precio_entero(precio)
    p, visto = None, None
    for x in entry.get("productos_ids") or []:
        p = catalogo_productos.encontrar_por_id_o_nombre(cliente, x, "producto")
        if p:
            visto = x
            break
    if p:
        fila = _fila_producto(cliente, p.get("id"))
        usa_tienda = precio is None and fila.get("precio") is not None
        return {"nombre": p.get("nombre") or visto, "descripcion": p.get("descripcion") or "",
                "regla": p.get("regla") or "", "precio": _precio_entero(fila.get("precio")) if usa_tienda else precio,
                "moneda": fila.get("moneda") if usa_tienda else None, "url_compra": fila.get("url_compra"),
                "tipo": p.get("tipo")}
    for r in entry.get("referencias") or []:
        if r.get("categoria") == "producto" and r.get("activo"):
            return {"nombre": r["activo"], "descripcion": "", "regla": r.get("regla") or "", "precio": precio,
                    "moneda": None, "url_compra": None, "tipo": None}
    accion = entry.get("accion_central") or ""
    return {"nombre": accion[:60], "descripcion": accion, "regla": "", "precio": precio, "moneda": None,
            "url_compra": None, "tipo": None}


def _referencia(entry, idioma_base):
    referencias = [r for r in (entry.get("referencias") or [])
                   if not r.get("logo") and r.get("tipo") != "logo"]
    frames = [r["frame_url"] for r in referencias if r.get("frame_url")]
    transcripcion, costo = None, 0.0
    for r in referencias:
        if r.get("tipo") == "video" and r.get("url"):
            try:
                t = fal_audio.transcribir_palabras(r["url"], idioma_base) or {}
                transcripcion = t.get("texto") or None
                costo = float(t.get("costo_usd") or 0.0)
            except Exception:
                transcripcion = None  # la transcripción es un extra: sin ella el guion sale igual
            break
    if not frames and not transcripcion:
        return None, costo
    return {"frames": frames, "transcripcion": transcripcion}, costo


def _opciones(opciones):
    o = dict(_OPCIONES_DEFECTO)
    o.update(opciones or {})
    return o


# ---------------------------------------------------------------- Triple Whale ---

def _canal_optimo_triple_whale(cliente, cf_id):
    """Detecta si el concepto está en un experimento con atribución triple_whale
    y retorna el canal óptimo (mayor ROAS) con su rendimiento.

    Retorna: {"canal": "google_ads|tiktok|...", "roas": 3.5, "duracion_sugerida_s": 6, "razon": "..."}
    o None si no hay triple_whale o no hay métricas."""
    import sqlalchemy as sa

    try:
        # Buscar el concepto por cliente y legado_id (cf_id)
        with db.conectar() as con:
            concepto = con.execute(
                sa.select(db.concepto.c.id).where(
                    db.concepto.c.cliente == cliente,
                    db.concepto.c.legado_id == cf_id
                )
            ).first()

            if not concepto:
                return None

            concepto_id = concepto[0]

            # Buscar experimentos que incluyan piezas de este concepto
            # Subquery: piezas del concepto
            piezas_query = sa.select(db.pieza.c.id).where(db.pieza.c.concepto_id == concepto_id)

            # Buscar experimento_pieza que referencie estas piezas
            ep_query = sa.select(db.experimento_pieza.c.experimento_id).where(
                db.experimento_pieza.c.pieza_id.in_(piezas_query)
            ).distinct()

            # Buscar experimentos con atribución triple_whale
            exp_ids = con.execute(ep_query).fetchall()
            if not exp_ids:
                return None

            exp_query = sa.select(db.experimento.c.id, db.experimento.c.atribucion).where(
                db.experimento.c.id.in_([r[0] for r in exp_ids]),
                db.experimento.c.cliente == cliente,
                db.experimento.c.atribucion == "triple_whale"
            )

            exp_rows = con.execute(exp_query).fetchall()
            if not exp_rows:
                return None

            # Tomar el primer experimento con triple_whale
            exp_id = exp_rows[0][0]

            # Buscar experimento_pieza de este experimento para obtener piezas
            ep_rows = con.execute(
                sa.select(db.experimento_pieza.c.id).where(
                    db.experimento_pieza.c.experimento_id == exp_id,
                    db.experimento_pieza.c.pieza_id.in_(piezas_query)
                )
            ).fetchall()

            if not ep_rows:
                return None

            # Buscar la métrica más reciente por canal
            canales_metrics = {}
            for ep_id_row in ep_rows:
                ep_id = ep_id_row[0]
                snap = con.execute(
                    sa.select(db.metrica_snapshot).where(
                        db.metrica_snapshot.c.experimento_pieza_id == ep_id
                    ).order_by(db.metrica_snapshot.c.id.desc()).limit(1)
                ).first()

                if snap:
                    roas = snap[db.metrica_snapshot.c.roas] or 0
                    extra = snap[db.metrica_snapshot.c.extra] or {}
                    canal = extra.get("channel", "desconocido")

                    if canal not in canales_metrics or canales_metrics[canal]["roas"] < roas:
                        canales_metrics[canal] = {
                            "roas": roas,
                            "gasto": snap[db.metrica_snapshot.c.gasto] or 0,
                            "compras": snap[db.metrica_snapshot.c.compras] or 0
                        }
    except Exception as e:
        # No bloquea si hay error en triple_whale: devuelve None
        import sys
        print(f"Advertencia en _canal_optimo_triple_whale: {e}", file=sys.stderr)
        return None

    # Encontrar el canal con mayor ROAS > 1.0
    mejor_canal = None
    mejor_roas = 0
    for canal, metricas in canales_metrics.items():
        roas = metricas.get("roas", 0)
        if roas > mejor_roas and roas > 1.0:
            mejor_roas = roas
            mejor_canal = canal

    if not mejor_canal or mejor_roas <= 0:
        return None

    # Mapear canal a duraciones y estrategias sugeridas
    duraciones_por_canal = {
        "Google Ads": 6,
        "google_ads": 6,
        "TikTok": 9,
        "tiktok": 9,
        "Instagram": 7,
        "instagram": 7,
        "Pinterest": 8,
        "pinterest": 8,
        "Facebook": 7,
        "facebook": 7,
    }

    duracion_sugerida = duraciones_por_canal.get(mejor_canal, 8)

    return {
        "canal": mejor_canal.lower().replace(" ", "_"),
        "roas": round(mejor_roas, 2),
        "duracion_sugerida_s": duracion_sugerida,
        "razon": f"ROAS {mejor_roas:.1f}x en {mejor_canal}"
    }


# ------------------------------------------------------------------- API ---

def _angulo_con_contenido(angulo):
    """Un ángulo que vale la pena guardar: dict con promesa y gancho."""
    return (isinstance(angulo, dict) and bool(str(angulo.get("promesa") or "").strip())
            and bool(str(angulo.get("gancho") or "").strip()))


def preparar_guion(cliente, cf_id, opciones=None, ref_sufijo=""):
    """Guion base de la sesión (capa 0). Devuelve `(guion_base, costo_usd)` y
    lo deja guardado en el concepto (`creative_flow.guardar_guion_base`).

    `ref_sufijo` (p. ej. `:t123`, el id de la tarea que paga) va al final de
    la referencia del gasto para que cada llamada real (una tarea nueva por
    clic) deje su propia fila — sin él, "Volver a escribir con IA" pisaría
    el cobro de la escritura anterior. Vacío por defecto: llamadas directas
    (tests/CLI) siguen siendo idempotentes entre sí, como antes."""
    o = _opciones(opciones)
    entry = _sesion(cliente, cf_id)
    idioma_base = o.get("idioma_base") or "es"
    producto = _producto(cliente, entry, o.get("precio"))
    # Precio base del guion (D, regla de CLAUDE.md): el escrito por la persona
    # manda tal cual. Sin uno escrito, el de la tienda solo cuenta como precio
    # base si su moneda es la del país base — si no, ninguna final lo llevaría
    # en esa moneda y Claude no debe voz-earlo: se le quita al producto.
    precio_base = o.get("precio")
    if precio_base is None and producto.get("precio") is not None:
        moneda_pais_base = tipos.PAISES[guion_mod._pais_por_idioma(idioma_base)]["moneda"]
        if producto.get("moneda") == moneda_pais_base:
            precio_base = producto["precio"]
        else:
            producto = dict(producto, precio=None, moneda=None)
    referencia, costo = _referencia(entry, idioma_base)
    duracion_s = o.get("duracion_s") or cortes.duracion(_clon_local(cliente, cf_id, entry))
    enfoque = entry.get("enfoque") or "producto"

    costo_whisper = costo
    # Detectar canal óptimo de Triple Whale si existe
    canal_optimo = _canal_optimo_triple_whale(cliente, cf_id)
    angulo_sesion = entry.get("angulo")
    guion_base, costo_guion = guion_mod.generar_guion_base(
        producto, referencia, enfoque, float(duracion_s), idioma_base,
        _guia_marca(cliente), entry.get("tono") or "", canal_optimo=canal_optimo, angulo=angulo_sesion)
    costo += float(costo_guion or 0.0)
    # Sin ángulo en la sesión, Claude ya lo decidió, corrigió y limpió junto
    # con el guion (B: `guion_mod.generar_guion_base` reusa su propia vuelta
    # de corrección); acá solo se separa y se guarda. Uno que ya existía (de
    # la idea del sprint o de «Recrear») nunca se pisa.
    nuevo = guion_base.pop("angulo", None)
    # El precio escrito al preparar viaja con el guion base para prellenar el
    # destino del país base al producir (los demás países piden el suyo).
    guion_base["precio_base"] = precio_base
    # Guardar contexto de canal óptimo si lo hay
    if canal_optimo:
        guion_base["canal_optimo"] = canal_optimo
    creative_flow.guardar_guion_base(cliente, cf_id, guion_base)
    # Cobro real del guion base (Claude + whisper de la referencia si la hubo).
    # Referencia por sesión + tarea (`ref_sufijo`): dos escrituras de la MISMA
    # tarea (retries) actualizan la misma fila; una tarea nueva (otro clic en
    # "Volver a escribir con IA") deja la suya, sin pisar la anterior.
    gastos.registrar_seguro(
        cliente, "guion", round(costo, 4), f"guion:{cf_id}{ref_sufijo}", proveedor="anthropic",
        detalle=f"guion base {idioma_base}" + (" + transcripción de la referencia" if costo_whisper else ""),
        extra={"usd_guion": round(float(costo_guion or 0.0), 4), "usd_whisper": round(costo_whisper, 4)})
    # F: el ángulo se guarda AL FINAL — si esto falla, el guion (ya pagado) y
    # su gasto ya quedaron a salvo; una tarea nueva no vuelve a pagar por él.
    # Solo uno con promesa y gancho: si Claude lo omitió en las dos vueltas,
    # llega un cascarón de «error: campo_faltante:…» y guardarlo haría que
    # todo guion, variante y caption posterior «escriba desde» la nada.
    if not angulo_sesion and _angulo_con_contenido(nuevo):
        creative_flow.actualizar(cliente, cf_id, angulo=nuevo)
    return guion_base, round(costo, 4)


def _siguiente(lista, actual):
    """El elemento que sigue a `actual` en `lista` (cíclico); el primero si
    `actual` no está. Para elegir "otra" voz / "otro" estilo de música."""
    lista = list(lista)
    if not lista:
        return actual
    try:
        return lista[(lista.index(actual) + 1) % len(lista)]
    except ValueError:
        return lista[0]


def _parametro_capa_original(cliente, cf_id, idioma, pais, capa, clave):
    """Valor usado por la final original (sin variante) del mismo destino en
    `capas[capa]["parametros"][clave]`, o None si no existe."""
    original = creative_flow.final_por_legado(cliente, f"{cf_id}__{idioma}_{pais}")
    if not original:
        return None
    return (((original.get("capas") or {}).get(capa) or {}).get("parametros") or {}).get(clave)


def producir(cliente, cf_id, idioma, pais, opciones=None, on_etapa=None, ref_sufijo=""):
    """Produce la pieza final `idioma`/`pais` de la sesión. Devuelve
    `(final_id, resumen)`; `resumen` es el dict de `creative_flow.finales`.
    `on_etapa(nombre)` se llama antes de cada etapa de `ETAPAS_FINAL`.
    `ref_sufijo` (id de la tarea que paga) va en la referencia del gasto.

    Desde la capa 2 del editor la producción va por `produccion.producir`
    (guion → borrador como edición → traducción del destino → versión →
    render del motor): mismo contrato, mismas capas, mismo gasto.
    `FINAL_EDITION_LEGADO=1` (seguro de despliegue) vuelve al pipeline de
    siempre, `producir_legado`."""
    if os.environ.get("FINAL_EDITION_LEGADO") == "1":
        return producir_legado(cliente, cf_id, idioma, pais, opciones, on_etapa, ref_sufijo)
    from final_edition import produccion   # import perezoso: produccion importa este paquete
    return produccion.producir(cliente, cf_id, idioma, pais, opciones, on_etapa, ref_sufijo)


def producir_legado(cliente, cf_id, idioma, pais, opciones=None, on_etapa=None, ref_sufijo=""):
    """Pipeline anterior al editor (render.py/texto.py); se retira al final de
    la spec §5. Hoy solo corre con FINAL_EDITION_LEGADO=1. Devuelve
    `(final_id, resumen)`; `resumen` es el dict de `creative_flow.finales`.
    `on_etapa(nombre)` se llama antes de cada etapa de `ETAPAS_FINAL`.

    `ref_sufijo` (el id de la tarea que paga, p. ej. `:t123`) se agrega a la
    referencia del gasto (`final:<final_id><ref_sufijo>`) y se pasa también
    al `preparar_guion` que corre adentro si el guion base todavía no
    existía: cada producción real (una tarea nueva) deja su propia fila en
    vez de pisar la de un intento anterior del mismo destino.

    Variantes: si `opciones` trae `variante` (int >= 1) y `variante_tipo`
    ("hook" | "estructura"), la pieza sale como `<cf_id>__<idioma>_<pais>__v<n>`
    con un guion variado a partir del guion base (`guion.variar_guion`) — el
    guion base del concepto NO se toca. Si no se fija `voz`/`estilo_musica`,
    `hook` cambia la voz respecto a la final original del destino y
    `estructura` cambia el estilo de música."""
    o = _opciones(opciones)
    entry = _sesion(cliente, cf_id)
    avisar = on_etapa or (lambda nombre: None)
    variante_tipo = o.get("variante_tipo")
    # `variante` y `variante_tipo` van juntos: sin el número la variante pisaría
    # la final original; sin el tipo se gastaría voz/música en una copia igual.
    if bool(variante_tipo) != (o.get("variante") is not None):
        raise ValueError("Para producir una variante hay que indicar `variante` (número) y "
                         "`variante_tipo` (hook | estructura) a la vez.")
    if variante_tipo and variante_tipo not in guion_mod.VARIANTES_GUION:
        raise ValueError(
            f"Tipo de variante no soportado: {variante_tipo}. Opciones: {sorted(guion_mod.VARIANTES_GUION)}")
    # Capa sonido (S2): se valida ANTES de crear la fila final para que un
    # preset o modo desconocido no deje una pieza a medias en la base.
    if o.get("sonido") not in SONIDOS_VALIDOS:
        raise ValueError(f"Capa de sonido no soportada: {o.get('sonido')}. Opciones: {SONIDOS_VALIDOS}")
    volumenes = mezcla.volumenes_para(o.get("mezcla"), o.get("volumenes"))   # ValueError si el preset no existe
    pedir_sonido = bool(o.get("con_sonido", True)) and o.get("sonido") == "nativo"

    final_id = creative_flow.crear_final(cliente, cf_id, idioma, pais, variante=o.get("variante"))
    costo = 0.0
    # Lo que preparar_guion cobró acá adentro ya quedó como `guion:<cf_id>`;
    # se descuenta del gasto de la final para no contarlo dos veces.
    costo_base = 0.0
    guion_base = None
    guion = None
    capas = {}
    degradada = False

    avisar(ETAPAS_FINAL[0][0])
    try:
        # Guion base (una vez por sesión) — si aún no existe se escribe aquí.
        guion_base = creative_flow.guion_base(cliente, cf_id)
        if not guion_base:
            guion_base, costo_base = preparar_guion(cliente, cf_id, o, ref_sufijo=ref_sufijo)
            costo += costo_base
            # F.1: si la sesión no tenía ángulo, preparar_guion pudo guardar
            # uno nuevo — recargar para que la variante y la localización de
            # ABAJO (en esta misma llamada) ya lo reciban, en vez de None.
            entry = _sesion(cliente, cf_id)
        # Variante: el guion variado reemplaza al base SOLO para esta pieza;
        # `concepto.guion_base` sigue intacto para las demás finales.
        costo_variante = 0.0
        angulo_variante = None
        if variante_tipo:
            guion_base, costo_variante = guion_mod.variar_guion(guion_base, variante_tipo, _guia_marca(cliente),
                                                                angulo=entry.get("angulo"))
            costo += float(costo_variante or 0.0)
            angulo_variante = guion_base.pop("angulo_variante", None)
    except Exception as e:
        capas["guion"] = {"proveedor": "anthropic", "parametros": {"variante_tipo": variante_tipo} if variante_tipo else {},
                          "costo_usd": 0.0, "estado": "error", "error": str(e)}
        creative_flow.actualizar_final(cliente, final_id, estado="error", error=str(e), capas=capas)
        raise
    carpeta = _carpeta_final(cliente, final_id)
    shutil.rmtree(carpeta, ignore_errors=True)
    os.makedirs(carpeta, exist_ok=True)

    def capa(nombre, proveedor, parametros, costo_capa=0.0, estado="ok", error=None):
        capas[nombre] = {"proveedor": proveedor, "parametros": parametros,
                         "costo_usd": round(float(costo_capa or 0.0), 4), "estado": estado, "error": error}

    try:
        # 0. Guion localizado — precio por destino (I1): la moneda del país
        # base y la del destino casi nunca coinciden, así que un solo precio
        # no se convierte de una a otra. `opciones["precios"]` trae un valor
        # por destino (clave "<idioma>_<pais>"); `opciones["precio"]` es un
        # atajo que solo aplica al país base del guion (misma moneda), nunca
        # a los demás destinos.
        precios_por_destino = o.get("precios") or {}
        clave_destino = f"{idioma}_{pais}"
        if clave_destino in precios_por_destino:
            precio = precios_por_destino.get(clave_destino)
        elif pais == (guion_base or {}).get("pais"):
            precio = o.get("precio")
            if precio is None:
                precio = (guion_base or {}).get("precio_base")
        else:
            precio = None
        params_guion = {"idioma": idioma, "pais": pais, "precio": precio}
        if variante_tipo:
            params_guion["variante_tipo"] = variante_tipo
        if angulo_variante and (angulo_variante.get("lead") or angulo_variante.get("gancho")):
            params_guion["angulo"] = angulo_variante
        try:
            guion, c = guion_mod.localizar_guion(guion_base, idioma, pais, precio, angulo=entry.get("angulo"))
        except Exception as e:
            capa("guion", "anthropic", params_guion, costo_variante, estado="error", error=str(e))
            raise
        costo += float(c or 0.0)
        capa("guion", "anthropic", params_guion, float(c or 0.0) + costo_variante)

        # 1. Cortes y plan de segmentos
        avisar(ETAPAS_FINAL[1][0])
        try:
            clon = _clon_local(cliente, cf_id, entry)
            duracion_clon = cortes.duracion(clon)
            fin_guion = (guion.get("bloques") or [{}])[-1].get("fin_s") or duracion_clon
            cortes_t = cortes.detectar_cortes(clon)
            segmentos = cortes.planificar_segmentos(duracion_clon, cortes_t, float(fin_guion))
            if not segmentos:
                raise RuntimeError("El clon no da para ningún segmento.")
            duracion_final = float(segmentos[-1]["fin"])
        except Exception as e:
            capa("cortes", "ffmpeg", {}, estado="error", error=str(e))
            raise
        capa("cortes", "ffmpeg", {"cortes": cortes_t, "segmentos": len(segmentos)})

        # 1b. Sonido de la escena (S2): capa gratis; el clon mudo no degrada la pieza.
        params_sonido = {"sonido": o.get("sonido"), "mezcla": o.get("mezcla") or mezcla.PRESET_DEFECTO,
                         "volumenes": volumenes}
        if not pedir_sonido:
            capa("sonido", "nativo", params_sonido, estado="omitida")
            con_sonido_render = False
        elif mezcla.tiene_audio(clon) is True:
            capa("sonido", "nativo", params_sonido, estado="ok")
            con_sonido_render = True
        else:
            capa("sonido", "nativo", params_sonido, estado="ausente")
            con_sonido_render = False

        # 2. Voz (degradable)
        avisar(ETAPAS_FINAL[2][0])
        archivo_voz, palabras = None, []
        voces = fal_audio.VOCES.get(idioma) or fal_audio.VOCES["es"]
        nombre_voz = o.get("voz")
        if not nombre_voz and variante_tipo == "hook":
            # Otra voz que la de la final original del destino (o la siguiente
            # a la de defecto si no hay original).
            nombre_voz = _siguiente(voces, _parametro_capa_original(cliente, cf_id, idioma, pais, "voz", "voz") or voces[0])
        nombre_voz = nombre_voz or voces[0]
        if not o.get("con_voz", True):
            capa("voz", "fal/elevenlabs", {"voz": nombre_voz}, estado="omitida")
        else:
            try:
                salida_voz, c = voz.sintetizar(guion, nombre_voz, os.path.join(carpeta, "voz"), cliente=cliente)
                archivo_voz = salida_voz.get("archivo_voz")
                palabras = salida_voz.get("palabras") or []
                costo += float(c or 0.0)
                capa("voz", "fal/elevenlabs", {"voz": nombre_voz}, c)
            except voz.ErrorPrimerBloque as e:
                # El primer bloque (hook) falló: casi siempre algo
                # determinístico (voz inválida para fal/ElevenLabs, texto
                # vacío) que fallaría igual en cualquier otro bloque —
                # degradar aquí solo pagaría música por una pieza que de
                # todos modos sale sin voz. Es fatal: no se genera música.
                capa("voz", "fal/elevenlabs", {"voz": nombre_voz}, estado="error", error=str(e))
                raise ValueError(
                    f"No se pudo generar la voz (revisa la voz elegida, '{nombre_voz}'): {e}"
                ) from e
            except Exception as e:
                degradada = True
                archivo_voz, palabras = None, []
                capa("voz", "fal/elevenlabs", {"voz": nombre_voz}, estado="error", error=str(e))

        # 3. Música (degradable)
        avisar(ETAPAS_FINAL[3][0])
        pista_musica = None
        estilo = o.get("estilo_musica")
        if not estilo:
            producto = _producto(cliente, entry, precio)
            estilo = musica.elegir_estilo(producto.get("tipo"), entry.get("enfoque"))
            if variante_tipo == "estructura":
                # Otro estilo que el de la final original del destino.
                estilo = _siguiente(tipos.ESTILOS_MUSICA,
                                    _parametro_capa_original(cliente, cf_id, idioma, pais, "musica", "estilo") or estilo)
        propia = musica.es_propia(estilo)
        if not o.get("con_musica", True):
            capa("musica", "propia" if propia else "fal/stable-audio", {"estilo": estilo}, estado="omitida")
        else:
            try:
                if propia:
                    # Mi música: la canción del cliente desde su segundo de inicio (costo 0).
                    pista, c = musica.pista_propia(cliente, estilo, o.get("musica_inicio_s") or 0)
                    proveedor = "elevenlabs" if pista["fuente"] == "elevenlabs" else "propia"
                    parametros = {"estilo": pista["estilo"], "url": pista.get("url"),
                                  "material_id": pista["material_id"], "inicio_s": pista["inicio_s"]}
                else:
                    pista, c = musica.obtener_pista(estilo, duracion_final)
                    proveedor, parametros = "fal/stable-audio", {"estilo": estilo, "url": pista.get("url")}
                pista_musica = pista.get("archivo")
                costo += float(c or 0.0)
                capa("musica", proveedor, parametros, c)
            except Exception as e:
                degradada = True
                pista_musica = None
                capa("musica", "propia" if propia else "fal/stable-audio", {"estilo": estilo}, estado="error", error=str(e))

        # 4. Texto en pantalla + 5. Render
        avisar(ETAPAS_FINAL[4][0])
        ancho, alto = _TAMANOS.get(entry.get("aspect_ratio") or "9:16", _TAMANOS["9:16"])
        try:
            marca_textos = {"color_acento": _color_acento(cliente), "logo_path": _logo_local(cliente, carpeta)}
            overlays = texto.generar_overlays(guion, palabras, marca_textos, os.path.join(carpeta, "overlays"), ancho, alto)
        except Exception as e:
            capa("texto", "pillow", {"ancho": ancho, "alto": alto}, estado="error", error=str(e))
            raise
        capa("texto", "pillow", {"ancho": ancho, "alto": alto, "logo": bool(marca_textos["logo_path"])})

        salida_mp4 = os.path.join(carpeta, f"{final_id}.mp4")
        try:
            resultado = render.componer(clon, segmentos, overlays, archivo_voz, pista_musica, salida_mp4,
                                        duracion_final, ancho, alto, con_sonido=con_sonido_render, volumenes=volumenes)
            key = f"clientes/{cliente}/finales/{final_id}"
            url_video = r2_uploader.upload_video(resultado["archivo"], key + ".mp4")
            url_miniatura = r2_uploader.upload_image(resultado["miniatura"], key + ".png")
        except Exception as e:
            capa("render", "ffmpeg", {"ancho": ancho, "alto": alto}, estado="error", error=str(e))
            raise
        capa("render", "ffmpeg", {"ancho": ancho, "alto": alto, "con_voz": bool(archivo_voz),
                                  "con_musica": bool(pista_musica), "con_sonido": bool(resultado.get("con_sonido")),
                                  "mezcla": o.get("mezcla") or mezcla.PRESET_DEFECTO})
    except Exception as e:
        creative_flow.actualizar_final(cliente, final_id, estado="error", error=str(e), capas=capas,
                                       costo_usd=round(costo, 4), guion=guion)
        _registrar_gasto_final(cliente, final_id, idioma, pais, costo - costo_base, capas, fallo=True,
                               ref_sufijo=ref_sufijo)
        raise

    creative_flow.actualizar_final(
        cliente, final_id, estado="degradada" if degradada else "listo", url_video=url_video,
        url_miniatura=url_miniatura, url_local=resultado["archivo"],
        duracion_s=float(resultado.get("duracion_s") or duracion_final), capas=capas,
        costo_usd=round(costo, 4), guion=guion, error=None)
    _registrar_gasto_final(cliente, final_id, idioma, pais, costo - costo_base, capas, ref_sufijo=ref_sufijo)
    return final_id, creative_flow.final_por_legado(cliente, final_id)


def _registrar_gasto_final(cliente, final_id, idioma, pais, usd, capas, fallo=False, ref_sufijo=""):
    """`final:<final_id><ref_sufijo>`: el total que cobraron las capas (por
    capa en `extra`). Si la pieza falló solo se registra cuando algo se
    cobró — con el detalle de qué capa falló y cuáles ya estaban pagadas
    (p. ej. "falló en render; voz y música cobradas"). `ref_sufijo` es el id
    de la tarea que pagó: sin él, reproducir el mismo destino (un cobro real
    nuevo, tarea nueva) pisaría el gasto del intento anterior."""
    por_capa = {n: round(float(c.get("costo_usd") or 0.0), 4) for n, c in (capas or {}).items()}
    cobradas = [n for n, v in por_capa.items() if v > 0]
    usd = round(max(0.0, float(usd or 0.0)), 4)
    if fallo:
        if usd <= 0:
            return
        fallida = next((n for n in reversed(list(capas or {})) if (capas[n] or {}).get("estado") == "error"), None)
        detalle = f"{idioma}_{pais} · falló en {fallida or 'la producción'}; " + (
            " y ".join(cobradas) + (" cobradas" if len(cobradas) > 1 else " cobrada") if cobradas else "nada cobrado")
    else:
        detalle = f"{idioma}_{pais} · " + (", ".join(cobradas) if cobradas else "sin cobros (todo cacheado u omitido)")
    gastos.registrar_seguro(cliente, "final", usd, f"final:{final_id}{ref_sufijo}", detalle=detalle,
                            proveedor="fal/anthropic", extra={"capas": por_capa, "fallo": bool(fallo)})


registrar_gasto_final = _registrar_gasto_final   # lo usa final_edition.produccion (vía del editor)
