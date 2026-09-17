"""
Calendario comercial por país: fechas de temporadas que un proyecto adopta con
un clic como `temporada` propia (spec §1.1, §1.6). Las fechas son del año
pedido; las que dependen de un domingo (Día de la madre, del padre) se
aproximan a una ventana fija de venta. Sin calendario para un país, se usa el
de Colombia.
"""
from datetime import date

from sprints import datos

_MADRE = {"clave": "dia_de_la_madre", "nombre": "Día de la madre", "tipo": "comercial",
          "contexto": "Regalos para mamá: detalle, cuidado y hogar. Compra emocional y de última hora.",
          "mood_visual": {"paleta": ["#F4A7B9", "#FFFFFF", "#C9A227"], "luz": "suave y cálida",
                          "elementos": ["flores", "desayuno", "abrazo"]}}
_PADRE = {"clave": "dia_del_padre", "nombre": "Día del padre", "tipo": "comercial",
          "contexto": "Regalos útiles y con carácter para papá; tono cercano, algo de humor.",
          "mood_visual": {"paleta": ["#1B2A41", "#8C6D46", "#E8E4DC"], "luz": "natural, de tarde",
                          "elementos": ["taller", "asado", "reloj"]}}
_NAVIDAD = {"clave": "navidad", "nombre": "Navidad", "tipo": "comercial", "mm_dd": ("11-15", "12-31"),
            "contexto": "Regalos, reuniones familiares y decoración; mucha demanda, envíos con plazo.",
            "mood_visual": {"paleta": ["#B3001B", "#0B6E4F", "#F2C14E"], "luz": "cálida, nocturna, luces",
                            "elementos": ["regalos", "luces", "mesa familiar"]}}
_BLACK = {"clave": "black_friday", "nombre": "Black Friday", "tipo": "comercial", "mm_dd": ("11-20", "11-30"),
          "contexto": "Descuentos y urgencia: precios tachados, cupos, cuenta regresiva.",
          "mood_visual": {"paleta": ["#000000", "#FFD400", "#FFFFFF"], "luz": "contrastada, de estudio",
                          "elementos": ["etiquetas de precio", "carrito", "reloj"]}}
_HALLOWEEN = {"clave": "halloween", "nombre": "Halloween", "tipo": "estacional", "mm_dd": ("10-15", "10-31"),
              "contexto": "Disfraces, fiestas y decoración; tono lúdico.",
              "mood_visual": {"paleta": ["#FF7A00", "#1A1A1A", "#7C3AED"], "luz": "nocturna, dramática",
                              "elementos": ["calabaza", "velas", "disfraz"]}}

PRESETS = {
    "CO": [
        {"clave": "regreso_a_clases", "nombre": "Regreso a clases", "tipo": "estacional", "mm_dd": ("01-15", "02-10"),
         "contexto": "Útiles, uniformes y organización del hogar para el inicio del año escolar.",
         "mood_visual": {"paleta": ["#2F80ED", "#F2C94C", "#FFFFFF"], "luz": "mañana, fresca",
                         "elementos": ["mochila", "escritorio", "calendario"]}},
        dict(_MADRE, mm_dd=("05-01", "05-15")),
        dict(_PADRE, mm_dd=("06-05", "06-20")),
        {"clave": "vacaciones_mitad_de_ano", "nombre": "Vacaciones de mitad de año", "tipo": "estacional",
         "mm_dd": ("06-15", "07-15"), "contexto": "Descanso, viajes y tiempo en casa; compras para el hogar.",
         "mood_visual": {"paleta": ["#00A6A6", "#F9F7F1", "#F4B942"], "luz": "sol directo, exteriores",
                         "elementos": ["terraza", "piscina", "maleta"]}},
        {"clave": "amor_y_amistad", "nombre": "Amor y amistad", "tipo": "comercial", "mm_dd": ("09-05", "09-20"),
         "contexto": "Regalos entre parejas y amigos, planes y detalles; tono afectivo.",
         "mood_visual": {"paleta": ["#E63946", "#FFE5EC", "#1D3557"], "luz": "cálida, atardecer",
                         "elementos": ["regalo", "cena", "flores"]}},
        _HALLOWEEN, _BLACK, _NAVIDAD,
    ],
    "MX": [
        {"clave": "san_valentin", "nombre": "San Valentín", "tipo": "comercial", "mm_dd": ("02-01", "02-14"),
         "contexto": "Regalos de pareja y amistad; detalles y experiencias.",
         "mood_visual": {"paleta": ["#E63946", "#FFE5EC", "#1D3557"], "luz": "cálida", "elementos": ["regalo", "cena", "flores"]}},
        dict(_MADRE, mm_dd=("05-01", "05-10")),
        dict(_PADRE, mm_dd=("06-05", "06-20")),
        {"clave": "regreso_a_clases", "nombre": "Regreso a clases", "tipo": "estacional", "mm_dd": ("08-10", "08-31"),
         "contexto": "Útiles, uniformes y organización del hogar para el inicio del ciclo escolar.",
         "mood_visual": {"paleta": ["#2F80ED", "#F2C94C", "#FFFFFF"], "luz": "mañana, fresca",
                         "elementos": ["mochila", "escritorio", "calendario"]}},
        {"clave": "buen_fin", "nombre": "El Buen Fin", "tipo": "comercial", "mm_dd": ("11-10", "11-20"),
         "contexto": "Descuentos y meses sin intereses; urgencia.",
         "mood_visual": {"paleta": ["#000000", "#FFD400", "#FFFFFF"], "luz": "contrastada", "elementos": ["etiquetas", "carrito"]}},
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


def adoptar(cliente, clave, pais=None, anio=None):
    """Crea la temporada del preset (o devuelve la existente con el mismo
    nombre e inicio, para que el clic repetido no duplique)."""
    p = next((x for x in presets(pais, anio) if x["clave"] == clave), None)
    if not p:
        raise datos.ErrorDatos("Ese preset de temporada no existe.")
    for t in datos.temporadas(cliente, incluir_archivadas=True):
        if t["nombre"] == p["nombre"] and t["inicio"] == p["inicio"]:
            return t["id"]
    return datos.crear_temporada(cliente, p["nombre"], p["inicio"], p["fin"], contexto=p["contexto"],
                                 mood_visual=p["mood_visual"], tipo=p["tipo"])
