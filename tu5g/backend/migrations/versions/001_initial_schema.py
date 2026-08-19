"""initial_schema

Revision ID: 001
Revises: 
Create Date: 2026-08-10 02:38:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Enable pgcrypto extension for UUID generation
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    # 2. Users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('phone_number', sa.String(), nullable=True),
        sa.Column('hashed_password', sa.String(), nullable=False),
        sa.Column('full_name', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=False, server_default='customer'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('kyc_status', sa.String(), nullable=False, server_default='not_submitted'),
        sa.Column('email_verified', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('phone_verified', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_index('ix_users_phone_number', 'users', ['phone_number'], unique=True)
    op.create_index('ix_users_created_date', 'users', ['created_date'])

    # 3. Customers table
    op.create_table(
        'customers',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('sim_number', sa.String(), nullable=False),
        sa.Column('iccid', sa.String(), nullable=False),
        sa.Column('country_code', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='inactive'),
        sa.Column('data_plan', sa.String(), nullable=False),
        sa.Column('phone_number', sa.String(), nullable=True),
        sa.Column('created_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_customers_iccid', 'customers', ['iccid'], unique=True)
    op.create_index('ix_customers_status', 'customers', ['status'])
    op.create_index('ix_customers_phone_number', 'customers', ['phone_number'])
    op.create_index('ix_customers_created_date', 'customers', ['created_date'])

    # 4. Virtual Cells table
    op.create_table(
        'virtual_cells',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('cell_id', sa.String(), nullable=False),
        sa.Column('mcc', sa.Integer(), nullable=False),
        sa.Column('mnc', sa.Integer(), nullable=False),
        sa.Column('rsrp', sa.Integer(), nullable=False),
        sa.Column('rtt', sa.Integer(), nullable=False),
        sa.Column('users', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_virtual_cells_cell_id', 'virtual_cells', ['cell_id'], unique=True)
    op.create_index('ix_virtual_cells_created_date', 'virtual_cells', ['created_date'])

    # 5. Holographic Sessions table
    op.create_table(
        'holographic_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('session_name', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='inactive'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_holographic_sessions_user_id', 'holographic_sessions', ['user_id'])
    op.create_index('ix_holographic_sessions_status', 'holographic_sessions', ['status'])

    # 6. Chat Messages table
    op.create_table(
        'chat_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_chat_messages_user_id', 'chat_messages', ['user_id'])
    op.create_index('ix_chat_messages_created_date', 'chat_messages', ['created_date'])

    # 7. Telemetry Records table
    op.create_table(
        'telemetry_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('cell_id', sa.String(), sa.ForeignKey('virtual_cells.cell_id', ondelete='CASCADE'), nullable=False),
        sa.Column('rsrp', sa.Integer(), nullable=False),
        sa.Column('rtt', sa.Integer(), nullable=False),
        sa.Column('users', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_telemetry_records_cell_id', 'telemetry_records', ['cell_id'])
    op.create_index('ix_telemetry_records_timestamp', 'telemetry_records', ['timestamp'])

    # 8. KYC Records table
    op.create_table(
        'kyc_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('full_name', sa.String(), nullable=False),
        sa.Column('id_type', sa.String(), nullable=False),
        sa.Column('id_number', sa.String(), nullable=False),
        sa.Column('address', sa.Text(), nullable=False),
        sa.Column('document_urls', sa.Text(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('admin_notes', sa.Text(), nullable=True, server_default=''),
        sa.Column('notes', sa.Text(), nullable=True, server_default=''),
        sa.Column('admin_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_kyc_records_user_id', 'kyc_records', ['user_id'])
    op.create_index('ix_kyc_records_status', 'kyc_records', ['status'])
    op.create_index('ix_kyc_records_created_date', 'kyc_records', ['created_date'])

    # 9. OTP Records table
    op.create_table(
        'otp_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('identifier', sa.String(), nullable=False),
        sa.Column('otp_code', sa.String(), nullable=False),
        sa.Column('otp_type', sa.String(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_otp_records_identifier', 'otp_records', ['identifier'])
    op.create_index('ix_otp_records_created_date', 'otp_records', ['created_date'])

    # 10. Payment Transactions table
    op.create_table(
        'payment_transactions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('currency', sa.String(), nullable=False, server_default='USD'),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('vpa_from', sa.String(), nullable=True),
        sa.Column('vpa_to', sa.String(), nullable=True),
        sa.Column('source_vpa', sa.String(), nullable=True),
        sa.Column('recipient_vpa', sa.String(), nullable=True),
        sa.Column('session_id', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('created_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_payment_transactions_user_id', 'payment_transactions', ['user_id'])
    op.create_index('ix_payment_transactions_status', 'payment_transactions', ['status'])
    op.create_index('ix_payment_transactions_created_date', 'payment_transactions', ['created_date'])

    # 11. Wallets table
    op.create_table(
        'wallets',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('balance', sa.Float(), nullable=False, server_default=sa.text('0.0')),
        sa.Column('currency', sa.String(), nullable=False, server_default='USD'),
        sa.Column('vpa', sa.String(), nullable=True),
        sa.Column('created_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_wallets_user_id', 'wallets', ['user_id'], unique=True)
    op.create_index('ix_wallets_vpa', 'wallets', ['vpa'], unique=True)
    op.create_index('ix_wallets_created_date', 'wallets', ['created_date'])

    # 12. VPAs table
    op.create_table(
        'vpas',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('vpa_address', sa.String(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_vpas_user_id', 'vpas', ['user_id'])
    op.create_index('ix_vpas_vpa_address', 'vpas', ['vpa_address'], unique=True)
    op.create_index('ix_vpas_created_date', 'vpas', ['created_date'])

    # 13. Hmail Accounts table
    op.create_table(
        'hmail_accounts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('username', sa.String(), nullable=False),
        sa.Column('email_address', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_hmail_accounts_user_id', 'hmail_accounts', ['user_id'], unique=True)
    op.create_index('ix_hmail_accounts_username', 'hmail_accounts', ['username'], unique=True)
    op.create_index('ix_hmail_accounts_email_address', 'hmail_accounts', ['email_address'], unique=True)
    op.create_index('ix_hmail_accounts_created_date', 'hmail_accounts', ['created_date'])

    # 14. Hmail Messages table
    op.create_table(
        'hmail_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('account_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('hmail_accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True),
        sa.Column('from_email', sa.String(), nullable=False),
        sa.Column('to_email', sa.String(), nullable=False),
        sa.Column('subject', sa.String(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_hmail_messages_account_id', 'hmail_messages', ['account_id'])
    op.create_index('ix_hmail_messages_user_id', 'hmail_messages', ['user_id'])
    op.create_index('ix_hmail_messages_created_date', 'hmail_messages', ['created_date'])

    # 15. Governance Applications table
    op.create_table(
        'governance_applications',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('organization_name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('proof_url', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('admin_notes', sa.Text(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_governance_applications_user_id', 'governance_applications', ['user_id'])
    op.create_index('ix_governance_applications_status', 'governance_applications', ['status'])
    op.create_index('ix_governance_applications_created_date', 'governance_applications', ['created_date'])

    # 16. ESIM Reservations table
    op.create_table(
        'esim_reservations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('number', sa.String(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_esim_reservations_user_id', 'esim_reservations', ['user_id'])
    op.create_index('ix_esim_reservations_number', 'esim_reservations', ['number'])
    op.create_index('ix_esim_reservations_created_date', 'esim_reservations', ['created_date'])

    # 17. Audit Logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('resource', sa.String(), nullable=False),
        sa.Column('ip_address', sa.String(), nullable=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('created_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_audit_logs_user_id', 'audit_logs', ['user_id'])
    op.create_index('ix_audit_logs_created_date', 'audit_logs', ['created_date'])

    # 18. ESIM Plans table
    op.create_table(
        'esim_plans',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('plan_code', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('price', sa.Float(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_esim_plans_plan_code', 'esim_plans', ['plan_code'], unique=True)
    op.create_index('ix_esim_plans_created_date', 'esim_plans', ['created_date'])

    # 19. Number Categories table
    op.create_table(
        'number_categories',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('code', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('price', sa.Float(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_number_categories_code', 'number_categories', ['code'], unique=True)
    op.create_index('ix_number_categories_created_date', 'number_categories', ['created_date'])


def downgrade() -> None:
    # Drop tables in reverse dependency order
    op.drop_table('number_categories')
    op.drop_table('esim_plans')
    op.drop_table('audit_logs')
    op.drop_table('esim_reservations')
    op.drop_table('governance_applications')
    op.drop_table('hmail_messages')
    op.drop_table('hmail_accounts')
    op.drop_table('vpas')
    op.drop_table('wallets')
    op.drop_table('payment_transactions')
    op.drop_table('otp_records')
    op.drop_table('kyc_records')
    op.drop_table('telemetry_records')
    op.drop_table('chat_messages')
    op.drop_table('holographic_sessions')
    op.drop_table('virtual_cells')
    op.drop_table('customers')
    op.drop_table('users')

    # Optionally drop pgcrypto extension
    op.execute('DROP EXTENSION IF EXISTS "pgcrypto"')
