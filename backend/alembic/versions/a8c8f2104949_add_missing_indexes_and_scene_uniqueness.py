"""add_missing_indexes_and_scene_uniqueness

Revision ID: a8c8f2104949
Revises: 029
Create Date: 2026-06-10 08:58:40.793482

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a8c8f2104949'
down_revision: Union[str, None] = '029'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create missing indexes for frequently queried columns
    op.create_index(op.f('ix_chat_token_usage_user_id'), 'chat_token_usage', ['user_id'], unique=False)
    op.create_index(op.f('ix_jobs_created_at'), 'jobs', ['created_at'], unique=False)
    op.create_index(op.f('ix_jobs_user_id'), 'jobs', ['user_id'], unique=False)
    op.create_index(op.f('ix_model_configs_model_id'), 'model_configs', ['model_id'], unique=False)
    op.create_index('ix_cost_log_created_at', 'cost_log', ['created_at'], unique=False)
    op.create_index('ix_cost_log_job_id', 'cost_log', ['job_id'], unique=False)
    op.create_index('ix_cost_log_provider_id', 'cost_log', ['provider_id'], unique=False)

    # Data cleanup: resolve duplicate (job_id, scene_number) rows before adding
    # the unique constraint. Keep the row with the lowest id; renumber others
    # to the next available scene_number for that job.
    op.execute(
        sa.text("""
            WITH ranked AS (
                SELECT id, job_id, scene_number,
                       ROW_NUMBER() OVER (PARTITION BY job_id, scene_number ORDER BY id) as dup_rn
                FROM video_scenes
            ),
            dups AS (
                SELECT id, job_id, scene_number,
                       ROW_NUMBER() OVER (PARTITION BY job_id ORDER BY scene_number, id) as seq
                FROM ranked
                WHERE dup_rn > 1
            ),
            job_max AS (
                SELECT job_id, MAX(scene_number) as max_scene
                FROM video_scenes
                GROUP BY job_id
            )
            UPDATE video_scenes
            SET scene_number = jm.max_scene + d.seq
            FROM dups d
            JOIN job_max jm ON d.job_id = jm.job_id
            WHERE video_scenes.id = d.id;
        """)
    )

    # Add unique constraint on VideoScene(job_id, scene_number)
    op.create_unique_constraint('uq_video_scene_job_scene', 'video_scenes', ['job_id', 'scene_number'])


def downgrade() -> None:
    op.drop_constraint('uq_video_scene_job_scene', 'video_scenes', type_='unique')
    op.drop_index('ix_cost_log_provider_id', table_name='cost_log')
    op.drop_index('ix_cost_log_job_id', table_name='cost_log')
    op.drop_index('ix_cost_log_created_at', table_name='cost_log')
    op.drop_index(op.f('ix_model_configs_model_id'), table_name='model_configs')
    op.drop_index(op.f('ix_jobs_user_id'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_created_at'), table_name='jobs')
    op.drop_index(op.f('ix_chat_token_usage_user_id'), table_name='chat_token_usage')
