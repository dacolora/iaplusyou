"""Enlaces al Administrador de anuncios de Meta (spec E2 §7): cada recomendación lleva uno con los objetos ya
seleccionados, para que la persona actúe allá (E2 no cambia nada en Meta).

Solo ids NUMÉRICOS validados (dígitos ASCII: «²».isdigit() es True y no es un id) y nunca un token: la URL se arma
a mano con dígitos y comas, sin nada que venga de la persona ni de Meta sin validar. En la plantilla el enlace va con
`target="_blank" rel="noopener noreferrer"`."""
import re

BASE = "https://adsmanager.facebook.com/adsmanager/manage"
MAX_IDS = 50   # el Administrador no abre una selección más larga en la URL

# nivel de Creatv -> (ruta del Administrador, parámetro de la selección)
_NIVELES = {"campana": ("campaigns", "selected_campaign_ids"), "conjunto": ("adsets", "selected_adset_ids"),
            "anuncio": ("ads", "selected_ad_ids")}
_DIGITOS = re.compile(r"[0-9]{1,30}")


def _digitos(valor):
    """El texto de un id numérico, o None. Un booleano no es un id (True es 1 para Python)."""
    if isinstance(valor, bool) or not isinstance(valor, (str, int)):
        return None
    texto = str(valor).strip()
    return texto if _DIGITOS.fullmatch(texto) else None


def cuenta_digitos(act):
    """Los dígitos de una cuenta publicitaria («act_123» o «123» -> «123»), o None si no es una cuenta válida."""
    if isinstance(act, str) and act.strip().lower().startswith("act_"):
        act = act.strip()[4:]
    return _digitos(act)


def enlace(act, nivel, ids):
    """La URL del Administrador en la vista de `nivel` (campana|conjunto|anuncio) con `ids` seleccionados: solo
    los numéricos, sin repetir y como mucho `MAX_IDS`, en el orden dado. None si la cuenta o el nivel no valen o
    si no queda ningún id válido."""
    digitos = cuenta_digitos(act)
    if digitos is None or nivel not in _NIVELES:
        return None
    validos = []
    for i in ids or ():
        d = _digitos(i)
        if d is not None and d not in validos:
            validos.append(d)
            if len(validos) == MAX_IDS:
                break
    if not validos:
        return None
    ruta, parametro = _NIVELES[nivel]
    return f"{BASE}/{ruta}?act={digitos}&{parametro}={','.join(validos)}"


def enlace_cuenta(act):
    """Las campañas de la cuenta en el Administrador, sin selección (para lo que es de toda la cuenta: su estado,
    su ROAS, un segmento). None si la cuenta no vale."""
    digitos = cuenta_digitos(act)
    return f"{BASE}/campaigns?act={digitos}" if digitos is not None else None
