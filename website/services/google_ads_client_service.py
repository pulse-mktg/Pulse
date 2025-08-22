"""
Google Ads Client Service
Clean implementation following Google's documentation for listing accessible customers.
"""

import logging
import requests
from google.oauth2.credentials import Credentials
from django.conf import settings

logger = logging.getLogger(__name__)


class GoogleAdsClientService:
    """
    Service for retrieving Google Ads accounts following Google's documentation:
    1. Use CustomerService.ListAccessibleCustomers to get accounts with direct access
    2. Get account details for each accessible customer
    """
    
    def __init__(self, connection):
        self.connection = connection
        self.access_token = None
    
    def get_fresh_token(self):
        """
        Get a fresh OAuth token
        """
        try:
            logger.info("🔄 Getting fresh OAuth token")
            
            # Create OAuth2 credentials and ensure they're fresh
            credentials = Credentials(
                token=self.connection.access_token,
                refresh_token=self.connection.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
                client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
            )
            
            # Refresh the token if needed
            if credentials.expired:
                logger.info("🔄 Token expired, refreshing...")
                from google.auth.transport.requests import Request
                credentials.refresh(Request())
            
            self.access_token = credentials.token
            logger.info("✅ Successfully got fresh OAuth token")
            return credentials.token
            
        except Exception as e:
            logger.error(f"❌ Failed to get fresh token: {str(e)}")
            raise
    
    def list_accessible_customers(self):
        """
        Get accessible customers using the CustomerService.ListAccessibleCustomers method
        This returns only accounts where the authenticated user has direct access.
        """
        try:
            logger.info("🔄 Getting accessible customers via CustomerService")
            
            if not self.access_token:
                self.get_fresh_token()
            
            # Try working API versions (v17-v20 are available)
            versions = ["v20", "v19", "v18", "v17"]
            
            for version in versions:
                try:
                    # Use the CustomerService.ListAccessibleCustomers endpoint
                    url = f"https://googleads.googleapis.com/{version}/customers:listAccessibleCustomers"
                    
                    headers = {
                        "Authorization": f"Bearer {self.access_token}",
                        "developer-token": settings.GOOGLE_ADS_DEVELOPER_TOKEN,
                        "Content-Type": "application/json"
                    }
                    
                    logger.info(f"🔄 Trying CustomerService.ListAccessibleCustomers with {version}")
                    response = requests.get(url, headers=headers)
                    
                    if response.status_code == 200:
                        data = response.json()
                        customer_ids = []
                        
                        # Extract customer IDs from resource names
                        for resource_name in data.get("resourceNames", []):
                            # Format: customers/123456789
                            customer_id = resource_name.split('/')[-1]
                            customer_ids.append(customer_id)
                            logger.info(f"📋 Found accessible customer: {customer_id}")
                        
                        logger.info(f"✅ {version} API worked! Found {len(customer_ids)} accessible customers")
                        return customer_ids, version
                    else:
                        logger.warning(f"⚠️ {version} API returned status {response.status_code}: {response.text}")
                        continue
                        
                except Exception as e:
                    logger.warning(f"⚠️ {version} API failed: {str(e)}")
                    continue
            
            # If all versions failed
            raise Exception("All API versions failed for ListAccessibleCustomers")
            
        except Exception as e:
            logger.error(f"❌ Error getting accessible customers: {str(e)}")
            raise
    
    def get_customer_details(self, customer_id, api_version):
        """
        Get customer details for a specific customer ID
        """
        try:
            if not self.access_token:
                self.get_fresh_token()
            
            # Query to get customer details
            url = f"https://googleads.googleapis.com/{api_version}/customers/{customer_id}/googleAds:search"
            
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "developer-token": settings.GOOGLE_ADS_DEVELOPER_TOKEN,
                "Content-Type": "application/json"
            }
            
            # Query customer table for basic info
            query = {
                "query": "SELECT customer.id, customer.descriptive_name, customer.currency_code, customer.time_zone FROM customer LIMIT 1"
            }
            
            response = requests.post(url, headers=headers, json=query)
            
            if response.status_code == 200:
                data = response.json()
                
                if "results" in data and len(data["results"]) > 0:
                    customer_data = data["results"][0]["customer"]
                    
                    # Extract customer info
                    customer_name = customer_data.get("descriptiveName", f"Google Ads Account {customer_id}")
                    currency_code = customer_data.get("currencyCode", "USD")
                    time_zone = customer_data.get("timeZone", "UTC")
                    
                    # Create account structure expected by frontend
                    account = {
                        "id": customer_id,
                        "name": customer_name,
                        "raw_id": customer_id,
                        "is_manager": False,  # For now, assume not manager
                        "currency_code": currency_code,
                        "time_zone": time_zone,
                        "status": "ACTIVE",
                        "level": 0,
                        "parent_id": None,
                        "child_accounts": []
                    }
                    
                    logger.info(f"✅ Retrieved customer details: {customer_name} ({customer_id})")
                    return account
                else:
                    logger.warning(f"⚠️ No results for customer {customer_id}")
                    return None
            else:
                logger.warning(f"⚠️ Failed to get details for customer {customer_id}: {response.status_code} {response.text}")
                return None
                
        except Exception as e:
            logger.warning(f"⚠️ Error getting details for customer {customer_id}: {str(e)}")
            return None
    
    def get_account_hierarchy(self, customer_id, api_version, processed_ids=None):
        """
        Get the full account hierarchy for a customer using breadth-first search.
        This implements Google's recommended approach for getting nested accounts.
        """
        if processed_ids is None:
            processed_ids = set()
        
        try:
            logger.info(f"🔄 Getting account hierarchy for customer {customer_id}")
            
            if not self.access_token:
                self.get_fresh_token()
            
            # Query to get child accounts (customer_client table)
            url = f"https://googleads.googleapis.com/{api_version}/customers/{customer_id}/googleAds:search"
            
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "developer-token": settings.GOOGLE_ADS_DEVELOPER_TOKEN,
                "Content-Type": "application/json"
            }
            
            # Query from Google's documentation to get account hierarchy
            # Remove level restriction to get all nested accounts
            query = {
                "query": """
                    SELECT
                      customer_client.client_customer,
                      customer_client.level,
                      customer_client.manager,
                      customer_client.descriptive_name,
                      customer_client.currency_code,
                      customer_client.time_zone,
                      customer_client.id
                    FROM customer_client
                    WHERE customer_client.level >= 1
                """
            }
            
            response = requests.post(url, headers=headers, json=query)
            
            if response.status_code != 200:
                logger.warning(f"⚠️ Failed to get hierarchy for {customer_id}: {response.status_code}")
                return []
            
            data = response.json()
            child_accounts = []
            
            if "results" in data:
                for result in data["results"]:
                    customer_client = result.get("customerClient", {})
                    
                    # Skip level 0 (the parent account itself)
                    if customer_client.get("level", 0) == 0:
                        continue
                    
                    child_customer_id = str(customer_client.get("id", ""))
                    
                    # Avoid infinite loops
                    if child_customer_id in processed_ids:
                        continue
                    
                    processed_ids.add(child_customer_id)
                    
                    # Create child account structure
                    child_account = {
                        "id": child_customer_id,
                        "name": customer_client.get("descriptiveName", f"Google Ads Account {child_customer_id}"),
                        "raw_id": child_customer_id,
                        "is_manager": customer_client.get("manager", False),
                        "currency_code": customer_client.get("currencyCode", "USD"),
                        "time_zone": customer_client.get("timeZone", "UTC"),
                        "status": "ACTIVE",
                        "level": customer_client.get("level", 1),
                        "parent_id": customer_id,
                        "child_accounts": []
                    }
                    
                    # If this is a manager account, recursively get its children
                    if customer_client.get("manager", False):
                        logger.info(f"🔄 Getting children for manager account {child_customer_id}")
                        try:
                            child_account["child_accounts"] = self.get_account_hierarchy(
                                child_customer_id, api_version, processed_ids
                            )
                        except Exception as e:
                            logger.warning(f"⚠️ Error getting children for {child_customer_id}: {str(e)}")
                    
                    child_accounts.append(child_account)
                    logger.info(f"✅ Added child account: {child_account['name']} ({child_customer_id})")
            
            return child_accounts
            
        except Exception as e:
            logger.error(f"❌ Error getting hierarchy for {customer_id}: {str(e)}")
            return []

    def get_accessible_accounts(self):
        """
        Get all accessible Google Ads accounts with full hierarchy.
        This follows Google's documentation for ListAccessibleCustomers and account hierarchy.
        
        Returns:
            List[dict]: List of account dictionaries with complete hierarchy
        """
        try:
            logger.info("🔄 Starting Google Ads account retrieval with hierarchy")
            
            # Step 1: Get fresh OAuth token
            self.get_fresh_token()
            
            # Step 2: Get accessible customers (accounts with direct access)
            customer_ids, api_version = self.list_accessible_customers()
            
            if not customer_ids:
                logger.warning("⚠️ No accessible customers found")
                return []
            
            # Step 3: Get details and hierarchy for each accessible customer
            accounts = []
            
            for customer_id in customer_ids:
                try:
                    # Get basic account details
                    account = self.get_customer_details(customer_id, api_version)
                    if not account:
                        # Create basic account if we can't get details
                        account = {
                            "id": customer_id,
                            "name": f"Google Ads Account {customer_id}",
                            "raw_id": customer_id,
                            "is_manager": False,
                            "currency_code": "USD",
                            "time_zone": "UTC",
                            "status": "ACTIVE",
                            "level": 0,
                            "parent_id": None,
                            "child_accounts": []
                        }
                        logger.info(f"✅ Created basic account for {customer_id}")
                    
                    # Get child accounts hierarchy
                    try:
                        child_accounts = self.get_account_hierarchy(customer_id, api_version)
                        account["child_accounts"] = child_accounts
                        
                        # Update is_manager flag based on whether we have children
                        if child_accounts:
                            account["is_manager"] = True
                            logger.info(f"✅ Found {len(child_accounts)} child accounts for {customer_id}")
                    except Exception as e:
                        logger.warning(f"⚠️ Error getting hierarchy for {customer_id}: {str(e)}")
                        account["child_accounts"] = []
                    
                    accounts.append(account)
                        
                except Exception as e:
                    logger.warning(f"⚠️ Error processing customer {customer_id}: {str(e)}")
                    continue
            
            # Count total accounts (including nested ones)
            total_accounts = self._count_total_accounts(accounts)
            logger.info(f"✅ Successfully retrieved {len(accounts)} top-level accounts with {total_accounts} total accounts")
            
            # Log accounts for debugging
            for account in accounts:
                self._log_account_hierarchy(account, 0)
            
            return accounts
            
        except Exception as e:
            logger.error(f"❌ Failed to retrieve accessible accounts: {str(e)}")
            return []
    
    def get_all_accounts_flat(self):
        """
        Get all accounts as a flat list (including nested ones).
        This is useful for displaying all selectable accounts.
        
        Returns:
            List[dict]: Flat list of all accounts
        """
        try:
            # Get hierarchical accounts first
            hierarchical_accounts = self.get_accessible_accounts()
            
            # Flatten the hierarchy
            all_accounts = []
            
            def flatten_accounts(accounts, level=0):
                for account in accounts:
                    # Add current account
                    flat_account = account.copy()
                    flat_account["level"] = level
                    all_accounts.append(flat_account)
                    
                    # Add child accounts recursively
                    if account.get("child_accounts"):
                        flatten_accounts(account["child_accounts"], level + 1)
            
            flatten_accounts(hierarchical_accounts)
            
            logger.info(f"✅ Flattened {len(all_accounts)} total accounts from hierarchy")
            return all_accounts
            
        except Exception as e:
            logger.error(f"❌ Failed to flatten accounts: {str(e)}")
            return []
    
    def _count_total_accounts(self, accounts):
        """Count total accounts including nested ones"""
        total = 0
        for account in accounts:
            total += 1  # Count this account
            total += self._count_total_accounts(account.get("child_accounts", []))
        return total
    
    def _log_account_hierarchy(self, account, depth):
        """Log account hierarchy with indentation"""
        indent = "  " * depth
        logger.info(f"{indent}• {account['name']} ({account['id']}) - Manager: {account['is_manager']}")
        
        for child in account.get("child_accounts", []):
            self._log_account_hierarchy(child, depth + 1)
    
    def get_accounts_with_hierarchy(self, force_refresh=False):
        """
        Get all accessible accounts with hierarchy information.
        Uses cached data if available, otherwise fetches from Google Ads API.
        
        Args:
            force_refresh (bool): If True, ignores cache and fetches fresh data
        
        Returns:
            dict: {
                'accounts': List[dict],
                'has_managers': bool,
                'total_accounts': int,
                'from_cache': bool
            }
        """
        try:
            # Check cache first (unless force refresh)
            if not force_refresh:
                cached_result = self._get_accounts_from_cache()
                if cached_result:
                    logger.info(f"✅ Using cached accounts: {len(cached_result['accounts'])} top-level accounts")
                    return cached_result
            
            # Cache miss or force refresh - fetch from API
            logger.info("🔄 Cache miss or force refresh - fetching accounts from Google Ads API")
            accounts = self.get_accessible_accounts()
            
            # Save to cache
            self._save_accounts_to_cache(accounts)
            
            # Check if we have any manager accounts
            has_managers = self._has_manager_accounts(accounts)
            
            # Count total accounts
            total_accounts = self._count_total_accounts(accounts)
            
            logger.info(f"✅ Retrieved {len(accounts)} top-level accounts, {total_accounts} total, has_managers: {has_managers}")
            
            return {
                'accounts': accounts,
                'has_managers': has_managers,
                'total_accounts': total_accounts,
                'from_cache': False
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to get accounts with hierarchy: {str(e)}")
            return {
                'accounts': [],
                'has_managers': False,
                'total_accounts': 0,
                'from_cache': False
            }
    
    def _has_manager_accounts(self, accounts):
        """Check if any account in the hierarchy is a manager account"""
        for account in accounts:
            if account.get("is_manager", False):
                return True
            # Check child accounts recursively
            if self._has_manager_accounts(account.get("child_accounts", [])):
                return True
        return False
    
    def _get_accounts_from_cache(self):
        """
        Retrieve accounts from database cache.
        
        Returns:
            dict or None: Cached account data or None if cache miss
        """
        try:
            from ..models import GoogleAdsAccount
            from django.utils import timezone
            from datetime import timedelta
            
            # Check if cache is still valid (24 hours)
            cache_cutoff = timezone.now() - timedelta(hours=24)
            
            # Get top-level accounts (those without parent)
            top_level_accounts = GoogleAdsAccount.objects.filter(
                platform_connection=self.platform_connection,
                parent_account__isnull=True,
                last_synced__gte=cache_cutoff
            ).order_by('name')
            
            if not top_level_accounts.exists():
                logger.info("⚠️ No cached accounts found or cache expired")
                return None
            
            # Convert to dictionary format
            accounts = []
            has_managers = False
            total_accounts = 0
            
            for account in top_level_accounts:
                account_dict = self._convert_model_to_dict(account)
                accounts.append(account_dict)
                
                # Check if this account or its children are managers
                if account.is_manager or self._has_manager_children(account):
                    has_managers = True
                
                # Count total accounts including children
                total_accounts += 1 + self._count_child_accounts(account)
            
            logger.info(f"✅ Cache hit: {len(accounts)} top-level accounts, {total_accounts} total")
            
            return {
                'accounts': accounts,
                'has_managers': has_managers,
                'total_accounts': total_accounts,
                'from_cache': True
            }
            
        except Exception as e:
            logger.error(f"❌ Error retrieving accounts from cache: {str(e)}")
            return None
    
    def _save_accounts_to_cache(self, accounts):
        """
        Save accounts to database cache.
        
        Args:
            accounts (List[dict]): Account hierarchy to cache
        """
        try:
            from ..models import GoogleAdsAccount, GoogleAdsAccountSync
            from django.utils import timezone
            
            # Start a sync record
            sync_record = GoogleAdsAccountSync.objects.create(
                platform_connection=self.platform_connection,
                sync_status='running'
            )
            
            # Clear existing cache for this connection
            GoogleAdsAccount.objects.filter(
                platform_connection=self.platform_connection
            ).delete()
            
            # Save accounts recursively
            accounts_saved = 0
            for account in accounts:
                accounts_saved += self._save_account_recursive(account, parent=None)
            
            # Complete sync record
            sync_record.completed_at = timezone.now()
            sync_record.sync_status = 'completed'
            sync_record.accounts_discovered = accounts_saved
            sync_record.accounts_added = accounts_saved
            sync_record.save()
            
            logger.info(f"✅ Cached {accounts_saved} accounts successfully")
            
        except Exception as e:
            logger.error(f"❌ Error saving accounts to cache: {str(e)}")
            # Mark sync as failed
            if 'sync_record' in locals():
                sync_record.sync_status = 'failed'
                sync_record.error_message = str(e)
                sync_record.save()
    
    def _save_account_recursive(self, account_dict, parent=None):
        """
        Save a single account and its children recursively.
        
        Args:
            account_dict (dict): Account data to save
            parent (GoogleAdsAccount): Parent account model instance
            
        Returns:
            int: Number of accounts saved
        """
        try:
            from ..models import GoogleAdsAccount
            
            # Create account record
            account = GoogleAdsAccount.objects.create(
                platform_connection=self.platform_connection,
                account_id=account_dict['id'],
                raw_account_id=account_dict['raw_id'],
                name=account_dict['name'],
                is_manager=account_dict.get('is_manager', False),
                status=account_dict.get('status', 'ACTIVE'),
                currency_code=account_dict.get('currency_code', 'USD'),
                time_zone=account_dict.get('time_zone', 'UTC'),
                parent_account=parent,
                level=account_dict.get('level', 0),
                sync_status='active'
            )
            
            accounts_saved = 1
            
            # Save child accounts
            for child_dict in account_dict.get('child_accounts', []):
                accounts_saved += self._save_account_recursive(child_dict, parent=account)
            
            return accounts_saved
            
        except Exception as e:
            logger.error(f"❌ Error saving account {account_dict.get('id', 'unknown')}: {str(e)}")
            return 0
    
    def _convert_model_to_dict(self, account):
        """
        Convert GoogleAdsAccount model to dictionary format.
        
        Args:
            account (GoogleAdsAccount): Account model instance
            
        Returns:
            dict: Account data in API format
        """
        account_dict = {
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
        
        # Add child accounts recursively
        for child in account.child_accounts.all().order_by('name'):
            account_dict['child_accounts'].append(self._convert_model_to_dict(child))
        
        return account_dict
    
    def _has_manager_children(self, account):
        """Check if account has any manager children recursively"""
        for child in account.child_accounts.all():
            if child.is_manager or self._has_manager_children(child):
                return True
        return False
    
    def _count_child_accounts(self, account):
        """Count all child accounts recursively"""
        count = 0
        for child in account.child_accounts.all():
            count += 1 + self._count_child_accounts(child)
        return count
    
    def refresh_account_cache(self):
        """
        Force refresh the account cache by fetching fresh data from Google Ads API.
        
        Returns:
            dict: Refreshed account data
        """
        logger.info("🔄 Force refreshing account cache")
        return self.get_accounts_with_hierarchy(force_refresh=True)
    
    def clear_account_cache(self):
        """
        Clear the account cache for this connection.
        """
        try:
            from ..models import GoogleAdsAccount
            
            deleted_count = GoogleAdsAccount.objects.filter(
                platform_connection=self.platform_connection
            ).delete()[0]
            
            logger.info(f"✅ Cleared {deleted_count} accounts from cache")
            
        except Exception as e:
            logger.error(f"❌ Error clearing account cache: {str(e)}")
    
    def get_cache_info(self):
        """
        Get information about the current cache state.
        
        Returns:
            dict: Cache information
        """
        try:
            from ..models import GoogleAdsAccount, GoogleAdsAccountSync
            from django.utils import timezone
            from datetime import timedelta
            
            # Get cache stats
            total_accounts = GoogleAdsAccount.objects.filter(
                platform_connection=self.platform_connection
            ).count()
            
            manager_accounts = GoogleAdsAccount.objects.filter(
                platform_connection=self.platform_connection,
                is_manager=True
            ).count()
            
            # Get last sync info
            last_sync = GoogleAdsAccountSync.objects.filter(
                platform_connection=self.platform_connection
            ).order_by('-started_at').first()
            
            # Check if cache is fresh (24 hours)
            cache_cutoff = timezone.now() - timedelta(hours=24)
            is_fresh = GoogleAdsAccount.objects.filter(
                platform_connection=self.platform_connection,
                last_synced__gte=cache_cutoff
            ).exists()
            
            return {
                'total_accounts': total_accounts,
                'manager_accounts': manager_accounts,
                'client_accounts': total_accounts - manager_accounts,
                'is_fresh': is_fresh,
                'last_sync': last_sync.started_at if last_sync else None,
                'last_sync_status': last_sync.sync_status if last_sync else None,
                'cache_age_hours': (timezone.now() - last_sync.started_at).total_seconds() / 3600 if last_sync else None
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting cache info: {str(e)}")
            return {
                'total_accounts': 0,
                'manager_accounts': 0,
                'client_accounts': 0,
                'is_fresh': False,
                'last_sync': None,
                'last_sync_status': None,
                'cache_age_hours': None
            }