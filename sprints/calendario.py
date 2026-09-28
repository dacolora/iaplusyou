"""
Calendario comercial por país: fechas de temporadas que un proyecto adopta con
un clic como `temporada` propia (spec §1.1, §1.6). Las fechas son del año
pedido; las que dependen de un domingo (Día de la madre, del padre) se
aproximan a una ventana fija de venta. Sin calendario para un país, se usa el
de Colombia.
"""
from datetime import date

from flask_babel import gettext

import idiomas
from idiomas import N_
from sprints import datos

_MADRE = {"clave": "dia_de_la_madre", "nombre": N_("Día de la madre"), "tipo": "comercial",
          "contexto": N_("Regalos para mamá: detalle, cuidado y hogar. Compra emocional y de última hora."),
          "mood_visual": {"paleta": ["#F4A7B9", "#FFFFFF", "#C9A227"], "luz": N_("suave y cálida"),
                          "elementos": [N_("flores"), N_("desayuno"), N_("abrazo")]}}
_PADRE = {"clave": "dia_del_padre", "nombre": N_("Día del padre"), "tipo": "comercial",
          "contexto": N_("Regalos útiles y con carácter para papá; tono cercano, algo de humor."),
          "mood_visual": {"paleta": ["#1B2A41", "#8C6D46", "#E8E4DC"], "luz": N_("natural, de tarde"),
                          "elementos": [N_("taller"), N_("asado"), N_("reloj")]}}
_NAVIDAD = {"clave": "navidad", "nombre": N_("Navidad"), "tipo": "comercial", "mm_dd": ("11-15", "12-31"),
            "contexto": N_("Regalos, reuniones familiares y decoración; mucha demanda, envíos con plazo."),
            "mood_visual": {"paleta": ["#B3001B", "#0B6E4F", "#F2C14E"], "luz": N_("cálida, nocturna, luces"),
                            "elementos": [N_("regalos"), N_("luces"), N_("mesa familiar")]}}
_BLACK = {"clave": "black_friday", "nombre": N_("Black Friday"), "tipo": "comercial", "mm_dd": ("11-20", "11-30"),
          "contexto": N_("Descuentos y urgencia: precios tachados, cupos, cuenta regresiva."),
          "mood_visual": {"paleta": ["#000000", "#FFD400", "#FFFFFF"], "luz": N_("contrastada, de estudio"),
                          "elementos": [N_("etiquetas de precio"), N_("carrito"), N_("reloj")]}}
_HALLOWEEN = {"clave": "halloween", "nombre": N_("Halloween"), "tipo": "estacional", "mm_dd": ("10-15", "10-31"),
              "contexto": N_("Disfraces, fiestas y decoración; tono lúdico."),
              "mood_visual": {"paleta": ["#FF7A00", "#1A1A1A", "#7C3AED"], "luz": N_("nocturna, dramática"),
                              "elementos": [N_("calabaza"), N_("velas"), N_("disfraz")]}}

PRESETS = {
    "CO": [
        {"clave": "regreso_a_clases", "nombre": N_("Regreso a clases"), "tipo": "estacional", "mm_dd": ("01-15", "02-10"),
         "contexto": N_("Útiles, uniformes y organización del hogar para el inicio del año escolar."),
         "mood_visual": {"paleta": ["#2F80ED", "#F2C94C", "#FFFFFF"], "luz": N_("mañana, fresca"),
                         "elementos": [N_("mochila"), N_("escritorio"), N_("calendario")]}},
        dict(_MADRE, mm_dd=("05-01", "05-15")),
        dict(_PADRE, mm_dd=("06-05", "06-20")),
        {"clave": "vacaciones_mitad_de_ano", "nombre": N_("Vacaciones de mitad de año"), "tipo": "estacional",
         "mm_dd": ("06-15", "07-15"), "contexto": N_("Descanso, viajes y tiempo en casa; compras para el hogar."),
         "mood_visual": {"paleta": ["#00A6A6", "#F9F7F1", "#F4B942"], "luz": N_("sol directo, exteriores"),
                         "elementos": [N_("terraza"), N_("piscina"), N_("maleta")]}},
        {"clave": "amor_y_amistad", "nombre": N_("Amor y amistad"), "tipo": "comercial", "mm_dd": ("09-05", "09-20"),
         "contexto": N_("Regalos entre parejas y amigos, planes y detalles; tono afectivo."),
         "mood_visual": {"paleta": ["#E63946", "#FFE5EC", "#1D3557"], "luz": N_("cálida, atardecer"),
                         "elementos": [N_("regalo"), N_("cena"), N_("flores")]}},
        _HALLOWEEN, _BLACK, _NAVIDAD,
    ],
    "MX": [
        {"clave": "san_valentin", "nombre": N_("San Valentín"), "tipo": "comercial", "mm_dd": ("02-01", "02-14"),
         "contexto": N_("Regalos de pareja y amistad; detalles y experiencias."),
         "mood_visual": {"paleta": ["#E63946", "#FFE5EC", "#1D3557"], "luz": N_("cálida"),
                         "elementos": [N_("regalo"), N_("cena"), N_("flores")]}},
        dict(_MADRE, mm_dd=("05-01", "05-10")),
        dict(_PADRE, mm_dd=("06-05", "06-20")),
        {"clave": "regreso_a_clases", "nombre": N_("Regreso a clases"), "tipo": "estacional", "mm_dd": ("08-10", "08-31"),
         "contexto": N_("Útiles, uniformes y organización del hogar para el inicio del ciclo escolar."),
         "mood_visual": {"paleta": ["#2F80ED", "#F2C94C", "#FFFFFF"], "luz": N_("mañana, fresca"),
                         "elementos": [N_("mochila"), N_("escritorio"), N_("calendario")]}},
        {"clave": "buen_fin", "nombre": N_("El Buen Fin"), "tipo": "comercial", "mm_dd": ("11-10", "11-20"),
         "contexto": N_("Descuentos y meses sin intereses; urgencia."),
         "mood_visual": {"paleta": ["#000000", "#FFD400", "#FFFFFF"], "luz": N_("contrastada"),
                         "elementos": [N_("etiquetas"), N_("carrito")]}},
        _HALLOWEEN, _BLACK, _NAVIDAD,
    ],
}


def tiene_calendario(pais):
    """False cuando `presets(pais)` va a caer al calendario de Colombia."""
    return (pais or "").upper() in PRESETS


def presets(pais, anio=None):
    anio = int(anio or date.today().year)
    lista = PRESETS.get((pais or "").upper()) or PRESETS["CO"]
    salida = []
    for p in lista:
        mi, mf = p["mm_dd"]
        salida.append({"clave": p["clave"], "nombre": p["nombre"], "tipo": p["tipo"],
                       "inicio": f"{anio}-{mi}", "fin": f"{anio}-{mf}", "contexto": p["contexto"],
                       "mood_visual": dict(p["mood_visual"])})
    return salida


def traducido(p):
    """Copia del preset con nombre, contexto, luz y elementos en el idioma
    activo (la paleta no cambia). Quien guarda la envuelve en
    `idiomas.en_idioma(idiomas.de_proyecto(cliente))` (spec §B8)."""
    mood = dict(p.get("mood_visual") or {})
    mood["luz"] = idiomas.traducir(mood.get("luz"))
    mood["elementos"] = [idiomas.traducir(e) for e in mood.get("elementos") or []]
    return dict(p, nombre=idiomas.traducir(p.get("nombre")), contexto=idiomas.traducir(p.get("contexto")),
                mood_visual=mood)


def adoptar(cliente, clave, pais=None, anio=None):
    """Crea la temporada del preset (o devuelve la existente con el mismo
    nombre e inicio, para que el clic repetido no duplique)."""
    p = next((x for x in presets(pais, anio) if x["clave"] == clave), None)
    if not p:
        raise datos.ErrorDatos(gettext("Ese preset de temporada no existe."))
    with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
        p = traducido(p)
    for t in datos.temporadas(cliente, incluir_archivadas=True):
        if t["nombre"] == p["nombre"] and t["inicio"] == p["inicio"]:
            return t["id"]
    return datos.crear_temporada(cliente, p["nombre"], p["inicio"], p["fin"], contexto=p["contexto"],
                                 mood_visual=p["mood_visual"], tipo=p["tipo"])
