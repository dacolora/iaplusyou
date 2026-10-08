"""PND-068: retiro de productores; las piezas y los datos pagados sobreviven."""
import pytest
from tests.test_rutas_referentes import app  # noqa: F401

RUTAS = [
    'idea/nueva', 'idea/nueva_visual', 'idea/i/eliminar', 'idea/i/eliminar_visual',
    'idea/i/concepto/c/higgsfield/aprobar', 'idea/i/concepto/c/higgsfield/descartar',
    'idea/i/concepto/c/higgsfield/animacion/a/generar_video',
    *[f'prompt/p/{accion}' for accion in ('guardar','aprobar','regenerar_imagen','aprobar_imagen','rechazar')],
]

@pytest.mark.parametrize('ruta', RUTAS)
def test_rutas_retiradas_dan_404_sin_generar(app, monkeypatch, ruta):
    d = app['dashboard']
    monkeypatch.setattr(d.trabajos, 'iniciar', lambda *a, **k: pytest.fail('no debe generar'))
    assert app['c'].post('/cliente/acme/' + ruta).status_code == 404


def test_pieza_higgsfield_importada_sigue_en_proyecto(app, monkeypatch, tmp_path):
    import creative_flow, gastos, estado, conceptos_imagen, json
    from flask import template_rendered
    monkeypatch.setattr(estado, 'BASE_DIR', str(tmp_path))
    monkeypatch.setattr(conceptos_imagen, 'BASE_DIR', str(tmp_path))
    estado.guardar('acme', {'viejo': {'estado': 'pendiente', 'video_url': 'https://r2.test/antiguo.mp4'}})
    conceptos_imagen.guardar('acme', {'idea_vieja': {'idea': 'Idea guardada', 'conceptos': {
        'c1': {'texto': 'Concepto guardado', **{p: {'estado': 'aprobado', 'url': 'https://r2.test/antigua.png'}
                                             for p in conceptos_imagen.PROVEEDORES}}}}})
    carpeta = tmp_path / 'clientes' / 'acme'
    (carpeta / 'prompts_pendientes.json').write_text(json.dumps({'p1': {'estado': 'aprobado'}}))
    archivos = {p: p.read_bytes() for p in carpeta.glob('*.json')}
    contextos = []
    def recoger(sender, template, context, **kw):
        if template.name == 'cliente.html':
            contextos.append(context)
    cid = creative_flow.crear('acme', [], [], [], 'Concepto antiguo conservado', 5, '', 'A',
                             referencias_urls=['https://r2.test/antigua.png'])
    creative_flow.actualizar('acme', cid, estado='video_listo', modelo='kling-2.1-pro',
                            video_url='https://r2.test/antiguo.mp4', imagen_url='https://r2.test/antigua.png')
    gastos.registrar_seguro('acme', 'video', 0.49, f'video:{cid}:t1', proveedor='higgsfield')
    antes = creative_flow.cargar('acme')
    with template_rendered.connected_to(recoger, app['dashboard'].app):
        r = app['c'].get('/cliente/acme')
    assert r.status_code == 200 and cid.encode() in r.data
    detalle = app['c'].get(f'/cliente/acme/creative_flow/{cid}/detalle')
    assert detalle.status_code == 200
    assert b'https://r2.test/antiguo.mp4' in detalle.data
    assert creative_flow.cargar('acme') == antes
    assert gastos.resumen_total('acme')['total'] == 0.49
    assert contextos[0]['videos'][0]['id'] == 'viejo'
    assert contextos[0]['ideas_visuales'][0]['conceptos'][0]['imagenes']['higgsfield']['url'] == 'https://r2.test/antigua.png'
    assert all(p.read_bytes() == original for p, original in archivos.items())


def test_tipo_desconocido_falla_en_palabras_sin_cobrar(base_temporal, monkeypatch):
    import cola, gastos, worker
    monkeypatch.setattr(worker, 'PERIODICAS', [])
    monkeypatch.setattr(gastos, 'registrar_seguro', lambda *a, **k: pytest.fail('no debe cobrar'))
    tid = cola.encolar('nueva_idea_retirada', {}, max_intentos=1)
    worker.ciclo()
    fila = cola.consultar_por_id(tid)
    assert fila['estado'] == 'error'
    assert 'tipo de tarea desconocido' in fila['error']
