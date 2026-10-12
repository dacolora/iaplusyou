from datetime import datetime, timedelta
import sqlalchemy as sa


def test_pnd177_guion_con_extra_json_null(base_temporal, monkeypatch):
    import creative_flow as cf
    db = base_temporal
    cid = cf.crear('acme', [], [], [], 'acción', 8, '', 'A')
    with db.conectar() as con:
        con.execute(db.concepto.update().where(db.concepto.c.legado_id == cid).values(extra=sa.JSON.NULL))
    monkeypatch.setattr(db, 'ahora', lambda: '2026-10-09T12:00:00')
    assert cf.guardar_guion_base('acme', cid, {'bloques': []})
    with db.conectar() as con:
        extra = con.execute(sa.select(db.concepto.c.extra).where(db.concepto.c.legado_id == cid)).scalar()
    assert extra == {'guion_modificado_en': '2026-10-09T12:00:00'}


def test_pnd178_reservas_solo_muertas_de_mas_de_diez_minutos(base_temporal, monkeypatch):
    from cobros import libro
    import cola
    db = base_temporal
    ahora = datetime(2026, 10, 9, 12)
    monkeypatch.setattr(db, 'ahora', lambda: ahora.isoformat(timespec='seconds'))
    with db.conectar() as con:
        for job, minutos in [('reciente', 0), ('limite', 10), ('vieja', 11), ('viva', 11)]:
            con.execute(db.reserva_saldo.insert().values(cliente='acme', job_id=job, milesimas=100,
                        creada_en=(ahora-timedelta(minutes=minutos)).isoformat(timespec='seconds')))
    cola.encolar('prueba', {}, cliente='acme', job_id='viva')
    assert libro.limpiar_reservas_muertas() == 1
    with db.conectar() as con:
        quedan = set(con.execute(sa.select(db.reserva_saldo.c.job_id)).scalars())
    assert quedan == {'reciente', 'limite', 'viva'}
