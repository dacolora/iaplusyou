import pytest

from tests.test_tareas_director import _sesion


@pytest.mark.parametrize('tipo', ['runtime', 'director', 'interrumpida'])
def test_pnd072_aviso_redactado_sin_cambiar_prompt(base_temporal, monkeypatch, tipo):
    import creative_flow as cf
    import tareas.director as td
    cid = _sesion(cf)
    entry = cf.cargar('acme')[cid]
    esperado, _ = td._fallback('acme', entry, 'sin secreto')
    secreto = 'valor-falso-director-llave-de-prueba'
    motivo = 'proveedor falló: token=' + secreto
    vistos = []
    def falla(cliente, sesion, idioma='es'):
        vistos.append(sesion)
        raise td.director.DirectorError(motivo) if tipo == 'director' else RuntimeError(motivo)
    monkeypatch.setattr(td.director, 'compilar', falla)
    tarea = {'payload': {'cliente': 'acme', 'cf_id': cid}, 'job_id': 'j72'}
    if tipo == 'interrumpida':
        td.interrumpida(tarea, motivo)
    else:
        td.ejecutar(tarea)
        assert vistos == [cf.datos_para_director('acme', entry)]
    final = cf.cargar('acme')[cid]
    assert secreto not in final['director']['aviso']
    assert 'token=***' in final['director']['aviso']
    assert final['prompt_relleno'] == esperado


def test_pnd072_encolado_compartido_preserva_contrato(base_temporal, monkeypatch):
    import dashboard
    import creative_flow as cf
    import tareas.director as td
    from sprints import produccion
    cid = _sesion(cf)
    original = getattr(td, 'encolar', None)
    compartidas = []
    def encolar(cliente, cf_id, auto_lanzar=False, prioridad=5):
        compartidas.append((cliente, cf_id, auto_lanzar, prioridad))
        return True
    monkeypatch.setattr(td, 'encolar', encolar, raising=False)
    monkeypatch.setattr(td.trabajos, 'encolar', lambda *a, **k: True)
    assert dashboard._encolar_director('acme', cid, prioridad=5)
    assert produccion.encolar_director('acme', cid, prioridad=3)
    assert compartidas == [('acme', cid, False, 5), ('acme', cid, True, 3)]
    # La implementación compartida conserva job, payload, prioridad y cero retries.
    monkeypatch.setattr(td, 'encolar', original)
    cola = []
    monkeypatch.setattr(td.trabajos, 'encolar', lambda *a, **k: cola.append((a, k)) or True)
    assert td.encolar('acme', cid, auto_lanzar=True, prioridad=3)
    args, kwargs = cola[0]
    assert args == (f'acme__{cid}__director', 'flowplus_director',
                    {'cliente': 'acme', 'cf_id': cid, 'auto_lanzar': True, 'prioridad': 3})
    assert kwargs == {'cliente': 'acme', 'duracion_estimada': td.DURACION_ESTIMADA,
                      'etapas': td.ETAPAS_DIRECTOR, 'max_intentos': 1, 'prioridad': 3}
