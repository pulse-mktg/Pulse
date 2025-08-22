"""
Management command to fix disconnected Google Ads platform connections
This helps resolve issues where connections were marked as disconnected but should be active
"""
import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from website.models import PlatformConnection, ClientPlatformAccount

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Fix disconnected Google Ads platform connections by reactivating them'

    def add_arguments(self, parser):
        parser.add_argument(
            '--tenant-id',
            type=int,
            help='Fix connections for specific tenant only'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without actually updating connections'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Skip confirmation prompts'
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🔧 Starting Google Ads connection repair...')
        )
        
        tenant_id = options['tenant_id']
        dry_run = options['dry_run']
        force = options['force']
        
        # Find disconnected Google Ads connections
        filters = {
            'platform_type__slug': 'google-ads',
            'connection_status': 'disconnected',
            'is_active': False
        }
        
        if tenant_id:
            filters['tenant_id'] = tenant_id
            
        disconnected_connections = PlatformConnection.objects.filter(**filters)
        
        if not disconnected_connections.exists():
            self.stdout.write(
                self.style.SUCCESS('✅ No disconnected Google Ads connections found')
            )
            return
            
        self.stdout.write(f'Found {disconnected_connections.count()} disconnected Google Ads connections:')
        
        # Display what will be fixed
        for conn in disconnected_connections:
            self.stdout.write(f'  - {conn.platform_account_email} (Tenant: {conn.tenant.name})')
            
            # Check if this connection has client accounts linked to it
            client_accounts = ClientPlatformAccount.objects.filter(
                platform_connection=conn,
                is_active=True
            )
            
            if client_accounts.exists():
                self.stdout.write(f'    📋 Linked to {client_accounts.count()} client accounts:')
                for ca in client_accounts:
                    self.stdout.write(f'      • {ca.client.name} ({ca.platform_client_name})')
            else:
                self.stdout.write('    📋 No active client accounts linked')
        
        # Ask for confirmation unless forced or dry run
        if not dry_run and not force:
            confirmation = input('\\nReactivate these connections? (y/N): ')
            if confirmation.lower() != 'y':
                self.stdout.write(self.style.WARNING('Operation cancelled'))
                return
        
        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN - No connections will be updated'))
            return
            
        # Reactivate connections
        updated_count = 0
        for conn in disconnected_connections:
            try:
                # Check if the connection has valid tokens
                has_tokens = bool(conn.access_token and conn.refresh_token)
                
                if not has_tokens:
                    self.stdout.write(
                        self.style.WARNING(f'⚠️  Skipping {conn.platform_account_email} - missing tokens')
                    )
                    continue
                
                # Reactivate the connection
                conn.is_active = True
                conn.connection_status = 'active'
                conn.status_message = 'Reactivated by fix_disconnected_connections command'
                conn.last_synced = timezone.now()
                conn.save()
                
                updated_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'✅ Reactivated: {conn.platform_account_email}')
                )
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Failed to reactivate {conn.platform_account_email}: {str(e)}')
                )
        
        # Summary
        self.stdout.write(
            self.style.SUCCESS(f'\\n🎉 Successfully reactivated {updated_count} connections')
        )
        
        if updated_count > 0:
            self.stdout.write('\\n💡 Next steps:')
            self.stdout.write('   1. Try running the bulk Google Ads refresh again')
            self.stdout.write('   2. Check that your client accounts are now syncing properly')
            self.stdout.write('   3. If tokens are still expired, you may need to refresh them manually')