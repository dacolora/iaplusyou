"""`base_temporal` borra su carpeta al terminar (2026-10-10: 781 296 carpetas `creatv_test_*`, 589 GB, llenaron el
disco porque nunca se borraban)."""
import os

import pytest

import conftest


def test_la_base_temporal_se_borra_al_terminar():
    mp = pytest.MonkeyPatch()
    try:
        abierta = conftest.abrir_base_temporal(mp)
        db = next(abierta)
        carpeta = os.path.dirname(str(db.engine().url.database))
        with db.conectar() as con:                    # escribe algo: deja la base y su -wal en la carpeta
            con.execute(db.kv.insert().values(clave="prueba", valor="1", actualizado_en=db.ahora()))
        assert os.path.basename(carpeta).startswith("creatv_test_") and os.listdir(carpeta)
        with pytest.raises(StopIteration):
            next(abierta)
        assert not os.path.exists(carpeta)
        assert db._ENGINE is None                     # el motor quedó suelto: nada sostiene la base abierta
    finally:
        mp.undo()


def test_tambien_se_borra_si_la_prueba_falla():
    """El `finally` del fixture: una prueba que revienta no deja su carpeta."""
    mp = pytest.MonkeyPatch()
    try:
        abierta = conftest.abrir_base_temporal(mp)
        db = next(abierta)
        carpeta = os.path.dirname(str(db.engine().url.database))
        with pytest.raises(RuntimeError):
            abierta.throw(RuntimeError("la prueba falló"))
        assert not os.path.exists(carpeta)
    finally:
        mp.undo()
