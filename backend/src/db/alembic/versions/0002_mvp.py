import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0002_mvp'
down_revision = '0001_public'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'generation_runs',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('model_name', sa.Text(), nullable=False),
        sa.Column('model_revision', sa.Text(), nullable=False),
        sa.Column('prompt_version', sa.Text(), nullable=False),
        sa.Column('generation_parameters', postgresql.JSONB(), nullable=False),
        sa.Column('input_snapshot', postgresql.JSONB(), nullable=False),
        sa.Column('input_hash', sa.Text(), nullable=False),
        sa.Column('output_json', postgresql.JSONB(), nullable=True),
        sa.Column('status', sa.Text(), server_default=sa.text("'pending'"), nullable=False),
        sa.Column('validation_errors', postgresql.JSONB(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'succeeded', 'failed', 'fallback')", name='generation_runs_status_check'),
        sa.CheckConstraint("status NOT IN ('succeeded', 'fallback') OR output_json IS NOT NULL", name='generation_result_required'),
        sa.CheckConstraint('latency_ms >= 0', name='generation_runs_latency_ms_check'),
        sa.PrimaryKeyConstraint('id'),
        schema='mvp',
    )
    op.create_index('ix_generation_runs_created_at', 'generation_runs', ['created_at'], unique=False, schema='mvp')
    op.create_index('ix_generation_runs_input_hash_created_at', 'generation_runs', ['input_hash', 'created_at'], unique=False, schema='mvp')
    op.create_table(
        'users',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('email', sa.Text(), nullable=False),
        sa.Column('password_hash', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
        schema='mvp',
    )
    op.create_index('uq_users_email_lower', 'users', [sa.literal_column('lower(email)')], unique=True, schema='mvp')
    op.create_table(
        'discount_grants',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('granted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('redeemed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('discount_percent', sa.Integer(), nullable=True),
        sa.Column('discount_amount_minor', sa.Integer(), nullable=True),
        sa.CheckConstraint('(discount_percent IS NOT NULL AND discount_percent > 0 AND discount_percent <= 100 AND discount_amount_minor IS NULL) OR (discount_percent IS NULL AND discount_amount_minor IS NOT NULL AND discount_amount_minor > 0)', name='discount_one_valid_amount'),
        sa.ForeignKeyConstraint(['user_id'], ['mvp.users.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        schema='mvp',
    )
    op.create_index('uq_discount_grants_onboarding', 'discount_grants', ['user_id'], unique=True, schema='mvp', postgresql_where=sa.text("reason = 'onboarding'"))
    op.create_table(
        'email_preferences',
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('marketing_consent', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('consent_updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('consent_version', sa.Text(), nullable=True),
        sa.Column('unsubscribed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('max_emails_per_week', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['mvp.users.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('user_id'),
        schema='mvp',
    )
    op.create_table(
        'favorite_folders',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('is_default', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['mvp.users.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        schema='mvp',
    )
    op.create_index('ix_favorite_folders_user_id', 'favorite_folders', ['user_id'], unique=False, schema='mvp')
    op.create_index('uq_favorite_folders_default', 'favorite_folders', ['user_id'], unique=True, schema='mvp', postgresql_where=sa.text('is_default = true'))
    op.create_table(
        'onboarding_responses',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('answers', postgresql.JSONB(), nullable=False),
        sa.Column('form_type', sa.Text(), nullable=False),
        sa.Column('questionnaire_version', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('submitted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("(status = 'completed' AND completed_at IS NOT NULL) OR (status <> 'completed' AND completed_at IS NULL)", name='onboarding_completion_state'),
        sa.CheckConstraint("form_type IN ('simple', 'advanced')", name='onboarding_responses_form_type_check'),
        sa.CheckConstraint("status IN ('partial', 'completed', 'skipped')", name='onboarding_responses_status_check'),
        sa.CheckConstraint('submitted_at >= created_at', name='onboarding_time_order'),
        sa.ForeignKeyConstraint(['user_id'], ['mvp.users.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        schema='mvp',
    )
    op.create_index('ix_onboarding_responses_user_id_submitted_at', 'onboarding_responses', ['user_id', 'submitted_at'], unique=False, schema='mvp')
    op.create_table(
        'subscription_access',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('subscription_id', sa.UUID(), nullable=False),
        sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('valid_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('source', sa.Text(), nullable=False),
        sa.Column('source_reference', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['subscription_id'], ['public.Subscription.Id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['user_id'], ['mvp.users.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        schema='mvp',
    )
    op.create_index('ix_subscription_access_user_id_subscription_id', 'subscription_access', ['user_id', 'subscription_id'], unique=False, schema='mvp')
    op.create_table(
        'materials',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('source_table', sa.Text(), nullable=False),
        sa.Column('source_id', sa.UUID(), nullable=False),
        sa.Column('kind', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('public_description', sa.Text(), nullable=True),
        sa.Column('url', sa.Text(), nullable=True),
        sa.Column('duration_minutes', sa.Integer(), nullable=True),
        sa.Column('access_type', sa.Text(), server_default=sa.text("'unknown'"), nullable=False),
        sa.Column('is_recommendable', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('source_version', sa.Text(), nullable=False),
        sa.Column('synced_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('verified_course_id', sa.UUID(), nullable=True),
        sa.Column('learning_role', sa.Text(), nullable=True),
        sa.Column('difficulty_level', sa.Text(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('metadata_schema_version', sa.Text(), nullable=True),
        sa.Column('annotation_source', sa.Text(), nullable=True),
        sa.Column('annotation_version', sa.Text(), nullable=True),
        sa.Column('metadata_reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("(source_table = 'Courses' AND kind = 'course' AND verified_course_id IS NOT NULL AND source_id = verified_course_id) OR (source_table = 'Articles' AND kind = 'article' AND verified_course_id IS NULL) OR (source_table = 'Documents' AND kind = 'document' AND verified_course_id IS NULL)", name='material_source_matches_kind'),
        sa.CheckConstraint("access_type IN ('free', 'paid', 'unknown')", name='materials_access_type_check'),
        sa.CheckConstraint("annotation_source IN ('import', 'manual', 'model')", name='materials_annotation_source_check'),
        sa.CheckConstraint("difficulty_level IN ('beginner', 'intermediate', 'advanced')", name='materials_difficulty_level_check'),
        sa.CheckConstraint("kind IN ('course', 'article', 'document')", name='materials_kind_check'),
        sa.CheckConstraint("learning_role IN ('intro', 'practice', 'advanced')", name='materials_learning_role_check'),
        sa.CheckConstraint("source_table IN ('Courses', 'Articles', 'Documents')", name='materials_source_table_check'),
        sa.CheckConstraint('(metadata IS NULL OR metadata_schema_version IS NOT NULL) AND ((metadata IS NULL AND learning_role IS NULL AND difficulty_level IS NULL) OR (annotation_source IS NOT NULL AND annotation_version IS NOT NULL))', name='material_annotation_provenance'),
        sa.CheckConstraint('duration_minutes > 0', name='materials_duration_minutes_check'),
        sa.ForeignKeyConstraint(['verified_course_id'], ['public.Courses.Id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_table', 'source_id', name='ix_materials_source_table_source_id'),
        schema='mvp',
    )
    op.create_index('ix_materials_kind_is_recommendable', 'materials', ['kind', 'is_recommendable'], unique=False, schema='mvp')
    op.create_index('ix_materials_verified_course_id', 'materials', ['verified_course_id'], unique=False, schema='mvp')
    op.create_table(
        'purchases',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('course_id', sa.UUID(), nullable=True),
        sa.Column('subscription_tariff_id', sa.UUID(), nullable=True),
        sa.Column('amount_minor', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('(course_id IS NOT NULL) <> (subscription_tariff_id IS NOT NULL)', name='purchase_one_target'),
        sa.CheckConstraint('amount_minor >= 0', name='purchases_amount_minor_check'),
        sa.ForeignKeyConstraint(['course_id'], ['public.Courses.Id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['subscription_tariff_id'], ['public.SubscriptionTariffs.Id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['user_id'], ['mvp.users.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        schema='mvp',
    )
    op.create_table(
        'recommendation_lists',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('onboarding_response_id', sa.UUID(), nullable=True),
        sa.Column('list_type', sa.Text(), server_default=sa.text("'feed'"), nullable=False),
        sa.Column('mode', sa.Text(), nullable=False),
        sa.Column('recommendation_format', sa.Text(), nullable=True),
        sa.Column('context_snapshot', postgresql.JSONB(), nullable=False),
        sa.Column('ranking_version', sa.Text(), nullable=False),
        sa.Column('ranking_config', postgresql.JSONB(), nullable=False),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('saved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('generation_run_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("(mode = 'popular' AND list_type = 'feed' AND recommendation_format IS NULL) OR (mode = 'personalized' AND ((list_type = 'feed' AND recommendation_format IN ('quick', 'medium')) OR (list_type = 'trajectory' AND recommendation_format = 'deep')) AND recommendation_format IS NOT NULL)", name='recommendation_mode_format'),
        sa.CheckConstraint("list_type IN ('feed', 'trajectory')", name='recommendation_lists_list_type_check'),
        sa.CheckConstraint("mode IN ('popular', 'personalized')", name='recommendation_lists_mode_check'),
        sa.CheckConstraint("recommendation_format IN ('quick', 'medium', 'deep')", name='recommendation_lists_recommendation_format_check'),
        sa.ForeignKeyConstraint(['generation_run_id'], ['mvp.generation_runs.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['onboarding_response_id'], ['mvp.onboarding_responses.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['user_id'], ['mvp.users.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        schema='mvp',
    )
    op.create_index('ix_recommendation_lists_user_id_created_at', 'recommendation_lists', ['user_id', 'created_at'], unique=False, schema='mvp')
    op.create_table(
        'user_profiles',
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('stage_code', sa.Text(), nullable=True),
        sa.Column('industry_code', sa.Text(), nullable=True),
        sa.Column('goal_code', sa.Text(), nullable=True),
        sa.Column('learning_mode', sa.Text(), nullable=True),
        sa.Column('profile_config_version', sa.Text(), nullable=False),
        sa.Column('source_onboarding_response_id', sa.UUID(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("learning_mode IN ('quick', 'practical', 'trajectory')", name='user_profiles_learning_mode_check'),
        sa.ForeignKeyConstraint(['source_onboarding_response_id'], ['mvp.onboarding_responses.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['user_id'], ['mvp.users.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('user_id'),
        schema='mvp',
    )
    op.create_table(
        'email_messages',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('list_id', sa.UUID(), nullable=True),
        sa.Column('kind', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('provider_message_id', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['list_id'], ['mvp.recommendation_lists.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['user_id'], ['mvp.users.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        schema='mvp',
    )
    op.create_index('ix_email_messages_user_id_sent_at', 'email_messages', ['user_id', 'sent_at'], unique=False, schema='mvp')
    op.create_table(
        'favorites',
        sa.Column('folder_id', sa.UUID(), nullable=False),
        sa.Column('material_id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['folder_id'], ['mvp.favorite_folders.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['material_id'], ['mvp.materials.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('folder_id', 'material_id'),
        schema='mvp',
    )
    op.create_index('ix_favorites_material_id', 'favorites', ['material_id'], unique=False, schema='mvp')
    op.create_table(
        'recommendation_items',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('list_id', sa.UUID(), nullable=False),
        sa.Column('material_id', sa.UUID(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('explanation', sa.Text(), nullable=True),
        sa.Column('offer_text', sa.Text(), nullable=True),
        sa.Column('selection_kind', sa.Text(), nullable=False),
        sa.Column('score', sa.Float(), nullable=True),
        sa.Column('step_role', sa.Text(), nullable=True),
        sa.Column('transition_text', sa.Text(), nullable=True),
        sa.Column('generation_run_id', sa.UUID(), nullable=True),
        sa.CheckConstraint("selection_kind IN ('relevance', 'exploration', 'fallback')", name='recommendation_items_selection_kind_check'),
        sa.CheckConstraint("step_role IN ('intro', 'practice', 'advanced')", name='recommendation_items_step_role_check'),
        sa.CheckConstraint('position > 0', name='recommendation_items_position_check'),
        sa.ForeignKeyConstraint(['generation_run_id'], ['mvp.generation_runs.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['list_id'], ['mvp.recommendation_lists.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['material_id'], ['mvp.materials.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('list_id', 'material_id', name='ix_recommendation_items_list_id_material_id'),
        sa.UniqueConstraint('list_id', 'position', name='ix_recommendation_items_list_id_position'),
        schema='mvp',
    )
    op.create_index('ix_recommendation_items_material_id', 'recommendation_items', ['material_id'], unique=False, schema='mvp')


def downgrade():
    op.drop_table('recommendation_items', schema='mvp')
    op.drop_table('favorites', schema='mvp')
    op.drop_table('email_messages', schema='mvp')
    op.drop_table('user_profiles', schema='mvp')
    op.drop_table('recommendation_lists', schema='mvp')
    op.drop_table('purchases', schema='mvp')
    op.drop_table('materials', schema='mvp')
    op.drop_table('subscription_access', schema='mvp')
    op.drop_table('onboarding_responses', schema='mvp')
    op.drop_table('favorite_folders', schema='mvp')
    op.drop_table('email_preferences', schema='mvp')
    op.drop_table('discount_grants', schema='mvp')
    op.drop_table('users', schema='mvp')
    op.drop_table('generation_runs', schema='mvp')
