#!/usr/bin/env python3
"""PND-049: comparación LOCAL del RSS de dos clips zoom 2,45 + fundido.

Sin red, base, proveedores ni Docker. Ejecutar en render-vps con Python del
proyecto; también funciona en macOS. Cada camino corre en un hijo aislado:
getrusage(RUSAGE_CHILDREN).ru_maxrss de ese hijo mide el máximo de ffmpeg,
NO la suma ni el máximo acumulado del camino anterior. Mac: bytes; Linux: KiB.
"""
import argparse
import json
from pathlib import Path
import resource
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from final_edition import cortes, documento, encuadre, motor
from final_edition.motor import compilador, tramos


def encuadre_anterior(cabeza, cl, i, ancho, alto):
    """Referencia congelada del compilador anterior al PND-049 (2026-10-08).
    Solo la usan esta medición y las pruebas de paridad; no es un camino vivo.
    """
    enc = cl.get('encuadre')
    if not enc:
        return [f'{cabeza}scale={ancho}:{alto}:force_original_aspect_ratio=increase,crop={ancho}:{alto}']
    k = encuadre.caja(cl['ancho_px'], cl['alto_px'], ancho, alto, enc)
    if encuadre.completo(enc)['modo'] == 'llenar':
        return [f"{cabeza}scale={k['sw']}:{k['sh']},crop={ancho}:{alto}:{-k['px']}:{-k['py']}"]
    fw, fh = encuadre.fondo(ancho, alto)
    return [f'{cabeza}split=2[f{i}a][f{i}b]',
            f'[f{i}a]scale={fw}:{fh}:force_original_aspect_ratio=increase,crop={fw}:{fh},'
            f'boxblur=luma_radius={encuadre.FONDO_RADIO}:luma_power={encuadre.FONDO_PASADAS},'
            f'scale={ancho}:{alto},setsar=1[f{i}c]',
            f"[f{i}b]scale={k['sw']}:{k['sh']},setsar=1[f{i}d]",
            f"[f{i}c][f{i}d]overlay=x={k['px']}:y={k['py']}"]


def documento_prueba(ms=1000):
    doc = documento.nuevo_video('9:16')
    doc['pistas'][0]['clips'] = [
        {'id': f'v{i}', 'inicio_ms': i * ms, 'duracion_ms': ms, 'material_id': i + 1,
         'recorte': {'desde_ms': 0, 'hasta_ms': ms}, 'ancho_px': 1920, 'alto_px': 1080,
         'encuadre': {'modo': 'llenar', 'zoom': 2.45, 'x': 0.5, 'y': 0.5},
         'transicion': {'tipo': 'fundido', 'duracion_ms': 300} if i == 0 else None}
        for i in range(2)]
    return documento.resolver(documento.validar(doc), 'es', 'CO')


def medir_hijo(carpeta, camino, ms):
    original = cortes.ffmpeg
    def un_cpu(args, **kw):
        return original(['-threads', '1', '-filter_complex_threads', '1', *args], **kw)
    cortes.ffmpeg = un_cpu
    if camino == 'viejo':
        compilador._encuadre = encuadre_anterior
    # Fuerza el tramo indivisible que incluye los dos clips y su transición.
    tramos.partir = lambda doc: [(0, documento.duracion_ms(doc))]
    # Los dos inputs decodifican con un hilo, igual en los dos caminos.
    compilar = compilador.compilar
    def plan_un_cpu(*args, **kw):
        plan = compilar(*args, **kw)
        for e in plan.entradas:
            e['opciones'] = ['-threads', '1', *(e.get('opciones') or [])]
        return plan
    compilador.compilar = plan_un_cpu
    fuente = str(Path(carpeta) / 'fuente.mp4')
    resultado = motor.renderizar(documento_prueba(ms), {1: fuente, 2: fuente}, str(Path(carpeta) / (camino + '.mp4')))
    rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    mib = rss / (1024 * 1024) if sys.platform == 'darwin' else rss / 1024
    print(json.dumps({'camino': camino, 'pico_mib': round(mib, 2), 'tramos': resultado['tramos'],
                      'duracion_s': resultado['duracion_s'], 'plataforma': sys.platform}))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--hijo', choices=['viejo', 'nuevo'])
    ap.add_argument('--carpeta')
    ap.add_argument('--duracion-ms', type=int, default=3000)
    opts = ap.parse_args()
    if opts.duracion_ms < 500:
        ap.error('duracion-ms debe ser al menos 500')
    if opts.hijo:
        medir_hijo(opts.carpeta, opts.hijo, opts.duracion_ms)
        return
    with tempfile.TemporaryDirectory(prefix='creatv_memoria_') as carpeta:
        cortes.ffmpeg(['-f', 'lavfi', '-i', 'testsrc2=size=1920x1080:rate=30',
                       '-t', str(opts.duracion_ms / 1000 + 0.4), '-threads', '1',
                       '-pix_fmt', 'yuv420p', str(Path(carpeta) / 'fuente.mp4')])
        resultados = []
        for camino in ('viejo', 'nuevo'):
            proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--hijo', camino,
                                   '--carpeta', carpeta, '--duracion-ms', str(opts.duracion_ms)],
                                  text=True, capture_output=True, check=True)
            print(proc.stdout.strip())
            resultados.append(json.loads(proc.stdout))
        a, b = (r['pico_mib'] for r in resultados)
        print(f'Reducción: {100 * (a - b) / a:.2f}% ({a:.2f} → {b:.2f} MiB)')


if __name__ == '__main__':
    main()
