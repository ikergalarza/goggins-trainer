"""triathlon planning

Añade soporte de triatlón al modelo de datos:
- goals: distancia de triatlón y splits objetivo por disciplina.
- workouts: updated_at y modified_by para rastrear ediciones del usuario.

Los tipos de deporte/entreno se guardan como String, así que los nuevos
valores de enum (sport=triathlon, WorkoutType swim/bike/brick/...) no
requieren cambios de esquema y no rompen registros existentes.

Revision ID: 002
Revises: 001
Create Date: 2026-06-30

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- goals: triatlón ---
    op.add_column("goals", sa.Column("triathlon_distance", sa.String(), nullable=True))
    op.add_column("goals", sa.Column("target_swim_time_seconds", sa.Integer(), nullable=True))
    op.add_column("goals", sa.Column("target_bike_time_seconds", sa.Integer(), nullable=True))
    op.add_column("goals", sa.Column("target_run_time_seconds", sa.Integer(), nullable=True))

    # --- workouts: tracking de ediciones ---
    op.add_column("workouts", sa.Column("modified_by", sa.String(), nullable=True))
    op.add_column(
        "workouts",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("workouts", "updated_at")
    op.drop_column("workouts", "modified_by")

    op.drop_column("goals", "target_run_time_seconds")
    op.drop_column("goals", "target_bike_time_seconds")
    op.drop_column("goals", "target_swim_time_seconds")
    op.drop_column("goals", "triathlon_distance")
