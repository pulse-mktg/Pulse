"""
Google Ads Account Service
Handles account discovery, hierarchy mapping, and caching for Google Ads accounts.
"""

import logging
import requests
import json
from django.conf import settings
from django.utils import timezone
from ..models import PlatformConnection, GoogleAdsAccount, GoogleAdsAccountSync

logger = logging.getLogger(__name__)


class GoogleAdsAccountService:
    """
    Service for discovering and managing Google Ads accounts with hierarchy support
    """
    
    def __init__(self, tenant):
        self.tenant = tenant
    
    def clear_cache(self, connection):
        """
        Clear all cached Google Ads account data
        """
        try:
            # Clear cached accounts
            deleted_accounts = GoogleAdsAccount.objects.filter(platform_connection=connection).delete()
            logger.info(f"🗑️ Cleared {deleted_accounts[0]} cached accounts")
            
            # Clear sync history
            deleted_syncs = GoogleAdsAccountSync.objects.filter(platform_connection=connection).delete()
            logger.info(f"🗑️ Cleared {deleted_syncs[0]} sync records")
            
            logger.info("✅ Cache cleared successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error clearing cache: {str(e)}")
            return False
    
    def get_accounts_for_connection(self, connection, force_refresh=False):
        """
        Get Google Ads accounts for a connection, using cache or fresh API calls
        
        Args:
            connection: PlatformConnection instance
            force_refresh: If True, bypass cache and make fresh API calls
            
        Returns:
            List[dict]: List of account dictionaries with hierarchy
        """
        try:
            logger.info(f"🔄 Getting accounts for connection {connection.id} (force_refresh={force_refresh})")
            
            if force_refresh:
                logger.info("🔄 FORCE REFRESH: Clearing cache and making fresh API calls")
                self.clear_cache(connection)
                return self._fetch_accounts_from_api(connection)
            else:
                logger.info("📋 Checking cache first")
                cached_accounts = self._get_cached_accounts(connection)
                
                if cached_accounts:
                    logger.info(f"📋 Found {len(cached_accounts)} cached accounts")
                    return cached_accounts
                else:
                    logger.info("📋 No cached accounts, fetching from API")
                    return self._fetch_accounts_from_api(connection)
                    
        except Exception as e:
            logger.error(f"Error getting accounts for connection: {str(e)}")
            return []
    
    def _get_cached_accounts(self, connection):
        """
        Get accounts from cache with proper hierarchy formatting
        """
        try:
            # Get all active accounts for this connection
            accounts = GoogleAdsAccount.objects.filter(
                platform_connection=connection,
                sync_status='active'
            ).order_by('level', 'name')
            
            if not accounts.exists():
                return []
            
            # Build hierarchy structure
            account_map = {}
            root_accounts = []
            
            # First pass: create account objects
            for account in accounts:
                account_data = {
                    'id': account.account_id,
                    'name': account.name,
                    'raw_id': account.raw_account_id,
                    'is_manager': account.is_manager,
                    'currency_code': account.currency_code,
                    'time_zone': account.time_zone,
                    'status': account.status,
                    'level': account.level,
                    'parent_id': account.parent_account.account_id if account.parent_account else None,
                    'child_accounts': []
                }
                account_map[account.account_id] = account_data
                
                # Root accounts have no parent
                if not account.parent_account:
                    root_accounts.append(account_data)
            
            # Second pass: build hierarchy
            for account in accounts:
                if account.parent_account:
                    parent_id = account.parent_account.account_id
                    if parent_id in account_map:
                        account_map[parent_id]['child_accounts'].append(account_map[account.account_id])
            
            logger.info(f"📋 Built hierarchy: {len(root_accounts)} root accounts, {len(account_map)} total accounts")
            return root_accounts
            
        except Exception as e:
            logger.error(f"Error getting cached accounts: {str(e)}")
            return []
    
    def _fetch_accounts_from_api(self, connection):
        """
        Fetch accounts from Google Ads API using dynamic customer discovery
        """
        try:
            logger.info("🔗 Starting dynamic API account discovery")
            
            # Check and refresh token if needed
            if connection.is_token_expired():
                logger.info("🔄 Token expired, refreshing...")
                if not self._refresh_token(connection):
                    logger.error("❌ Token refresh failed")
                    return []
            
            # Step 1: Get all accessible customers dynamically
            accessible_customers = self._get_accessible_customers(connection)
            
            if not accessible_customers:
                logger.warning("⚠️ No accessible customers found")
                return []
            
            logger.info(f"🔍 Found {len(accessible_customers)} accessible customers to process")
            
            # Step 2: For each accessible customer, discover all accounts and hierarchy
            all_accounts = []
            processed_ids = set()
            
            for customer_id in accessible_customers:
                if customer_id in processed_ids:
                    continue
                    
                logger.info(f"🔍 Processing accessible customer: {customer_id}")
                
                # Get account hierarchy for this customer
                account_details = self._get_account_hierarchy(connection, customer_id, customer_id)
                
                if account_details:
                    for account in account_details:
                        account_id = account['id']
                        if account_id not in processed_ids:
                            all_accounts.append(account)
                            processed_ids.add(account_id)
                            logger.info(f"📋 Added account: {account['name']} ({account_id})")
                        else:
                            logger.info(f"🔄 Skipped duplicate account: {account_id}")
                else:
                    # If hierarchy query fails, try to get just the customer info
                    single_account = self._get_single_customer_info(connection, customer_id, customer_id)
                    if single_account:
                        for account in single_account:
                            account_id = account['id']
                            if account_id not in processed_ids:
                                all_accounts.append(account)
                                processed_ids.add(account_id)
                                logger.info(f"📋 Added single account: {account['name']} ({account_id})")
            
            # Step 3: Cache the results
            if all_accounts:
                logger.info(f"💾 Caching {len(all_accounts)} discovered accounts")
                self._cache_accounts(connection, all_accounts)
            else:
                logger.warning("⚠️ No accounts found after processing all accessible customers")
            
            return all_accounts
            
        except Exception as e:
            logger.error(f"Error fetching accounts from API: {str(e)}")
            return []
    
    def _get_accessible_customers(self, connection):
        """
        Get list of accessible customer IDs using REST API v20 discovery approach
        """
        try:
            logger.info("🔗 Using REST API v20 to discover accessible customers")
            
            # Since listAccessibleCustomers isn't available via REST API,
            # we'll use a discovery approach by trying to access customer info
            # and discovering accounts through the search API
            
            return self._discover_customers_via_search(connection)
            
        except Exception as e:
            logger.error(f"Error getting accessible customers: {str(e)}")
            return []
    
    def _discover_customers_via_search(self, connection):
        """
        Discover customer IDs by trying to access accounts via the search API
        """
        try:
            logger.info("🔍 Discovering customers via REST API v20 search approach")
            
            # Method 1: Try to discover through connection metadata first
            potential_customers = self._get_potential_seed_customers(connection)
            
            if potential_customers:
                logger.info(f"🔍 Found {len(potential_customers)} potential seed customers")
                
                # Try to access each potential customer and discover hierarchy
                discovered_customers = []
                
                for customer_id in potential_customers:
                    discovered = self._discover_from_seed_customer(connection, customer_id)
                    if discovered:
                        discovered_customers.extend(discovered)
                
                # Remove duplicates
                unique_customers = list(set(discovered_customers))
                
                if unique_customers:
                    logger.info(f"✅ Discovered {len(unique_customers)} unique customers: {unique_customers}")
                    return unique_customers
            
            # Method 2: Try to discover through OAuth token inspection
            logger.info("🔍 Attempting OAuth token-based customer discovery")
            return self._discover_via_oauth_token(connection)
            
        except Exception as e:
            logger.error(f"Error in customer discovery via search: {str(e)}")
            return []
    
    def _get_potential_seed_customers(self, connection):
        """
        Get potential customer IDs from various sources to use as discovery seeds
        """
        try:
            potential_customers = []
            
            # From connection metadata
            if hasattr(connection, 'platform_account_id') and connection.platform_account_id:
                clean_id = connection.platform_account_id.replace('-', '')
                potential_customers.append(clean_id)
                logger.info(f"🔍 Added seed customer from platform_account_id: {clean_id}")
            
            # From additional_data
            if hasattr(connection, 'additional_data') and connection.additional_data:
                try:
                    import json
                    data = json.loads(connection.additional_data)
                    if 'customer_id' in data:
                        clean_id = str(data['customer_id']).replace('-', '')
                        potential_customers.append(clean_id)
                        logger.info(f"🔍 Added seed customer from additional_data: {clean_id}")
                except:
                    pass
            
            # From OAuth token analysis (if possible)
            oauth_customer = self._extract_customer_from_oauth(connection)
            if oauth_customer:
                potential_customers.append(oauth_customer)
                logger.info(f"🔍 Added seed customer from OAuth token: {oauth_customer}")
            
            return list(set(potential_customers))  # Remove duplicates
            
        except Exception as e:
            logger.error(f"Error getting potential seed customers: {str(e)}")
            return []
    
    def _extract_customer_from_oauth(self, connection):
        """
        Try to extract customer ID from OAuth token or related data
        """
        try:
            # This is a placeholder for OAuth token analysis
            # In practice, you might be able to extract customer info from the token
            # or from the account that granted the OAuth access
            
            logger.info("🔍 Attempting to extract customer ID from OAuth token")
            
            # For now, we'll return None as this would require specific OAuth token analysis
            # that depends on how the OAuth was granted
            return None
            
        except Exception as e:
            logger.error(f"Error extracting customer from OAuth: {str(e)}")
            return None
    
    def _discover_from_seed_customer(self, connection, seed_customer_id):
        """
        Use a seed customer ID to discover other accessible customers
        """
        try:
            logger.info(f"🔍 Discovering customers using seed: {seed_customer_id}")
            
            discovered = []
            
            # First, verify the seed customer exists and we have access
            if self._verify_customer_access(connection, seed_customer_id):
                discovered.append(seed_customer_id)
                logger.info(f"✅ Verified access to seed customer: {seed_customer_id}")
                
                # Try to discover related customers through hierarchy queries
                hierarchy_customers = self._discover_hierarchy_customers(connection, seed_customer_id)
                if hierarchy_customers:
                    discovered.extend(hierarchy_customers)
                    logger.info(f"✅ Discovered {len(hierarchy_customers)} hierarchy customers")
            else:
                logger.warning(f"⚠️ No access to seed customer: {seed_customer_id}")
            
            return discovered
            
        except Exception as e:
            logger.error(f"Error discovering from seed customer {seed_customer_id}: {str(e)}")
            return []
    
    def _verify_customer_access(self, connection, customer_id):
        """
        Verify that we have access to a specific customer ID
        """
        try:
            headers = {
                'Authorization': f'Bearer {connection.access_token}',
                'developer-token': settings.GOOGLE_ADS_DEVELOPER_TOKEN,
                'Content-Type': 'application/json'
            }
            
            url = f"https://googleads.googleapis.com/v20/customers/{customer_id}/googleAds:search"
            
            # Simple query to test access
            query = """
                SELECT customer.id, customer.descriptive_name
                FROM customer
                LIMIT 1
            """
            
            payload = {'query': query}
            
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if 'results' in data and len(data['results']) > 0:
                    logger.info(f"✅ Verified access to customer {customer_id}")
                    return True
            
            logger.warning(f"⚠️ No access to customer {customer_id}: {response.status_code}")
            return False
            
        except Exception as e:
            logger.error(f"Error verifying customer access for {customer_id}: {str(e)}")
            return False
    
    def _discover_hierarchy_customers(self, connection, seed_customer_id):
        """
        Discover other customers through hierarchy queries
        """
        try:
            logger.info(f"🔍 Discovering hierarchy customers from seed: {seed_customer_id}")
            
            headers = {
                'Authorization': f'Bearer {connection.access_token}',
                'developer-token': settings.GOOGLE_ADS_DEVELOPER_TOKEN,
                'login-customer-id': seed_customer_id,
                'Content-Type': 'application/json'
            }
            
            url = f"https://googleads.googleapis.com/v20/customers/{seed_customer_id}/googleAds:search"
            
            # Query to find all customers in the hierarchy
            query = """
                SELECT 
                    customer_client.id,
                    customer_client.descriptive_name,
                    customer_client.manager
                FROM customer_client
                WHERE customer_client.status != 'CLOSED'
            """
            
            payload = {'query': query}
            
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                if 'results' in data:
                    discovered_customers = []
                    
                    for result in data['results']:
                        customer_client = result.get('customerClient', {})
                        customer_id = str(customer_client.get('id', ''))
                        
                        if customer_id and customer_id not in discovered_customers:
                            discovered_customers.append(customer_id)
                            logger.info(f"📋 Found hierarchy customer: {customer_id}")
                    
                    return discovered_customers
                else:
                    logger.info(f"📋 No hierarchy customers found for seed: {seed_customer_id}")
                    return []
            else:
                logger.warning(f"⚠️ Hierarchy query failed for {seed_customer_id}: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"Error discovering hierarchy customers: {str(e)}")
            return []
    
    def _discover_via_oauth_token(self, connection):
        """
        Try to discover customers through OAuth token analysis
        """
        try:
            logger.info("🔍 Attempting OAuth token-based discovery")
            
            # This would require analyzing the OAuth token to extract customer information
            # For now, we'll return empty and rely on manual customer ID provision
            
            logger.info("💡 OAuth token-based discovery not implemented")
            logger.info("💡 Please provide at least one customer ID to get started")
            
            return []
            
        except Exception as e:
            logger.error(f"Error in OAuth token discovery: {str(e)}")
            return []
                
        except Exception as e:
            logger.error(f"Error getting accessible customers via REST API: {str(e)}")
            logger.error(f"Error details: {repr(e)}")
            return []
    
    def _try_rest_api_alternatives(self, connection):
        """
        Alternative REST API methods to discover customers
        """
        try:
            logger.info("🔍 Trying alternative REST API methods for customer discovery")
            
            # Method 1: Try different API versions
            api_versions = ['v14', 'v13', 'v12']
            
            for version in api_versions:
                logger.info(f"🔍 Trying API version {version}")
                
                url = f"https://googleads.googleapis.com/{version}/customers:listAccessibleCustomers"
                
                headers = {
                    'Authorization': f'Bearer {connection.access_token}',
                    'developer-token': settings.GOOGLE_ADS_DEVELOPER_TOKEN,
                    'Content-Type': 'application/json'
                }
                
                try:
                    response = requests.get(url, headers=headers, timeout=30)
                    
                    if response.status_code == 200:
                        data = response.json()
                        if 'resourceNames' in data:
                            customer_ids = []
                            for resource_name in data['resourceNames']:
                                customer_id = resource_name.split('/')[-1]
                                customer_ids.append(customer_id)
                            
                            logger.info(f"✅ Found {len(customer_ids)} customers using {version}: {customer_ids}")
                            return customer_ids
                    else:
                        logger.info(f"⚠️ {version} failed with status {response.status_code}")
                        
                except Exception as e:
                    logger.info(f"⚠️ {version} failed with error: {str(e)}")
                    continue
            
            # Method 2: Try alternative endpoint format
            logger.info("🔍 Trying alternative endpoint format")
            
            alternative_urls = [
                "https://googleads.googleapis.com/v14/customers:listAccessibleCustomers",
                "https://googleads.googleapis.com/v14/customers/listAccessibleCustomers",
                "https://googleads.googleapis.com/v14/customers:list",
                "https://googleads.googleapis.com/v14/customers/list"
            ]
            
            for url in alternative_urls:
                try:
                    logger.info(f"🔍 Trying URL: {url}")
                    
                    headers = {
                        'Authorization': f'Bearer {connection.access_token}',
                        'developer-token': settings.GOOGLE_ADS_DEVELOPER_TOKEN,
                        'Content-Type': 'application/json'
                    }
                    
                    response = requests.get(url, headers=headers, timeout=30)
                    
                    if response.status_code == 200:
                        data = response.json()
                        logger.info(f"✅ Success with URL {url}: {data}")
                        
                        if 'resourceNames' in data:
                            customer_ids = []
                            for resource_name in data['resourceNames']:
                                customer_id = resource_name.split('/')[-1]
                                customer_ids.append(customer_id)
                            
                            logger.info(f"✅ Found {len(customer_ids)} customers: {customer_ids}")
                            return customer_ids
                    else:
                        logger.info(f"⚠️ URL {url} failed with status {response.status_code}")
                        
                except Exception as e:
                    logger.info(f"⚠️ URL {url} failed with error: {str(e)}")
                    continue
            
            # Method 3: Try to discover customers through other means
            logger.info("🔍 Trying discovery through alternative methods")
            return self._try_discovery_through_search(connection)
            
        except Exception as e:
            logger.error(f"Error in REST API alternatives: {str(e)}")
            return []
    
    def _try_discovery_through_search(self, connection):
        """
        Try to discover customer IDs through search queries
        """
        try:
            logger.info("🔍 Attempting customer discovery through search queries")
            
            # This approach tries to use the search API to discover customers
            # We'll try some common customer ID patterns or search methods
            
            # For now, we'll use the fallback to connection metadata
            logger.info("🔍 Falling back to connection metadata discovery")
            return self._get_fallback_customer_ids(connection)
            
        except Exception as e:
            logger.error(f"Error in discovery through search: {str(e)}")
            return []
    
    def _try_alternative_customer_discovery(self, connection):
        """
        Alternative method to discover customers when client library fails
        """
        try:
            logger.info("🔍 Trying alternative customer discovery methods")
            
            # Alternative 1: Try to use any customer IDs from connection metadata
            # This is not hardcoded - it's from the actual connection data
            potential_ids = self._get_fallback_customer_ids(connection)
            
            if potential_ids:
                logger.info(f"🔍 Using {len(potential_ids)} customer IDs from connection metadata")
                return potential_ids
            
            # Alternative 2: If we have OAuth token, try to find accounts through search
            # This is an experimental approach
            discovered_ids = self._experimental_customer_discovery(connection)
            
            if discovered_ids:
                logger.info(f"🔍 Discovered {len(discovered_ids)} customer IDs through experimental method")
                return discovered_ids
            
            logger.warning("⚠️ All customer discovery methods failed")
            return []
            
        except Exception as e:
            logger.error(f"Error in alternative customer discovery: {str(e)}")
            return []
    
    def _experimental_customer_discovery(self, connection):
        """
        Experimental method to discover customer IDs
        """
        try:
            logger.info("🔬 Attempting experimental customer discovery")
            
            # This method attempts to discover customer IDs through various means
            # without using hardcoded values
            
            # Try to make a search query without specifying a customer ID
            # to see if we can discover any account information
            headers = {
                'Authorization': f'Bearer {connection.access_token}',
                'developer-token': settings.GOOGLE_ADS_DEVELOPER_TOKEN,
                'Content-Type': 'application/json'
            }
            
            # Try different approaches to discover customer IDs
            # This is experimental and may not work in all cases
            
            logger.info("🔬 Experimental discovery methods not yet implemented")
            logger.info("💡 Consider using the Google Ads client library or providing customer IDs")
            
            return []
            
        except Exception as e:
            logger.error(f"Error in experimental customer discovery: {str(e)}")
            return []
    
    def _get_potential_customer_ids(self, connection):
        """
        Get potential customer IDs from connection metadata only (no cache, no hardcoded)
        """
        try:
            customer_ids = []
            
            # ONLY use connection metadata - no cached accounts or hardcoded IDs
            logger.info("🔍 Using ONLY fresh discovery - no cached or hardcoded customer IDs")
            
            # Check if there's a customer ID in the connection data
            if hasattr(connection, 'customer_id') and connection.customer_id:
                customer_ids.append(connection.customer_id)
                logger.info(f"🔍 Found customer_id in connection: {connection.customer_id}")
            
            # Check platform_account_id
            if hasattr(connection, 'platform_account_id') and connection.platform_account_id:
                clean_id = connection.platform_account_id.replace('-', '')
                customer_ids.append(clean_id)
                logger.info(f"🔍 Found platform_account_id in connection: {clean_id}")
            
            # Check additional_data
            if hasattr(connection, 'additional_data') and connection.additional_data:
                try:
                    import json
                    data = json.loads(connection.additional_data)
                    if 'customer_id' in data:
                        clean_id = str(data['customer_id']).replace('-', '')
                        customer_ids.append(clean_id)
                        logger.info(f"🔍 Found customer_id in additional_data: {clean_id}")
                except:
                    pass
            
            # Remove duplicates and return
            unique_ids = list(set(customer_ids))
            logger.info(f"🔍 Found {len(unique_ids)} unique customer IDs from connection metadata")
            
            if not unique_ids:
                logger.warning("⚠️ No customer IDs found in connection metadata")
                logger.info("💡 To enable account discovery, add customer_id to:")
                logger.info("💡 - connection.platform_account_id")
                logger.info("💡 - connection.additional_data as JSON: {'customer_id': 'YOUR_ID'}")
            
            return unique_ids
            
        except Exception as e:
            logger.error(f"Error getting potential customer IDs: {str(e)}")
            return []
    
    def _get_account_info_direct(self, connection, customer_id):
        """
        Get account info directly for a specific customer ID
        """
        try:
            # Clean the customer ID (remove hyphens)
            clean_customer_id = customer_id.replace('-', '')
            
            # Try to get basic customer info first
            account_info = self._get_single_customer_info(connection, clean_customer_id, clean_customer_id)
            
            if account_info:
                logger.info(f"✅ Successfully retrieved account info for {customer_id}")
                return account_info
            else:
                logger.warning(f"⚠️ Could not retrieve account info for {customer_id}")
                return []
                
        except Exception as e:
            logger.error(f"Error getting account info for {customer_id}: {str(e)}")
            return []
    
    def _try_get_own_account_info(self, connection):
        """
        Try to get account info without specifying a customer ID
        """
        try:
            # This is a fallback approach - try to make a basic query
            # without specifying a customer ID to see if we can get any account info
            headers = {
                'Authorization': f'Bearer {connection.access_token}',
                'developer-token': settings.GOOGLE_ADS_DEVELOPER_TOKEN,
                'Content-Type': 'application/json'
            }
            
            # Try to list some basic account info
            # This might not work, but it's worth a try
            logger.info("🔍 Trying to get account info without customer ID")
            
            # For now, return empty as this approach is limited
            # In a real scenario, you'd need at least one customer ID to bootstrap
            logger.info("💡 Cannot retrieve accounts without a customer ID")
            logger.info("💡 Please provide a customer ID manually for initial setup")
            
            return []
            
        except Exception as e:
            logger.error(f"Error trying to get own account info: {str(e)}")
            return []
    
    def _get_fallback_customer_ids(self, connection):
        """
        Get customer IDs from connection metadata ONLY (no cached data)
        """
        try:
            # NO CACHED DATA - only connection metadata
            logger.info("🔍 Getting customer IDs from connection metadata only - NO CACHE")
            
            potential_ids = []
            
            # Check if there's a customer ID stored in the connection
            if hasattr(connection, 'platform_account_id') and connection.platform_account_id:
                clean_id = connection.platform_account_id.replace('-', '')
                potential_ids.append(clean_id)
                logger.info(f"📋 Using connection's platform_account_id: {clean_id}")
            
            # Check if there's a customer ID in the connection's additional data
            if hasattr(connection, 'additional_data') and connection.additional_data:
                try:
                    import json
                    data = json.loads(connection.additional_data)
                    if 'customer_id' in data:
                        clean_id = str(data['customer_id']).replace('-', '')
                        potential_ids.append(clean_id)
                        logger.info(f"📋 Using customer_id from additional_data: {clean_id}")
                except:
                    pass
            
            if potential_ids:
                return potential_ids
            
            # If no connection data, we need manual specification
            logger.warning("⚠️ No customer IDs found in connection metadata")
            logger.info("💡 To get started, you need to provide at least one customer ID")
            logger.info("💡 You can add it to the connection's additional_data or platform_account_id")
            return []
            
        except Exception as e:
            logger.error(f"Error in fallback customer ID retrieval: {str(e)}")
            return []
    
    def _get_account_hierarchy(self, connection, login_customer_id, target_customer_id):
        """
        Get account hierarchy starting from a specific customer using REST API v20
        """
        try:
            logger.info(f"🔍 Getting hierarchy for customer {target_customer_id} using login {login_customer_id}")
            
            headers = {
                'Authorization': f'Bearer {connection.access_token}',
                'developer-token': settings.GOOGLE_ADS_DEVELOPER_TOKEN,
                'login-customer-id': login_customer_id,
                'Content-Type': 'application/json'
            }
            
            url = f"https://googleads.googleapis.com/v20/customers/{target_customer_id}/googleAds:search"
            
            # Query to get customer hierarchy
            query = """
                SELECT 
                    customer_client.id,
                    customer_client.descriptive_name,
                    customer_client.currency_code,
                    customer_client.time_zone,
                    customer_client.level,
                    customer_client.manager,
                    customer_client.status,
                    customer_client_link.manager_link_id
                FROM customer_client
                WHERE customer_client.status != 'CLOSED'
                ORDER BY customer_client.level, customer_client.descriptive_name
            """
            
            payload = {'query': query}
            
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                if 'results' in data:
                    accounts = []
                    
                    for result in data['results']:
                        customer_client = result.get('customerClient', {})
                        customer_client_link = result.get('customerClientLink', {})
                        
                        # Extract account ID and format it
                        raw_id = str(customer_client.get('id', ''))
                        formatted_id = self._format_account_id(raw_id)
                        
                        # Get manager link ID for parent relationship
                        manager_link_id = customer_client_link.get('managerLinkId')
                        parent_id = self._format_account_id(str(manager_link_id)) if manager_link_id else None
                        
                        account_data = {
                            'id': formatted_id,
                            'name': customer_client.get('descriptiveName', f'Account {formatted_id}'),
                            'raw_id': raw_id,
                            'is_manager': customer_client.get('manager', False),
                            'currency_code': customer_client.get('currencyCode', 'USD'),
                            'time_zone': customer_client.get('timeZone', 'UTC'),
                            'status': customer_client.get('status', 'ACTIVE'),
                            'level': customer_client.get('level', 0),
                            'parent_id': parent_id,
                            'child_accounts': []
                        }
                        
                        accounts.append(account_data)
                        logger.info(f"📋 Found account: {account_data['name']} ({formatted_id})")
                    
                    if accounts:
                        # Build hierarchy structure
                        return self._build_hierarchy(accounts)
                    else:
                        logger.info(f"📋 No hierarchy results for customer {target_customer_id}")
                        # Try to get just the single customer info
                        return self._get_single_customer_info(connection, login_customer_id, target_customer_id)
                else:
                    logger.info(f"📋 No hierarchy results for customer {target_customer_id}")
                    return self._get_single_customer_info(connection, login_customer_id, target_customer_id)
            else:
                logger.error(f"❌ Hierarchy request failed: {response.status_code}")
                logger.error(f"Response: {response.text}")
                return self._get_single_customer_info(connection, login_customer_id, target_customer_id)
                
        except Exception as e:
            logger.error(f"Error getting account hierarchy via REST API: {str(e)}")
            # Fallback to single customer info
            return self._get_single_customer_info(connection, login_customer_id, target_customer_id)
    
    def _get_single_customer_info(self, connection, login_customer_id, target_customer_id):
        """
        Get basic info for a single customer when hierarchy query fails
        """
        try:
            headers = {
                'Authorization': f'Bearer {connection.access_token}',
                'developer-token': settings.GOOGLE_ADS_DEVELOPER_TOKEN,
                'login-customer-id': login_customer_id,
                'Content-Type': 'application/json'
            }
            
            url = f"https://googleads.googleapis.com/v20/customers/{target_customer_id}/googleAds:search"
            
            logger.info(f"🔍 Getting single customer info for {target_customer_id}")
            
            # Simple query for customer info
            query = """
                SELECT 
                    customer.id,
                    customer.descriptive_name,
                    customer.currency_code,
                    customer.time_zone,
                    customer.manager,
                    customer.status
                FROM customer
                LIMIT 1
            """
            
            payload = {'query': query}
            
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            logger.info(f"🔍 Single customer response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                if 'results' in data and data['results']:
                    result = data['results'][0]
                    customer = result.get('customer', {})
                    
                    raw_id = str(customer.get('id', target_customer_id))
                    formatted_id = self._format_account_id(raw_id)
                    
                    account_data = {
                        'id': formatted_id,
                        'name': customer.get('descriptiveName', f'Account {formatted_id}'),
                        'raw_id': raw_id,
                        'is_manager': customer.get('manager', False),
                        'currency_code': customer.get('currencyCode', 'USD'),
                        'time_zone': customer.get('timeZone', 'UTC'),
                        'status': customer.get('status', 'ACTIVE'),
                        'level': 0,
                        'parent_id': None,
                        'child_accounts': []
                    }
                    
                    logger.info(f"📋 Got single customer: {account_data['name']} ({formatted_id})")
                    return [account_data]
                else:
                    logger.warning(f"⚠️ No customer info found for {target_customer_id}")
                    return []
            else:
                logger.error(f"❌ Single customer request failed: {response.status_code}")
                logger.error(f"Response: {response.text}")
                return []
                
        except Exception as e:
            logger.error(f"Error getting single customer info: {str(e)}")
            return []
    
    def _format_account_id(self, raw_id):
        """
        Format account ID with hyphens (XXX-XXX-XXXX)
        """
        raw_id = str(raw_id).replace('-', '')
        if len(raw_id) >= 10:
            return f"{raw_id[:3]}-{raw_id[3:6]}-{raw_id[6:]}"
        return raw_id
    
    def _build_hierarchy(self, accounts):
        """
        Build parent-child hierarchy from flat account list
        """
        try:
            account_map = {acc['id']: acc for acc in accounts}
            root_accounts = []
            
            for account in accounts:
                if account['parent_id'] and account['parent_id'] in account_map:
                    # Add this account as child of parent
                    parent = account_map[account['parent_id']]
                    parent['child_accounts'].append(account)
                else:
                    # Root account (no parent or parent not found)
                    root_accounts.append(account)
            
            logger.info(f"📋 Built hierarchy: {len(root_accounts)} root accounts from {len(accounts)} total")
            return root_accounts
            
        except Exception as e:
            logger.error(f"Error building hierarchy: {str(e)}")
            return accounts  # Return flat list if hierarchy building fails
    
    def _cache_accounts(self, connection, accounts):
        """
        Cache accounts to database with hierarchy relationships
        """
        try:
            # Clear existing cache
            GoogleAdsAccount.objects.filter(platform_connection=connection).delete()
            
            # Cache accounts with hierarchy
            account_instances = {}
            
            # First pass: create all accounts
            for account in self._flatten_accounts(accounts):
                instance = GoogleAdsAccount.objects.create(
                    platform_connection=connection,
                    account_id=account['id'],
                    raw_account_id=account['raw_id'],
                    name=account['name'],
                    is_manager=account['is_manager'],
                    currency_code=account['currency_code'],
                    time_zone=account['time_zone'],
                    status=account['status'],
                    level=account['level'],
                    sync_status='active'
                )
                account_instances[account['id']] = instance
            
            # Second pass: set parent relationships
            for account in self._flatten_accounts(accounts):
                if account['parent_id'] and account['parent_id'] in account_instances:
                    instance = account_instances[account['id']]
                    parent_instance = account_instances[account['parent_id']]
                    instance.parent_account = parent_instance
                    instance.save(update_fields=['parent_account'])
            
            logger.info(f"💾 Successfully cached {len(account_instances)} accounts")
            
        except Exception as e:
            logger.error(f"Error caching accounts: {str(e)}")
    
    def _flatten_accounts(self, accounts):
        """
        Flatten hierarchical account structure to a list
        """
        flat_accounts = []
        
        def flatten_recursive(account_list):
            for account in account_list:
                flat_accounts.append(account)
                if account.get('child_accounts'):
                    flatten_recursive(account['child_accounts'])
        
        flatten_recursive(accounts)
        return flat_accounts
    
    def _refresh_token(self, connection):
        """
        Refresh OAuth token using REST API
        """
        try:
            import requests
            
            if not connection.refresh_token:
                logger.error("No refresh token available")
                return False
                
            # Use Google's OAuth2 token endpoint
            token_url = "https://oauth2.googleapis.com/token"
            
            data = {
                'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
                'client_secret': settings.GOOGLE_OAUTH_CLIENT_SECRET,
                'refresh_token': connection.refresh_token,
                'grant_type': 'refresh_token'
            }
            
            response = requests.post(token_url, data=data, timeout=30)
            
            if response.status_code == 200:
                token_data = response.json()
                
                # Update connection with new token
                connection.access_token = token_data.get('access_token')
                connection.token_expiry = timezone.now() + timezone.timedelta(seconds=token_data.get('expires_in', 3600))
                connection.save(update_fields=['access_token', 'token_expiry'])
                
                logger.info("✅ Token refreshed successfully")
                return True
            else:
                logger.error(f"Token refresh failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error refreshing token: {str(e)}")
            return False
    
    def sync_accounts(self, connection):
        """
        Sync accounts and update cache (used by resync functionality)
        """
        try:
            logger.info(f"🔄 Starting account sync for connection {connection.id}")
            
            # Create sync record
            sync_record = GoogleAdsAccountSync.objects.create(
                platform_connection=connection,
                sync_status='running'
            )
            
            try:
                # Force refresh accounts
                accounts = self.get_accounts_for_connection(connection, force_refresh=True)
                
                # Count total accounts discovered
                total_accounts = len(self._flatten_accounts(accounts)) if accounts else 0
                
                # Update sync record
                sync_record.accounts_discovered = total_accounts
                sync_record.accounts_updated = total_accounts
                sync_record.sync_status = 'completed'
                
                # Mark as completed
                sync_record.completed_at = timezone.now()
                sync_record.save()
                
                logger.info(f"✅ Sync completed: {total_accounts} accounts processed")
                return True
                
            except Exception as e:
                # Mark sync as failed
                sync_record.sync_status = 'failed'
                sync_record.error_message = str(e)
                sync_record.completed_at = timezone.now()
                sync_record.save()
                
                logger.error(f"❌ Sync failed: {str(e)}")
                return False
                
        except Exception as e:
            logger.error(f"Error in sync_accounts: {str(e)}")
            return False