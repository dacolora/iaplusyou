"""Avisos por correo después de cada copia de Triple Whale (spec 2026-09-28
§12): la persona se entera de lo que cambió sin abrir la pestaña.

Tras cada `sync.sincronizar` el worker evalúa los últimos 30 días
(`panel.evaluar_periodo`, gratis) y compara con lo que se avisó la vez
anterior (`triple_whale.extra.avisados`: {ad_id: {veredicto, fatiga}}):

- anuncios que pasaron a `ganador` → «Nuevos ganadores»;
- ganadores/prometedores que ahora se están cansando → «Se están cansando»;
- anuncios que pasaron a `perdedor` → «Nuevos perdedores» (para pausarlos);
- gasto sin ninguna venta atribuida en 30 días → un aviso, una sola vez
  (`extra.aviso_sin_ventas`), hasta que vuelva a haber ventas.

La primera copia (sin `avisados`) solo guarda la base: nada de mandar 90
días de historia como si fuera noticia. Un solo correo por copia, tipo
`tw_evaluacion` (`notificaciones.avisar`: sin SMTP o sin correo del
proyecto queda en la bitácora). `cambios` es pura.
"""
from flask_babel import gettext

import notificaciones
import triple_whale_tiendas

DIAS = 30
MAX_POR_LISTA = 8


def _estado(ev):
    return {a["ad_id"]: {"veredicto": a["veredicto"], "fatiga": bool(a.get("fatiga")), "nombre": a["nombre"]}
            for a in ev["anuncios"]}


def cambios(previo, ev):
    """{"ganadores": [...], "cansados": [...], "perdedores": [...], "estado": {...}}
    comparando el estado guardado con la evaluación actual. Cada lista trae
    {"ad_id", "nombre", "roas", "pedidos", "gasto"}."""
    actual = _estado(ev)
    previo = previo or {}
    ganadores, cansados, perdedores = [], [], []
    for a in ev["anuncios"]:
        antes = previo.get(a["ad_id"]) or {}
        resumen = {"ad_id": a["ad_id"], "nombre": a["nombre"], "roas": a["m"].get("roas"),
                   "pedidos": a["m"].get("pedidos"), "gasto": a["m"].get("gasto")}
        if a["veredicto"] == "ganador" and antes.get("veredicto") != "ganador":
            ganadores.append(resumen)
        if a.get("fatiga") and a["veredicto"] in ("ganador", "prometedor") and not antes.get("fatiga"):
            cansados.append(resumen)
        if a["veredicto"] == "perdedor" and antes.get("veredicto") != "perdedor":
            perdedores.append(resumen)
    return {"ganadores": ganadores, "cansados": cansados, "perdedores": perdedores, "estado": actual}


def _linea(a, moneda):
    from idiomas import numero
    partes = []
    if a.get("roas"):
        partes.append(gettext("ROAS %(roas)s×", roas=numero(a["roas"], 1)))
    if a.get("pedidos"):
        partes.append(gettext("%(n)s pedidos", n=numero(a["pedidos"], 0)))
    if a.get("gasto"):
        partes.append(gettext("gasto %(gasto)s %(moneda)s", gasto=numero(a["gasto"], 0), moneda=moneda))
    return f"- {a['nombre']}" + (f" ({', '.join(partes)})" if partes else "")


def cuerpo(cliente, c, moneda, sin_ventas=False):
    """El correo, o "" si no hay nada que contar."""
    bloques = []
    for clave, titulo in (("ganadores", gettext("Nuevos ganadores")),
                          ("cansados", gettext("Ganadores que se están cansando (toca hacer variantes)")),
                          ("perdedores", gettext("Nuevos perdedores (pausarlos libera presupuesto)"))):
        lista = c.get(clave) or []
        if not lista:
            continue
        lineas = [_linea(a, moneda) for a in lista[:MAX_POR_LISTA]]
        if len(lista) > MAX_POR_LISTA:
            lineas.append(gettext("… y %(n)s más", n=len(lista) - MAX_POR_LISTA))
        bloques.append(titulo + ":\n" + "\n".join(lineas))
    if sin_ventas:
        bloques.append(gettext("Triple Whale no atribuye ninguna venta a tus anuncios en los últimos %(dias)s días "
                               "aunque hay gasto. Revisa los parámetros de rastreo (tw_source y tw_adid) o la "
                               "ventana de atribución.", dias=DIAS))
    if not bloques:
        return ""
    return "\n\n".join(bloques) + "\n\n" + gettext(
        "Mira el detalle en la pestaña Triple Whale del proyecto %(cliente)s.", cliente=cliente)


def revisar_y_avisar(cliente, ev=None, config=None, dias=DIAS):
    """Evalúa (o usa `ev`), manda el correo si algo cambió y guarda la base.
    Devuelve los cambios, o None en la primera copia. Nunca lanza."""
    from triple_whale import panel
    config = config or triple_whale_tiendas.obtener(cliente)
    if not config:
        return None
    if ev is None:
        ev, _, _ = panel.evaluar_periodo(cliente, dias)
    extra = config.get("extra") or {}
    if "avisados" not in extra:
        triple_whale_tiendas.actualizar_extra(cliente, {"avisados": _estado(ev)})
        return None
    c = cambios(extra.get("avisados"), ev)
    gasto = float((ev.get("cuenta") or {}).get("m", {}).get("gasto") or 0)
    sin_ventas = gasto > 0 and not ev.get("hay_ventas")
    avisar_sin_ventas = sin_ventas and not extra.get("aviso_sin_ventas")
    texto = cuerpo(cliente, c, config.get("moneda") or "", sin_ventas=avisar_sin_ventas)
    if texto:
        n = len(c["ganadores"]) + len(c["cansados"]) + len(c["perdedores"])
        asunto = (gettext("Triple Whale: %(n)s cambio(s) en tus anuncios", n=n) if n
                  else gettext("Triple Whale: anuncios sin ventas atribuidas"))
        notificaciones.avisar(cliente, "tw_evaluacion", asunto, texto)
    cambios_extra = {"avisados": c["estado"]}
    if avisar_sin_ventas:
        cambios_extra["aviso_sin_ventas"] = ev.get("hasta") or True
    elif not sin_ventas and extra.get("aviso_sin_ventas"):
        cambios_extra["aviso_sin_ventas"] = None
    triple_whale_tiendas.actualizar_extra(cliente, cambios_extra)
    c["avisado"] = bool(texto)
    return c
