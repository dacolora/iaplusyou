"""Qué cuentas publicitarias de Meta puede usar un experimento de un proyecto (PND-148, spec 2026-10-16).

Por qué existe: happyflops tiene 7 cuentas publicitarias en SEK, una por país, y hasta el 2026-10-16 todo experimento
se lanzaba en la única cuenta de `meta.json`. Ahora cada país de un experimento dice en qué cuenta se lanza
(`experimento.paises[i]["ad_account_id"]`; sin ese campo, la de defecto).

Reglas:
- La cuenta por defecto es la de `meta.json` (la conexión): siempre puede lanzar, como hasta ahora, y su moneda es la
  del experimento.
- Las demás salen de `meta_cuenta` (las que el proyecto LEE en Rendimiento; un admin las elige y una cuenta solo puede
  estar en un proyecto) con `extra["puede_lanzar"]` en True — lo escribe la copia de Rendimiento a partir de
  `user_tasks` (`ADVERTISE` o `MANAGE`) — y la MISMA moneda que el experimento: un experimento tiene una sola moneda.
- En modo agencia solo la de defecto (spec §3: fuera de alcance).

Quien elige (la ruta de «Nuevo experimento») valida con `validar`; quien gasta (el lanzador: lanzar, activar, cambiar
un diario) vuelve a mirar con `disponibles` antes de tocar Meta, porque una cuenta puede salir del proyecto o perder
el permiso después de elegida. Pausar no se frena nunca."""
from flask_babel import gettext

import meta_conexion
from meta_rendimiento import cuentas

# Lo que la persona conectada puede hacer en la cuenta (`user_tasks` de la cuenta en Graph) para que Creatv lance ahí.
TAREAS_QUE_LANZAN = frozenset({"ADVERTISE", "MANAGE"})


def normalizar(act):
    """«123» o «act_123» -> «act_123»; vacío -> None."""
    act = str(act or "").strip()
    return cuentas.normalizar_id(act) if act else None


def puede_lanzar(user_tasks):
    """True si la lista de tareas de Meta deja crear y activar anuncios en la cuenta."""
    if not isinstance(user_tasks, (list, tuple, set, frozenset)):
        return False
    return bool(TAREAS_QUE_LANZAN & {str(t).strip().upper() for t in user_tasks if t})


def defecto(cliente):
    """{"id", "nombre", "moneda"} de la cuenta de `meta.json`, o None sin conexión."""
    datos = meta_conexion.cargar(cliente) or {}
    act = normalizar(datos.get("ad_account_id"))
    if not act:
        return None
    return {"id": act, "nombre": datos.get("ad_account_nombre") or act, "moneda": datos.get("moneda")}


def disponibles(cliente, moneda, defecto_id=None):
    """Las cuentas de `meta_cuenta` del proyecto, aparte de la de defecto, que pueden lanzar un experimento en
    `moneda`: [{"id", "nombre", "pais", "moneda"}], en el orden de `cuentas.listar` (por nombre). En modo agencia,
    ninguna. `defecto_id` evita releer `meta.json` cuando quien llama ya lo tiene. Una consulta."""
    if meta_conexion.modo(cliente) == meta_conexion.MODO_AGENCIA:
        return []
    if defecto_id is None:
        d = defecto(cliente)
        defecto_id = d["id"] if d else None
    defecto_id = normalizar(defecto_id)
    moneda = (moneda or "").strip().upper()
    salida = []
    for c in cuentas.listar(cliente):
        if c["ad_account_id"] == defecto_id or (c.get("extra") or {}).get("puede_lanzar") is not True:
            continue
        if not moneda or (c.get("moneda") or "").strip().upper() != moneda:
            continue
        salida.append({"id": c["ad_account_id"], "nombre": c.get("nombre") or c["ad_account_id"],
                       "pais": c.get("pais"), "moneda": c.get("moneda")})
    if salida:
        # Aislamiento (revisión de PND-148): la cuenta con la que LANZA otro proyecto (su meta.json) nunca se ofrece ni
        # se acepta, aunque haya quedado en el `meta_cuenta` de este (R20 solo la frena al elegir cuentas para leer, y
        # el otro proyecto pudo conectarla después). Leer las cuentas de lanzamiento cuesta un archivo por proyecto:
        # solo si hay alguna candidata.
        ajenas = {a for a, dueno in meta_conexion.cuentas_de_lanzamiento().items() if dueno != cliente}
        salida = [c for c in salida if c["id"] not in ajenas]
    return salida


def sugeridas(codigos, disponibles_, defecto_id):
    """{país: cuenta} por defecto para cada código: la cuenta disponible de ese país (la primera por nombre) o la de
    defecto. No lee nada."""
    por_pais = {}
    for c in disponibles_:
        if c.get("pais"):
            por_pais.setdefault(c["pais"], c["id"])
    return {p: por_pais.get(p, normalizar(defecto_id)) for p in codigos}


def validar(cliente, moneda, eleccion, defecto_id=None):
    """`eleccion` = {país: cuenta elegida ("" o la de defecto = la de defecto)}. Devuelve {país: cuenta} SOLO con las
    que no son la de defecto (lo que se guarda en `paises[i]["ad_account_id"]`). Lanza ValueError si alguna no está
    entre las `disponibles` del proyecto: de otro proyecto, sin permiso para anunciar, en otra moneda o escrita a mano."""
    if defecto_id is None:
        d = defecto(cliente)
        defecto_id = d["id"] if d else None
    defecto_id = normalizar(defecto_id)
    elegidas = {p: normalizar(a) for p, a in (eleccion or {}).items()}
    elegidas = {p: a for p, a in elegidas.items() if a and a != defecto_id}
    if not elegidas:
        return {}
    permitidas = {c["id"] for c in disponibles(cliente, moneda, defecto_id=defecto_id)}
    malas = sorted(p for p, a in elegidas.items() if a not in permitidas)
    if malas:
        raise ValueError(gettext(
            "La cuenta publicitaria elegida para %(paises)s no puede lanzar en este proyecto (no está en sus cuentas de "
            "Meta, no tiene permiso para anunciar o factura en otra moneda).", paises=", ".join(malas)))
    return elegidas


def nombres(cliente):
    """{cuenta: nombre} de las cuentas del proyecto (las de `meta_cuenta` y la de defecto): lo que la gestión de un
    experimento dice junto a cada país. Una consulta; una cuenta que ya no está se pinta por su id."""
    salida = {c["ad_account_id"]: c.get("nombre") or c["ad_account_id"] for c in cuentas.listar(cliente)}
    d = defecto(cliente)
    if d and (d["nombre"] != d["id"] or d["id"] not in salida):
        salida[d["id"]] = d["nombre"]
    return salida
