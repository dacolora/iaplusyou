"""`base_temporal` borra su carpeta al terminar (2026-10-10: 31 000 carpetas
creatv_test_*, 25 GB en el Mac de Daniel). Los dos tests corren en orden: el
primero guarda la ruta que usó, el segundo comprueba que ya no existe."""
import os

_rutas = []


def test_usa_una_base_temporal(base_temporal):
    ruta = str(base_temporal.engine().url.database)
    carpeta = os.path.dirname(ruta)
    assert os.path.isdir(carpeta)
    _rutas.append(carpeta)


def test_la_carpeta_del_test_anterior_ya_no_existe():
    assert _rutas, "el test anterior debe correr antes (mismo módulo, en orden)"
    assert not os.path.exists(_rutas[0])
