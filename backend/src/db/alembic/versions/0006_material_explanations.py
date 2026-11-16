import sqlalchemy as sa
from alembic import op

revision = '0006_material_explanations'
down_revision = '0005_study_marked_at'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'material_explanations',
        sa.Column('user_id', sa.UUID(), sa.ForeignKey('mvp.users.id', ondelete='RESTRICT'), primary_key=True),
        sa.Column('material_id', sa.UUID(), sa.ForeignKey('mvp.materials.id', ondelete='RESTRICT'), primary_key=True),
        sa.Column('explanation', sa.Text()),
        sa.Column('offer_text', sa.Text()),
        sa.Column('profile_hash', sa.Text()),
        sa.Column('context_hash', sa.Text()),
        sa.Column('source_version', sa.Text()),
        sa.Column('generated_at', sa.DateTime(timezone=True)),
        sa.Column('attempted_at', sa.DateTime(timezone=True)),
        sa.Column('lease_id', sa.UUID()),
        sa.Column('lease_until', sa.DateTime(timezone=True)),
        schema='mvp',
    )


def downgrade():
    op.drop_table('material_explanations', schema='mvp')
