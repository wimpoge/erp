"""usernames for login

Revision ID: b421eeacfe30
Revises: 3c5f24b4252b
Create Date: 2026-10-03 09:42:12.991183

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b421eeacfe30'
down_revision: Union[str, Sequence[str], None] = '3c5f24b4252b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("user_account") as batch:
        batch.add_column(sa.Column("username", sa.String(length=40), nullable=True))

    # Existing users get the part of their email before the @, made unique with the user id if needed.
    conn = op.get_bind()
    taken: set[str] = set()
    for user_id, email in conn.execute(sa.text("SELECT id, email FROM user_account ORDER BY id")).all():
        base = email.split("@")[0].lower()[:30]
        name = base if base not in taken else f"{base}{user_id}"
        taken.add(name)
        conn.execute(sa.text("UPDATE user_account SET username = :u WHERE id = :id"), {"u": name, "id": user_id})

    with op.batch_alter_table("user_account") as batch:
        batch.alter_column("username", existing_type=sa.String(length=40), nullable=False)
        batch.create_unique_constraint("uq_user_account_username", ["username"])


def downgrade() -> None:
    with op.batch_alter_table("user_account") as batch:
        batch.drop_constraint("uq_user_account_username", type_="unique")
        batch.drop_column("username")
