"""Add document provenance and import batch receipts."""
from alembic import op
import sqlalchemy as sa

revision = '7ac921e1d012'
down_revision = '3fd00033dd87'
branch_labels = None
depends_on = None


def upgrade():
    # The legacy startup uses create_all; tolerate tables already created there.
    if op.get_bind().dialect.name == 'postgresql':
        op.alter_column('document_revisions', 'mime_type', type_=sa.String(255), existing_type=sa.String(64))
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if 'import_batches' not in existing:
        op.create_table('import_batches',
            sa.Column('id',sa.String(64),primary_key=True),
            sa.Column('user_id',sa.String(64),nullable=False),
            sa.Column('source_collection',sa.String(128),nullable=False),
            sa.Column('manifest_sha256',sa.String(64),nullable=False),
            sa.Column('status',sa.String(32),nullable=False),
            sa.Column('report_json',sa.JSON()),
            sa.Column('created_at',sa.DateTime()),
            sa.Column('completed_at',sa.DateTime()))
        op.create_index('ix_import_batches_user_id','import_batches',['user_id'])
    if 'document_origins' not in existing:
        op.create_table('document_origins',
            sa.Column('document_id',sa.String(64),sa.ForeignKey('documents.id'),primary_key=True),
            sa.Column('source_collection',sa.String(128),nullable=False),
            sa.Column('source_path',sa.Text(),nullable=False),
            sa.Column('privacy_class',sa.String(32),nullable=False),
            sa.Column('source_kind',sa.String(32),nullable=False),
            sa.Column('source_date',sa.String(64)),
            sa.Column('metadata_json',sa.JSON()),
            sa.Column('batch_id',sa.String(64),sa.ForeignKey('import_batches.id')),
            sa.Column('created_at',sa.DateTime()))
        op.create_index('ix_document_origins_source_collection','document_origins',['source_collection'])


def downgrade():
    op.drop_table('document_origins')
    op.drop_table('import_batches')
