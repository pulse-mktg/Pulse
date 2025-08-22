"""
Management command to sync Google Ads campaign data for all clients
This command fetches fresh campaign performance data and stores it in the database
"""
import logging
import traceback
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from website.models import (
    Tenant, Client, ClientPlatformAccount, PlatformConnection, 
    GoogleAdsCampaign, GoogleAdsMetrics
)
from website.services.google_ads_data import GoogleAdsDataService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sync Google Ads campaign data for all active clients'

    def add_arguments(self, parser):
        parser.add_argument(
            '--tenant-id',
            type=int,
            help='Sync specific tenant ID only'
        )
        parser.add_argument(
            '--client-id',
            type=int,
            help='Sync specific client ID only'
        )
        parser.add_argument(
            '--max-age-hours',
            type=int,
            default=6,
            help='Skip syncing if data was refreshed within this many hours (default: 6)'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force sync even if recently synced'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be synced without actually syncing'
        )

    def handle(self, *args, **options):
        start_time = timezone.now()
        self.stdout.write(
            self.style.SUCCESS(f'🚀 Starting Google Ads campaign data sync at {start_time}')
        )
        
        # Get tenants to process
        tenants = Tenant.objects.filter(is_active=True)
        if options['tenant_id']:
            tenants = tenants.filter(id=options['tenant_id'])
        
        if not tenants.exists():
            self.stdout.write(self.style.WARNING('No active tenants found'))
            return
        
        # Process each tenant
        total_stats = {
            'tenants_processed': 0,
            'clients_processed': 0,
            'accounts_synced': 0,
            'accounts_skipped': 0,
            'accounts_failed': 0,
            'campaigns_updated': 0
        }
        
        for tenant in tenants:
            tenant_stats = self.process_tenant(tenant, options)
            
            # Aggregate stats
            for key in total_stats:
                total_stats[key] += tenant_stats.get(key, 0)
        
        # Final summary
        end_time = timezone.now()
        duration = end_time - start_time
        
        self.stdout.write(self.style.SUCCESS(f'\\n📊 SYNC COMPLETED in {duration}'))
        self.stdout.write(f'  Tenants processed: {total_stats["tenants_processed"]}')
        self.stdout.write(f'  Clients processed: {total_stats["clients_processed"]}')
        self.stdout.write(f'  Accounts synced: {total_stats["accounts_synced"]}')
        self.stdout.write(f'  Accounts skipped: {total_stats["accounts_skipped"]}')
        self.stdout.write(f'  Accounts failed: {total_stats["accounts_failed"]}')
        self.stdout.write(f'  Campaigns updated: {total_stats["campaigns_updated"]}')

    def process_tenant(self, tenant, options):
        """Process all clients for a tenant"""
        self.stdout.write(f'\\n🏢 Processing tenant: {tenant.name}')
        
        stats = {
            'tenants_processed': 1,
            'clients_processed': 0,
            'accounts_synced': 0,
            'accounts_skipped': 0,
            'accounts_failed': 0,
            'campaigns_updated': 0
        }
        
        # Get clients to process
        clients = Client.objects.filter(tenant=tenant, is_active=True)
        if options['client_id']:
            clients = clients.filter(id=options['client_id'])
        
        if not clients.exists():
            self.stdout.write('  No active clients found')
            return stats
        
        # Initialize Google Ads service for this tenant
        try:
            google_ads_service = GoogleAdsDataService(tenant)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ❌ Failed to initialize Google Ads service: {str(e)}'))
            return stats
        
        # Process each client
        for client in clients:
            client_stats = self.process_client(client, google_ads_service, options)
            
            # Aggregate client stats
            for key in ['accounts_synced', 'accounts_skipped', 'accounts_failed', 'campaigns_updated']:
                stats[key] += client_stats.get(key, 0)
            stats['clients_processed'] += 1
        
        return stats

    def process_client(self, client, google_ads_service, options):
        """Process all Google Ads accounts for a client"""
        self.stdout.write(f'\\n  👤 Processing client: {client.name}')
        
        stats = {
            'accounts_synced': 0,
            'accounts_skipped': 0,
            'accounts_failed': 0,
            'campaigns_updated': 0
        }
        
        # Get Google Ads accounts for this client
        google_ads_accounts = ClientPlatformAccount.objects.filter(
            client=client,
            platform_connection__platform_type__slug='google-ads',
            platform_connection__is_active=True,
            platform_connection__connection_status='active',
            is_active=True
        ).select_related('platform_connection')
        
        if not google_ads_accounts.exists():
            self.stdout.write('    No active Google Ads accounts found')
            return stats
        
        # Process each account
        for account in google_ads_accounts:
            account_stats = self.process_account(account, google_ads_service, options)
            
            # Aggregate account stats
            for key in stats:
                stats[key] += account_stats.get(key, 0)
        
        return stats

    def process_account(self, account, google_ads_service, options):
        """Process a single Google Ads account"""
        self.stdout.write(f'    🎯 Processing account: {account.platform_client_name} ({account.platform_client_id})')
        
        stats = {
            'accounts_synced': 0,
            'accounts_skipped': 0,
            'accounts_failed': 0,
            'campaigns_updated': 0
        }
        
        try:
            # Check if recently synced (unless forced)
            if not options['force']:
                recent_sync_threshold = timezone.now() - timedelta(hours=options['max_age_hours'])
                
                # Check if any campaigns for this account were recently synced
                recent_campaigns = GoogleAdsCampaign.objects.filter(
                    client_account=account,
                    last_synced__gte=recent_sync_threshold
                ).exists()
                
                if recent_campaigns:
                    self.stdout.write(f'      ⏭️  Skipping (data refreshed within {options["max_age_hours"]} hours)')
                    stats['accounts_skipped'] = 1
                    return stats
            
            # Dry run mode
            if options['dry_run']:
                self.stdout.write('      🔍 Would sync (dry run mode)')
                return stats
            
            # Sync the account data
            self.stdout.write('      📡 Syncing campaign data...')
            success, message = google_ads_service.sync_client_account_data(account)
            
            if success:
                self.stdout.write(self.style.SUCCESS(f'      ✅ Synced successfully'))
                stats['accounts_synced'] = 1
                
                # Count campaigns updated
                campaigns_count = GoogleAdsCampaign.objects.filter(client_account=account).count()
                stats['campaigns_updated'] = campaigns_count
                
            else:
                self.stdout.write(self.style.ERROR(f'      ❌ Sync failed: {message}'))
                stats['accounts_failed'] = 1
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'      ❌ Error: {str(e)}'))
            logger.error(f'Error processing account {account.id}: {str(e)}')
            logger.error(traceback.format_exc())
            stats['accounts_failed'] = 1
        
        return stats

    def get_account_freshness_info(self, account):
        """Get information about data freshness for an account"""
        try:
            # Get the most recent sync timestamp
            latest_campaign = GoogleAdsCampaign.objects.filter(
                client_account=account
            ).order_by('-last_synced').first()
            
            if not latest_campaign or not latest_campaign.last_synced:
                return "Never synced", "danger"
            
            time_since_sync = timezone.now() - latest_campaign.last_synced
            hours_since = time_since_sync.total_seconds() / 3600
            
            if hours_since < 1:
                return f"{int(time_since_sync.total_seconds() / 60)} minutes ago", "success"
            elif hours_since < 6:
                return f"{int(hours_since)} hours ago", "success"
            elif hours_since < 24:
                return f"{int(hours_since)} hours ago", "warning"
            else:
                days_since = int(hours_since / 24)
                return f"{days_since} days ago", "danger"
                
        except Exception as e:
            logger.error(f'Error getting freshness info: {str(e)}')
            return "Unknown", "secondary"