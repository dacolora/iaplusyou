"""
State machine para Nicho Parte 3 (investigación automática).

Funciones puras que leen/escriben el diccionario extra.investigacion.
El worker y Flask usan estas para avanzar la cadena sin lógica duplicada.
"""
from typing import Optional

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

def siguiente_paso(investigacion: dict) -> Optional[str]:
    """
    Lee investigacion.estado y pasos. Devuelve el próximo paso pendiente o None.
    Lógica:
    - Si estado es detenida/interrumpida/lista: None (no avanzar)
    - Si un paso de la cadena está pendiente, devuelve ése (en orden)
    - Si todos están hechos, devuelve None
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


def marcar_paso(investigacion: dict, paso: str, estado: str, **kwargs) -> dict:
    """
    Crea una copia con pasos[paso].estado actualizado + kwargs adicionales.
    """
    inv = dict(investigacion)
    pasos = dict(inv.get("pasos", {}))
    pasos[paso] = {**(pasos.get(paso) or {}), "estado": estado, **kwargs}
    inv["pasos"] = pasos
    return inv


def resumen(investigacion: dict) -> dict:
    """
    Construye un dict con todo lo que la UI necesita para mostrar el resumen.
    """
    consultas = investigacion.get("consultas", [])
    pasos = investigacion.get("pasos", {})
    gastado = investigacion.get("gastado_usd", 0)
    aprobado = investigacion.get("aprobado_usd", 0)
    estado = investigacion.get("estado", "")
    
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
        "estado": estado,
        "detenida_por": investigacion.get("detenida_por"),
        "pasos": pasos
    }


def puede_reanudar(estado: str) -> bool:
    """True si el estado permite reanudar."""
    return estado in ("detenida", "interrumpida")


def estimar(estudio: dict, pais: str, plataformas: list, redes: list, topes: dict) -> dict:
    """
    Devuelve desglose de costos.
    {"filas": [...], "claude_usd", "avatares_usd", "total_usd"}
    """
    filas = []
    total = 0.0
    
    # Cada plataforma: búsqueda + reseñas
    for plat in plataformas:
        busqueda = 0.15
        resenas = 1.20
        filas.append({
            "clave": plat, "nombre": plat.replace("_", " ").title(),
            "busqueda_usd": busqueda, "resenas_usd": resenas,
            "texto": f"Búsqueda + reseñas"
        })
        total += busqueda + resenas
    
    # Claude: consultas + selección
    claude = 0.05
    total += claude
    
    # Avatares
    avatares = 1.20
    total += avatares
    
    return {
        "filas": filas,
        "claude_usd": claude,
        "avatares_usd": avatares,
        "total_usd": round(total, 2),
        "texto": f"Investigación: {len(plataformas)} plataforma(s)"
    }


def inicializar() -> dict:
    """Crea un dict investigacion vacío."""
    return {
        "version": 1,
        "estado": "",
        "consultas": [],
        "plataformas": [],
        "redes": [],
        "pasos": {},
        "gastado_usd": 0.0,
        "aprobado_usd": 0.0,
        "ultimo_error": None,
        "detenida_por": None
    }
