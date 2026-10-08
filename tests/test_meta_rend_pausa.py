"""La pausa compartida de las copias de Meta (ruling R22): un solo escritor, solo se alarga y vence sola."""
from datetime import datetime, timedelta

import db
from meta_rendimiento import pausa

AHORA = datetime(2026, 10, 8, 12, 0, 0)


def test_sin_pausa_no_esta_activa(base_temporal):
    assert pausa.pausada_hasta(AHORA) is None and pausa.activa(AHORA) is False


def test_pausar_pone_al_menos_30_minutos_y_vence_sola(base_temporal):
    hasta = pausa.pausar(5, ahora=AHORA)                       # menos de 30: se sube a 30
    assert hasta == "2026-10-08T12:30:00"
    assert pausa.activa(AHORA + timedelta(minutes=29)) and pausa.pausada_hasta(AHORA) == hasta
    assert not pausa.activa(AHORA + timedelta(minutes=30, seconds=1))
    assert pausa.pausada_hasta(AHORA + timedelta(hours=1)) is None


def test_pausar_usa_la_espera_de_meta_si_es_mayor_y_acepta_basura(base_temporal):
    assert pausa.pausar(45, ahora=AHORA) == "2026-10-08T12:45:00"
    assert pausa.pausar(None, ahora=AHORA) == "2026-10-08T12:45:00"      # None = 30, y no acorta la que ya hay
    assert pausa.pausar("x", ahora=AHORA) == "2026-10-08T12:45:00"


def test_la_pausa_solo_se_alarga_nunca_se_acorta(base_temporal):
    pausa.pausar(120, ahora=AHORA)
    assert pausa.pausar(30, ahora=AHORA) == "2026-10-08T14:00:00"
    assert pausa.pausar(180, ahora=AHORA) == "2026-10-08T15:00:00"


def test_un_valor_ilegible_en_la_base_es_sin_pausa(base_temporal):
    import sqlalchemy as sa
    with db.conectar() as con:
        con.execute(sa.insert(db.kv).values(clave=pausa.CLAVE, valor="no es una fecha", actualizado_en=db.ahora()))
    assert pausa.pausada_hasta(AHORA) is None and not pausa.activa(AHORA)
    assert pausa.pausar(30, ahora=AHORA) == "2026-10-08T12:30:00"
