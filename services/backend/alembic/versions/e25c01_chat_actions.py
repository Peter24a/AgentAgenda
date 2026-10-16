"""Device-scoped clarifications and optional recurring proposal metadata."""
from alembic import op

revision = "e25c01"
down_revision = "d24c01"
branch_labels = None
depends_on = None


def upgrade():
    from app.models.canonical import ChatPendingAction, ProposalContext
    ChatPendingAction.__table__.create(bind=op.get_bind(), checkfirst=True)
    ProposalContext.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade():
    op.drop_table("proposal_contexts")
    op.drop_table("chat_pending_actions")
