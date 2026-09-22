"""sprints: agregar campo funnel (TOF/MOF/BOF) a campana

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-21 00:00:00.000000

Agrega soporte para TOF (Top of Funnel), MOF (Middle of Funnel), BOF (Bottom of Funnel)
en las campañas del sprint.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0014'
down_revision: Union[str, Sequence[str], None] = '0013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('campana', sa.Column('funnel', sa.String(length=3), server_default='tof'))


def downgrade() -> None:
    op.drop_column('campana', 'funnel')
