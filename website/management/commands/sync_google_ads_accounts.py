import logging
import traceback
from django.core.management.base import BaseCommand
from django.utils import timezone
from website.models import PlatformConnection, PlatformType
from website.models import GoogleAdsAccount, GoogleAdsAccountSync
from website.services.google_ads_account_service import GoogleAdsAccountService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sync Google Ads accounts for all active connections'

    def add_arguments(self, parser):
        parser.add_argument(
            '--connection-id',
            type=int,
            help='Sync specific connection ID only'
        )
        parser.add_argument(
            '--tenant-id',
            type=int,
            help='Sync all connections for specific tenant only'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force sync even if recently synced'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting Google Ads account sync...'))
        
        # Get platform type
        try:
            platform_type = PlatformType.objects.get(slug='google-ads')
        except PlatformType.DoesNotExist:
            self.stdout.write(self.style.ERROR('Google Ads platform type not found'))
            return
        
        # Filter connections based on options
        connections = PlatformConnection.objects.filter(
            platform_type=platform_type,
            is_active=True,
            connection_status='active'
        )
        
        if options['connection_id']:
            connections = connections.filter(id=options['connection_id'])
        
        if options['tenant_id']:
            connections = connections.filter(tenant_id=options['tenant_id'])
        
        if not connections.exists():
            self.stdout.write(self.style.WARNING('No active Google Ads connections found'))
            return
        
        # Process each connection
        total_connections = connections.count()
        successful_syncs = 0
        failed_syncs = 0
        
        for i, connection in enumerate(connections, 1):
            self.stdout.write(f'Processing connection {i}/{total_connections}: {connection}')
            
            try:
                success = self.sync_connection(connection, options['force'])
                if success:
                    successful_syncs += 1
                    self.stdout.write(self.style.SUCCESS(f'  ✓ Synced successfully'))
                else:
                    failed_syncs += 1
                    self.stdout.write(self.style.ERROR(f'  ✗ Sync failed'))
                    
            except Exception as e:
                failed_syncs += 1
                self.stdout.write(self.style.ERROR(f'  ✗ Sync error: {str(e)}'))
                logger.error(f'Error syncing connection {connection.id}: {str(e)}')
        
        # Final summary
        self.stdout.write(self.style.SUCCESS(f'\\nSync completed:'))
        self.stdout.write(f'  - Successful: {successful_syncs}')
        self.stdout.write(f'  - Failed: {failed_syncs}')
        self.stdout.write(f'  - Total: {total_connections}')

    def sync_connection(self, connection, force_sync=False):
        """Sync accounts for a single connection"""
        
        # Check if recently synced (unless forced)
        if not force_sync:
            recent_sync = GoogleAdsAccountSync.objects.filter(
                platform_connection=connection,
                started_at__gte=timezone.now() - timezone.timedelta(hours=1),
                sync_status='completed'
            ).exists()
            
            if recent_sync:
                self.stdout.write(f'  - Skipping (recently synced)')
                return True
        
        # Create sync record
        sync_record = GoogleAdsAccountSync.objects.create(
            platform_connection=connection,
            sync_status='running'
        )
        
        try:
            # Initialize Google Ads account service
            from website.services.google_ads_account_service import GoogleAdsAccountService
            service = GoogleAdsAccountService(connection.tenant)
            
            # Get fresh account list from API with better error handling
            self.stdout.write(f'  - Fetching accounts from Google Ads API (SYNC MODE - bypassing cache)...')
            api_accounts = self._get_accounts_for_sync(service, connection)
            
            if not api_accounts:
                sync_record.mark_failed('No accounts found from API')
                return False
            
            # Check for API errors
            error_accounts = [acc for acc in api_accounts if acc.get('id') == 'ERROR']
            if error_accounts:
                error_msg = error_accounts[0].get('name', 'Unknown API error')
                sync_record.mark_failed(f'API error: {error_msg}')
                return False
            
            sync_record.accounts_discovered = len(api_accounts)
            
            # Process accounts
            accounts_added = 0
            accounts_updated = 0
            accounts_deactivated = 0
            
            # Get existing accounts
            existing_accounts = {
                acc.account_id: acc for acc in 
                GoogleAdsAccount.objects.filter(platform_connection=connection)
            }
            
            # Track which accounts are still active
            active_account_ids = set()
            
            # Process each account from API
            for api_account in api_accounts:
                account_id = api_account.get('id')
                if not account_id or account_id == 'ERROR':
                    continue
                
                active_account_ids.add(account_id)
                
                # Check if account exists
                if account_id in existing_accounts:
                    # Update existing account
                    account = existing_accounts[account_id]
                    updated = self.update_account(account, api_account)
                    if updated:
                        accounts_updated += 1
                else:
                    # Create new account
                    account = self.create_account(connection, api_account)
                    if account:
                        accounts_added += 1
                        existing_accounts[account_id] = account
            
            # Deactivate accounts that are no longer in API response
            for account_id, account in existing_accounts.items():
                if account_id not in active_account_ids and account.sync_status == 'active':
                    account.sync_status = 'inactive'
                    account.save(update_fields=['sync_status'])
                    accounts_deactivated += 1
            
            # Build hierarchy relationships
            self.build_hierarchy(connection, api_accounts, existing_accounts)
            
            # Determine login customer capabilities
            self.determine_login_customers(connection, existing_accounts)
            
            # Update sync record
            sync_record.accounts_added = accounts_added
            sync_record.accounts_updated = accounts_updated
            sync_record.accounts_deactivated = accounts_deactivated
            sync_record.mark_completed()
            
            self.stdout.write(f'  - Added: {accounts_added}, Updated: {accounts_updated}, Deactivated: {accounts_deactivated}')
            
            return True
            
        except Exception as e:
            sync_record.mark_failed(str(e))
            logger.error(f'Error in sync_connection: {str(e)}')
            logger.error(traceback.format_exc())
            return False

    def create_account(self, connection, api_account):
        """Create new GoogleAdsAccount from API data"""
        try:
            account_id = api_account.get('id')
            raw_account_id = account_id.replace('-', '') if account_id else ''
            
            account = GoogleAdsAccount.objects.create(
                platform_connection=connection,
                account_id=account_id,
                raw_account_id=raw_account_id,
                name=api_account.get('name', f'Account {account_id}'),
                is_manager=api_account.get('is_manager', False),
                status=api_account.get('status', 'ACTIVE'),
                currency_code=api_account.get('currency_code', ''),
                time_zone=api_account.get('time_zone', ''),
                level=api_account.get('level', 0),
                sync_status='active'
            )
            
            return account
            
        except Exception as e:
            logger.error(f'Error creating account {api_account.get("id")}: {str(e)}')
            return None

    def update_account(self, account, api_account):
        """Update existing account with API data"""
        try:
            updated = False
            
            # Check for changes
            if account.name != api_account.get('name', account.name):
                account.name = api_account.get('name', account.name)
                updated = True
            
            if account.is_manager != api_account.get('is_manager', account.is_manager):
                account.is_manager = api_account.get('is_manager', account.is_manager)
                updated = True
            
            if account.status != api_account.get('status', account.status):
                account.status = api_account.get('status', account.status)
                updated = True
            
            if account.sync_status != 'active':
                account.sync_status = 'active'
                updated = True
            
            if updated:
                account.save()
            
            return updated
            
        except Exception as e:
            logger.error(f'Error updating account {account.account_id}: {str(e)}')
            return False

    def build_hierarchy(self, connection, api_accounts, existing_accounts):
        """Build parent-child relationships"""
        try:
            # First, clear existing hierarchy to rebuild
            GoogleAdsAccount.objects.filter(
                platform_connection=connection
            ).update(parent_account=None)
            
            # Build hierarchy from API data
            for api_account in api_accounts:
                account_id = api_account.get('id')
                parent_id = api_account.get('parent_id')
                
                if account_id and parent_id and account_id in existing_accounts:
                    account = existing_accounts[account_id]
                    
                    # Find parent account
                    parent_account = existing_accounts.get(parent_id)
                    if parent_account:
                        account.parent_account = parent_account
                        account.save(update_fields=['parent_account'])
                    
                    # Process child accounts if they exist
                    child_accounts = api_account.get('child_accounts', [])
                    for child_data in child_accounts:
                        child_id = child_data.get('id')
                        if child_id and child_id in existing_accounts:
                            child_account = existing_accounts[child_id]
                            child_account.parent_account = account
                            child_account.level = account.level + 1
                            child_account.save(update_fields=['parent_account', 'level'])
                            
        except Exception as e:
            logger.error(f'Error building hierarchy: {str(e)}')

    def determine_login_customers(self, connection, existing_accounts):
        """Determine which accounts can be used as login customers"""
        try:
            # For now, mark manager accounts as potential login customers
            # In a more sophisticated implementation, you could test API access
            for account in existing_accounts.values():
                if account.is_manager:
                    account.can_be_login_customer = True
                    account.accessible_account_count = len(account.get_all_child_accounts())
                    account.save(update_fields=['can_be_login_customer', 'accessible_account_count'])
                    
        except Exception as e:
            logger.error(f'Error determining login customers: {str(e)}')
    
    def _get_accounts_for_sync(self, service, connection):
        """
        Get accounts for sync with better error handling and retry logic
        
        Args:
            service: GoogleAdsAccountService instance
            connection: PlatformConnection instance
            
        Returns:
            List of account dictionaries or empty list
        """
        try:
            # Use the new account service to get accounts
            api_accounts = service.get_accounts_for_connection(connection, force_refresh=True)
            
            # Handle empty account retrieval
            if not api_accounts:
                self.stdout.write(f'  - No accounts found - skipping sync')
                return []
            
            # Check for error responses
            if api_accounts:
                error_accounts = [acc for acc in api_accounts if acc.get('id') == 'ERROR']
                if error_accounts:
                    error_msg = error_accounts[0].get('name', 'Unknown API error')
                    self.stdout.write(self.style.ERROR(f'  ✗ API Error: {error_msg}'))
                    return []
            
            return api_accounts or []
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ✗ Error fetching accounts: {str(e)}'))
            return []