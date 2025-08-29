"""add credit_transactions table

Revision ID: 20250828_add_credit_transactions
Revises: <PON_AQUI_TU_DOWN_REVISION>
Create Date: 2025-08-28
"""
from alembic import op
import sqlalchemy as sa

revision = '20250828_add_credit_transactions'
down_revision = 'f8894ce70cbf'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'credit_transactions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('price_id', sa.String(length=255), nullable=False),
        sa.Column('credits', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(length=10), nullable=False, server_default='usd'),
        sa.Column('stripe_event_id', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.UniqueConstraint('stripe_event_id', name='uq_credit_tx_stripe_event'),
    )
    op.create_index('ix_credit_tx_user_id', 'credit_transactions', ['user_id'])
    op.create_index('ix_credit_tx_email', 'credit_transactions', ['email'])
    op.create_index('ix_credit_tx_price', 'credit_transactions', ['price_id'])

def downgrade():
    op.drop_table('credit_transactions')
