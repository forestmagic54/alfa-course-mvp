import sqlalchemy as sa
from alembic import op

revision = '0005_study_marked_at'
down_revision = '0004_default_offer_text'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user_material_studies', sa.Column('marked_at', sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text('now()')), schema='mvp')


def downgrade():
    op.drop_column('user_material_studies', 'marked_at', schema='mvp')
