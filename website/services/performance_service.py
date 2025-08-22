"""
Performance data aggregation service for Google Ads clients
"""
import logging
from datetime import datetime, timedelta
from django.utils import timezone
from django.db import models
from ..models import Client, GoogleAdsCampaign, GoogleAdsMetrics, ClientPlatformAccount, GoogleAdsDataFreshness

logger = logging.getLogger(__name__)


class PerformanceDataService:
    """Service to aggregate and calculate performance metrics for clients"""
    
    def __init__(self, tenant):
        self.tenant = tenant
        self._freshness_cache = {}  # Cache for performance
    
    def get_client_performance_data(self, client, date_range_days=30):
        """
        Get aggregated performance data for a single client
        
        Args:
            client: Client instance
            date_range_days: Number of days to look back for metrics
            
        Returns:
            dict: Aggregated performance metrics
        """
        try:
            # Calculate date range
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=date_range_days)
            
            # Get all Google Ads accounts for this client
            google_ads_accounts = client.platform_accounts.filter(
                platform_connection__platform_type__slug='google-ads',
                is_active=True
            )
            
            # Initialize metrics
            total_metrics = {
                'impressions': 0,
                'clicks': 0,
                'conversions': 0,
                'cost': 0,
                'campaigns_count': 0,
                'active_campaigns_count': 0
            }
            
            # Aggregate metrics from all campaigns
            for account in google_ads_accounts:
                campaigns = account.google_ads_campaigns.all()
                total_metrics['campaigns_count'] += campaigns.count()
                
                for campaign in campaigns:
                    # Get recent metrics for this campaign
                    recent_metrics = campaign.metrics.filter(
                        date_start__gte=start_date,
                        date_end__lte=end_date
                    ).order_by('-date_end').first()
                    
                    if recent_metrics:
                        total_metrics['impressions'] += recent_metrics.impressions
                        total_metrics['clicks'] += recent_metrics.clicks
                        total_metrics['conversions'] += float(recent_metrics.conversions)
                        total_metrics['cost'] += float(recent_metrics.cost)
                        
                        # Count as active campaign if it has recent impressions
                        if recent_metrics.impressions > 0:
                            total_metrics['active_campaigns_count'] += 1
            
            # Calculate derived metrics
            total_metrics['ctr'] = 0
            total_metrics['conversion_rate'] = 0
            total_metrics['avg_cpc'] = 0
            total_metrics['cost_per_conversion'] = 0
            
            if total_metrics['impressions'] > 0:
                total_metrics['ctr'] = round(
                    (total_metrics['clicks'] / total_metrics['impressions']) * 100, 2
                )
            
            if total_metrics['clicks'] > 0:
                total_metrics['conversion_rate'] = round(
                    (total_metrics['conversions'] / total_metrics['clicks']) * 100, 2
                )
                total_metrics['avg_cpc'] = round(
                    total_metrics['cost'] / total_metrics['clicks'], 2
                )
            
            if total_metrics['conversions'] > 0:
                total_metrics['cost_per_conversion'] = round(
                    total_metrics['cost'] / total_metrics['conversions'], 2
                )
            
            # Add performance goals comparison with backward compatibility
            try:
                performance_goals = client.performance_goals
                
                # Try to use new enhanced method, fall back to old method
                try:
                    effective_goals = performance_goals.get_effective_goals()
                    total_metrics['ctr_goal'] = effective_goals['ctr_goal']
                    total_metrics['conversion_rate_goal'] = effective_goals['conversion_rate_goal']
                    total_metrics['cost_per_click_goal'] = effective_goals.get('cost_per_click_goal')
                    total_metrics['cost_per_conversion_goal'] = effective_goals.get('cost_per_conversion_goal')
                    total_metrics['goals_source'] = effective_goals.get('source', 'client')
                    
                    # Use new get_performance_status method if available
                    if hasattr(performance_goals, 'get_performance_status'):
                        total_metrics['ctr_status'] = performance_goals.get_performance_status(
                            'ctr', total_metrics['ctr']
                        ) if effective_goals['ctr_goal'] else 'no_goal'
                        
                        total_metrics['conversion_rate_status'] = performance_goals.get_performance_status(
                            'conversion_rate', total_metrics['conversion_rate']
                        ) if effective_goals['conversion_rate_goal'] else 'no_goal'
                        
                        total_metrics['cost_per_click_status'] = performance_goals.get_performance_status(
                            'cost_per_click', total_metrics['avg_cpc']
                        ) if effective_goals.get('cost_per_click_goal') else 'no_goal'
                        
                        total_metrics['cost_per_conversion_status'] = performance_goals.get_performance_status(
                            'cost_per_conversion', total_metrics['cost_per_conversion']
                        ) if effective_goals.get('cost_per_conversion_goal') else 'no_goal'
                    else:
                        # Fall back to old individual methods
                        total_metrics['ctr_status'] = performance_goals.get_ctr_performance_status(
                            total_metrics['ctr']
                        )
                        total_metrics['conversion_rate_status'] = performance_goals.get_conversion_rate_performance_status(
                            total_metrics['conversion_rate']
                        )
                        total_metrics['cost_per_click_status'] = 'no_goal'
                        total_metrics['cost_per_conversion_status'] = 'no_goal'
                        
                except Exception as inner_e:
                    logger.debug(f"Enhanced goals not available for client {client.id}, using legacy: {inner_e}")
                    # Fall back to legacy goal system
                    total_metrics['ctr_goal'] = performance_goals.ctr_goal
                    total_metrics['conversion_rate_goal'] = performance_goals.conversion_rate_goal
                    total_metrics['cost_per_click_goal'] = None
                    total_metrics['cost_per_conversion_goal'] = None
                    total_metrics['goals_source'] = 'client'
                    total_metrics['ctr_status'] = performance_goals.get_ctr_performance_status(
                        total_metrics['ctr']
                    )
                    total_metrics['conversion_rate_status'] = performance_goals.get_conversion_rate_performance_status(
                        total_metrics['conversion_rate']
                    )
                    total_metrics['cost_per_click_status'] = 'no_goal'
                    total_metrics['cost_per_conversion_status'] = 'no_goal'
                
            except Exception as e:
                logger.debug(f"No performance goals found for client {client.id}: {e}")
                # Set default values
                total_metrics['ctr_goal'] = None
                total_metrics['conversion_rate_goal'] = None
                total_metrics['cost_per_click_goal'] = None
                total_metrics['cost_per_conversion_goal'] = None
                total_metrics['goals_source'] = 'none'
                total_metrics['ctr_status'] = 'no_goal'
                total_metrics['conversion_rate_status'] = 'no_goal'
                total_metrics['cost_per_click_status'] = 'no_goal'
                total_metrics['cost_per_conversion_status'] = 'no_goal'
            
            return total_metrics
            
        except Exception as e:
            logger.error(f"Error getting performance data for client {client.id}: {str(e)}")
            return self._get_empty_metrics()
    
    def get_all_clients_performance_data(self, date_range_days=30):
        """
        Get performance data for all active clients in the tenant
        
        Args:
            date_range_days: Number of days to look back for metrics
            
        Returns:
            list: List of clients with their performance metrics
        """
        try:
            # Get all active clients with their Google Ads connections
            clients = Client.objects.filter(
                tenant=self.tenant,
                is_active=True
            ).prefetch_related(
                'platform_accounts__google_ads_campaigns__metrics',
                'performance_goals'
            )
            
            clients_with_metrics = []
            
            for client in clients:
                # Get performance data for this client
                client_metrics = self.get_client_performance_data(client, date_range_days)
                
                # Add metrics to client object
                client.metrics = client_metrics
                clients_with_metrics.append(client)
            
            return clients_with_metrics
            
        except Exception as e:
            logger.error(f"Error getting performance data for all clients: {str(e)}")
            return []
    
    def get_all_clients_performance_data_for_range(self, start_date, end_date):
        """
        Get performance data for all active clients in the tenant for a specific date range
        
        Args:
            start_date: Start date (datetime.date object)
            end_date: End date (datetime.date object)
            
        Returns:
            list: List of clients with their performance metrics for the date range
        """
        try:
            # Get all active clients with their Google Ads connections
            clients = Client.objects.filter(
                tenant=self.tenant,
                is_active=True
            ).prefetch_related(
                'platform_accounts__google_ads_campaigns__metrics',
                'performance_goals'
            )
            
            clients_with_metrics = []
            
            for client in clients:
                # Get performance data for this client with the specific date range
                client_metrics = self.get_client_performance_data_for_range(client, start_date, end_date)
                
                # Add metrics to client object
                client.metrics = client_metrics
                clients_with_metrics.append(client)
            
            return clients_with_metrics
            
        except Exception as e:
            logger.error(f"Error getting performance data for all clients (date range): {str(e)}")
            return []
    
    def get_client_performance_data_for_range(self, client, start_date, end_date):
        """
        Get aggregated performance data for a single client within a specific date range
        
        Args:
            client: Client instance
            start_date: Start date (datetime.date object)
            end_date: End date (datetime.date object)
            
        Returns:
            dict: Aggregated performance metrics for the date range
        """
        try:
            # Get all Google Ads accounts for this client
            google_ads_accounts = client.platform_accounts.filter(
                platform_connection__platform_type__slug='google-ads',
                is_active=True
            )
            
            # Initialize metrics
            total_metrics = {
                'impressions': 0,
                'clicks': 0,
                'conversions': 0,
                'cost': 0,
                'campaigns_count': 0,
                'active_campaigns_count': 0
            }
            
            # Aggregate metrics from all campaigns within the date range
            for account in google_ads_accounts:
                campaigns = account.google_ads_campaigns.all()
                total_metrics['campaigns_count'] += campaigns.count()
                
                for campaign in campaigns:
                    # Get metrics for this campaign within the date range
                    date_range_metrics = campaign.metrics.filter(
                        date_start__gte=start_date,
                        date_end__lte=end_date
                    ).aggregate(
                        total_impressions=models.Sum('impressions'),
                        total_clicks=models.Sum('clicks'),
                        total_conversions=models.Sum('conversions'),
                        total_cost=models.Sum('cost')
                    )
                    
                    if any(date_range_metrics.values()):
                        total_metrics['impressions'] += date_range_metrics['total_impressions'] or 0
                        total_metrics['clicks'] += date_range_metrics['total_clicks'] or 0
                        total_metrics['conversions'] += float(date_range_metrics['total_conversions'] or 0)
                        total_metrics['cost'] += float(date_range_metrics['total_cost'] or 0)
                        
                        # Count as active campaign if it has impressions in this range
                        if date_range_metrics['total_impressions'] and date_range_metrics['total_impressions'] > 0:
                            total_metrics['active_campaigns_count'] += 1
            
            # Calculate derived metrics
            total_metrics['ctr'] = 0
            total_metrics['conversion_rate'] = 0
            total_metrics['avg_cpc'] = 0
            total_metrics['cost_per_conversion'] = 0
            
            if total_metrics['impressions'] > 0:
                total_metrics['ctr'] = round(
                    (total_metrics['clicks'] / total_metrics['impressions']) * 100, 2
                )
            
            if total_metrics['clicks'] > 0:
                total_metrics['conversion_rate'] = round(
                    (total_metrics['conversions'] / total_metrics['clicks']) * 100, 2
                )
                total_metrics['avg_cpc'] = round(
                    total_metrics['cost'] / total_metrics['clicks'], 2
                )
            
            if total_metrics['conversions'] > 0:
                total_metrics['cost_per_conversion'] = round(
                    total_metrics['cost'] / total_metrics['conversions'], 2
                )
            
            # Add performance goals comparison with backward compatibility
            try:
                performance_goals = client.performance_goals
                
                # Try to use new enhanced method, fall back to old method
                try:
                    effective_goals = performance_goals.get_effective_goals()
                    total_metrics['ctr_goal'] = effective_goals['ctr_goal']
                    total_metrics['conversion_rate_goal'] = effective_goals['conversion_rate_goal']
                    total_metrics['cost_per_click_goal'] = effective_goals.get('cost_per_click_goal')
                    total_metrics['cost_per_conversion_goal'] = effective_goals.get('cost_per_conversion_goal')
                    total_metrics['goals_source'] = effective_goals.get('source', 'client')
                    
                    # Use new get_performance_status method if available
                    if hasattr(performance_goals, 'get_performance_status'):
                        total_metrics['ctr_status'] = performance_goals.get_performance_status(
                            'ctr', total_metrics['ctr']
                        ) if effective_goals['ctr_goal'] else 'no_goal'
                        
                        total_metrics['conversion_rate_status'] = performance_goals.get_performance_status(
                            'conversion_rate', total_metrics['conversion_rate']
                        ) if effective_goals['conversion_rate_goal'] else 'no_goal'
                        
                        total_metrics['cost_per_click_status'] = performance_goals.get_performance_status(
                            'cost_per_click', total_metrics['avg_cpc']
                        ) if effective_goals.get('cost_per_click_goal') else 'no_goal'
                        
                        total_metrics['cost_per_conversion_status'] = performance_goals.get_performance_status(
                            'cost_per_conversion', total_metrics['cost_per_conversion']
                        ) if effective_goals.get('cost_per_conversion_goal') else 'no_goal'
                    else:
                        # Fall back to old individual methods
                        total_metrics['ctr_status'] = performance_goals.get_ctr_performance_status(
                            total_metrics['ctr']
                        )
                        total_metrics['conversion_rate_status'] = performance_goals.get_conversion_rate_performance_status(
                            total_metrics['conversion_rate']
                        )
                        total_metrics['cost_per_click_status'] = 'no_goal'
                        total_metrics['cost_per_conversion_status'] = 'no_goal'
                        
                except Exception as inner_e:
                    logger.debug(f"Enhanced goals not available for client {client.id}, using legacy: {inner_e}")
                    # Fall back to legacy goal system
                    total_metrics['ctr_goal'] = performance_goals.ctr_goal
                    total_metrics['conversion_rate_goal'] = performance_goals.conversion_rate_goal
                    total_metrics['cost_per_click_goal'] = None
                    total_metrics['cost_per_conversion_goal'] = None
                    total_metrics['goals_source'] = 'client'
                    total_metrics['ctr_status'] = performance_goals.get_ctr_performance_status(
                        total_metrics['ctr']
                    )
                    total_metrics['conversion_rate_status'] = performance_goals.get_conversion_rate_performance_status(
                        total_metrics['conversion_rate']
                    )
                    total_metrics['cost_per_click_status'] = 'no_goal'
                    total_metrics['cost_per_conversion_status'] = 'no_goal'
                
            except Exception as e:
                logger.debug(f"No performance goals found for client {client.id}: {e}")
                # Set default values
                total_metrics['ctr_goal'] = None
                total_metrics['conversion_rate_goal'] = None
                total_metrics['cost_per_click_goal'] = None
                total_metrics['cost_per_conversion_goal'] = None
                total_metrics['goals_source'] = 'none'
                total_metrics['ctr_status'] = 'no_goal'
                total_metrics['conversion_rate_status'] = 'no_goal'
                total_metrics['cost_per_click_status'] = 'no_goal'
                total_metrics['cost_per_conversion_status'] = 'no_goal'
            
            return total_metrics
            
        except Exception as e:
            logger.error(f"Error getting performance data for client {client.id} (date range): {str(e)}")
            return self._get_empty_metrics()
    
    def get_tenant_performance_summary(self, date_range_days=30):
        """
        Get overall performance summary for the tenant
        
        Args:
            date_range_days: Number of days to look back for metrics
            
        Returns:
            dict: Tenant-wide performance summary
        """
        try:
            clients_with_metrics = self.get_all_clients_performance_data(date_range_days)
            
            summary = {
                'total_clients': len(clients_with_metrics),
                'active_clients': 0,
                'total_impressions': 0,
                'total_clicks': 0,
                'total_conversions': 0,
                'total_cost': 0,
                'total_campaigns': 0,
                'active_campaigns': 0,
                'clients_with_goals': 0,
                'clients_meeting_ctr_goal': 0,
                'clients_meeting_conversion_goal': 0
            }
            
            for client in clients_with_metrics:
                metrics = client.metrics
                
                # Count active clients (those with any impressions)
                if metrics['impressions'] > 0:
                    summary['active_clients'] += 1
                
                # Aggregate totals
                summary['total_impressions'] += metrics['impressions']
                summary['total_clicks'] += metrics['clicks']
                summary['total_conversions'] += metrics['conversions']
                summary['total_cost'] += metrics['cost']
                summary['total_campaigns'] += metrics['campaigns_count']
                summary['active_campaigns'] += metrics['active_campaigns_count']
                
                # Count goal performance
                if metrics['ctr_goal'] or metrics['conversion_rate_goal']:
                    summary['clients_with_goals'] += 1
                
                if metrics['ctr_status'] in ['excellent', 'good']:
                    summary['clients_meeting_ctr_goal'] += 1
                
                if metrics['conversion_rate_status'] in ['excellent', 'good']:
                    summary['clients_meeting_conversion_goal'] += 1
            
            # Calculate tenant-wide averages
            if summary['total_impressions'] > 0:
                summary['avg_ctr'] = round(
                    (summary['total_clicks'] / summary['total_impressions']) * 100, 2
                )
            else:
                summary['avg_ctr'] = 0
            
            if summary['total_clicks'] > 0:
                summary['avg_conversion_rate'] = round(
                    (summary['total_conversions'] / summary['total_clicks']) * 100, 2
                )
            else:
                summary['avg_conversion_rate'] = 0
            
            return summary
            
        except Exception as e:
            logger.error(f"Error getting tenant performance summary: {str(e)}")
            return {}
    
    def _get_empty_metrics(self):
        """Return empty metrics dictionary"""
        return {
            'impressions': 0,
            'clicks': 0,
            'conversions': 0,
            'cost': 0,
            'ctr': 0,
            'conversion_rate': 0,
            'avg_cpc': 0,
            'cost_per_conversion': 0,
            'campaigns_count': 0,
            'active_campaigns_count': 0,
            'ctr_goal': None,
            'conversion_rate_goal': None,
            'ctr_status': 'no_goal',
            'conversion_rate_status': 'no_goal'
        }
    
    def sync_client_performance_data(self, client):
        """
        Sync performance data for a specific client by fetching latest metrics
        
        Args:
            client: Client instance to sync data for
            
        Returns:
            dict: Sync results with success status and details
        """
        try:
            from .google_ads_data import GoogleAdsDataService
            
            logger.info(f"Syncing performance data for client {client.name}")
            
            # Initialize Google Ads data service
            google_ads_service = GoogleAdsDataService(client.tenant)
            
            # Get all Google Ads accounts for this client with detailed debugging
            logger.info(f"🔍 DEBUG: Looking for Google Ads accounts for client {client.name} (ID: {client.id})")
            
            # First, check all platform accounts for this client
            all_platform_accounts = client.platform_accounts.all()
            logger.info(f"🔍 DEBUG: Client {client.name} has {all_platform_accounts.count()} total platform accounts")
            
            for account in all_platform_accounts:
                logger.info(f"🔍 DEBUG: Platform account: {account.platform_client_name} (ID: {account.id})")
                logger.info(f"    - Platform type: {account.platform_connection.platform_type.name}")
                logger.info(f"    - Platform slug: {account.platform_connection.platform_type.slug}")
                logger.info(f"    - Connection active: {account.platform_connection.is_active}")
                logger.info(f"    - Connection status: {account.platform_connection.connection_status}")
                logger.info(f"    - Account active: {account.is_active}")
                logger.info(f"    - Token expired: {account.platform_connection.is_token_expired()}")
                if account.platform_connection.token_expiry:
                    logger.info(f"    - Token expiry: {account.platform_connection.token_expiry}")
                else:
                    logger.info("    - Token expiry: Not set")
            
            # Now filter for Google Ads accounts
            google_ads_accounts = client.platform_accounts.filter(
                platform_connection__platform_type__slug='google-ads',
                platform_connection__is_active=True,
                platform_connection__connection_status='active',
                is_active=True
            )
            
            logger.info(f"🔍 DEBUG: Found {google_ads_accounts.count()} active Google Ads accounts for client {client.name}")
            
            if not google_ads_accounts.exists():
                logger.warning(f"⚠️ No active Google Ads accounts found for client {client.name}")
                logger.info("🔍 DEBUG: Checking why no accounts were found...")
                
                # Check each filter condition
                google_ads_platform_accounts = client.platform_accounts.filter(
                    platform_connection__platform_type__slug='google-ads'
                )
                logger.info(f"    - Google Ads platform accounts (any status): {google_ads_platform_accounts.count()}")
                
                inactive_connections = google_ads_platform_accounts.filter(
                    platform_connection__is_active=False
                )
                logger.info(f"    - With inactive connections: {inactive_connections.count()}")
                
                wrong_status_connections = google_ads_platform_accounts.exclude(
                    platform_connection__connection_status='active'
                )
                logger.info(f"    - With non-active status: {wrong_status_connections.count()}")
                for conn in wrong_status_connections:
                    logger.info(f"      * {conn.platform_client_name}: status = {conn.platform_connection.connection_status}")
                
                inactive_accounts = google_ads_platform_accounts.filter(
                    is_active=False
                )
                logger.info(f"    - With inactive account records: {inactive_accounts.count()}")
                
                expired_tokens = []
                for account in google_ads_platform_accounts:
                    if account.platform_connection.is_token_expired():
                        expired_tokens.append(account)
                logger.info(f"    - With expired tokens: {len(expired_tokens)}")
                for account in expired_tokens:
                    logger.warning(f"      * EXPIRED TOKEN: {account.platform_client_name} - expired {account.platform_connection.token_expiry}")
                
                return {
                    'success': True,
                    'message': 'No active Google Ads accounts found',
                    'accounts_synced': 0,
                    'accounts_failed': 0,
                    'debug_info': {
                        'total_platform_accounts': all_platform_accounts.count(),
                        'google_ads_accounts_any_status': google_ads_platform_accounts.count(),
                        'inactive_connections': inactive_connections.count(),
                        'wrong_status_connections': wrong_status_connections.count(),
                        'inactive_accounts': inactive_accounts.count(),
                        'expired_tokens': len(expired_tokens)
                    }
                }
            
            # Sync each account with detailed debugging
            accounts_synced = 0
            accounts_failed = 0
            error_messages = []
            
            logger.info(f"🚀 Starting sync process for {google_ads_accounts.count()} Google Ads accounts...")
            
            for account in google_ads_accounts:
                try:
                    logger.info(f"🔄 Syncing account: {account.platform_client_name} (ID: {account.platform_client_id})")
                    logger.info(f"    - Connection ID: {account.platform_connection.id}")
                    logger.info(f"    - Connection email: {account.platform_connection.platform_account_email}")
                    logger.info(f"    - Token expired: {account.platform_connection.is_token_expired()}")
                    
                    # Check if token needs refresh before sync
                    if account.platform_connection.is_token_expired():
                        logger.warning(f"⚠️ Token is expired for {account.platform_client_name}, attempting refresh...")
                        from .google_ads import GoogleAdsService
                        google_ads_auth_service = GoogleAdsService(client.tenant)
                        refresh_success = google_ads_auth_service.refresh_token(account.platform_connection)
                        if refresh_success:
                            logger.info(f"✅ Token refreshed successfully for {account.platform_client_name}")
                        else:
                            logger.error(f"❌ Token refresh failed for {account.platform_client_name}")
                            accounts_failed += 1
                            error_messages.append(f"{account.platform_client_name}: Token refresh failed")
                            continue
                    
                    logger.info(f"📡 Calling GoogleAdsDataService.sync_client_account_data() for {account.platform_client_name}")
                    success, message = google_ads_service.sync_client_account_data(account)
                    
                    logger.info(f"📊 Sync result for {account.platform_client_name}: success={success}, message='{message}'")
                    
                    if success:
                        accounts_synced += 1
                        logger.info(f"✅ Successfully synced account {account.platform_client_name}")
                    else:
                        accounts_failed += 1
                        error_messages.append(f"{account.platform_client_name}: {message}")
                        logger.error(f"❌ Failed to sync account {account.platform_client_name}: {message}")
                        
                except Exception as e:
                    accounts_failed += 1
                    error_msg = str(e)
                    error_messages.append(f"{account.platform_client_name}: {error_msg}")
                    logger.error(f"💥 Exception syncing account {account.platform_client_name}: {error_msg}")
                    # Log the full traceback for debugging
                    import traceback
                    logger.error(f"Full traceback: {traceback.format_exc()}")
            
            # Determine overall success
            overall_success = accounts_failed == 0
            
            result = {
                'success': overall_success,
                'accounts_synced': accounts_synced,
                'accounts_failed': accounts_failed,
                'total_accounts': google_ads_accounts.count()
            }
            
            if overall_success:
                result['message'] = f"Successfully synced all {accounts_synced} accounts"
            else:
                result['message'] = f"Synced {accounts_synced}/{google_ads_accounts.count()} accounts. Failures: {'; '.join(error_messages[:3])}"
                if len(error_messages) > 3:
                    result['message'] += f" (+{len(error_messages) - 3} more)"
            
            return result
            
        except Exception as e:
            logger.error(f"Error syncing performance data for client {client.id}: {str(e)}")
            return {
                'success': False,
                'message': f"Sync error: {str(e)}",
                'accounts_synced': 0,
                'accounts_failed': 0
            }
    
    def sync_all_clients_performance_data(self):
        """
        Sync performance data for all active clients in the tenant
        
        Returns:
            dict: Overall sync results
        """
        try:
            logger.info(f"Starting bulk sync for tenant {self.tenant.name}")
            
            # Get all active clients
            clients = Client.objects.filter(
                tenant=self.tenant,
                is_active=True
            )
            
            if not clients.exists():
                return {
                    'success': True,
                    'message': 'No active clients found',
                    'clients_processed': 0,
                    'total_accounts_synced': 0,
                    'total_accounts_failed': 0
                }
            
            # Process each client
            clients_processed = 0
            clients_failed = 0
            total_accounts_synced = 0
            total_accounts_failed = 0
            client_results = []
            
            for client in clients:
                try:
                    result = self.sync_client_performance_data(client)
                    clients_processed += 1
                    total_accounts_synced += result['accounts_synced']
                    total_accounts_failed += result['accounts_failed']
                    
                    client_results.append({
                        'client_name': client.name,
                        'client_id': client.id,
                        'success': result['success'],
                        'message': result['message'],
                        'accounts_synced': result['accounts_synced'],
                        'accounts_failed': result['accounts_failed']
                    })
                    
                    if not result['success']:
                        clients_failed += 1
                        
                except Exception as e:
                    clients_failed += 1
                    error_msg = str(e)
                    logger.error(f"Error processing client {client.name}: {error_msg}")
                    
                    client_results.append({
                        'client_name': client.name,
                        'client_id': client.id,
                        'success': False,
                        'message': f"Client sync error: {error_msg}",
                        'accounts_synced': 0,
                        'accounts_failed': 0
                    })
            
            # Generate summary
            overall_success = clients_failed == 0
            
            result = {
                'success': overall_success,
                'clients_processed': clients_processed,
                'clients_failed': clients_failed,
                'total_clients': clients.count(),
                'total_accounts_synced': total_accounts_synced,
                'total_accounts_failed': total_accounts_failed,
                'client_results': client_results
            }
            
            if overall_success:
                result['message'] = f"Successfully synced all {clients_processed} clients ({total_accounts_synced} accounts)"
            else:
                result['message'] = f"Synced {clients_processed - clients_failed}/{clients_processed} clients successfully"
            
            logger.info(f"Bulk sync completed: {result['message']}")
            return result
            
        except Exception as e:
            logger.error(f"Error in bulk sync for tenant {self.tenant.id}: {str(e)}")
            return {
                'success': False,
                'message': f"Bulk sync error: {str(e)}",
                'clients_processed': 0,
                'total_accounts_synced': 0,
                'total_accounts_failed': 0
            }
    
    def get_data_freshness_info(self):
        """
        Get data freshness information for all clients in the tenant
        
        Returns:
            dict: Data freshness summary
        """
        try:
            from ..models import GoogleAdsCampaign
            
            clients = Client.objects.filter(
                tenant=self.tenant,
                is_active=True
            )
            
            freshness_info = {
                'total_clients': clients.count(),
                'clients_with_data': 0,
                'clients_fresh': 0,  # < 6 hours
                'clients_stale': 0,  # 6-24 hours  
                'clients_very_stale': 0,  # > 24 hours
                'clients_never_synced': 0,
                'oldest_sync': None,
                'newest_sync': None,
                'client_details': []
            }
            
            for client in clients:
                # Get most recent campaign sync for this client
                latest_campaign = GoogleAdsCampaign.objects.filter(
                    client_account__client=client,
                    client_account__is_active=True
                ).order_by('-last_synced').first()
                
                client_info = {
                    'client_name': client.name,
                    'client_id': client.id,
                    'last_synced': None,
                    'freshness_status': 'never_synced',
                    'hours_since_sync': None
                }
                
                if latest_campaign and latest_campaign.last_synced:
                    client_info['last_synced'] = latest_campaign.last_synced
                    
                    # Calculate time since sync
                    time_since_sync = timezone.now() - latest_campaign.last_synced
                    hours_since = time_since_sync.total_seconds() / 3600
                    client_info['hours_since_sync'] = hours_since
                    
                    # Categorize freshness
                    if hours_since < 6:
                        client_info['freshness_status'] = 'fresh'
                        freshness_info['clients_fresh'] += 1
                    elif hours_since < 24:
                        client_info['freshness_status'] = 'stale'
                        freshness_info['clients_stale'] += 1
                    else:
                        client_info['freshness_status'] = 'very_stale'
                        freshness_info['clients_very_stale'] += 1
                    
                    freshness_info['clients_with_data'] += 1
                    
                    # Track oldest and newest syncs
                    if freshness_info['oldest_sync'] is None or latest_campaign.last_synced < freshness_info['oldest_sync']:
                        freshness_info['oldest_sync'] = latest_campaign.last_synced
                    
                    if freshness_info['newest_sync'] is None or latest_campaign.last_synced > freshness_info['newest_sync']:
                        freshness_info['newest_sync'] = latest_campaign.last_synced
                        
                else:
                    freshness_info['clients_never_synced'] += 1
                
                freshness_info['client_details'].append(client_info)
            
            return freshness_info
            
        except Exception as e:
            logger.error(f"Error getting data freshness info: {str(e)}")
            return {
                'total_clients': 0,
                'error': str(e)
            }
    def intelligent_sync_all_clients(self, freshness_hours=24, date_range_days=30):
        """
        Intelligently sync only clients with stale data (older than freshness_hours)
        
        Args:
            freshness_hours: Only sync data older than this many hours
            date_range_days: Number of days to sync for each client
            
        Returns:
            dict: Sync results with freshness information
        """
        try:
            logger.info(f"Starting intelligent sync for tenant {self.tenant.name} (freshness: {freshness_hours}h)")
            
            # Get all active clients
            clients = Client.objects.filter(
                tenant=self.tenant,
                is_active=True
            )
            
            if not clients.exists():
                return {
                    "success": True,
                    "message": "No active clients found",
                    "clients_processed": 0,
                    "clients_skipped": 0,
                    "total_accounts_synced": 0,
                    "total_accounts_failed": 0
                }
            
            # Check data freshness for each client - simplified approach
            clients_to_sync = []
            clients_skipped = []
            
            for client in clients:
                # Simple freshness check based on last campaign sync
                latest_campaign = GoogleAdsCampaign.objects.filter(
                    client_account__client=client,
                    client_account__is_active=True
                ).order_by("-last_synced").first()
                
                needs_sync = True
                age_display = "Never synced"
                
                if latest_campaign and latest_campaign.last_synced:
                    age_hours = (timezone.now() - latest_campaign.last_synced).total_seconds() / 3600
                    needs_sync = age_hours > freshness_hours
                    
                    if age_hours < 1:
                        age_display = f"{int(age_hours * 60)}m ago"
                    elif age_hours < 24:
                        age_display = f"{int(age_hours)}h ago"
                    else:
                        age_display = f"{int(age_hours / 24)}d ago"
                
                if needs_sync:
                    clients_to_sync.append(client)
                    logger.info(f"🔄 Client {client.name} needs sync - data age: {age_display}")
                else:
                    clients_skipped.append(client)
                    logger.info(f"⏭️ Client {client.name} skipped - data is fresh ({age_display})")
            
            logger.info(f"📋 Intelligent sync plan: {len(clients_to_sync)} clients to sync, {len(clients_skipped)} skipped")
            
            if not clients_to_sync:
                return {
                    "success": True,
                    "message": f"All {len(clients)} clients have fresh data (< {freshness_hours}h old)",
                    "clients_processed": 0,
                    "clients_skipped": len(clients_skipped),
                    "total_accounts_synced": 0,
                    "total_accounts_failed": 0
                }
            
            # Sync only clients that need it
            clients_processed = 0
            clients_failed = 0
            total_accounts_synced = 0
            total_accounts_failed = 0
            client_results = []
            
            for client in clients_to_sync:
                try:
                    result = self.sync_client_performance_data(client)
                    clients_processed += 1
                    total_accounts_synced += result["accounts_synced"]
                    total_accounts_failed += result["accounts_failed"]
                    
                    client_results.append({
                        "client_name": client.name,
                        "client_id": client.id,
                        "success": result["success"],
                        "message": result["message"],
                        "accounts_synced": result["accounts_synced"],
                        "accounts_failed": result["accounts_failed"]
                    })
                    
                    if not result["success"]:
                        clients_failed += 1
                        
                except Exception as e:
                    clients_failed += 1
                    error_msg = str(e)
                    logger.error(f"Error processing client {client.name}: {error_msg}")
                    
                    client_results.append({
                        "client_name": client.name,
                        "client_id": client.id,
                        "success": False,
                        "message": f"Client sync error: {error_msg}",
                        "accounts_synced": 0,
                        "accounts_failed": 0
                    })
            
            # Generate summary
            overall_success = clients_failed == 0
            
            result = {
                "success": overall_success,
                "clients_processed": clients_processed,
                "clients_skipped": len(clients_skipped),
                "clients_failed": clients_failed,
                "total_clients": clients.count(),
                "total_accounts_synced": total_accounts_synced,
                "total_accounts_failed": total_accounts_failed,
                "client_results": client_results
            }
            
            if overall_success:
                if clients_processed > 0:
                    result["message"] = f"Intelligently synced {clients_processed} clients ({total_accounts_synced} accounts), skipped {len(clients_skipped)} with fresh data"
                else:
                    result["message"] = f"All {len(clients)} clients have fresh data (< {freshness_hours}h old)"
            else:
                result["message"] = f"Synced {clients_processed - clients_failed}/{clients_processed} clients successfully"
            
            logger.info(f"✅ Intelligent sync completed: {result['message']}")
            return result
            
        except Exception as e:
            logger.error(f"Error in intelligent sync for tenant {self.tenant.id}: {str(e)}")
            return {
                "success": False,
                "message": f"Intelligent sync error: {str(e)}",
                "clients_processed": 0,
                "clients_skipped": 0,
                "total_accounts_synced": 0,
                "total_accounts_failed": 0
            }

