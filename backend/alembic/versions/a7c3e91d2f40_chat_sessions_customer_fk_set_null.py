"""chat_sessions customer FKs ON DELETE SET NULL

Week 4 (admin can delete a customer): a chat session that was linked to a deleted customer keeps its transcript
(Section 4.6) but loses the link. A verified session without customer_id fails closed — require_verified refuses
lookup_shipments — and is never moved to another customer.

Revision ID: a7c3e91d2f40
Revises: 357af0a384f5
Create Date: 2026-10-04 12:00:00.000000

"""
from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a7c3e91d2f40'
down_revision: str | None = '357af0a384f5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FKS = (
    ("chat_sessions_customer_id_fkey", "customer_id"),
    ("chat_sessions_pending_customer_id_fkey", "pending_customer_id"),
)


def upgrade() -> None:
    for name, column in _FKS:
        op.drop_constraint(name, "chat_sessions", type_="foreignkey")
        op.create_foreign_key(name, "chat_sessions", "customers", [column], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    for name, column in _FKS:
        op.drop_constraint(name, "chat_sessions", type_="foreignkey")
        op.create_foreign_key(name, "chat_sessions", "customers", [column], ["id"])
