"""
Google Ads data retrieval service for Pulse.
Handles fetching campaign data, ad groups, and performance metrics.
"""

import datetime
import logging
import json
from django.utils import timezone
from django.conf import settings

import google.oauth2.credentials
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from ..models import PlatformConnection, ClientPlatformAccount
from ..models import GoogleAdsCampaign, GoogleAdsAdGroup, GoogleAdsMetrics, GoogleAdsDailyMetrics
from .google_ads import GoogleAdsService

logger = logging.getLogger(__name__)

class GoogleAdsDataService:
    """
    Service for retrieving and managing Google Ads data
    """
    
    def __init__(self, tenant):
        """
        Initialize the Google Ads data service.
        
        Args:
            tenant: The tenant model instance
        """
        self.tenant = tenant
        self.google_ads_service = GoogleAdsService(tenant)
    
    def sync_client_account_data(self, client_account):
        """
        Sync campaign data for a client account
        
        Args:
            client_account: ClientPlatformAccount instance
            
        Returns:
            tuple: (success, message)
        """
        try:
            # Get the platform connection
            connection = client_account.platform_connection
            
            # Check if connection is active
            if not connection.is_active or connection.connection_status != 'active':
                return False, "Google Ads connection is not active"
            
            # Refresh token if needed
            if connection.is_token_expired():
                success = self.google_ads_service.refresh_token(connection)
                if not success:
                    return False, "Failed to refresh OAuth token"
            
            # Create credentials
            credentials = google.oauth2.credentials.Credentials(
                token=connection.access_token,
                refresh_token=connection.refresh_token,
                token_uri='https://oauth2.googleapis.com/token',
                client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
                client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET
            )
            
            # Create Google Ads client
            client = GoogleAdsClient(
                credentials=credentials,
                developer_token=settings.GOOGLE_ADS_DEVELOPER_TOKEN,
                use_proto_plus=True
            )
            
            # Sync campaigns
            self._sync_campaigns(client, client_account)
            
            # Update last synced timestamp
            connection.last_synced = timezone.now()
            connection.save()
            
            return True, "Data synced successfully"
            
        except GoogleAdsException as gae:
            error_message = f"Google Ads API error: {gae.error.message}"
            logger.error(error_message)
            return False, error_message
            
        except Exception as e:
            error_message = f"Error syncing Google Ads data: {str(e)}"
            logger.error(error_message)
            return False, error_message
    
    def _sync_campaigns(self, client, client_account):
        """
        Sync campaign data from Google Ads API
        
        Args:
            client: GoogleAdsClient instance
            client_account: ClientPlatformAccount instance
        """
        # Get the customer ID
        customer_id = client_account.platform_client_id.replace('-', '')
        
        try:
            # Create a Google Ads service client
            ga_service = client.get_service("GoogleAdsService")
            
            # Define the query
            query = """
                SELECT 
                  campaign.id, 
                  campaign.name, 
                  campaign.status,
                  campaign.campaign_budget,
                  campaign.advertising_channel_type,
                  campaign.start_date,
                  campaign.end_date,
                  campaign.network_settings.target_search_network,
                  campaign.network_settings.target_content_network,
                  metrics.impressions,
                  metrics.clicks,
                  metrics.cost_micros,
                  metrics.conversions,
                  metrics.ctr,
                  metrics.average_cpc,
                  metrics.conversions_value
                FROM campaign
                WHERE campaign.status != 'REMOVED'
                ORDER BY campaign.name
            """
            
            # Issue the search request
            search_request = client.get_type("SearchGoogleAdsRequest")
            search_request.customer_id = customer_id
            search_request.query = query
            
            # Execute the query
            response = ga_service.search(request=search_request)
            
            # Process each campaign
            for row in response:
                campaign = row.campaign
                metrics = row.metrics
                
                # Format campaign ID
                campaign_id = str(campaign.id)
                
                # Get or create campaign in the database
                db_campaign, created = GoogleAdsCampaign.objects.update_or_create(
                    client_account=client_account,
                    campaign_id=campaign_id,
                    defaults={
                        'name': campaign.name,
                        'status': campaign.status.name,
                        'campaign_type': campaign.advertising_channel_type.name if campaign.advertising_channel_type else None,
                        'budget_amount': float(campaign.campaign_budget.split('/')[-1]) / 1000000 if campaign.campaign_budget else None,
                        'start_date': self._format_google_date(campaign.start_date) if campaign.start_date else None,
                        'end_date': self._format_google_date(campaign.end_date) if campaign.end_date else None,
                        'last_synced': timezone.now()
                    }
                )
                
                # Calculate metrics for different date ranges
                for date_range in ['LAST_7_DAYS', 'LAST_30_DAYS', 'LAST_90_DAYS']:
                    # Get date start and end based on date range
                    date_end = timezone.now().date()
                    if date_range == 'LAST_7_DAYS':
                        date_start = date_end - datetime.timedelta(days=7)
                        date_range_days = 7
                    elif date_range == 'LAST_30_DAYS':
                        date_start = date_end - datetime.timedelta(days=30)
                        date_range_days = 30
                    else:  # LAST_90_DAYS
                        date_start = date_end - datetime.timedelta(days=90)
                        date_range_days = 90
                    
                    # Convert metrics
                    impressions = int(metrics.impressions)
                    clicks = int(metrics.clicks)
                    cost = float(metrics.cost_micros) / 1000000  # Convert micros to dollars
                    conversions = float(metrics.conversions)
                    
                    # Calculate derived metrics
                    ctr = float(metrics.ctr) * 100  # Convert to percentage
                    avg_cpc = float(metrics.average_cpc) / 1000000  # Convert micros to dollars
                    conversion_rate = (conversions / clicks * 100) if clicks > 0 else 0
                    avg_daily_spend = cost / date_range_days
                    
                    # Update campaign metrics
                    GoogleAdsMetrics.objects.update_or_create(
                        campaign=db_campaign,
                        ad_group=None,
                        date_range=date_range,
                        defaults={
                            'date_start': date_start,
                            'date_end': date_end,
                            'date_range_days': date_range_days,
                            'impressions': impressions,
                            'clicks': clicks,
                            'cost': cost,
                            'conversions': conversions,
                            'ctr': ctr,
                            'avg_cpc': avg_cpc,
                            'conversion_rate': conversion_rate,
                            'avg_daily_spend': avg_daily_spend
                        }
                    )
                
                # Sync ad groups for this campaign
                self._sync_ad_groups(client, customer_id, db_campaign)
                
                # Sync daily metrics for this campaign
                self._sync_daily_metrics(client, customer_id, db_campaign)
            
        except GoogleAdsException as gae:
            for error in gae.failure.errors:
                logger.error(f"Error syncing campaigns: {error.message}")
            raise
        
        except Exception as e:
            logger.error(f"Error syncing campaigns: {str(e)}")
            raise
    
    def _sync_ad_groups(self, client, customer_id, campaign):
        """
        Sync ad groups for a campaign
        
        Args:
            client: GoogleAdsClient instance
            customer_id: Google Ads customer ID
            campaign: GoogleAdsCampaign instance
        """
        try:
            # Create a Google Ads service client
            ga_service = client.get_service("GoogleAdsService")
            
            # Define the query
            query = f"""
                SELECT 
                  ad_group.id, 
                  ad_group.name, 
                  ad_group.status,
                  ad_group.type,
                  metrics.impressions,
                  metrics.clicks,
                  metrics.cost_micros,
                  metrics.conversions,
                  metrics.ctr,
                  metrics.average_cpc
                FROM ad_group
                WHERE ad_group.campaign = '{campaign.campaign_id}'
                ORDER BY ad_group.name
            """
            
            # Issue the search request
            search_request = client.get_type("SearchGoogleAdsRequest")
            search_request.customer_id = customer_id
            search_request.query = query
            
            # Execute the query
            response = ga_service.search(request=search_request)
            
            # Process each ad group
            for row in response:
                ad_group = row.ad_group
                metrics = row.metrics
                
                # Format ad group ID
                ad_group_id = str(ad_group.id)
                
                # Get or create ad group in the database
                db_ad_group, created = GoogleAdsAdGroup.objects.update_or_create(
                    campaign=campaign,
                    ad_group_id=ad_group_id,
                    defaults={
                        'name': ad_group.name,
                        'status': ad_group.status.name,
                        'ad_group_type': ad_group.type.name if ad_group.type else None,
                        'last_synced': timezone.now()
                    }
                )
                
                # Calculate metrics for different date ranges
                for date_range in ['LAST_7_DAYS', 'LAST_30_DAYS', 'LAST_90_DAYS']:
                    # Get date start and end based on date range
                    date_end = timezone.now().date()
                    if date_range == 'LAST_7_DAYS':
                        date_start = date_end - datetime.timedelta(days=7)
                        date_range_days = 7
                    elif date_range == 'LAST_30_DAYS':
                        date_start = date_end - datetime.timedelta(days=30)
                        date_range_days = 30
                    else:  # LAST_90_DAYS
                        date_start = date_end - datetime.timedelta(days=90)
                        date_range_days = 90
                    
                    # Convert metrics
                    impressions = int(metrics.impressions)
                    clicks = int(metrics.clicks)
                    cost = float(metrics.cost_micros) / 1000000  # Convert micros to dollars
                    conversions = float(metrics.conversions)
                    
                    # Calculate derived metrics
                    ctr = float(metrics.ctr) * 100  # Convert to percentage
                    avg_cpc = float(metrics.average_cpc) / 1000000  # Convert micros to dollars
                    conversion_rate = (conversions / clicks * 100) if clicks > 0 else 0
                    
                    # Update ad group metrics
                    GoogleAdsMetrics.objects.update_or_create(
                        campaign=None,
                        ad_group=db_ad_group,
                        date_range=date_range,
                        defaults={
                            'date_start': date_start,
                            'date_end': date_end,
                            'date_range_days': date_range_days,
                            'impressions': impressions,
                            'clicks': clicks,
                            'cost': cost,
                            'conversions': conversions,
                            'ctr': ctr,
                            'avg_cpc': avg_cpc,
                            'conversion_rate': conversion_rate
                        }
                    )
        
        except GoogleAdsException as gae:
            for error in gae.failure.errors:
                logger.error(f"Error syncing ad groups: {error.message}")
            raise
        
        except Exception as e:
            logger.error(f"Error syncing ad groups: {str(e)}")
            raise
    
    def _sync_daily_metrics(self, client, customer_id, campaign):
        """
        Sync daily metrics for a campaign
        
        Args:
            client: GoogleAdsClient instance
            customer_id: Google Ads customer ID
            campaign: GoogleAdsCampaign instance
        """
        try:
            # Create a Google Ads service client
            ga_service = client.get_service("GoogleAdsService")
            
            # Define the query
            query = f"""
                SELECT 
                  segments.date,
                  metrics.impressions,
                  metrics.clicks,
                  metrics.cost_micros,
                  metrics.conversions,
                  metrics.ctr,
                  metrics.average_cpc
                FROM campaign
                WHERE campaign.id = {campaign.campaign_id}
                  AND segments.date DURING LAST_90_DAYS
                ORDER BY segments.date
            """
            
            # Issue the search request
            search_request = client.get_type("SearchGoogleAdsRequest")
            search_request.customer_id = customer_id
            search_request.query = query
            
            # Execute the query
            response = ga_service.search(request=search_request)
            
            # Process each day's metrics
            for row in response:
                segments = row.segments
                metrics = row.metrics
                
                # Format date
                date = self._format_google_date(segments.date)
                
                # Convert metrics
                impressions = int(metrics.impressions)
                clicks = int(metrics.clicks)
                cost = float(metrics.cost_micros) / 1000000  # Convert micros to dollars
                conversions = float(metrics.conversions)
                
                # Calculate derived metrics
                ctr = float(metrics.ctr) * 100  # Convert to percentage
                avg_cpc = float(metrics.average_cpc) / 1000000  # Convert micros to dollars
                
                # Update daily metrics
                GoogleAdsDailyMetrics.objects.update_or_create(
                    campaign=campaign,
                    date=date,
                    defaults={
                        'impressions': impressions,
                        'clicks': clicks,
                        'cost': cost,
                        'conversions': conversions,
                        'ctr': ctr,
                        'avg_cpc': avg_cpc
                    }
                )
        
        except GoogleAdsException as gae:
            for error in gae.failure.errors:
                logger.error(f"Error syncing daily metrics: {error.message}")
            raise
        
        except Exception as e:
            logger.error(f"Error syncing daily metrics: {str(e)}")
            raise
    
    def _format_google_date(self, date_str):
        """
        Format Google Ads date string (YYYY-MM-DD) to a Python date object
        
        Args:
            date_str: Date string in YYYY-MM-DD format
            
        Returns:
            datetime.date: Parsed date object
        """
        try:
            if isinstance(date_str, str):
                return datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
            return date_str
        except Exception as e:
            logger.error(f"Error parsing date: {str(e)}")
            return None