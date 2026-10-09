"""Owner feedback for assistant responses."""
from alembic import op

revision = "d24c01"
down_revision = "c23c01"
branch_labels = None
depends_on = None


def upgrade():
    from app.models.canonical import ChatResponseReport
    ChatResponseReport.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade():
    op.drop_table("chat_response_reports")
