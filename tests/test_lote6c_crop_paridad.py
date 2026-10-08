"""PND-049: renders ffmpeg pequeños; referencia anterior congelada y marco JS intacto."""
import subprocess
import pytest
from PIL import Image, ImageChops, ImageStat
from final_edition import cortes, documento as d, encuadre, motor
from final_edition.motor import compilador as c, render as r
from deploy.medir_memoria_render import encuadre_anterior

CASOS = [
    ('llenar_centro', {'zoom': 2.45}, False, False),
    ('llenar_izquierda', {'zoom': 2.45, 'x': 0, 'y': 0}, False, False),
    ('llenar_derecha', {'zoom': 2.45, 'x': 1, 'y': 1}, False, False),
    ('llenar_desplazado', {'zoom': 1.5, 'x': 0.27, 'y': 0.73}, False, False),
    ('ajustar', {'modo': 'ajustar'}, False, False),
    ('ajustar_zoom', {'modo': 'ajustar', 'zoom': 2.45, 'x': 0.27}, False, False),
    ('ajustar_menor_1', {'modo': 'ajustar', 'zoom': 0.8}, False, False),
    ('foto', {'zoom': 2.45, 'x': 0.73}, True, False),
    ('foto_ajustar', {'modo': 'ajustar', 'zoom': 1.5}, True, False),
    ('foto_zoom_lento', {'zoom': 1.5, 'y': 0.27}, True, False),
    ('rotado', {'zoom': 2.45, 'y': 0.73}, False, True),
    ('rotado_ajustar', {'modo': 'ajustar'}, False, True),
]

@pytest.fixture(scope='module')
def medios(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp('paridad_crop')
    fuente, rotado, foto = [str(carpeta / n) for n in ('src.mp4', 'rot.mp4', 'foto.png')]
    cortes.ffmpeg(['-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=30', '-t', '1',
                   '-c:v', 'libx264', '-crf', '0', '-pix_fmt', 'yuv420p', fuente])
    cortes.ffmpeg(['-display_rotation:v:0', '90', '-i', fuente, '-c', 'copy', rotado])
    cortes.ffmpeg(['-i', fuente, '-frames:v', '1', foto])
    return fuente, rotado, foto


def _cuadro(path, tiempo, tmp_path, nombre):
    out = str(tmp_path / (nombre + '.png'))
    r.miniatura(path, out, tiempo)
    with Image.open(out) as im:
        return im.convert('RGB')


@pytest.mark.slow
@pytest.mark.parametrize('nombre,enc,foto,rotado', CASOS)
def test_paridad_real(tmp_path, medios, monkeypatch, nombre, enc, foto, rotado):
    monkeypatch.setitem(c.FORMATOS, '9:16', (360, 640))
    fuente = medios[2 if foto else 1 if rotado else 0]
    w, h = (360, 640) if rotado else (640, 360)
    doc = d.nuevo_video('9:16')
    # Usamos el contrato normalizado salvo zoom < 1, solo en ajustar. No es
    # editable hoy (ZOOM_MIN=1); se prueba el comportamiento geométrico existente.
    doc['pistas'][0]['clips'] = [
        {'id': f'v{i}', 'inicio_ms': i * 400, 'duracion_ms': 400, 'material_id': 1,
         'foto': foto, 'ancho_px': w, 'alto_px': h, 'encuadre': enc,
         'recorte': {'desde_ms': 0, 'hasta_ms': 400},
         'ken_burns': 'in' if nombre == 'foto_zoom_lento' else None,
         'transicion': {'tipo': 'fundido', 'duracion_ms': 200} if i == 0 else None}
        for i in range(2)]
    rutas = {'foto:1' if foto else 1: fuente}
    nuevo_fn = c._encuadre
    monkeypatch.setattr(r, 'OPCIONES_VIDEO', ['-c:v', 'libx264', '-crf', '0', '-pix_fmt', 'yuv420p'])
    archivos = []
    for modo, fn in [('viejo', encuadre_anterior), ('nuevo', nuevo_fn)]:
        monkeypatch.setattr(c, '_encuadre', fn)
        path = str(tmp_path / (modo + '.mp4'))
        r.ejecutar(c.compilar(doc, rutas, con_ass=False), path)
        archivos.append(path)
    valores = []
    for tiempo in (100, 400, 500, 700):
        a, b = [_cuadro(path, tiempo, tmp_path, f'{i}_{tiempo}') for i, path in enumerate(archivos)]
        mae = sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3
        valores.append(mae)
        # 0.5/255 por canal: admite pequeñas diferencias de redondeo del
        # interpolador; la prueba de sensibilidad rechaza mover 2 px el cuadro.
        assert mae < 0.5, (nombre, tiempo, mae)
    print(f'{nombre}: MAE RGB por cuadro = ' + ', '.join(f'{v:.6f}' for v in valores))
    # El centro y límites visibles conservan EXACTAMENTE la cuadrícula que
    # encuadre.caja comparte con JS; no se regeneran sus fixtures.
    k = encuadre.caja(w, h, 360, 640, enc)
    v = c._ventana_visible(w, h, k, 360, 640)
    assert v['px'] == k['px'] + v['x'] * k['sw'] // w
    assert v['py'] == k['py'] + v['y'] * k['sh'] // h


@pytest.mark.slow
def test_umbral_no_permite_un_corrimiento_de_dos_pixeles(tmp_path, medios):
    cl = {'id': 'v', 'ancho_px': 640, 'alto_px': 360, 'encuadre': {'zoom': 2.45}}
    filtro = encuadre_anterior('', cl, 0, 360, 640)[0]
    k = encuadre.caja(640, 360, 360, 640, cl['encuadre'])
    desplazado = filtro.rsplit(':', 2)[0] + f":{-k['px'] + 2}:{-k['py']}"
    cuadros = []
    for i, cadena in enumerate((filtro, desplazado)):
        path = str(tmp_path / f'{i}.png')
        cortes.ffmpeg(['-i', medios[0], '-vf', cadena, '-frames:v', '1', path])
        cuadros.append(Image.open(path).convert('RGB'))
    mae = sum(ImageStat.Stat(ImageChops.difference(*cuadros)).mean) / 3
    print(f'Control desplazamiento 2 px: MAE = {mae:.6f}')
    assert mae > 0.5
