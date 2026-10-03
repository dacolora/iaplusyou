"""PND-042: escritores reales simultáneos, JSON aislado."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, BrokenBarrierError, local

import pytest


@pytest.mark.parametrize('segundo', ['nombre', 'idioma', 'aprendizaje'])
def test_pnd042_no_pierde_escrituras(tmp_path, monkeypatch, segundo):
    import proyectos
    import idiomas
    monkeypatch.setattr(proyectos, '_path', lambda c: str(tmp_path / f'{c}.json'))
    leer = proyectos.cargar
    barrera = Barrier(2)
    hilo = local()
    def lenta(c):
        datos = leer(c)
        if not getattr(hilo, 'leido', False):
            hilo.leido = True
            try:
                barrera.wait(timeout=.2)
            except BrokenBarrierError:
                pass
        return datos
    monkeypatch.setattr(proyectos, 'cargar', lenta)
    cambios = {'nombre': lambda: proyectos.guardar_nombre('acme', 'Acme'),
               'idioma': lambda: idiomas.guardar_de_proyecto('acme', 'en'),
               'aprendizaje': lambda: proyectos.agregar_aprendizaje('acme', {'id': 'b', 'texto': 'segundo'})}
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(proyectos.agregar_aprendizaje, 'acme', {'id': 'a', 'texto': 'primero'})
        b = pool.submit(cambios[segundo])
        a.result(); b.result()
    datos = leer('acme')
    assert 'a' in [x['id'] for x in datos.get('aprendizajes', [])]
    if segundo == 'aprendizaje':
        assert {x['id'] for x in datos['aprendizajes']} == {'a', 'b'}
    else:
        assert datos[segundo] == {'nombre': 'Acme', 'idioma': 'en'}[segundo]
