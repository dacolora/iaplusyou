"""
Contrato común de las fuentes de barrido (spec 2026-09-23 §4). Un módulo por
fuente (`atria.py`, y en el bloque 5 `apify_adlibrary.py`) con tres funciones
de nivel de módulo: `estimar(consulta, tope)`, `probar()`,
`traer(consulta, tope, avanzar)`. `ErrorFuente` es el único error que una
fuente deja escapar hacia la ruta o el worker: `.usuario` (== `str(e)`) es un
mensaje en español apto para mostrarse tal cual y nunca lleva llaves ni HTML
ajeno.

`AVISO_CUOTA_AGOTADA`: valor que una fuente puede pasar como `detalle` a
`avanzar()` (nunca como excepción) para señalar que dejó de traer páginas
porque se acabó su cupo — no porque la búsqueda esté genuinamente agotada
(`traer()` sigue devolviendo `([], None, {})` en los dos casos, indistinguibles
por su forma; `avanzar` es la única señal fuera de banda). `_fase_trayendo`
(tareas/referentes.py) lo intercepta para dejar un aviso en el barrido en vez
de tragárselo en silencio (spec §12).

Cada página que `traer()` entrega es un 3-tuple `(pagina, cursor_siguiente,
meta)`; `meta` es un dict — `{}` cuando la fuente no tiene costo propio por
llamada que reportar (Atria: solo consume el cupo mensual del plan), o
`{"costo_real": float}` cuando sí lo tiene (p. ej. una fuente que factura por
resultado real). `_fase_trayendo` registra ese costo en `gastos` bajo una
referencia fija por tarea (bid + fuente + tarea_id), no por página: una
fuente que reportara `costo_real` en más de un yield dentro de la MISMA
llamada a `traer()` vería pisado (no sumado) el costo de las páginas
anteriores, así que debe reportarlo en, a lo sumo, una página por llamada."""

AVISO_CUOTA_AGOTADA = "cuota_agotada"


class ErrorFuente(Exception):
    """Error mostrable al usuario. `usuario` es el mensaje en español (sin
    llaves, sin HTML) y `str(e)` devuelve exactamente lo mismo."""

    def __init__(self, usuario):
        self.usuario = str(usuario)
        super().__init__(self.usuario)
