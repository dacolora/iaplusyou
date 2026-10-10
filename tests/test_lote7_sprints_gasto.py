"""PND-166: Claude falso, cola y libro reales; sin llamadas a proveedores."""
import json
from types import SimpleNamespace
import pytest


@pytest.fixture
def claude(monkeypatch):
    import anthropic, generador_prompts, marca, catalogo_productos, proyectos
    from sprints.analisis import CLAVES
    estado = {'llamadas': [], 'texto': json.dumps({k: ([] if k in ('paleta', 'elementos') else 'ok') for k in CLAVES})}
    class Falso:
        def __init__(self, **kw):
            estado['opciones'] = kw
            self.messages = self
        def create(self, **kw):
            estado['llamadas'].append(kw)
            return SimpleNamespace(content=[SimpleNamespace(type='text', text=estado['texto'])],
                                   usage=SimpleNamespace(input_tokens=1000, output_tokens=200, cache_creation_input_tokens=400, cache_read_input_tokens=200))
    monkeypatch.setattr(anthropic, 'Anthropic', Falso)
    monkeypatch.setattr(generador_prompts, '_api_key', lambda: 'llave-de-prueba')
    monkeypatch.setattr(marca, 'guia_efectiva', lambda c: '')
    monkeypatch.setattr(catalogo_productos, 'listar_productos', lambda *a: [])
    monkeypatch.setattr(proyectos, 'nombre_visible', lambda c: c)
    return estado


def referencia():
    from sprints import datos
    sid = datos.crear_sprint('acme', 'Octubre', '2026-10-01', '2026-10-31')
    pid = datos.crear_persona('acme', 'Ana')
    cid = datos.agregar_campana('acme', sid, pid, 'producto', None, 1, 1)
    return datos.agregar_referencia('acme', cid, 'imagen', 'https://ejemplo.test/a.jpg')


@pytest.mark.parametrize('tipo', ['analizar', 'sugerir'])
@pytest.mark.parametrize('fallo', [None, 'json', 'persistir'])
def test_pnd166_gasto_con_usage_incluso_si_falla(base_temporal, claude, monkeypatch, tipo, fallo):
    from sprints import datos
    from tareas import sprints as ts
    from nicho.avatares import costo_real
    from cobros import libro
    import gastos
    rid = referencia()
    if tipo == 'sugerir':
        claude['texto'] = json.dumps({'personas': [{'nombre': 'Nueva', 'resumen': '', 'descripcion': '', 'edad_rango': '', 'tono': '', 'senales_visuales': [], 'palabras_clave': []}]})
    if fallo == 'json':
        claude['texto'] = 'no json'
    if fallo == 'persistir':
        def romper(*a, **kw):
            raise RuntimeError('guardar falló')
        monkeypatch.setattr(datos, 'actualizar_referencia' if tipo == 'analizar' else 'crear_persona', romper)
    libro.configurar('acme', cobrar=True, margen=2, usuario='admin')
    tarea = {'id': 44, 'payload': {'cliente': 'acme', 'referencia_id': rid, 'cuantas': 1}}
    with libro.en_trabajo(44, 'job'):
        if fallo:
            with pytest.raises(Exception):
                getattr(ts, 'ejecutar_' + tipo)(tarea)
        else:
            getattr(ts, 'ejecutar_' + tipo)(tarea)
    filas = gastos.historial('acme')
    assert len(filas) == 1
    n = len(claude['llamadas'])
    assert filas[0]['usd'] == pytest.approx(round(costo_real(1520*n, 200*n), 4))
    assert filas[0]['referencia'].endswith(':t44')
    assert filas[0]['proveedor'] == 'anthropic'
    assert filas[0]['detalle']
    assert ('·' in filas[0]['detalle']) == bool(fallo)
    assert 'max_retries' not in claude['opciones']
    with base_temporal.conectar() as con:
        m = con.execute(base_temporal.movimiento_saldo.select()).mappings().all()
    assert len(m) == 1 and m[0]['tipo'] == ('no_cobrado' if fallo else 'cobro')


@pytest.mark.parametrize('tipo', ['analizar', 'sugerir'])
def test_pnd166_encolar_con_precio_un_intento(base_temporal, tipo):
    import cola, gastos
    from cobros import libro
    libro.configurar('acme', cobrar=True, margen=2, usuario='admin')
    with base_temporal.conectar() as con:
        libro.acreditar(con, 'acme', 'ajuste', 10000, 'prueba', usuario='admin')
    from tareas import sprints as ts
    if tipo == 'analizar':
        ts.encolar_analisis('acme', referencia())
    else:
        ts.encolar_sugerir('acme')
    t = cola.reclamar()
    assert t['max_intentos'] == 1
    tarifa = 'analizar_referencia' if tipo == 'analizar' else 'sugerir_personas'
    assert libro.reservado('acme') == libro.precio_milesimas(gastos.estimar(tarifa)['usd'], 2)
    assert cola.fallar(t['id'], 'fallo') == 'error'
    assert cola.reclamar() is None
