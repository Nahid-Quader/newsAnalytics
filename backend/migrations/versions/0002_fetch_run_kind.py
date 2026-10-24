"""fetch_runs.kind and target_date (distinguish feed runs from backfill runs)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("fetch_runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("kind", sa.String(length=16), server_default="feed", nullable=False))
        batch_op.add_column(sa.Column("target_date", sa.String(length=10), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("fetch_runs", schema=None) as batch_op:
        batch_op.drop_column("target_date")
        batch_op.drop_column("kind")
