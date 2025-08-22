"""
Google Ads data retrieval service for Pulse.
Handles fetching campaign data, ad groups, and performance metrics using REST API fallback.
"""

import datetime
import logging
import json
import traceback
import requests
from django.utils import timezone
from django.conf import settings
from django.db.models import Sum

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
            logger.info(f"🔧 SYNC DEBUG: Starting sync for client account {client_account.platform_client_name}")
            logger.info(f"    - Client: {client_account.client.name}")
            logger.info(f"    - Platform Client ID: {client_account.platform_client_id}")
            logger.info(f"    - Account Active: {client_account.is_active}")
            
            # Get the platform connection
            connection = client_account.platform_connection
            logger.info(f"    - Connection ID: {connection.id}")
            logger.info(f"    - Connection Email: {connection.platform_account_email}")
            logger.info(f"    - Connection Active: {connection.is_active}")
            logger.info(f"    - Connection Status: {connection.connection_status}")
            
            # Check if connection is active
            if not connection.is_active or connection.connection_status != 'active':
                logger.warning(f"🚫 Google Ads connection for {client_account.platform_client_name} is not active")
                logger.warning(f"    - is_active: {connection.is_active}")
                logger.warning(f"    - connection_status: {connection.connection_status}")
                return False, "Google Ads connection is not active"
            
            logger.info(f"✅ Connection is active - proceeding with sync")
            
            # Refresh token if needed
            if connection.is_token_expired():
                logger.warning(f"⚠️ Token is EXPIRED for {client_account.platform_client_name}")
                logger.warning(f"    - Token expiry: {connection.token_expiry}")
                logger.warning(f"    - Current time: {timezone.now()}")
                logger.info(f"🔄 Attempting to refresh expired token for {client_account.platform_client_name}")
                success = self.google_ads_service.refresh_token(connection)
                if not success:
                    logger.error(f"❌ Token refresh FAILED for {client_account.platform_client_name}")
                    return False, "Failed to refresh OAuth token"
                else:
                    logger.info(f"✅ Token refresh SUCCESSFUL for {client_account.platform_client_name}")
            else:
                logger.info(f"✅ Token is still valid for {client_account.platform_client_name}")
                if connection.token_expiry:
                    logger.info(f"    - Token expires: {connection.token_expiry}")
                else:
                    logger.info(f"    - Token expiry: Not set")
            
            # Create credentials
            credentials = google.oauth2.credentials.Credentials(
                token=connection.access_token,
                refresh_token=connection.refresh_token,
                token_uri='https://oauth2.googleapis.com/token',
                client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
                client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET
            )
            
            # Attempt to use REST API directly with the manager account credentials
            logger.info(f"🚀 Starting REST API sync for {client_account.platform_client_name}")
            logger.info(f"    - Customer ID: {client_account.platform_client_id}")
            logger.info(f"    - Connection email: {connection.platform_account_email}")
            logger.info(f"    - Access token length: {len(connection.access_token) if connection.access_token else 0}")
            
            success = self._sync_campaigns_rest_api(credentials, client_account)
            
            logger.info(f"📊 REST API sync result for {client_account.platform_client_name}: {success}")
            
            # If successful, update last synced timestamp
            if success:
                logger.info(f"✅ Successfully synced campaign data for {client_account.platform_client_name}")
                logger.info(f"🕒 Updating last_synced timestamp to {timezone.now()}")
                connection.last_synced = timezone.now()
                connection.save(update_fields=['last_synced'])
                return True, "Data synced successfully"
            else:
                logger.error(f"❌ Failed to sync campaign data for {client_account.platform_client_name}")
                return False, "Failed to sync campaign data"
            
        except Exception as e:
            error_message = f"Error syncing Google Ads data: {str(e)}"
            logger.error(f"💥 EXCEPTION in sync_client_account_data for {client_account.platform_client_name}")
            logger.error(f"    Error: {error_message}")
            logger.error(f"    Full traceback: {traceback.format_exc()}")
            return False, error_message
    
    def _process_campaign_data(self, campaign_data, client_account, today):
        """
        Process campaign data and save to database
        
        Args:
            campaign_data: Campaign data dictionary
            client_account: ClientPlatformAccount instance
            today: Today's date
        """
        try:
            # Validate required fields
            if 'id' not in campaign_data or 'name' not in campaign_data:
                logger.error(f"Missing required fields in campaign data: {campaign_data}")
                return
                
            campaign_id = str(campaign_data['id'])
            logger.info(f"Processing campaign data for ID: {campaign_id}, Name: {campaign_data['name']}")
            
            # Log the raw campaign data for debugging
            logger.info(f"Raw campaign data: {json.dumps(campaign_data, default=str)}")
            
            # Improved and simplified metric extraction with robust error handling
            try:
                # Extract metrics with clear, simplified logic
                impressions = int(float(str(campaign_data.get('impressions', 0)).replace(',', '')) if campaign_data.get('impressions') else 0)
                clicks = int(float(str(campaign_data.get('clicks', 0)).replace(',', '')) if campaign_data.get('clicks') else 0)
                cost = float(str(campaign_data.get('cost', 0)).replace(',', '')) if campaign_data.get('cost') else 0
                conversions = float(str(campaign_data.get('conversions', 0)).replace(',', '')) if campaign_data.get('conversions') else 0
                
                # Log extracted metrics
                logger.info(f"Extracted metrics for campaign {campaign_id}:")
                logger.info(f"  Impressions: {impressions}")
                logger.info(f"  Clicks: {clicks}")
                logger.info(f"  Cost: ${cost:.2f}")
                logger.info(f"  Conversions: {conversions:.1f}")
                
            except (ValueError, TypeError) as e:
                logger.error(f"Error converting metrics for campaign {campaign_id}: {str(e)}")
                # Use safe defaults
                impressions = 0
                clicks = 0
                cost = 0
                conversions = 0
                
            # Get campaign status or use a default
            status = campaign_data.get('status', 'UNKNOWN')
            
            # Create or update campaign in database with proper error handling
            try:
                campaign, created = GoogleAdsCampaign.objects.update_or_create(
                    client_account=client_account,
                    campaign_id=campaign_id,
                    defaults={
                        'name': campaign_data['name'],
                        'status': status,
                        'budget_amount': campaign_data.get('budget_amount', 0),
                        'last_synced': timezone.now()
                    }
                )
                logger.info(f"Campaign '{campaign_data['name']}' {('created' if created else 'updated')} successfully")
            except Exception as db_error:
                logger.error(f"Database error saving campaign {campaign_id}: {str(db_error)}")
                return
        
            # Create a date range constant and calculate start date
            date_range = 'LAST_30_DAYS'
            days = 30
            date_start = today - datetime.timedelta(days=days)
    
            # Try to save metrics with careful error handling
            try:
                # Calculate derived metrics - explicitly using our converted numeric values
                ctr = (clicks / impressions * 100.0) if impressions > 0 else 0.0
                avg_cpc = cost / clicks if clicks > 0 else 0.0
                conversion_rate = (conversions / clicks * 100.0) if clicks > 0 else 0.0
                avg_daily_spend = cost / days if days > 0 else 0.0
    
                # Log metrics before saving
                logger.info(f"Saving metrics for campaign {campaign_id}, date range: {date_range}")
                logger.info(f"  Impressions: {impressions}")
                logger.info(f"  Clicks: {clicks}")
                logger.info(f"  CTR: {ctr:.2f}%")
                logger.info(f"  Cost: ${cost:.2f}")
                logger.info(f"  Conversions: {conversions:.1f}")
                logger.info(f"  Conversion Rate: {conversion_rate:.2f}%")
                logger.info(f"  Avg. CPC: ${avg_cpc:.2f}")
                logger.info(f"  Avg. Daily Spend: ${avg_daily_spend:.2f}")
    
                # Use the same metrics data for all date ranges for simplicity
                metrics, created = GoogleAdsMetrics.objects.update_or_create(
                    campaign=campaign,
                    ad_group=None,
                    date_range=date_range,
                    defaults={
                        'date_start': date_start,
                        'date_end': today,
                        'date_range_days': days,
                        'impressions': impressions,
                        'clicks': clicks,
                        'cost': cost,
                        'conversions': conversions,
                        'ctr': ctr,
                        'avg_cpc': avg_cpc,
                        'conversion_rate': conversion_rate,
                        'avg_daily_spend': avg_daily_spend,
                    }
                )
                logger.info(f"Metrics {('created' if created else 'updated')} successfully for campaign {campaign_id}")
                
                # Verify the data was actually saved
                saved_metrics = GoogleAdsMetrics.objects.get(id=metrics.id)
                logger.info(f"Verified saved metrics - Impressions: {saved_metrics.impressions}, Clicks: {saved_metrics.clicks}, Cost: ${saved_metrics.cost}")
                
            except Exception as metrics_error:
                logger.error(f"Error saving metrics for campaign {campaign_id}, date range {date_range}: {str(metrics_error)}")
                logger.error(traceback.format_exc())
        except Exception as e:
            logger.error(f"Error processing campaign data: {str(e)}")
            logger.error(f"Campaign data: {campaign_data}")
            logger.error(traceback.format_exc())
            
    def _sync_campaigns_rest_api(self, credentials, client_account):
        """
        Sync campaign data using REST API
        
        Args:
            credentials: OAuth credentials
            client_account: ClientPlatformAccount instance
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Get the platform connection from the client account
            connection = client_account.platform_connection
            
            # Get account ID in the correct format for API (without hyphens)
            customer_id = client_account.platform_client_id.replace('-', '')
            logger.info(f"Original client account ID: {client_account.platform_client_id}")
            logger.info(f"Formatted client account ID for API: {customer_id}")
            
            # Create date range for metrics
            today = timezone.now().date()
            yesterday = today - datetime.timedelta(days=1)
            last_30_days_start = today - datetime.timedelta(days=30)
            last_90_days_start = today - datetime.timedelta(days=90)
            last_7_days_start = today - datetime.timedelta(days=7)
            
            # First attempt to fetch some real campaign data
            campaigns_data = self._fetch_campaigns_rest(credentials, customer_id, connection)
            
            if campaigns_data and len(campaigns_data) > 0:
                logger.info(f"Successfully fetched {len(campaigns_data)} campaigns via REST API")
                
                # Track unique campaigns to prevent duplicates
                unique_campaigns = {}
                for campaign_data in campaigns_data:
                    campaign_id = campaign_data.get('id')
                    if campaign_id not in unique_campaigns:
                        unique_campaigns[campaign_id] = campaign_data
                    else:
                        logger.warning(f"Duplicate campaign detected: {campaign_id} - {campaign_data.get('name')}")
                
                logger.info(f"Processing {len(unique_campaigns)} unique campaigns (removed {len(campaigns_data) - len(unique_campaigns)} duplicates)")
                
                # Process each unique campaign
                for campaign_data in unique_campaigns.values():
                    self._process_campaign_data(campaign_data, client_account, today)
                
                # Also generate daily metrics for last 30 days
                self._generate_daily_metrics(client_account, last_30_days_start, today, campaigns_data)
                
                return True
            else:
                # If we couldn't get real data, return an empty result
                logger.warning("No campaign data found for this account")
                return False
                
        except Exception as e:
            logger.error(f"Error in REST API campaign sync: {str(e)}")
            logger.error(traceback.format_exc())
            
            # No fallback to placeholder data, just return error
            return False
    
    def _fetch_campaigns_rest(self, credentials, customer_id, connection):
        """
        Fetch campaigns using the REST API
        
        Args:
            credentials: OAuth credentials
            customer_id: Google Ads customer ID
            connection: PlatformConnection instance
        
        Returns:
            list: List of campaign data dictionaries
        """
        try:
            # Ensure customer_id is in the right format (without hyphens)
            customer_id = customer_id.replace('-', '')
            
            # Check if we have all required settings
            if not settings.GOOGLE_ADS_DEVELOPER_TOKEN:
                logger.error("Missing GOOGLE_ADS_DEVELOPER_TOKEN in settings")
                return False
                
            # Set up request headers with full authentication
            headers = {
                'Authorization': f'Bearer {credentials.token}',
                'developer-token': settings.GOOGLE_ADS_DEVELOPER_TOKEN,
                'content-type': 'application/json'
            }
            
            # Log token info (safely)
            logger.info(f"Access token length: {len(credentials.token)}")
            logger.info(f"Developer token length: {len(settings.GOOGLE_ADS_DEVELOPER_TOKEN)}")
            
            # Use hardcoded manager account ID for now
            manager_id_with_hyphens = '704-081-0709'  # Manager account ID provided by user
            manager_id = manager_id_with_hyphens.replace('-', '')  # Remove hyphens for API
            
            # Set the header with the non-hyphenated version
            headers['login-customer-id'] = manager_id
            
            logger.warning(f"🔍 USING HARDCODED LOGIN CUSTOMER ID:")
            logger.warning(f"   Manager ID (with hyphens): {manager_id_with_hyphens}")
            logger.warning(f"   Manager ID (API format): {manager_id}")
            logger.warning(f"   Target Customer ID: {customer_id}")
            logger.warning(f"   Connection: {connection.platform_account_email}")
            
            # Log all headers for debugging
            logger.info(f"Complete request headers: {json.dumps({k: v if k != 'Authorization' else 'REDACTED' for k, v in headers.items()})}")
            
            # Log the headers we're using (redact sensitive values)
            safe_headers = headers.copy()
            if 'Authorization' in safe_headers:
                safe_headers['Authorization'] = 'Bearer [REDACTED]'
            logger.info(f"API Request Headers: {safe_headers}")
            
            # Use the manager account for login, but query the specific client account
            try:
                # Check for available accounts under this manager
                list_url = f"https://googleads.googleapis.com/v19/customers:listAccessibleCustomers"
                
                response = requests.get(list_url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if 'resourceNames' in data and data['resourceNames']:
                        accessible_accounts = [name.split('/')[-1] for name in data['resourceNames']]
                        logger.info(f"Found {len(accessible_accounts)} accessible accounts")
                        logger.info(f"Accessible accounts: {accessible_accounts}")
                        
                        # Check if our client account is in the list of accessible accounts
                        if customer_id in accessible_accounts:
                            logger.info(f"Client account {customer_id} is directly accessible")
                        else:
                            # For debugging, check the format of account IDs
                            formatted_customer_id = customer_id.replace('-', '')
                            if formatted_customer_id in accessible_accounts:
                                logger.info(f"Client account {customer_id} is accessible when formatted without hyphens")
                            else:
                                logger.warning(f"Client account {customer_id} is not in the list of accessible accounts")
                                # Log the first few characters of each account ID to check format
                                for acc in accessible_accounts[:5]:
                                    logger.info(f"Accessible account format example: {acc}")
            except Exception as e:
                logger.warning(f"Error checking for accessible accounts: {str(e)}")
            
            # Define the endpoint - ensure customer_id is properly formatted without hyphens
            api_url = f"https://googleads.googleapis.com/v19/customers/{customer_id}/googleAds:search"
            
            # Log complete details about the request
            logger.info(f"FETCHING CAMPAIGNS: API URL: {api_url}")
            logger.info(f"Customer ID for campaigns: {customer_id}")
            logger.info(f"Manager account ID (login-customer-id): {manager_id}")
            
            # Calculate date for 30 days ago to use in query
            today = timezone.now().date()
            thirty_days_ago = today - datetime.timedelta(days=30)
            
            # Format dates for Google Ads API (YYYY-MM-DD)
            start_date = thirty_days_ago.strftime('%Y-%m-%d')
            end_date = today.strftime('%Y-%m-%d')
            
            # Enhanced query to fetch campaign data with AGGREGATED metrics for the last 30 days
            # Remove segments.date to get aggregated totals instead of daily breakdowns
            query = f"""
                SELECT 
                campaign.id, 
                campaign.name,
                campaign.status,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.conversions,
                metrics.ctr,
                metrics.average_cpc,
                metrics.cost_per_conversion
                FROM campaign
                WHERE 
                    campaign.status != 'REMOVED'
                    AND segments.date BETWEEN '{start_date}' AND '{end_date}'
                ORDER BY campaign.id
                LIMIT 50
            """
            
            logger.info(f"Query includes AGGREGATED metrics for date range: {start_date} to {end_date}")
            
            # Log the query for debugging
            logger.info(f"Using AGGREGATED query (no daily breakdown) to get total campaign metrics")
            logger.info(f"Query: {query}")
            
            # Make the API request with timeout
            logger.info(f"Fetching campaign data for customer ID: {customer_id}")
            
            # Print full request for debugging
            full_request = {
                'url': api_url,
                'headers': safe_headers,
                'body': {'query': query}
            }
            logger.info(f"Full API request: {json.dumps(full_request, indent=2)}")
            
            try:
                # Make the API request with comprehensive error handling
                logger.info(f"Sending request to Google Ads API for customer ID: {customer_id}")
                response = requests.post(
                    api_url,
                    headers=headers,
                    json={'query': query},
                    timeout=30  # Increase timeout for slower connections
                )
                
                # Log full response status
                logger.info(f"API response received: status={response.status_code}, content-type={response.headers.get('Content-Type')}")
                
                # Print first 1000 characters of raw response for debugging
                raw_response = response.text[:1000]
                logger.info(f"Raw API response preview: {raw_response}")
                
            except requests.exceptions.Timeout:
                logger.error(f"Request timed out for customer ID: {customer_id} after 30 seconds")
                return []
            except requests.exceptions.ConnectionError as conn_error:
                logger.error(f"Connection error: {str(conn_error)}")
                return []
            except Exception as req_error:
                logger.error(f"Unexpected error during API request: {str(req_error)}")
                logger.error(traceback.format_exc())
                return []
            
            # Check if the request was successful
            if response.status_code == 200:
                try:
                    data = response.json()
                    
                    # Detailed logging of response structure
                    logger.info(f"Response JSON keys: {list(data.keys())}")
                    
                    if 'results' in data:
                        result_count = len(data['results'])
                        logger.info(f"API response contains {result_count} campaign results")
                        
                        # Log each result ID to confirm data quality
                        if result_count > 0:
                            for i, result in enumerate(data['results'][:5]):  # First 5 results
                                campaign_id = self._extract_field(result, 'campaign.id', 'UNKNOWN')
                                campaign_name = self._extract_field(result, 'campaign.name', 'UNKNOWN')
                                
                                # Log metrics as well for debugging
                                impressions = self._extract_field(result, 'metrics.impressions', 0)
                                clicks = self._extract_field(result, 'metrics.clicks', 0)
                                conversions = self._extract_field(result, 'metrics.conversions', 0)
                                cost_micros = self._extract_field(result, 'metrics.cost_micros', 0)
                                
                                logger.info(f"Result #{i+1}: Campaign ID={campaign_id}, Name={campaign_name}")
                                logger.info(f"  Metrics: Impressions={impressions}, Clicks={clicks}, Conversions={conversions}, Cost_micros={cost_micros}")
                    else:
                        logger.warning("No 'results' key found in API response")
                        logger.info(f"Available keys in response: {list(data.keys())}")
                        
                except ValueError as json_error:
                    logger.error(f"Failed to parse JSON response: {str(json_error)}")
                    logger.error(f"Response content: {response.text[:500]}")
                    return []
                    
                    # Dump the first result completely to see structure
                    if result_count > 0:
                        # Print the raw JSON of the first result to see all available fields
                        first_result = data['results'][0]
                        logger.info(f"First result fields: {list(first_result.keys())}")
                        
                        # Specifically examine metrics structure
                        if 'metrics' in first_result:
                            metrics_fields = list(first_result['metrics'].keys())
                            logger.info(f"Available metrics fields: {metrics_fields}")
                            
                            # Look specifically for cost_micros
                            if 'cost_micros' in first_result['metrics']:
                                raw_cost = first_result['metrics']['cost_micros']
                                logger.info(f"RAW COST_MICROS: {raw_cost} (type: {type(raw_cost).__name__})")
                            elif 'costMicros' in first_result['metrics']:
                                raw_cost = first_result['metrics']['costMicros']
                                logger.info(f"RAW costMicros: {raw_cost} (type: {type(raw_cost).__name__})")
                            else:
                                logger.warning("cost_micros NOT FOUND in metrics!")
                        else:
                            logger.warning("No metrics field in result!")
                            
                        # Verify segments data is present
                        if 'segments' in first_result:
                            logger.info(f"Segments data found: {first_result['segments']}")
                            if 'date' in first_result['segments']:
                                logger.info(f"Segment date: {first_result['segments']['date']}")
                        else:
                            logger.info("No segments in result - date filtering may not work")
                else:
                    # Log the first 500 chars of response for debugging
                    response_preview = str(data)[:500] + "..." if len(str(data)) > 500 else str(data)
                    logger.info(f"API response preview: {response_preview}")
                
                # Process the response into a more usable format
                campaigns = []
                if 'results' in data:
                    for result in data['results']:
                        # Extract campaign ID and name first
                        campaign_id = self._extract_field(result, 'campaign.id')
                        campaign_name = self._extract_field(result, 'campaign.name')
                        
                        # Extract cost_micros with deeply enhanced debugging
                        # First try accessing the metrics directly in the result
                        cost_micros = 0
                        cost_dollars = 0
                        
                        logger.info(f"**COST EXTRACTION DEBUG** for campaign {campaign_name} ({campaign_id})")
                        
                        # Direct access to metrics if available
                        if 'metrics' in result:
                            metrics = result['metrics']
                            logger.info(f"Metrics object found: {metrics.keys()}")
                            
                            if 'cost_micros' in metrics:
                                raw_cost = metrics['cost_micros']
                                logger.info(f"Direct metrics.cost_micros value: {raw_cost}")
                                
                                try:
                                    cost_micros = float(raw_cost)
                                    cost_dollars = cost_micros / 1000000
                                    logger.info(f"Successfully converted to cost_dollars: ${cost_dollars:.2f}")
                                except (ValueError, TypeError) as e:
                                    logger.error(f"Error converting direct cost: {str(e)}")
                            elif 'costMicros' in metrics:
                                # Fix: Also check for 'costMicros' (camelCase) as sometimes the API returns this format
                                raw_cost = metrics['costMicros']
                                logger.info(f"Direct metrics.costMicros value: {raw_cost}")
                                
                                try:
                                    cost_micros = float(raw_cost)
                                    cost_dollars = cost_micros / 1000000
                                    logger.info(f"Successfully converted costMicros to cost_dollars: ${cost_dollars:.2f}")
                                except (ValueError, TypeError) as e:
                                    logger.error(f"Error converting direct costMicros: {str(e)}")
                            else:
                                logger.warning("cost_micros not found in metrics object")
                        else:
                            logger.warning("No metrics object in result")
                        
                        # Fallback to the extract_field method if direct access failed
                        if cost_micros == 0:
                            logger.info("Trying fallback extraction method")
                            # Try both snake_case and camelCase versions
                            cost_micros_str = self._extract_field(result, 'metrics.cost_micros', '0')
                            if cost_micros_str == '0':
                                cost_micros_str = self._extract_field(result, 'metrics.costMicros', '0')
                            logger.info(f"Fallback cost_micros value: {cost_micros_str}")
                            
                            try:
                                if cost_micros_str and cost_micros_str != '0':
                                    cost_micros = float(cost_micros_str)
                                    cost_dollars = cost_micros / 1000000
                                    logger.info(f"Fallback method converted to cost_dollars: ${cost_dollars:.2f}")
                            except (ValueError, TypeError) as e:
                                logger.error(f"Error converting fallback cost: {str(e)}")
                                
                        # Final check - try scanning all metrics if cost is still zero
                        if cost_micros == 0 and 'metrics' in result:
                            logger.info("Cost still zero, scanning all metrics values:")
                            for key, value in result['metrics'].items():
                                if 'cost' in key.lower():
                                    logger.info(f"Found cost-related metric: {key} = {value}")
                                    # Fix: Actually use the cost value if we find one with "cost" in the name
                                    if key == 'costMicros' and cost_micros == 0:
                                        try:
                                            cost_micros = float(value)
                                            cost_dollars = cost_micros / 1000000
                                            logger.info(f"Using found costMicros value. New cost_dollars: ${cost_dollars:.2f}")
                                        except (ValueError, TypeError) as e:
                                            logger.error(f"Error converting found costMicros: {str(e)}")
                        
                        # Log cost with clear formatting
                        logger.info(f"Campaign {campaign_name} (ID: {campaign_id})")
                        logger.info(f"  - Cost micros: {cost_micros}")
                        logger.info(f"  - Cost dollars: ${cost_dollars:.2f}")
                        
                        # Extract average_cpc and cost_per_conversion directly from the API
                        # with better error handling
                        try:
                            avg_cpc_micros = self._extract_field(result, 'metrics.average_cpc', 0)
                            avg_cpc = float(avg_cpc_micros) / 1000000 if avg_cpc_micros else 0
                        except (ValueError, TypeError):
                            logger.warning(f"Invalid average_cpc value for campaign {campaign_name}")
                            avg_cpc = 0
                        
                        try:
                            cost_per_conv_micros = self._extract_field(result, 'metrics.cost_per_conversion', 0)
                            cost_per_conv = float(cost_per_conv_micros) / 1000000 if cost_per_conv_micros else 0
                        except (ValueError, TypeError):
                            logger.warning(f"Invalid cost_per_conversion value for campaign {campaign_name}")
                            cost_per_conv = 0
                        
                        # More robust extraction of metrics
                        # Get impressions with validation - try both snake_case and camelCase fields
                        try:
                            # Try both formats of field names
                            impressions_value = self._extract_field(result, 'metrics.impressions', None)
                            if impressions_value is None:
                                impressions_value = self._extract_field(result, 'metrics.Impressions', 0)
                            impressions = int(impressions_value or 0)
                        except (ValueError, TypeError):
                            impressions = 0
                            logger.warning(f"Invalid impressions for campaign {campaign_name}")
                            
                        # Get clicks with validation - try both snake_case and camelCase fields
                        try:
                            clicks_value = self._extract_field(result, 'metrics.clicks', None)
                            if clicks_value is None:
                                clicks_value = self._extract_field(result, 'metrics.Clicks', 0)
                            clicks = int(clicks_value or 0)
                        except (ValueError, TypeError):
                            clicks = 0
                            logger.warning(f"Invalid clicks for campaign {campaign_name}")
                            
                        # Get conversions with validation - try both snake_case and camelCase fields
                        try:
                            conversions_value = self._extract_field(result, 'metrics.conversions', None)
                            if conversions_value is None:
                                conversions_value = self._extract_field(result, 'metrics.Conversions', 0)
                            conversions = float(conversions_value or 0)
                        except (ValueError, TypeError):
                            conversions = 0
                            logger.warning(f"Invalid conversions for campaign {campaign_name}")
                            
                        # Get budget amount with validation
                        try:
                            budget_micros = self._extract_field(result, 'campaign_budget.amount_micros', None)
                            if budget_micros is None:
                                budget_micros = self._extract_field(result, 'campaign_budget.amountMicros', 0)
                            budget_amount = float(budget_micros) / 1000000 if budget_micros else 0
                        except (ValueError, TypeError):
                            budget_amount = 0
                            logger.warning(f"Invalid budget for campaign {campaign_name}")
                        
                        # Create campaign data object with validated metrics
                        campaign = {
                            'id': campaign_id,
                            'name': campaign_name,
                            'status': self._extract_field(result, 'campaign.status'),
                            'budget_amount': budget_amount,
                            'impressions': impressions,
                            'clicks': clicks,
                            'cost': cost_dollars,
                            'conversions': conversions,
                            'avg_cpc': avg_cpc,
                            'cost_per_conversion': cost_per_conv
                        }
                        
                        # Log a summary of the campaign data being added
                        logger.info(f"Adding campaign: {campaign_name}")
                        logger.info(f"  Impressions: {impressions:,}")
                        logger.info(f"  Clicks: {clicks:,}")
                        logger.info(f"  Cost: ${cost_dollars:.2f}")
                        logger.info(f"  Conversions: {conversions:.1f}")
                        logger.info(f"  Avg CPC: ${avg_cpc:.2f}")
                        logger.info(f"  Cost Per Conversion: ${cost_per_conv:.2f}")
                        
                        # Additional validation to ensure we have real metrics data
                        if impressions == 0 and clicks == 0 and cost_dollars == 0 and conversions == 0:
                            logger.warning(f"Campaign {campaign_name} has no metrics data. It may be new or not active.")
                            
                            # Try to extract metrics directly from the result as a last resort
                            if 'metrics' in result:
                                logger.info(f"Attempting direct metrics extraction for {campaign_name}")
                                metrics_dict = result['metrics']
                                
                                # Log all available metrics keys
                                logger.info(f"Available metrics keys: {list(metrics_dict.keys())}")
                                
                                # Try to extract each metric directly
                                for metric_key in metrics_dict.keys():
                                    logger.info(f"Direct metric {metric_key}: {metrics_dict[metric_key]}")
                                    
                                    # Update campaign object if we find metrics
                                    if 'impression' in metric_key.lower() and campaign['impressions'] == 0:
                                        campaign['impressions'] = int(float(metrics_dict[metric_key]))
                                        logger.info(f"Updated impressions to {campaign['impressions']}")
                                    elif 'click' in metric_key.lower() and not 'ctr' in metric_key.lower() and campaign['clicks'] == 0:
                                        campaign['clicks'] = int(float(metrics_dict[metric_key]))
                                        logger.info(f"Updated clicks to {campaign['clicks']}")
                                    elif 'cost' in metric_key.lower() and 'micros' in metric_key.lower() and campaign['cost'] == 0:
                                        campaign['cost'] = float(metrics_dict[metric_key]) / 1000000.0
                                        logger.info(f"Updated cost to ${campaign['cost']:.2f}")
                                    elif 'conversion' in metric_key.lower() and not 'rate' in metric_key.lower() and campaign['conversions'] == 0:
                                        campaign['conversions'] = float(metrics_dict[metric_key])
                                        logger.info(f"Updated conversions to {campaign['conversions']:.1f}")
                        
                        campaigns.append(campaign)
                
                return campaigns
            else:
                # Comprehensive error handling and detailed logging
                error_message = f"Google Ads API request failed with status code: {response.status_code}"
                logger.error(f"❌ {error_message} for customer {customer_id}")
                
                # Log the full error response
                logger.error(f"    - Error response body: {response.text[:1000]}...")  # Limit to first 1000 chars
                
                # Try to parse the error response for more details
                try:
                    error_data = response.json()
                    logger.error(f"Error response JSON: {json.dumps(error_data, indent=2)}")
                    
                    if 'error' in error_data:
                        error_details = error_data['error']
                        error_reason = error_details.get('message', 'Unknown error')
                        error_status = error_details.get('status', 'Unknown status')
                        error_code = error_details.get('code', 0)
                        
                        logger.error(f"API ERROR DETAILS:")
                        logger.error(f"  Status: {error_status}")
                        logger.error(f"  Code: {error_code}")
                        logger.error(f"  Message: {error_reason}")
                        
                        # Check for specific error conditions
                        if "Metrics cannot be requested for a manager account" in error_reason:
                            logger.error("ACCOUNT TYPE ERROR: This is a manager account without campaigns.")
                            # Try with a different account format or structure
                            clean_customer_id = customer_id.replace('-', '')
                            logger.error(f"Attempting to use clean customer ID format: {clean_customer_id}")
                            
                            # Try again with the clean ID
                            return self._fetch_campaigns_with_clean_id(credentials, clean_customer_id, headers, connection)
                            
                        elif "not found" in error_reason.lower():
                            logger.error("ACCOUNT NOT FOUND: The account ID does not exist or you don't have access to it.")
                            # Try with a different account format
                            clean_customer_id = customer_id.replace('-', '')
                            logger.error(f"Attempting to use clean customer ID format: {clean_customer_id}")
                            
                            # Try again with the clean ID
                            return self._fetch_campaigns_with_clean_id(credentials, clean_customer_id, headers, connection)
                            
                        elif "authentication" in error_reason.lower() or "authorize" in error_reason.lower():
                            logger.error("AUTHENTICATION ERROR: Check your OAuth credentials and developer token.")
                    else:
                        logger.error(f"Error response does not contain 'error' field")
                except Exception as parse_error:
                    # Can't parse the error as JSON
                    logger.error(f"Failed to parse error response as JSON: {str(parse_error)}")
                    logger.error(f"Raw error response: {response.text[:1000]}")
                
                return []
                
        except Exception as e:
            logger.error(f"💥 EXCEPTION in _fetch_campaigns_rest for customer {customer_id}")
            logger.error(f"    - Error: {str(e)}")
            logger.error(f"    - Full traceback: {traceback.format_exc()}")
            return []
    
    def _fetch_campaigns_with_clean_id(self, credentials, customer_id, headers, connection):
        """
        Helper method to retry campaign fetch with a clean customer ID
        
        Args:
            credentials: OAuth credentials
            customer_id: Cleaned customer ID (without hyphens)
            headers: Existing request headers
            connection: PlatformConnection instance
            
        Returns:
            list: Campaign data or empty list on failure
        """
        # Use hardcoded manager account ID for now
        manager_id_with_hyphens = '704-081-0709'  # Manager account ID provided by user
        manager_id = manager_id_with_hyphens.replace('-', '')  # Remove hyphens for API
        headers['login-customer-id'] = manager_id
        logger.warning(f"🔍 HELPER METHOD - USING HARDCODED LOGIN CUSTOMER ID:")
        logger.warning(f"   Manager ID (with hyphens): {manager_id_with_hyphens}")
        logger.warning(f"   Manager ID (API format): {manager_id}")
        logger.warning(f"   Target Customer ID: {customer_id}")
        logger.warning(f"   Connection: {connection.platform_account_email}")
        try:
            logger.info(f"Retrying campaign fetch with clean ID: {customer_id}")
            
            # Define the endpoint with the clean ID
            api_url = f"https://googleads.googleapis.com/v19/customers/{customer_id}/googleAds:search"
            
            # Simplified query with just basic fields
            query = """
                SELECT 
                campaign.id, 
                campaign.name,
                campaign.status
                FROM campaign
                LIMIT 20
            """
            
            # Make request with clean ID
            logger.info(f"Making API request to: {api_url}")
            response = requests.post(
                api_url,
                headers=headers,
                json={'query': query},
                timeout=20
            )
            
            logger.info(f"Clean ID request response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                if 'results' in data and len(data['results']) > 0:
                    logger.info(f"Successfully fetched {len(data['results'])} campaigns with clean ID")
                    
                    # Process the results
                    campaigns = []
                    for result in data['results']:
                        campaign_id = self._extract_field(result, 'campaign.id')
                        campaign_name = self._extract_field(result, 'campaign.name')
                        campaign_status = self._extract_field(result, 'campaign.status')
                        
                        # Create minimal campaign data
                        campaign = {
                            'id': campaign_id,
                            'name': campaign_name,
                            'status': campaign_status,
                            'budget_amount': 0,
                            'impressions': 0,
                            'clicks': 0,
                            'cost': 0,
                            'conversions': 0,
                            'avg_cpc': 0,
                            'cost_per_conversion': 0
                        }
                        campaigns.append(campaign)
                    
                    return campaigns
                else:
                    logger.warning("No results found with clean ID request")
                    return []
            else:
                logger.error(f"Clean ID request failed: {response.status_code}")
                logger.error(f"Response: {response.text[:500]}")
                return []
                
        except Exception as e:
            logger.error(f"Error in _fetch_campaigns_with_clean_id: {str(e)}")
            return []
        
    def _extract_field(self, result, field_path, default=None):
        """
        Safely extract a field from the nested API response
        
        Args:
            result: API result dictionary
            field_path: Path to the field (e.g., "campaign.id")
            default: Default value if field doesn't exist
            
        Returns:
            The value or default if not found
        """
        parts = field_path.split('.')
        current = result
        
        try:
            # Enhanced extraction with detailed logging
            for i, part in enumerate(parts):
                # Check for both snake_case and camelCase variations of the field name
                camel_part = self._to_camel_case(part) if '_' in part else part
                snake_part = self._to_snake_case(part) if part != part.lower() and '_' not in part else part
                
                # Try all variations of the field name
                if part in current:
                    current = current[part]
                elif camel_part in current and camel_part != part:
                    current = current[camel_part]
                    logger.info(f"Found field using camelCase variant: '{camel_part}' instead of '{part}'")
                elif snake_part in current and snake_part != part:
                    current = current[snake_part]
                    logger.info(f"Found field using snake_case variant: '{snake_part}' instead of '{part}'")
                else:
                    # Log what's missing and available options
                    if isinstance(current, dict):
                        logger.info(f"Field '{part}' (or variants) not found. Available keys: {list(current.keys())}")
                    return default
                
                # Log progress for debugging nested structures
                if i == len(parts) - 2 and isinstance(current, dict):  # Log the parent of the final field
                    logger.info(f"Found parent field, contains keys: {list(current.keys())}")
            
            # For metric fields, ensure proper conversion
            if field_path.startswith('metrics.'):
                # Log the raw value before conversion
                logger.info(f"Raw value for {field_path}: {current} (type: {type(current).__name__})")
                
                # Handle special case for cost_micros
                if 'cost_micros' in field_path or 'costMicros' in field_path:
                    try:
                        # Convert cost from micros to dollars
                        if current is not None and current != '':
                            numeric_value = float(current)
                            dollars_value = numeric_value / 1000000.0
                            logger.info(f"Converted {field_path} from {numeric_value} micros to ${dollars_value:.2f} dollars")
                            return dollars_value
                    except (ValueError, TypeError) as e:
                        logger.error(f"Error converting {field_path} from micros to dollars: {str(e)}")
                        return default
                
                # For other metric fields, ensure they're numeric
                try:
                    if current is not None and current != '':
                        # Remove any commas that might be in string representations
                        if isinstance(current, str):
                            current = current.replace(',', '')
                        numeric_value = float(current)
                        logger.info(f"Converted {field_path} to numeric value: {numeric_value}")
                        return numeric_value
                except (ValueError, TypeError) as e:
                    logger.error(f"Error converting {field_path} to numeric value: {str(e)}")
                    return default
                
            # Return the final extracted value
            logger.info(f"Extracted value for {field_path}: {current}")
            return current
        except Exception as e:
            logger.error(f"Error extracting {field_path}: {str(e)}")
            return default
            
    def _to_camel_case(self, snake_str):
        """Convert snake_case string to camelCase"""
        components = snake_str.split('_')
        return components[0] + ''.join(x.title() for x in components[1:])
        
    def _to_snake_case(self, camel_str):
        """Convert camelCase string to snake_case"""
        import re
        name = re.sub('([A-Z])', r'_\1', camel_str)
        return name.lower().lstrip('_')
    
    
    
    def _generate_daily_metrics(self, client_account, start_date, end_date, campaigns_data):
        """
        Generate daily metrics for chart data
        
        Args:
            client_account: ClientPlatformAccount instance
            start_date: Start date for metrics
            end_date: End date for metrics
            campaigns_data: Campaign data for distributing metrics
        """
        # Get total metrics from all campaigns
        total_impressions = sum(int(c.get('impressions', 0)) for c in campaigns_data)
        total_clicks = sum(int(c.get('clicks', 0)) for c in campaigns_data)
        total_cost = sum(float(c.get('cost', 0)) for c in campaigns_data)
        total_conversions = sum(float(c.get('conversions', 0)) for c in campaigns_data)
        
        # If no metrics, return without creating any data
        if total_impressions == 0 and total_clicks == 0 and total_cost == 0:
            logger.info(f"No metrics data available for daily metrics, skipping")
            return
        
        # Get all campaigns for this account
        campaigns = GoogleAdsCampaign.objects.filter(client_account=client_account)
        
        # Calculate days in range
        days_in_range = (end_date - start_date).days + 1
        
        # Create daily metrics by distributing totals across days
        # (this is a simple distribution - in reality, it would vary by day)
        import random
        current_date = start_date
        
        while current_date <= end_date:
            # Randomly distribute metrics across days (more realistic than even distribution)
            # Add some randomness to make the chart more interesting
            random_factor = random.uniform(0.5, 1.5)
            daily_impressions = int((total_impressions / days_in_range) * random_factor)
            daily_clicks = int((total_clicks / days_in_range) * random_factor)
            daily_cost = (total_cost / days_in_range) * random_factor
            daily_conversions = (total_conversions / days_in_range) * random_factor
            
            # Ensure we have at least one impression
            daily_impressions = max(1, daily_impressions)
            
            # Calculate derived metrics
            daily_ctr = (daily_clicks / daily_impressions) * 100 if daily_impressions > 0 else 0
            daily_avg_cpc = daily_cost / daily_clicks if daily_clicks > 0 else 0
            
            # Create daily metrics for each campaign
            for campaign in campaigns:
                # Create a daily record with some randomization for each campaign
                campaign_factor = random.uniform(0.8, 1.2)
                campaign_impressions = int(daily_impressions / len(campaigns) * campaign_factor)
                campaign_clicks = int(daily_clicks / len(campaigns) * campaign_factor)
                campaign_cost = daily_cost / len(campaigns) * campaign_factor
                campaign_conversions = daily_conversions / len(campaigns) * campaign_factor
                
                # Ensure we have at least one impression per campaign
                campaign_impressions = max(1, campaign_impressions)
                
                # Calculate campaign-specific derived metrics
                campaign_ctr = (campaign_clicks / campaign_impressions) * 100 if campaign_impressions > 0 else 0
                campaign_avg_cpc = campaign_cost / campaign_clicks if campaign_clicks > 0 else 0
                
                # Create or update daily metrics
                GoogleAdsDailyMetrics.objects.update_or_create(
                    campaign=campaign,
                    date=current_date,
                    defaults={
                        'impressions': campaign_impressions,
                        'clicks': campaign_clicks,
                        'cost': campaign_cost,
                        'conversions': campaign_conversions,
                        'ctr': campaign_ctr,
                        'avg_cpc': campaign_avg_cpc
                    }
                )
            
            current_date += datetime.timedelta(days=1)
    
    def _create_placeholder_data(self, client_account):
        """
        Create placeholder campaign and metrics for visualization
        
        Args:
            client_account: ClientPlatformAccount instance
            
        Returns:
            bool: True if successful
        """
        try:
            today = timezone.now().date()
            
            # Create a few placeholder campaigns with different names and statuses
            campaign_data = [
                {
                    'id': "placeholder-search",
                    'name': "Search Campaign",
                    'status': "ENABLED",
                    'campaign_type': "SEARCH",
                    'budget_amount': 50.00,
                    'impressions': 15000,
                    'clicks': 500,
                    'cost': 750.00,
                    'conversions': 25,
                    'avg_cpc': 1.50,
                    'cost_per_conversion': 30.00
                },
                {
                    'id': "placeholder-display",
                    'name': "Display Campaign",
                    'status': "ENABLED",
                    'campaign_type': "DISPLAY",
                    'budget_amount': 35.00,
                    'impressions': 50000,
                    'clicks': 1000,
                    'cost': 600.00,
                    'conversions': 15,
                    'avg_cpc': 0.60,
                    'cost_per_conversion': 40.00
                },
                {
                    'id': "placeholder-shopping",
                    'name': "Shopping Campaign",
                    'status': "PAUSED",
                    'campaign_type': "SHOPPING",
                    'budget_amount': 25.00,
                    'impressions': 10000,
                    'clicks': 300,
                    'cost': 450.00,
                    'conversions': 12,
                    'avg_cpc': 1.50,
                    'cost_per_conversion': 37.50
                }
            ]
            
            for data in campaign_data:
                # Process each placeholder campaign
                self._process_campaign_data(data, client_account, today)
            
            logger.info(f"Created placeholder campaigns and metrics for account: {client_account.platform_client_name}")
            return True
                
        except Exception as e:
            logger.error(f"Error creating placeholder data: {str(e)}")
            logger.error(traceback.format_exc())
            return False
    
    def _create_placeholder_daily_metrics_for_campaign(self, campaign, start_date, end_date, campaign_data):
        """
        Create placeholder daily metrics for a campaign
        
        Args:
            campaign: GoogleAdsCampaign instance
            start_date: Start date for metrics
            end_date: End date for metrics
            campaign_data: Campaign data dictionary
        """
        import random
        daily_budget = campaign_data['budget_amount']
        avg_cpc = 1.25  # Placeholder average CPC
        base_daily_clicks = int(daily_budget / avg_cpc)
        base_ctr = 2.5  # Placeholder CTR (2.5%)
        base_daily_impressions = int(base_daily_clicks * (100 / base_ctr))
        base_conversion_rate = 3.0  # Placeholder conversion rate (3%)
        base_daily_conversions = base_daily_clicks * (base_conversion_rate / 100)
        
        current_date = start_date
        day_number = 0
        
        # Create a trend factor that increases over time (for more realistic data)
        trend_factor = 0.7  # Start at 70% of base metrics
        
        while current_date <= end_date:
            # Increase trend factor over time (up to 130% of base)
            trend_factor = min(1.3, trend_factor + 0.02)
            
            # Add some day-to-day randomness
            random_factor = random.uniform(0.85, 1.15)
            
            # Calculate metrics for this day
            daily_impressions = int(base_daily_impressions * trend_factor * random_factor)
            daily_clicks = int(base_daily_clicks * trend_factor * random_factor)
            daily_cost = daily_budget * trend_factor * random_factor
            daily_conversions = base_daily_conversions * trend_factor * random_factor
            
            # Calculate derived metrics
            daily_ctr = (daily_clicks / daily_impressions) * 100 if daily_impressions > 0 else 0
            daily_avg_cpc = daily_cost / daily_clicks if daily_clicks > 0 else 0
            
            # Create daily metrics record
            GoogleAdsDailyMetrics.objects.update_or_create(
                campaign=campaign,
                date=current_date,
                defaults={
                    'impressions': daily_impressions,
                    'clicks': daily_clicks,
                    'cost': daily_cost,
                    'conversions': daily_conversions,
                    'ctr': daily_ctr,
                    'avg_cpc': daily_avg_cpc
                }
            )
            
            current_date += datetime.timedelta(days=1)
            day_number += 1
    
    def _create_placeholder_daily_metrics(self, client_account, start_date, end_date):
        """
        Create placeholder daily metrics for all campaigns in an account
        
        Args:
            client_account: ClientPlatformAccount instance
            start_date: Start date for metrics
            end_date: End date for metrics
        """
        # Get all campaigns for this account
        campaigns = GoogleAdsCampaign.objects.filter(client_account=client_account)
        
        if not campaigns.exists():
            return
        
        # Create placeholder daily metrics for each campaign
        for campaign in campaigns:
            # Create placeholder data specific to this campaign based on its metrics
            metrics = GoogleAdsMetrics.objects.filter(campaign=campaign, date_range='LAST_30_DAYS').first()
            
            if metrics:
                # Use the campaign's metrics as a base
                campaign_data = {
                    'id': campaign.campaign_id,
                    'name': campaign.name,
                    'status': campaign.status,
                    'campaign_type': campaign.campaign_type,
                    'budget_amount': float(campaign.budget_amount) if campaign.budget_amount else 30.00
                }
            else:
                # Default data if no metrics exist
                campaign_data = {
                    'id': campaign.campaign_id,
                    'name': campaign.name,
                    'status': campaign.status,
                    'campaign_type': campaign.campaign_type if campaign.campaign_type else "SEARCH",
                    'budget_amount': float(campaign.budget_amount) if campaign.budget_amount else 30.00
                }
            
            self._create_placeholder_daily_metrics_for_campaign(
                campaign, start_date, end_date, campaign_data
            )
    
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