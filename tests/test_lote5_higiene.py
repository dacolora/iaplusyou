import pytest


def test_pnd077_los_tres_caminos_comparten_verticales(monkeypatch):
    import dashboard
    import tareas.flowplus as fp
    from sprints import produccion
    assert dashboard.PLATAFORMAS_VERTICALES is fp.PLATAFORMAS_VERTICALES
    assert produccion.PLATAFORMAS_VERTICALES is fp.PLATAFORMAS_VERTICALES
    for plataformas, esperado in [([], '9:16'), (['youtube'], '16:9'),
                                   (['youtube', 'instagram'], '9:16'), (['tiktok'], '9:16')]:
        assert dashboard._aspect_ratio_para_plataformas(plataformas) == esperado
        assert fp._aspect_ratio_para_plataformas(plataformas) == esperado
        assert produccion._aspect_ratio(plataformas) == esperado


@pytest.mark.parametrize('tipo, soporta, estado, esperado', [
    ('otro', True, 'conectada', 'tienda'), ('shopify', False, 'conectada', 'ninguna'),
    ('woo', True, 'error', 'ninguna'), ('desconocida', None, 'conectada', 'ninguna')])
def test_pnd078_atribucion_lee_capacidad_del_conector(monkeypatch, tipo, soporta, estado, esperado):
    from types import SimpleNamespace
    import conectores
    import experimentos
    import meta_conexion
    import tiendas
    monkeypatch.setattr(meta_conexion, 'estado_pixel', lambda *a, **k: {'estado': 'sin_pixel'})
    monkeypatch.setattr(tiendas, 'listar', lambda c: [{'tipo': tipo, 'estado': estado}])
    def conector(t):
        if soporta is None:
            raise ValueError('conector desconocido')
        return SimpleNamespace(soporta_utm=soporta)
    monkeypatch.setattr(conectores, 'por_tipo', conector)
    assert experimentos.atribucion_sugerida('acme') == esperado


def test_pnd079_estados_compartidos_sin_aprobar_errores(monkeypatch):
    from sprints import estado, revision
    assert revision.TERMINADAS is estado.LISTAS_PARA_REVISION
    for e, campana, aprueba in [('listo', 'revision', True), ('degradada', 'revision', True),
                              ('error', 'revision', False), ('generando', 'generando', False)]:
        assert estado.estado_campana(0, 1, piezas=[{'estado': e, 'revision': 'pendiente'}]) == campana
        monkeypatch.setattr(revision, '_pieza', lambda *a, e=e: {'estado': e, 'titulo': 'P', 'sprint_id': 1, 'campana_id': 1})
        monkeypatch.setattr(revision.datos, 'actualizar_idea', lambda *a, **k: None)
        monkeypatch.setattr(revision.datos, 'texto_guardado', lambda *a, **k: '')
        monkeypatch.setattr(revision.datos, 'registrar_evento', lambda *a, **k: None)
        monkeypatch.setattr(estado, 'recalcular', lambda *a, **k: None)
        assert revision.aprobar('acme', 1) is aprueba
