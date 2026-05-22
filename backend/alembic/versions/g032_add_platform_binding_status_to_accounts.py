"""add platform_binding_status to accounts

Revision ID: g032_add_platform_binding_status
Revises: g031_fix_kol_status
Create Date: 2026-05-22
"""
from __future__ import annotations

from alembic import op


revision = "g032_add_platform_binding_status"
down_revision = "g031_fix_kol_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE accounts
        ADD COLUMN platform_binding_status VARCHAR(30) NOT NULL DEFAULT 'unbound'
        """
    )
    op.execute(
        """
        CREATE INDEX ix_accounts_platform_binding_status
        ON accounts (platform_binding_status)
        """
    )
    op.execute(
        """
        UPDATE accounts
        SET platform_binding_status = CASE
            WHEN EXISTS (
                SELECT 1
                FROM account_channel_reservations acr
                WHERE acr.account_id = accounts.id
                  AND acr.status = 'bound'
            )
            AND NOT EXISTS (
                SELECT 1
                FROM account_channel_reservations acr
                WHERE acr.account_id = accounts.id
                  AND acr.status = 'bound'
                  AND COALESCE(acr.channel_status, 'active') <> 'disabled'
            ) THEN 'disabled'
            WHEN EXISTS (
                SELECT 1
                FROM account_channel_reservations acr
                WHERE acr.account_id = accounts.id
                  AND acr.status = 'bound'
            ) THEN 'bound'
            WHEN EXISTS (
                SELECT 1
                FROM account_channel_reservations acr
                WHERE acr.account_id = accounts.id
                  AND acr.status IN ('confirmed', 'reserved')
            ) THEN 'confirmed'
            ELSE 'unbound'
        END
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_accounts_platform_binding_status")
    op.execute("ALTER TABLE accounts DROP COLUMN platform_binding_status")
