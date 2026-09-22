"""
State machine pura para Nicho Parte 3 (spec §1, §2, §5–§6).

Funciones puras que leen/escriben el diccionario extra.investigacion.
El worker y Flask usan estas para avanzar la cadena sin lógica duplicada.

Las tres tareas principales (consultas, buscar, seleccionar) caen en
max_intentos=2 (Claude, barato); búsquedas y reseñas en max_intentos=1
(Apify, de pago).
"""
from datetime import datetime
from typing import Optional, Dict, Any, List

# ------ Enums y constantes ------

ESTADOS_CADENA = (
    "consultas", "buscando", "seleccionando", "resenas",
    "redes", "generando", "lista", "detenida", "interrumpida"
)

PASOS_CADENA = (
    "consultas", "buscar:amazon", "buscar:meli", "buscar:tiktok_shop",
    "seleccionar", "resenas:amazon", "resenas:meli", "resenas:tiktok_shop",
    "redes:reddit", "redes:youtube", "generar"
)

TOPES_DEFECTO = {
    "consultas": 3,
    "productos_por_consulta": 20,
    "productos_elegidos": 15,
    "resenas_por_producto": 100
}

IDIOMAS = {
    "SE": "sv", "CO": "es", "MX": "es", "ES": "es", "AR": "es", "CL": "es",
    "PE": "es", "US": "en", "GB": "en", "CA": "en", "AU": "en", "IN": "en",
    "BR": "pt", "DE": "de", "FR": "fr", "IT": "it", "NL": "nl", "JP": "ja", "AE": "en"
}

PLATAFORMAS_POR_PAIS = {
    "amazon": {"US": "com", "GB": "co.uk", "DE": "de", "FR": "fr", "IT": "it",
               "ES": "es", "NL": "nl", "SE": "se", "CA": "ca", "MX": "com.mx",
               "BR": "com.br", "AU": "com.au", "IN": "in", "JP": "co.jp", "AE": "ae"},
    "meli": {"AR": "com.ar", "BR": "com.br", "CL": "cl", "CO": "com.co",
             "MX": "com.mx", "PE": "com.pe", "UY": "com.uy"},
    "tiktok_shop": {"*": None}  # worldwide
}

# ------ API pura ------

def siguiente_paso(investigacion: Dict[str, Any]) -> Optional[str]:
    """
    Lee investigacion.estado y pasos. Devuelve el próximo paso pendiente o None.

    Lógica:
    - Si estado es detenida/interrumpida/lista: None (no avanzar)
    - Si estado es en_curso (ej "buscando"), devuelve el paso activo
    - Si un paso de la cadena está pendiente, devuelve ése (en orden)
    - Si todos están hechos o ausentes, devuelve None
    """
    estado = investigacion.get("estado")
    pasos = investigacion.get("pasos", {})

    if estado in ("lista", "detenida", "interrumpida"):
        return None

    # Recorrer la cadena en orden
    for paso in PASOS_CADENA:
        info = pasos.get(paso, {})
        paso_estado = info.get("estado")

        if paso_estado is None:  # nunca hecho
            return paso
        elif paso_estado == "en_curso":  # retomar este
            return paso
        # else: "hecho", "error", "vacio" -> continuar

    return None  # todos hechos


def marcar_paso(investigacion: Dict[str, Any], paso: str, estado: str, **kwargs) -> Dict[str, Any]:
    """
    Crea una copia con pasos[paso].estado actualizado + kwargs adicionales
    (usd, productos, relevantes, resenas, aviso, etc).

    Args:
        investigacion: dict actual de investigacion
        paso: nombre del paso (ej "consultas", "buscar:amazon")
        estado: "hecho", "en_curso", "error", "vacio"
        **kwargs: campos adicionales (usd, productos, etc)

    Returns:
        investigacion con pasos actualizado
    """
    inv = dict(investigacion)
    pasos = dict(inv.get("pasos", {}))
    pasos[paso] = {**(pasos.get(paso) or {}), "estado": estado, **kwargs}
    inv["pasos"] = pasos
    return inv


def resumen(investigacion: Dict[str, Any]) -> Dict[str, Any]:
    """
    Construye un dict con todo lo que la UI necesita para mostrar
    el resumen: consultas usadas, productos por plataforma, etc.
    """
    consultas = investigacion.get("consultas", [])
    pasos = investigacion.get("pasos", {})
    gastado = investigacion.get("gastado_usd", 0)
    aprobado = investigacion.get("aprobado_usd", 0)

    # Contar productos y relevantes por plataforma
    productos_total = 0
    relevantes_total = 0
    for paso, info in pasos.items():
        if paso.startswith("buscar:"):
            productos_total += info.get("productos", 0)
        elif paso == "seleccionar":
            relevantes_total = info.get("relevantes", 0)

    return {
        "consultas": consultas,
        "productos": productos_total,
        "relevantes": relevantes_total,
        "gastado": gastado,
        "aprobado": aprobado,
        "detenida_por": investigacion.get("detenida_por"),
        "pasos": pasos,
        "estado": investigacion.get("estado"),
        "ultimo_error": investigacion.get("ultimo_error")
    }


def puede_reanudar(estado: str) -> bool:
    """True si el estado permite reanudar."""
    return estado in ("detenida", "interrumpida")


def estimar(estudio: Dict[str, Any], pais: str, plataformas: List[str],
            redes: List[str], topes: Dict[str, int]) -> Dict[str, Any]:
    """
    Devuelve desglose de costos:
    {"filas": [{"clave", "nombre", "busqueda_usd", "resenas_usd"}],
     "claude_usd", "avatares_usd", "total_usd", "texto"}

    Args:
        estudio: dict con el estudio (pais puede venir del estudio o del param)
        pais: código de país (ej "SE", "CO")
        plataformas: list["amazon", "meli", "tiktok_shop"]
        redes: list["reddit", "youtube"]
        topes: dict con limites (consultas, productos_por_consulta, etc)

    Returns:
        dict con estructura de costos
    """
    from nicho.fuentes import plataformas as plat_module

    filas = []
    total = 0.0

    # Iterar plataformas y estimar costos
    for plat_clave in plataformas:
        busqueda_usd = plat_module.estimar_busqueda(
            plat_clave,
            topes.get("consultas", TOPES_DEFECTO["consultas"]),
            topes.get("productos_por_consulta", TOPES_DEFECTO["productos_por_consulta"])
        )
        resenas_usd = plat_module.estimar_resenas(
            plat_clave,
            topes.get("productos_elegidos", TOPES_DEFECTO["productos_elegidos"]),
            topes.get("resenas_por_producto", TOPES_DEFECTO["resenas_por_producto"])
        )

        filas.append({
            "clave": plat_clave,
            "nombre": plat_module.PLATAFORMAS.get(plat_clave, {}).get("nombre", plat_clave.title()),
            "busqueda_usd": round(busqueda_usd, 2),
            "resenas_usd": round(resenas_usd, 2),
            "texto": f"Búsqueda + reseñas"
        })
        total += busqueda_usd + resenas_usd

    # Claude: consultas (~$0.03) + selección (~$0.02)
    claude_usd = 0.05
    total += claude_usd

    # Avatares: ~US$ 1.20
    avatares_usd = 1.20
    total += avatares_usd

    return {
        "filas": filas,
        "claude_usd": round(claude_usd, 2),
        "avatares_usd": round(avatares_usd, 2),
        "total_usd": round(total, 2),
        "texto": f"Investigación: {len(plataformas)} plataforma(s), {len(redes)} red(es)"
    }


def crear_inicial(tema: str, pais: str, plataformas: List[str],
                  redes: List[str], topes: Dict[str, int]) -> Dict[str, Any]:
    """
    Crea el dict inicial de investigacion antes de encolar.

    Args:
        tema: descripción del nicho
        pais: código de país
        plataformas: list de plataformas seleccionadas
        redes: list de redes sociales seleccionadas
        topes: dict con limites de búsqueda

    Returns:
        dict investigacion listo para guardar en estudio.extra
    """
    ahora = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    return {
        "version": 1,
        "estado": "consultas",
        "tema": tema,
        "pais": pais,
        "plataformas": plataformas,
        "redes": redes,
        "topes": topes,
        "consultas": [],
        "pasos": {},
        "creado_en": ahora,
        "actualizado_en": ahora,
        "gastado_usd": 0.0,
        "aprobado_usd": estimar({}, pais, plataformas, redes, topes).get("total_usd", 0.0)
    }
