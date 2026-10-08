from sqlalchemy import event
from tests.test_tablero import _experimento, _pieza_en, sin_red  # noqa: F401
from tests.test_experimentos_db import _pieza


def test_pnd134_ultima_metrica_en_una_consulta_sin_cambiar_valores(base_temporal, sin_red):
    import decisor
    import experimentos as ex
    ids = [_experimento(base_temporal, nombre=str(i)) for i in range(2)]
    eps = [_pieza_en(base_temporal, ids[i % 2], legado=f'cf_{i}') for i in range(13)]
    otro = ex.crear('otro', 'Otro vivo', [], 'OUTCOME_TRAFFIC', 7, 10, '', 'USD', atribucion='ninguna')
    ep_otro = ex.agregar_pieza('otro', otro, _pieza(base_temporal, cliente='otro', legado='cf_otro'), 'CO')
    ex.actualizar('otro', otro, estado='corriendo')
    ex.snapshot(ep_otro, {'gasto': 999, 'impresiones': 9999})
    esperadas = {}
    historias = {}
    for i, ep in enumerate(eps[:-1]):
        ex.snapshot(ep, {'gasto': 10, 'ctr': 2, 'fuente_ventas': 'meta'}, tomado_en='2026-10-07T00:00:00')
        ex.snapshot(ep, {'gasto': i + 20, 'ctr': 3, 'compras': 2, 'fuente_ventas': 'tienda', 'custom': i,
                         'impresiones': 1500, 'thruplay_rate': .3, 'roas': 3 if i % 2 else 1},
                    tomado_en='2026-10-06T00:00:00')  # backfill: manda id, igual que antes
        esperadas[ep] = ex.ultima_metrica(ep)
        historias[ep] = ex.snapshots(ep)
    esperadas[eps[-1]] = {}
    sql = []
    def contar(conn, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith('SELECT') and 'metrica_snapshot' in statement:
            sql.append(statement)
    event.listen(base_temporal.engine(), 'before_cursor_execute', contar)
    try:
        cargados = ex.cargar('acme')
    finally:
        event.remove(base_temporal.engine(), 'before_cursor_execute', contar)
    assert len(sql) == 1, f'{len(sql)} lecturas de metrica_snapshot para 13 piezas'
    metricas = {p['id']: p['metricas'] for e in cargados for p in e['piezas']}
    assert metricas == esperadas
    pieza_otra, = ex.cargar('otro')[0]['piezas']
    assert pieza_otra['id'] == ep_otro and pieza_otra['metricas']['gasto'] == 999
    assert ep_otro not in metricas
    contexto = {'horas_activo': 96, 'atribucion': 'tienda', 'compras_pais': 3}
    veredictos = set()
    for ep, historia in historias.items():
        assert ex.snapshots(ep) == historia
        decision = decisor.decidir([metricas[ep]], {}, contexto)
        assert decision == decisor.decidir(historia, {}, contexto)
        veredictos.add(decision['veredicto'])
    assert veredictos == {'ganador', 'perdedor'}
    for eid in ids:
        assert ex.obtener('acme', eid)['piezas'] == next(e['piezas'] for e in cargados if e['id'] == eid)


def test_pnd137_bloqueo_cuenta_vivos_sin_cargar_piezas(base_temporal, sin_red, monkeypatch):
    import dashboard
    import experimentos as ex
    import organico
    for estado in (*ex.ESTADOS_VIVOS, 'cerrado', 'error'):
        _experimento(base_temporal, nombre=estado, estado=estado)
    # No cuenta ni el otro proyecto ni el experimento legado.
    otro = ex.crear('otro', 'Otro', [], 'OUTCOME_TRAFFIC', 7, 10, '', 'USD', atribucion='ninguna')
    legado = _experimento(base_temporal, nombre='Legado', estado='corriendo')
    with base_temporal.conectar() as con:
        con.execute(base_temporal.experimento.update().where(base_temporal.experimento.c.id == otro).values(estado='corriendo'))
        con.execute(base_temporal.experimento.update().where(base_temporal.experimento.c.id == legado).values(legado=True))
    monkeypatch.setattr(organico, 'listar', lambda c: [{'estado': 'publicando'}] if c == 'acme' else [])
    def pesado(*a):
        raise AssertionError('se cargaron piezas para contar vivos')
    monkeypatch.setattr(ex, 'cargar', pesado)
    assert '5 experimentos vivos' in dashboard._bloqueo_cambio_forma('acme')
    assert '1 publicación en curso' in dashboard._bloqueo_cambio_forma('acme')
    assert '1 experimento vivo' in dashboard._bloqueo_cambio_forma('otro')
    assert dashboard._bloqueo_cambio_forma('nadie') is None
