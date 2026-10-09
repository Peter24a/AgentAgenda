"""Durable encrypted enrollment receipts."""
from alembic import op
revision = 'c23c01'
down_revision = 'b22c01'
branch_labels = None
depends_on = None

def upgrade():
    from app.models.canonical import EnrollmentReceipt
    EnrollmentReceipt.__table__.create(bind=op.get_bind(), checkfirst=True)

def downgrade():
    op.drop_table('enrollment_receipts')
