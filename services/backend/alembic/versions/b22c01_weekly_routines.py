"""Durable rolling weekly routines."""
from alembic import op
revision = 'b22c01'
down_revision = 'a21b12c01'
branch_labels = None
depends_on = None

def upgrade():
    from app.models.canonical import WeeklyRoutine
    WeeklyRoutine.__table__.create(bind=op.get_bind(), checkfirst=True)

def downgrade():
    op.drop_table('weekly_routines')
