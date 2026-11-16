import json
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision = '0004_default_offer_text'
down_revision = '0003_material_studies'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('materials', sa.Column('default_offer_text', sa.Text(), nullable=True), schema='mvp')
    # Frozen seed shared with sync: migrations can run before the catalog is imported.
    path = Path(__file__).resolve().parents[3] / 'config' / 'default_offer_texts.v1.json'
    offers = json.loads(path.read_text(encoding='utf-8'))
    materials = sa.table('materials', sa.column('source_table', sa.Text()),
                         sa.column('source_id', sa.UUID()), sa.column('kind', sa.Text()),
                         sa.column('default_offer_text', sa.Text()), schema='mvp')
    for course_id, item in offers.items():
        op.execute(materials.update().where(
            materials.c.source_table == 'Courses', materials.c.kind == 'course',
            materials.c.source_id == UUID(course_id), materials.c.default_offer_text.is_(None),
        ).values(default_offer_text=item['text']))


def downgrade():
    op.drop_column('materials', 'default_offer_text', schema='mvp')
