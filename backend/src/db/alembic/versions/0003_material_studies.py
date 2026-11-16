import sqlalchemy as sa
from alembic import op

revision = '0003_material_studies'
down_revision = '0002_mvp'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'user_material_studies',
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('material_id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['mvp.users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['material_id'], ['mvp.materials.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('user_id', 'material_id'),
        schema='mvp',
    )
    op.create_index('ix_user_material_studies_material_id', 'user_material_studies', ['material_id'], schema='mvp')


def downgrade():
    op.drop_index('ix_user_material_studies_material_id', table_name='user_material_studies', schema='mvp')
    op.drop_table('user_material_studies', schema='mvp')
