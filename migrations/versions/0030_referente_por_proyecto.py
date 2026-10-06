"""Referentes únicos por proyecto (PND-006, 2026-10-02).

Revision ID: 0030
Revises: 0029

Conserva ids, filas, clasificaciones y barridos. NULL sigue siendo la
biblioteca global, con su propia unicidad. Bajar con anuncios repetidos entre
proyectos se rechaza: decidir qué fila borrar perdería datos de un cliente.
"""
from alembic import op
import sqlalchemy as sa

revision = '0030'
down_revision = '0029'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('referente') as batch:
        batch.drop_constraint('uq_referente_anuncio', type_='unique')
    op.create_index('uq_referente_cliente_anuncio', 'referente', ['cliente', 'anuncio_id'], unique=True,
                    sqlite_where=sa.text('cliente IS NOT NULL'))
    op.create_index('uq_referente_global_anuncio', 'referente', ['anuncio_id'], unique=True,
                    sqlite_where=sa.text('cliente IS NULL'))


def downgrade():
    duplicado = op.get_bind().execute(sa.text(
        'SELECT anuncio_id FROM referente GROUP BY anuncio_id HAVING COUNT(*) > 1 LIMIT 1')).first()
    if duplicado:
        raise RuntimeError('No se puede bajar 0030: hay anuncios duplicados entre proyectos; conservar sus datos.')
    with op.batch_alter_table('referente') as batch:
        batch.drop_index('uq_referente_cliente_anuncio')
        batch.drop_index('uq_referente_global_anuncio')
        batch.create_unique_constraint('uq_referente_anuncio', ['anuncio_id'])
