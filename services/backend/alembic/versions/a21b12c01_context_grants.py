"""Revision-scoped consent for the local phone assistant; indexed history windows."""
from alembic import op
import sqlalchemy as sa
revision = 'a21b12c01'
down_revision = '7ac921e1d012'
branch_labels = None
depends_on = None

def upgrade():
    from app.models.canonical import DocumentContextGrant
    DocumentContextGrant.__table__.create(bind=op.get_bind(), checkfirst=True)
    indexes = {i['name'] for i in sa.inspect(op.get_bind()).get_indexes('chat_messages')}
    if 'ix_chat_user_time_id' not in indexes:
        op.create_index('ix_chat_user_time_id', 'chat_messages', ['user_id', 'created_at', 'id'])
    if op.get_bind().dialect.name == 'postgresql':
        op.execute("CREATE INDEX IF NOT EXISTS ix_chat_user_text_search ON chat_messages USING gin (to_tsvector('spanish', content)) WHERE role = 'user'")

def downgrade():
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('DROP INDEX IF EXISTS ix_chat_user_text_search')
    op.drop_index('ix_chat_user_time_id', table_name='chat_messages')
    op.drop_table('document_context_grants')
