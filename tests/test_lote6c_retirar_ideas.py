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


def test_proyecto_con_legado_responde_200_sin_leer_conceptos_retirados(app, monkeypatch, tmp_path):
    import estado, conceptos_imagen, json
    monkeypatch.setattr(estado, 'BASE_DIR', str(tmp_path))
    monkeypatch.setattr(conceptos_imagen, 'BASE_DIR', str(tmp_path))
    estado.guardar('acme', {'viejo': {'estado': 'pendiente', 'video_url': 'https://r2.test/antiguo.mp4'}})
    conceptos_imagen.guardar('acme', {'idea_vieja': {'idea': 'Idea guardada', 'conceptos': {
        'c1': {'texto': 'Concepto guardado', **{p: {'estado': 'aprobado', 'url': 'https://r2.test/antigua.png'}
                                             for p in conceptos_imagen.PROVEEDORES}}}}})
    carpeta = tmp_path / 'clientes' / 'acme'
    (carpeta / 'prompts_pendientes.json').write_text(json.dumps({'p1': {'estado': 'aprobado'}}))
    archivos = {p: p.read_bytes() for p in carpeta.glob('*.json')}
    monkeypatch.setattr(conceptos_imagen, 'cargar', lambda c: pytest.fail('la página lee conceptos que no pinta'))
    assert app['c'].get('/cliente/acme').status_code == 200
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
