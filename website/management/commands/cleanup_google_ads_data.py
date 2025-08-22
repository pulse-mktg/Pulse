"""
Management command to clean up old Google Ads data for better performance
This command removes old daily metrics and consolidates historical data
"""
import logging
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from django.db.models import Count
from website.models import (
    GoogleAdsDailyMetrics, GoogleAdsMetrics, GoogleAdsCampaign,
    GoogleAdsAccountSync, Tenant
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Clean up old Google Ads data to maintain database performance'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days-to-keep-daily',
            type=int,
            default=90,
            help='Keep daily metrics for this many days (default: 90)'
        )
        parser.add_argument(
            '--days-to-keep-sync-logs',
            type=int,
            default=30,
            help='Keep sync logs for this many days (default: 30)'
        )
        parser.add_argument(
            '--tenant-id',
            type=int,
            help='Clean data for specific tenant only'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be cleaned without actually deleting data'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Skip confirmation prompts'
        )

    def handle(self, *args, **options):
        start_time = timezone.now()
        self.stdout.write(
            self.style.SUCCESS(f'🧹 Starting Google Ads data cleanup at {start_time}')
        )
        
        # Get configuration
        days_to_keep_daily = options['days_to_keep_daily']
        days_to_keep_sync_logs = options['days_to_keep_sync_logs']
        tenant_id = options['tenant_id']
        dry_run = options['dry_run']
        force = options['force']
        
        # Calculate cutoff dates
        daily_cutoff_date = timezone.now().date() - timedelta(days=days_to_keep_daily)
        sync_cutoff_date = timezone.now() - timedelta(days=days_to_keep_sync_logs)
        
        self.stdout.write(f'Configuration:')
        self.stdout.write(f'  Daily metrics cutoff: {daily_cutoff_date} (keep {days_to_keep_daily} days)')
        self.stdout.write(f'  Sync logs cutoff: {sync_cutoff_date.date()} (keep {days_to_keep_sync_logs} days)')
        self.stdout.write(f'  Tenant filter: {tenant_id or "All tenants"}')
        self.stdout.write(f'  Dry run: {dry_run}')
        
        # Get tenant filter
        tenant_filter = {}
        if tenant_id:
            tenant_filter['client_account__client__tenant_id'] = tenant_id
        
        # Analyze what will be cleaned
        cleanup_stats = self.analyze_cleanup(daily_cutoff_date, sync_cutoff_date, tenant_filter)
        
        # Display cleanup plan
        self.display_cleanup_plan(cleanup_stats)
        
        # Confirm before proceeding (unless forced or dry run)
        if not dry_run and not force:
            confirmation = input('\\nProceed with cleanup? (y/N): ')
            if confirmation.lower() != 'y':
                self.stdout.write(self.style.WARNING('Cleanup cancelled'))
                return
        
        # Perform cleanup
        if dry_run:
            self.stdout.write(self.style.WARNING('\\n🔍 DRY RUN - No data will be deleted'))
        else:
            self.stdout.write('\\n🗑️  Starting cleanup...')
            self.perform_cleanup(daily_cutoff_date, sync_cutoff_date, tenant_filter)
        
        # Final summary
        end_time = timezone.now()
        duration = end_time - start_time
        
        self.stdout.write(self.style.SUCCESS(f'\\n✅ Cleanup completed in {duration}'))

    def analyze_cleanup(self, daily_cutoff_date, sync_cutoff_date, tenant_filter):
        """Analyze what data will be cleaned up"""
        
        stats = {
            'daily_metrics_to_delete': 0,
            'sync_logs_to_delete': 0,
            'campaigns_analyzed': 0,
            'total_daily_metrics': 0,
            'total_sync_logs': 0
        }
        
        # Count daily metrics to delete
        daily_query = GoogleAdsDailyMetrics.objects.filter(
            date__lt=daily_cutoff_date,
            **tenant_filter
        )
        stats['daily_metrics_to_delete'] = daily_query.count()
        
        # Count total daily metrics for reference
        all_daily_query = GoogleAdsDailyMetrics.objects.all()
        if tenant_filter:
            all_daily_query = all_daily_query.filter(**tenant_filter)
        stats['total_daily_metrics'] = all_daily_query.count()
        
        # Count sync logs to delete (no tenant filter needed as it's connection-level)
        sync_query = GoogleAdsAccountSync.objects.filter(
            started_at__lt=sync_cutoff_date
        )
        if tenant_filter and 'client_account__client__tenant_id' in tenant_filter:
            sync_query = sync_query.filter(
                platform_connection__tenant_id=tenant_filter['client_account__client__tenant_id']
            )
        stats['sync_logs_to_delete'] = sync_query.count()
        
        # Count total sync logs for reference
        all_sync_query = GoogleAdsAccountSync.objects.all()
        if tenant_filter and 'client_account__client__tenant_id' in tenant_filter:
            all_sync_query = all_sync_query.filter(
                platform_connection__tenant_id=tenant_filter['client_account__client__tenant_id']
            )
        stats['total_sync_logs'] = all_sync_query.count()
        
        # Count campaigns that will be affected
        campaigns_query = GoogleAdsCampaign.objects.filter(
            daily_metrics__date__lt=daily_cutoff_date
        ).distinct()
        if tenant_filter:
            campaigns_query = campaigns_query.filter(**tenant_filter)
        stats['campaigns_analyzed'] = campaigns_query.count()
        
        return stats

    def display_cleanup_plan(self, stats):
        """Display what will be cleaned up"""
        
        self.stdout.write('\\n📊 CLEANUP ANALYSIS')
        self.stdout.write('=' * 50)
        
        # Daily metrics
        daily_pct = (stats['daily_metrics_to_delete'] / max(stats['total_daily_metrics'], 1)) * 100
        self.stdout.write(f'Daily Metrics:')
        self.stdout.write(f'  Will delete: {stats["daily_metrics_to_delete"]:,} records ({daily_pct:.1f}%)')
        self.stdout.write(f'  Will keep: {stats["total_daily_metrics"] - stats["daily_metrics_to_delete"]:,} records')
        self.stdout.write(f'  Total currently: {stats["total_daily_metrics"]:,} records')
        
        # Sync logs
        sync_pct = (stats['sync_logs_to_delete'] / max(stats['total_sync_logs'], 1)) * 100
        self.stdout.write(f'\\nSync Logs:')
        self.stdout.write(f'  Will delete: {stats["sync_logs_to_delete"]:,} records ({sync_pct:.1f}%)')
        self.stdout.write(f'  Will keep: {stats["total_sync_logs"] - stats["sync_logs_to_delete"]:,} records')
        self.stdout.write(f'  Total currently: {stats["total_sync_logs"]:,} records')
        
        # Campaigns affected
        self.stdout.write(f'\\nCampaigns with old daily data: {stats["campaigns_analyzed"]:,}')
        
        # Impact assessment
        total_to_delete = stats['daily_metrics_to_delete'] + stats['sync_logs_to_delete']
        self.stdout.write(f'\\nTotal records to delete: {total_to_delete:,}')
        
        if total_to_delete == 0:
            self.stdout.write(self.style.SUCCESS('✅ No cleanup needed - all data is within retention periods'))
        elif total_to_delete < 1000:
            self.stdout.write(self.style.SUCCESS('✅ Small cleanup - minimal impact expected'))
        elif total_to_delete < 10000:
            self.stdout.write(self.style.WARNING('⚠️  Moderate cleanup - some performance impact during deletion'))
        else:
            self.stdout.write(self.style.ERROR('⚠️  Large cleanup - significant performance impact expected'))

    def perform_cleanup(self, daily_cutoff_date, sync_cutoff_date, tenant_filter):
        """Perform the actual cleanup"""
        
        try:
            with transaction.atomic():
                # Clean up daily metrics
                self.stdout.write('\\n🗑️  Cleaning up daily metrics...')
                daily_query = GoogleAdsDailyMetrics.objects.filter(
                    date__lt=daily_cutoff_date,
                    **tenant_filter
                )
                
                daily_deleted_count = 0
                # Delete in batches to avoid memory issues
                batch_size = 1000
                while True:
                    batch = list(daily_query[:batch_size])
                    if not batch:
                        break
                    
                    batch_ids = [obj.id for obj in batch]
                    deleted_count = GoogleAdsDailyMetrics.objects.filter(id__in=batch_ids).delete()[0]
                    daily_deleted_count += deleted_count
                    self.stdout.write(f'  Deleted {daily_deleted_count:,} daily metrics...', ending='\\r')
                
                self.stdout.write(f'\\n  ✅ Deleted {daily_deleted_count:,} daily metrics')
                
                # Clean up sync logs
                self.stdout.write('\\n🗑️  Cleaning up sync logs...')
                sync_query = GoogleAdsAccountSync.objects.filter(
                    started_at__lt=sync_cutoff_date
                )
                if tenant_filter and 'client_account__client__tenant_id' in tenant_filter:
                    sync_query = sync_query.filter(
                        platform_connection__tenant_id=tenant_filter['client_account__client__tenant_id']
                    )
                
                sync_deleted_count, _ = sync_query.delete()
                self.stdout.write(f'  ✅ Deleted {sync_deleted_count:,} sync logs')
                
                # Verify cleanup
                self.stdout.write('\\n🔍 Verifying cleanup...')
                remaining_daily = GoogleAdsDailyMetrics.objects.filter(
                    date__lt=daily_cutoff_date,
                    **tenant_filter
                ).count()
                
                remaining_sync = GoogleAdsAccountSync.objects.filter(
                    started_at__lt=sync_cutoff_date
                ).count()
                if tenant_filter and 'client_account__client__tenant_id' in tenant_filter:
                    remaining_sync = GoogleAdsAccountSync.objects.filter(
                        started_at__lt=sync_cutoff_date,
                        platform_connection__tenant_id=tenant_filter['client_account__client__tenant_id']
                    ).count()
                
                if remaining_daily > 0 or remaining_sync > 0:
                    self.stdout.write(self.style.WARNING(f'⚠️  Cleanup incomplete - {remaining_daily} daily metrics and {remaining_sync} sync logs remain'))
                else:
                    self.stdout.write(self.style.SUCCESS('✅ Cleanup completed successfully'))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Cleanup failed: {str(e)}'))
            logger.error(f'Cleanup error: {str(e)}')
            raise

    def get_database_size_info(self):
        """Get information about database table sizes (if available)"""
        try:
            from django.db import connection
            
            with connection.cursor() as cursor:
                # Get table sizes (PostgreSQL specific)
                cursor.execute("""
                    SELECT 
                        schemaname,
                        tablename,
                        attname,
                        n_distinct,
                        most_common_vals
                    FROM pg_stats
                    WHERE tablename IN ('website_googleadsdailymetrics', 'website_googleadsaccountsync')
                    ORDER BY tablename, attname
                """)
                
                results = cursor.fetchall()
                if results:
                    self.stdout.write('\\n📊 DATABASE TABLE STATISTICS')
                    self.stdout.write('=' * 40)
                    for row in results:
                        self.stdout.write(f'{row[1]}.{row[2]}: {row[3]} distinct values')
                        
        except Exception as e:
            # Not critical if this fails
            logger.debug(f'Could not get database size info: {str(e)}')
            pass