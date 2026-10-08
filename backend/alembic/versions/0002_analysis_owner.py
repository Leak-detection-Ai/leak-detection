from alembic import op
import sqlalchemy as sa

revision = "0002_analysis_owner"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("analysis_results", sa.Column("user_id", sa.String(36), nullable=True))
    op.create_index("ix_analysis_results_user_id", "analysis_results", ["user_id"])
    op.create_foreign_key(
        "fk_analysis_results_user_id",
        "analysis_results", "users", ["user_id"], ["id"], ondelete="CASCADE"
    )
    op.execute(
        "UPDATE analysis_results ar SET user_id = i.user_id "
        "FROM incidents i WHERE i.analysis_id = ar.id AND ar.user_id IS NULL"
    )

def downgrade():
    op.drop_constraint("fk_analysis_results_user_id", "analysis_results", type_="foreignkey")
    op.drop_index("ix_analysis_results_user_id", table_name="analysis_results")
    op.drop_column("analysis_results", "user_id")
