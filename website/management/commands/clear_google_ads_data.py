from django.core.management.base import BaseCommand
from website.models import GoogleAdsCampaign, GoogleAdsAdGroup, GoogleAdsMetrics, GoogleAdsDailyMetrics
from django.db import transaction
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Clears all Google Ads data from the database'

    def add_arguments(self, parser):
        parser.add_argument('--client-id', type=int, help='Optional client ID to limit clearing to a specific client')
        parser.add_argument('--account-id', type=int, help='Optional account ID to limit clearing to a specific account')
        
    def handle(self, *args, **options):
        client_id = options.get('client_id')
        account_id = options.get('account_id')
        
        with transaction.atomic():
            # Build filters based on parameters
            campaign_filters = {}
            if client_id:
                self.stdout.write(f"Limiting to client ID: {client_id}")
                campaign_filters['client_account__client_id'] = client_id
            if account_id:
                self.stdout.write(f"Limiting to account ID: {account_id}")
                campaign_filters['client_account_id'] = account_id
                
            # Get affected campaigns for reporting
            campaign_count = GoogleAdsCampaign.objects.filter(**campaign_filters).count()
            
            # Delete daily metrics
            daily_metrics_deleted = GoogleAdsDailyMetrics.objects.filter(
                campaign__in=GoogleAdsCampaign.objects.filter(**campaign_filters)
            ).delete()[0]
            
            # Delete metrics 
            metrics_deleted = GoogleAdsMetrics.objects.filter(
                campaign__in=GoogleAdsCampaign.objects.filter(**campaign_filters)
            ).delete()[0]
            
            # Delete ad groups
            ad_groups_deleted = GoogleAdsAdGroup.objects.filter(
                campaign__in=GoogleAdsCampaign.objects.filter(**campaign_filters)
            ).delete()[0]
            
            # Delete campaigns
            campaigns_deleted = GoogleAdsCampaign.objects.filter(**campaign_filters).delete()[0]
            
            # Report results
            self.stdout.write(self.style.SUCCESS(f"Successfully deleted:"))
            self.stdout.write(f"- {campaigns_deleted} campaigns")
            self.stdout.write(f"- {ad_groups_deleted} ad groups")
            self.stdout.write(f"- {metrics_deleted} metrics records")
            self.stdout.write(f"- {daily_metrics_deleted} daily metrics records")
            
            if campaign_count == 0:
                self.stdout.write(self.style.WARNING("No matching campaign data found to delete"))