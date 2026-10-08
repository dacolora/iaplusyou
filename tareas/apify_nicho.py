"""PND-051: una espera de Nicho conserva las corridas pagadas al parar.

El checkpoint vive en estudio.extra (único escritor: nicho.datos), separado
por job_id. La continuación y un Reanudar manual leen esos mismos IDs. No
se guardan sesiones HTTP ni tokens; el contexto del proveedor es por hilo.
"""
from copy import deepcopy

from flask_babel import gettext

import gastos
from nicho import datos
from nicho.fuentes import apify_actores, plataformas
from providers import apify
from tareas import Continuar


def ejecutar(tarea, fn, detener):
    p = tarea.get('payload') or {}
    if tarea['tipo'] not in ('nicho_recolectar', 'nicho_inv_buscar') or not p.get('estudio_id'):
        return fn(tarea)
    cliente, eid = p['cliente'], int(p['estudio_id'])
    clave = tarea.get('job_id') or f"{tarea['tipo']}:{p.get('fuente') or p.get('plataforma')}"
    est = datos.estudio(cliente, eid)
    previo = ((est or {}).get('extra') or {}).get('apify_pendientes', {}).get(clave)
    original = (previo or {}).get('tarea_id', tarea.get('id', 0))
    estado = deepcopy(previo or {})

    def guardar(checkpoint):
        estado.clear()
        estado.update(deepcopy(checkpoint), tarea_id=original)
        def cambiar(extra):
            pendientes = dict(extra.get('apify_pendientes') or {})
            pendientes[clave] = deepcopy(estado)
            return {**extra, 'apify_pendientes': pendientes}
        if datos.actualizar_extra_estudio(cliente, eid, cambiar) is None:
            raise RuntimeError(gettext('No se pudo guardar la corrida de Apify; no se lanza otra.'))

    def limpiar(extra):
        pendientes = dict(extra.get('apify_pendientes') or {})
        pendientes.pop(clave, None)
        return {**extra, 'apify_pendientes': pendientes}

    # El gasto conserva la referencia de la tarea que lanzó, también al retomar.
    with apify.recuperable(previo, guardar, detener) as contexto:
        try:
            resultado = fn({**tarea, 'id': original})
        except apify.EsperaInterrumpida:
            _registrar_pausa(tarea, estado)
            return Continuar(tarea['tipo'], p, gettext('La espera a Apify se pausó; seguirá con la misma corrida, sin volver a lanzarla.'))
        else:
            if contexto.get("usado"):
                datos.actualizar_extra_estudio(cliente, eid, limpiar)
            return resultado


def _registrar_pausa(tarea, estado):
    p = tarea['payload']
    busqueda = tarea['tipo'] == 'nicho_inv_buscar'
    if busqueda:
        tarifa = plataformas.actor_busqueda(p['plataforma'])
    elif p['fuente'] == 'apify':
        tarifa = apify_actores.ACTORES[p['params']['actor']]
    else:
        tarifa = plataformas.actor_resenas(p['fuente'])
    usd, extra = apify.costo_guardado(estado.get('registros') or [], estado.get('corridas') or [], tarifa)
    if usd <= 0:
        return
    paso = f":buscar:{p['plataforma']}" if busqueda else ''
    gastos.registrar_seguro(p['cliente'], 'recoleccion', usd,
                            f"recoleccion:{p['estudio_id']}{paso}:t{estado['tarea_id']}", proveedor='apify',
                            detalle=gettext('Corrida de Apify pausada; se recuperará sin volver a lanzarla.'),
                            extra=extra, conservar_mayor=True)
