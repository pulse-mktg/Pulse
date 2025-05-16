import datetime
import logging
import requests
import traceback
from django.conf import settings
from django.utils import timezone

import google.oauth2.credentials
import google_auth_oauthlib.flow
import google.auth.transport.requests
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from ..models import PlatformConnection, PlatformType
from .base import PlatformService

logger = logging.getLogger(__name__)

class GoogleAdsService(PlatformService):
    """
    Service for integrating with Google Ads API.
    Handles OAuth flow, token management, and account information retrieval.
    """
    
    def __init__(self, tenant):
        """
        Initialize the Google Ads service.
        
        Args:
            tenant: The tenant model instance
        """
        super().__init__(tenant)
        self.platform_type = PlatformType.objects.get(slug='google-ads')
    
    def get_authorized_connections(self):
        """
        Get all active Google Ads connections for the tenant.
        
        Returns:
            QuerySet of active PlatformConnection objects for Google Ads
        """
        connections = PlatformConnection.objects.filter(
            tenant=self.tenant,
            platform_type=self.platform_type,
            is_active=True
        )
        return connections
    
    def initialize_oauth_flow(self, redirect_uri):
        """
        Initialize the OAuth flow for Google Ads.
        
        Args:
            redirect_uri: The URL to redirect to after authorization
            
        Returns:
            tuple: (authorization_url, state)
        """
        # Log environment information for debugging
        logger.warning(f"OAuth Flow - Current ENVIRONMENT: {settings.ENVIRONMENT}")
        logger.warning(f"OAuth Flow - IS_DEVELOPMENT: {settings.IS_DEVELOPMENT}")
        logger.warning(f"OAuth Flow - GOOGLE_OAUTH_CLIENT_ID exists: {settings.GOOGLE_OAUTH_CLIENT_ID is not None}")
        logger.warning(f"OAuth Flow - GOOGLE_OAUTH_CLIENT_SECRET exists: {settings.GOOGLE_OAUTH_CLIENT_SECRET is not None}")
        
        # Check if we're in production environment
        if settings.ENVIRONMENT == 'production':
            # Verify that environment variables are available
            if not settings.GOOGLE_OAUTH_CLIENT_ID or not settings.GOOGLE_OAUTH_CLIENT_SECRET:
                logger.error("Production environment detected but OAuth credentials are missing from environment variables")
                raise ValueError("Google OAuth credentials are not configured in environment variables")
                
            # Use client credentials from environment variables
            client_config = {
                "web": {
                    "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                    "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token"
                }
            }
            flow = google_auth_oauthlib.flow.Flow.from_client_config(
                client_config,
                scopes=settings.GOOGLE_OAUTH_SCOPES
            )
        else:
            # Use client credentials from file in development
            try:
                flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
                    settings.GOOGLE_OAUTH_CLIENT_SECRET_PATH,
                    scopes=settings.GOOGLE_OAUTH_SCOPES
                )
            except FileNotFoundError:
                logger.error(f"Client secrets file not found at: {settings.GOOGLE_OAUTH_CLIENT_SECRET_PATH}")
                raise ValueError(f"Google OAuth client secrets file not found. Please check the path: {settings.GOOGLE_OAUTH_CLIENT_SECRET_PATH}")
            except Exception as e:
                logger.error(f"Error loading client secrets: {str(e)}")
                raise
            
        flow.redirect_uri = redirect_uri
        
        # Generate URL for user authorization
        authorization_url, state = flow.authorization_url(
            # Enable offline access to get a refresh token
            access_type='offline',
            # Enable incremental authorization
            include_granted_scopes='true',
            # Force to always prompt for consent
            prompt='consent'
        )
        
        return authorization_url, state
    
    def handle_oauth_callback(self, authorization_response, state, user):
        """
        Process the OAuth callback and save the connection.
        
        Args:
            authorization_response: The full callback URL with query parameters
            state: The OAuth state parameter for CSRF protection
            user: The user who initiated the connection
            
        Returns:
            PlatformConnection: The created or updated connection
        """
        try:
            # Log environment information for debugging
            logger.warning(f"OAuth Callback - Current ENVIRONMENT: {settings.ENVIRONMENT}")
            logger.warning(f"OAuth Callback - IS_DEVELOPMENT: {settings.IS_DEVELOPMENT}")
            logger.warning(f"OAuth Callback - GOOGLE_OAUTH_CLIENT_ID exists: {settings.GOOGLE_OAUTH_CLIENT_ID is not None}")
            logger.warning(f"OAuth Callback - GOOGLE_OAUTH_CLIENT_SECRET exists: {settings.GOOGLE_OAUTH_CLIENT_SECRET is not None}")
            
            # Check if we're in production environment
            if settings.ENVIRONMENT == 'production':
                # Verify that environment variables are available
                if not settings.GOOGLE_OAUTH_CLIENT_ID or not settings.GOOGLE_OAUTH_CLIENT_SECRET:
                    logger.error("Production environment detected but OAuth credentials are missing from environment variables")
                    raise ValueError("Google OAuth credentials are not configured in environment variables")
                    
                # Use client credentials from environment variables
                client_config = {
                    "web": {
                        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                        "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token"
                    }
                }
                flow = google_auth_oauthlib.flow.Flow.from_client_config(
                    client_config,
                    scopes=settings.GOOGLE_OAUTH_SCOPES,
                    state=state
                )
            else:
                # Use client credentials from file in development
                try:
                    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
                        settings.GOOGLE_OAUTH_CLIENT_SECRET_PATH,
                        scopes=settings.GOOGLE_OAUTH_SCOPES,
                        state=state
                    )
                except FileNotFoundError:
                    logger.error(f"Client secrets file not found at: {settings.GOOGLE_OAUTH_CLIENT_SECRET_PATH}")
                    raise ValueError(f"Google OAuth client secrets file not found. Please check the path: {settings.GOOGLE_OAUTH_CLIENT_SECRET_PATH}")
                except Exception as e:
                    logger.error(f"Error loading client secrets: {str(e)}")
                    raise
            
            # Set the same redirect URI used in the initial request
            flow.redirect_uri = authorization_response.split('?')[0]
            
            # Exchange authorization code for tokens
            flow.fetch_token(authorization_response=authorization_response)
            
            # Get credentials
            credentials = flow.credentials
            
            # Get user info
            user_info = self._get_user_info(credentials)
            
            # Check if this Google account is already connected
            existing_connection = PlatformConnection.objects.filter(
                tenant=self.tenant,
                platform_type=self.platform_type,
                platform_account_email=user_info.get('email'),
                is_active=True
            ).first()
            
            # If the account is already connected and active, update it
            if existing_connection:
                # Update the existing connection
                existing_connection.access_token = credentials.token
                existing_connection.refresh_token = credentials.refresh_token
                existing_connection.token_expiry = datetime.datetime.fromtimestamp(credentials.expiry.timestamp()) if hasattr(credentials, 'expiry') and credentials.expiry else None
                existing_connection.connection_status = 'active'
                existing_connection.status_message = ''
                
                # Update with comprehensive token metadata
                token_metadata = existing_connection.token_metadata or {}
                token_metadata['updated_at'] = timezone.now().isoformat()
                token_metadata['token_uri'] = 'https://oauth2.googleapis.com/token'
                token_metadata['client_id'] = settings.GOOGLE_OAUTH_CLIENT_ID
                token_metadata['scopes'] = settings.GOOGLE_OAUTH_SCOPES
                
                if hasattr(credentials, 'id_token'):
                    token_metadata['id_token'] = credentials.id_token
                    
                if hasattr(credentials, 'token_type'):
                    token_metadata['token_type'] = credentials.token_type
                    
                existing_connection.token_metadata = token_metadata
                existing_connection.status_message = ''
                existing_connection.save()
                
                return existing_connection
            else:
                # Build a comprehensive token metadata object
                token_metadata = {
                    'created_at': timezone.now().isoformat(),
                    'token_uri': 'https://oauth2.googleapis.com/token',
                    'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
                    'scopes': settings.GOOGLE_OAUTH_SCOPES
                }
                
                if hasattr(credentials, 'id_token'):
                    token_metadata['id_token'] = credentials.id_token
                    
                if hasattr(credentials, 'token_type'):
                    token_metadata['token_type'] = credentials.token_type
                
                # Create a new connection with all required fields
                connection = PlatformConnection.objects.create(
                    tenant=self.tenant,
                    platform_type=self.platform_type,
                    platform_account_email=user_info.get('email'),
                    platform_account_name=user_info.get('name', user_info.get('email')),
                    connected_user=user,
                    access_token=credentials.token,
                    refresh_token=credentials.refresh_token,
                    token_expiry=datetime.datetime.fromtimestamp(credentials.expiry.timestamp()) if hasattr(credentials, 'expiry') and credentials.expiry else None,
                    token_metadata=token_metadata,
                    is_active=True,
                    connection_status='active',
                    status_message=''
                )
                
                return connection
                
        except Exception as e:
            logger.error(f"Error in OAuth callback: {str(e)}")
            raise
        
    def refresh_token(self, connection):
        """
        Refresh the access token for a Google Ads connection.
        
        Args:
            connection: The PlatformConnection object to refresh
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not connection.refresh_token:
            connection.set_connection_error("No refresh token available")
            return False
        
        # Check if required settings are available
        if not settings.GOOGLE_OAUTH_CLIENT_ID or not settings.GOOGLE_OAUTH_CLIENT_SECRET:
            connection.set_connection_error("Google OAuth client ID or secret not configured")
            return False
        
        try:
            # Create credentials from stored tokens with all required fields
            credentials = google.oauth2.credentials.Credentials(
                token=connection.access_token,
                refresh_token=connection.refresh_token,
                token_uri='https://oauth2.googleapis.com/token',
                client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
                client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
                scopes=settings.GOOGLE_OAUTH_SCOPES
            )
            
            # Force token refresh
            request = google.auth.transport.requests.Request()
            credentials.refresh(request)
            
            # Update the connection with new token info
            connection.access_token = credentials.token
            connection.token_expiry = datetime.datetime.fromtimestamp(credentials.expiry.timestamp()) if hasattr(credentials, 'expiry') and credentials.expiry else None
            connection.connection_status = 'active'
            connection.status_message = ''
            
            # Update token metadata to include any missing fields
            token_metadata = connection.token_metadata or {}
            token_metadata['updated_at'] = timezone.now().isoformat()
            token_metadata['token_uri'] = 'https://oauth2.googleapis.com/token'
            
            if hasattr(credentials, 'id_token'):
                token_metadata['id_token'] = credentials.id_token
                
            if hasattr(credentials, 'token_type'):
                token_metadata['token_type'] = credentials.token_type
                
            connection.token_metadata = token_metadata
            connection.save()
            
            return True
            
        except Exception as e:
            error_msg = f"Failed to refresh token: {str(e)}"
            logger.error(f"Token refresh error for connection {connection.id}: {error_msg}")
            logger.error(f"Connection details: refresh_token exists: {bool(connection.refresh_token)}, client_id exists: {bool(settings.GOOGLE_OAUTH_CLIENT_ID)}")
            connection.set_connection_error(error_msg)
            return False
    
    def disconnect(self, connection):
        """
        Revoke Google Ads tokens and mark connection as disconnected.
        
        Args:
            connection: The PlatformConnection object to disconnect
            
        Returns:
            bool: True if successful, False otherwise
        """
        if connection.access_token:
            try:
                # Revoke the token
                requests.post(
                    'https://oauth2.googleapis.com/revoke',
                    params={'token': connection.access_token},
                    headers={'content-type': 'application/x-www-form-urlencoded'}
                )
            except Exception as e:
                logger.warning(f"Error revoking token: {str(e)}")
        
        # Mark connection as disconnected
        connection.is_active = False
        connection.connection_status = 'disconnected'
        connection.save()
        
        return True
    
    def get_account_info(self, connection):
        """
        Get information about the connected Google account.
        
        Args:
            connection: The PlatformConnection object
            
        Returns:
            dict: Account information or None if unavailable
        """
        if connection.is_token_expired():
            success = self.refresh_token(connection)
            if not success:
                return None
        
        try:
            # Create credentials
            credentials = google.oauth2.credentials.Credentials(
                token=connection.access_token,
                refresh_token=connection.refresh_token,
                token_uri='https://oauth2.googleapis.com/token',
                client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
                client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET
            )
            
            # Get user info
            user_info = self._get_user_info(credentials)
            return user_info
            
        except Exception as e:
            connection.set_connection_error(f"Failed to get account info: {str(e)}")
            return None
        
    def _get_account_info(self, credentials, customer_id):
        """
        Get detailed information about a Google Ads account
        
        Args:
            credentials: OAuth credentials
            customer_id: Google Ads customer ID
        
        Returns:
            dict: Account information
        """
        try:
            # Set up request headers
            headers = {
                'Authorization': f'Bearer {credentials.token}',
                'developer-token': settings.GOOGLE_ADS_DEVELOPER_TOKEN
            }
            
            # Define the endpoint
            api_url = f"https://googleads.googleapis.com/v19/customers/{customer_id}/googleAds:search"
            
            # Define the query for customer information
            query = """
                SELECT 
                    customer.id, 
                    customer.descriptive_name, 
                    customer.manager,
                    customer.currency_code,
                    customer.time_zone
                FROM customer
            """
            
            # Make the API request
            logger.warning(f"FETCHING DETAILS FOR ACCOUNT {customer_id}")
            
            response = requests.post(
                api_url,
                headers=headers,
                json={'query': query}
            )
            
            # Parse the response and extract account details
            if response.status_code == 200:
                data = response.json()
                logger.warning(f"API RESPONSE FOR {customer_id}: {data}")
                
                if 'results' in data and len(data['results']) > 0:
                    # Find the main customer info
                    for result in data['results']:
                        if 'customer' in result:
                            customer = result['customer']
                            logger.warning(f"FOUND CUSTOMER INFO: {customer}")
                            
                            account_info = {
                                'id': customer.get('id'),
                                'descriptive_name': customer.get('descriptive_name'),
                                'is_manager': customer.get('manager', False),
                                'currency_code': customer.get('currency_code'),
                                'time_zone': customer.get('time_zone')
                            }
                            
                            logger.warning(f"RETURNING ACCOUNT INFO: {account_info}")
                            return account_info
                
                # If we couldn't find detailed info, return a minimal response
                return {'id': customer_id}
                
            elif response.status_code == 400 and "Metrics cannot be requested for a manager account" in response.text:
                # This is a manager account
                return {
                    'id': customer_id,
                    'is_manager': True
                }
            
            else:
                logger.warning(f"Could not get account info for {customer_id}: {response.status_code} - {response.text}")
                return {'id': customer_id}
                
        except Exception as e:
            logger.warning(f"Error getting account info: {str(e)}")
            return {'id': customer_id}
    
    def _get_user_info(self, credentials):
        """
        Helper method to get Google user info using tokens.
        
        Args:
            credentials: Google OAuth credentials object
            
        Returns:
            dict: User information from Google
        """
        try:
            # Use the access token to get user info
            response = requests.get(
                'https://www.googleapis.com/oauth2/v1/userinfo',
                headers={'Authorization': f'Bearer {credentials.token}'}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error getting user info: {str(e)}")
            return {'email': 'unknown@example.com', 'name': 'Unknown User'}
            
    def lookup_account_names(self, connection, account_ids):
        """
        Directly lookup account names using customer IDs
        
        Args:
            connection: The PlatformConnection object
            account_ids: List of account IDs to look up names for
            
        Returns:
            dict: Mapping of account ID to name
        """
        logger.warning(f"DIRECT NAME LOOKUP: Looking up names for {len(account_ids)} accounts")
        
        # Check if token needs refresh
        if connection.is_token_expired():
            success = self.refresh_token(connection)
            if not success:
                logger.error("TOKEN REFRESH FAILED during name lookup")
                return {}
        
        # Create credentials
        credentials = google.oauth2.credentials.Credentials(
            token=connection.access_token,
            refresh_token=connection.refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
            client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET
        )
        
        # Use the first account as login customer ID
        login_id = account_ids[0].replace('-', '') if account_ids else None
        if not login_id:
            logger.error("No account IDs provided for lookup")
            return {}
            
        # Set up request headers
        headers = {
            'Authorization': f'Bearer {credentials.token}',
            'developer-token': settings.GOOGLE_ADS_DEVELOPER_TOKEN,
            'login-customer-id': login_id
        }
        
        account_names = {}
        
        # Look up names for each account
        for account_id in account_ids:
            try:
                # Remove hyphens for API call
                customer_id = account_id.replace('-', '')
                
                # API endpoint
                api_url = f"https://googleads.googleapis.com/v19/customers/{customer_id}/googleAds:search"
                
                # Query for account name
                query = f"""
                    SELECT customer.id, customer.descriptive_name, customer.manager
                    FROM customer
                    WHERE customer.id = {customer_id}
                    LIMIT 1
                """
                
                # Make the request
                response = requests.post(
                    api_url,
                    headers=headers,
                    json={'query': query}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    logger.warning(f"NAME LOOKUP RESPONSE FOR {account_id}: {data}")
                    
                    if 'results' in data and len(data['results']) > 0:
                        for result in data['results']:
                            if 'customer' in result:
                                customer = result['customer']
                                if customer.get('descriptive_name'):
                                    account_names[account_id] = customer['descriptive_name']
                                    logger.warning(f"✅ FOUND NAME for {account_id}: '{customer['descriptive_name']}'")
                                else:
                                    logger.warning(f"❌ NO NAME found for {account_id}")
                else:
                    logger.warning(f"❌ API ERROR for {account_id}: {response.status_code} - {response.text}")
            except Exception as e:
                logger.error(f"Error looking up name for {account_id}: {str(e)}")
        
        logger.warning(f"NAME LOOKUP COMPLETE: Found names for {len(account_names)} of {len(account_ids)} accounts")
        return account_names

    def get_adwords_customer_ids(self, connection):
        try:
            # Check if token needs refresh
            if connection.is_token_expired():
                success = self.refresh_token(connection)
                if not success:
                    return [{"id": "ERROR", "name": "OAuth token refresh failed"}]
            
            # Log environment information for debugging
            logger.warning(f"Current ENVIRONMENT: {settings.ENVIRONMENT}")
            logger.warning(f"IS_DEVELOPMENT: {settings.IS_DEVELOPMENT}")
            logger.warning(f"GOOGLE_OAUTH_CLIENT_ID from settings: {settings.GOOGLE_OAUTH_CLIENT_ID is not None}")
            logger.warning(f"GOOGLE_OAUTH_CLIENT_SECRET from settings: {settings.GOOGLE_OAUTH_CLIENT_SECRET is not None}")
            
            # Create credentials
            credentials = google.oauth2.credentials.Credentials(
                token=connection.access_token,
                refresh_token=connection.refresh_token,
                token_uri='https://oauth2.googleapis.com/token',
                client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
                client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET
            )
            
            all_accounts = []
            manager_accounts = []
            
            try:
                logger.info("Using Google Ads API v19...")
                
                # Set up request headers for REST API
                headers = {
                    'Authorization': f'Bearer {credentials.token}',
                    'developer-token': settings.GOOGLE_ADS_DEVELOPER_TOKEN
                }
                
                # Use listAccessibleCustomers API to get all available accounts
                list_url = 'https://googleads.googleapis.com/v19/customers:listAccessibleCustomers'
                
                response = requests.get(list_url, headers=headers)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if 'resourceNames' in data and data['resourceNames']:
                        # Process each account ID
                        for resource_name in data['resourceNames']:
                            customer_id = resource_name.split('/')[-1]
                            
                            # Format with hyphens for readability
                            if len(customer_id) >= 10:
                                formatted_id = f"{customer_id[:3]}-{customer_id[3:6]}-{customer_id[6:]}"
                            else:
                                formatted_id = customer_id
                            
                            # Try to get account details (may not be available for all accounts)
                            account_info = self._get_account_info(credentials, customer_id)
                            
                            # LOG ACTUAL ACCOUNT INFO FOR DEBUGGING
                            logger.warning(f"ACCOUNT INFO FOR {formatted_id}: {account_info}")
                            
                            # Determine if this is a manager account
                            is_manager = account_info.get('is_manager', False)
                            
                            # Set account display name - THIS IS THE CRITICAL PART THAT'S NOT WORKING
                            if account_info and account_info.get('descriptive_name'):
                                display_name = account_info['descriptive_name']
                                logger.warning(f"✅ Using descriptive name from API: '{display_name}' for account {formatted_id}")
                            else:
                                # IMPORTANT: Generate a more descriptive name based on account type
                                account_type = "Manager" if is_manager else "Client" 
                                display_name = f"Google Ads {account_type} {formatted_id}"
                                logger.warning(f"⚠️ Using GENERATED name: '{display_name}' for account {formatted_id} because API returned no name")
                                
                                # Try to infer if it's a manager account from the name
                                if "manager" in display_name.lower():
                                    is_manager = True
                            
                            # Store manager accounts separately to process manager-client relationships
                            if is_manager:
                                manager_accounts.append({
                                    "id": formatted_id,
                                    "name": display_name,
                                    "raw_id": customer_id,
                                    "is_manager": True
                                })
                                
                            # Add to the main accounts list
                            account_data = {
                                "id": formatted_id,
                                "name": display_name,
                                "raw_id": customer_id,
                                "is_manager": is_manager
                            }
                            
                            # Add parent_id if available
                            if account_info and account_info.get('parent_id'):
                                parent_raw_id = account_info['parent_id']
                                if len(parent_raw_id) >= 9:
                                    parent_id = f"{parent_raw_id[:3]}-{parent_raw_id[3:6]}-{parent_raw_id[6:]}"
                                    account_data["parent_id"] = parent_id
                            
                            all_accounts.append(account_data)
                        
                        logger.info(f"Successfully found {len(all_accounts)} accounts via REST API")
                        
                        # Try to enhance the hierarchy information
                        self._enhance_accounts_hierarchy(all_accounts, manager_accounts, credentials)
                        
                        # NEW: Perform direct account name lookup for all accounts
                        logger.warning("🔎 PERFORMING DIRECT ACCOUNT NAME LOOKUP")
                        account_ids = [account['id'] for account in all_accounts]
                        account_names = self.lookup_account_names(connection, account_ids)
                        
                        # Update account names with the results from direct lookup
                        if account_names:
                            logger.warning(f"✅ UPDATING ACCOUNTS with {len(account_names)} names from direct lookup")
                            for account in all_accounts:
                                if account['id'] in account_names:
                                    old_name = account.get('name', 'NONE')
                                    account['name'] = account_names[account['id']]
                                    logger.warning(f"Updated account {account['id']} name: '{old_name}' -> '{account['name']}'")
                            
                            # Also update child accounts that might not be in the main list
                            for account in all_accounts:
                                if account.get('child_accounts'):
                                    for child in account['child_accounts']:
                                        if child['id'] in account_names:
                                            old_name = child.get('name', 'NONE')
                                            child['name'] = account_names[child['id']]
                                            logger.warning(f"Updated child account {child['id']} name: '{old_name}' -> '{child['name']}'")
                        
                        return all_accounts
                    else:
                        logger.warning("No accounts found with REST API")
                else:
                    logger.warning(f"REST API failed: {response.status_code} - {response.text}")
            
            except Exception as rest_error:
                logger.warning(f"REST API approach failed: {str(rest_error)}")
                logger.warning(traceback.format_exc())
            
            # If all API methods fail but we have a valid token, return empty list
            return all_accounts if all_accounts else []
                
        except Exception as e:
            logger.error(f"Error getting Google Ads customer IDs: {str(e)}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            
            return []
        
    
    def _enhance_accounts_hierarchy(self, all_accounts, manager_accounts, credentials):
        """
        Try to enhance the accounts with hierarchy information and fetch child accounts
        
        Args:
            all_accounts: List of all account dictionaries
            manager_accounts: List or dict of manager account dictionaries
            credentials: OAuth credentials
        """
        try:
            # CRITICAL FIX: Create a dict for quick account lookup by ID
            # Make sure we handle IDs consistently with and without dashes
            account_dict = {}
            for account in all_accounts:
                account_id = account['id']
                account_dict[account_id] = account
                # Also add entry with raw ID (no dashes) for lookups that might use either format
                raw_id = account_id.replace('-', '')
                if raw_id != account_id:
                    account_dict[raw_id] = account
                    
            # Add special debug for our target accounts
            if '359-352-3038' in account_dict:
                logger.warning(f"🔍 Manager 359-352-3038 exists in account_dict")
            if '676-582-6170' in account_dict:
                logger.warning(f"🔍 Child account 676-582-6170 exists in account_dict")
            
            # Handle manager_accounts being either a list or a dictionary
            if isinstance(manager_accounts, dict):
                # Convert to list of values
                managers_list = list(manager_accounts.values())
                logger.info(f"Converting manager_accounts dict to list with {len(managers_list)} items")
            else:
                managers_list = manager_accounts
                
            # Process all manager accounts, including nested ones
            processed_managers = set()
            
            # Function to recursively process manager accounts and their children
            def process_manager(manager, depth=0):
                if depth > 5:  # Prevent infinite recursion
                    return
                
                # CRITICAL FIX: Check for our specific target manager and add extra debugging
                if manager['id'] == '359-352-3038':
                    logger.warning(f"🚨 PROCESSING TARGET MANAGER: 359-352-3038")
                    logger.warning(f"Manager raw ID: {manager.get('raw_id', 'unknown')}")
                
                # CRITICAL FIX: Make sure raw_id exists, and handle format consistently
                manager_id = manager.get('raw_id')
                if not manager_id:
                    manager_id = manager['id'].replace('-', '')
                    manager['raw_id'] = manager_id
                    
                if manager_id in processed_managers:
                    logger.info(f"Skipping already processed manager: {manager['id']}")
                    return
                
                processed_managers.add(manager_id)
                logger.info(f"Processing manager {manager['id']} at depth {depth}")
                
                try:
                    # Set up request headers
                    headers = {
                        'Authorization': f'Bearer {credentials.token}',
                        'developer-token': settings.GOOGLE_ADS_DEVELOPER_TOKEN
                    }
                    
                    # Use the v19 API endpoint
                    api_url = f"https://googleads.googleapis.com/v19/customers/{manager_id}/googleAds:search"
                    
                    # Define the query to get ALL child accounts with no status filter to include paused/removed accounts
                    query = """
                        SELECT 
                            customer_client.client_customer,
                            customer_client.level,
                            customer_client.descriptive_name,
                            customer_client.id,
                            customer_client.manager, 
                            customer_client.status,
                            customer_client.resource_name
                        FROM customer_client
                        ORDER BY customer_client.level ASC, customer_client.descriptive_name ASC
                    """
                    
                    # Log specific debug info for important manager accounts - especially 359-352-3038
                    if manager['id'] == '359-352-3038':
                        logger.warning(f"🔍 DEBUGGING SPECIFIC MANAGER: {manager['id']} ({manager['name']})")
                        logger.warning(f"Raw ID: {manager['raw_id']}")
                    
                    # Make the API request
                    response = requests.post(
                        api_url,
                        headers=headers,
                        json={'query': query}
                    )
                    
                    child_accounts = []
                    sub_managers = []
                    
                    # Parse the response to identify child accounts
                    if response.status_code == 200:
                        data = response.json()
                        
                        # CRITICAL: Import json if not already imported
                        import json
                        
                        # Log the response for debugging
                        logger.info(f"API Response for manager {manager['id']}: status={response.status_code}")
                        results_count = len(data.get('results', []))
                        logger.info(f"Found {results_count} results for manager {manager['id']}")
                        
                        # Extra debugging for specific manager account
                        if manager['id'] == '359-352-3038':
                            logger.warning(f"🔍 DETAILED DEBUG: Manager 359-352-3038 returned {results_count} results")
                            # Print first 5 results for debugging
                            for i, result in enumerate(data.get('results', [])[:5]):
                                logger.warning(f"Result {i+1}: {json.dumps(result, indent=2)}")
                        
                        # Flag to track if we find any valid child accounts
                        valid_child_accounts_found = False
                        
                        if 'results' in data:
                            for result in data['results']:
                                if 'customerClient' in result and 'clientCustomer' in result['customerClient']:
                                    # Extract child account ID
                                    child_id_raw = result['customerClient']['clientCustomer'].split('/')[-1]
                                    
                                    # CRITICAL FIX: Make sure we're comparing raw IDs properly
                                    # The manager_id might have dashes, so remove them for comparison
                                    manager_raw_id = manager_id.replace('-', '')
                                    if child_id_raw == manager_raw_id:
                                        logger.info(f"Skipping self-reference for manager {manager['id']}")
                                        continue
                                    
                                    # Format with hyphens
                                    if len(child_id_raw) >= 9:
                                        child_id = f"{child_id_raw[:3]}-{child_id_raw[3:6]}-{child_id_raw[6:]}"
                                    else:
                                        child_id = child_id_raw
                                        
                                    # Special debug for the specific account we're looking for
                                    if child_id == '676-582-6170' or child_id_raw == '6765826170':
                                        logger.warning(f"🎯 FOUND TARGET ACCOUNT 676-582-6170 under manager {manager['id']}")
                                        logger.warning(f"Parent manager: {manager['id']}, Raw child ID: {child_id_raw}, Formatted: {child_id}")
                                    
                                    # Special debug for manager 359-352-3038
                                    if manager['id'] == '359-352-3038':
                                        logger.warning(f"Child account found under 359-352-3038: {child_id}")
                                    
                                    # Get account details
                                    descriptive_name = None
                                    is_manager = False
                                    level = 0
                                    status = 'ACTIVE' # Default status
                                    
                                    if 'descriptive_name' in result['customerClient']:
                                        descriptive_name = result['customerClient']['descriptive_name']
                                    
                                    # CRITICAL FIX: Implement better manager account detection
                                    # Google Ads API sometimes incorrectly marks accounts as managers
                                    manager_flag = False
                                    if 'manager' in result['customerClient']:
                                        manager_flag = result['customerClient']['manager']
                                    
                                    # Simply use the manager flag from the API
                                    is_manager = manager_flag
                                    
                                    # Log debug info for accounts marked as managers
                                    if manager_flag:
                                        logger.info(f"API reports account as manager: {child_id} ({descriptive_name})")
                                        
                                    if 'level' in result['customerClient']:
                                        level = int(result['customerClient']['level'])
                                    
                                    if 'status' in result['customerClient']:
                                        status = result['customerClient']['status']
                                    
                                    # Skip inactive accounts
                                    if status == 'INACTIVE':
                                        logger.info(f"Skipping inactive account: {descriptive_name} (ID: {child_id})")
                                        continue
                                        
                                    # We found at least one valid child account
                                    valid_child_accounts_found = True
                                        
                                    # Log account details for debugging
                                    logger.info(f"Found account: {descriptive_name} (ID: {child_id}), Manager: {is_manager}, Level: {level}, Status: {status}")
                                    
                                    # Create child account object with consistent ID formatting
                                    child_account = {
                                        "id": child_id,
                                        "name": descriptive_name or f"Account {child_id}",
                                        "raw_id": child_id_raw,
                                        "is_manager": is_manager,
                                        "parent_id": manager['id'],
                                        "level": level,
                                        "status": status
                                    }
                                    
                                    # CRITICAL FIX: Special debug when child account is 676-582-6170
                                    if child_id == '676-582-6170':
                                        logger.warning(f"📌 Created child account object for 676-582-6170:")
                                        logger.warning(f"📌 Parent: {manager['id']}, Is manager: {is_manager}, Status: {status}")
                                    
                                    # CRITICAL FIX: Check if this account is already in our main list
                                    # We need to be consistent with ID formats (raw vs dashed)
                                    existing_account = None
                                    if child_id in account_dict:
                                        existing_account = account_dict[child_id]
                                    elif child_id_raw in account_dict:
                                        existing_account = account_dict[child_id_raw]
                                        
                                    if existing_account:
                                        # Update existing account with parent info
                                        for key, value in child_account.items():
                                            existing_account[key] = value
                                            
                                        # Special debug for our target account
                                        if child_id == '676-582-6170':
                                            logger.warning(f"🔄 UPDATED existing account 676-582-6170 with parent info")
                                    else:
                                        # Add to our data structures
                                        all_accounts.append(child_account)
                                        account_dict[child_id] = child_account
                                        # Also add with raw ID for future lookups
                                        account_dict[child_id_raw] = child_account
                                        
                                        # Special debug for our target account
                                        if child_id == '676-582-6170':
                                            logger.warning(f"➕ ADDED NEW account 676-582-6170 to all_accounts")
                                    
                                    # Add to child accounts list
                                    child_accounts.append(child_account)
                                    
                                    # Track sub-managers for recursive processing
                                    if is_manager:
                                        sub_managers.append(child_account)
                    
                    # Explicitly add child accounts to the manager account to create hierarchy
                    # CRITICAL FIX: Make sure the child accounts list is properly attached
                    manager['child_accounts'] = child_accounts
                    
                    # Update this manager account in the master list if it exists there
                    # This ensures hierarchy changes propagate to the final output
                    found_in_all_accounts = False
                    for i, acct in enumerate(all_accounts):
                        if acct.get('id') == manager['id']:
                            all_accounts[i]['child_accounts'] = child_accounts
                            found_in_all_accounts = True
                            logger.info(f"Updated manager {manager['id']} in all_accounts with {len(child_accounts)} children")
                            break
                    
                    # Special debugging for our target manager
                    if manager['id'] == '359-352-3038':
                        child_ids = [child.get('id') for child in child_accounts]
                        logger.warning(f"🔍 Manager 359-352-3038 child accounts: {child_ids}")
                        # Check if our specific account is in the children
                        if '676-582-6170' in child_ids:
                            logger.warning(f"✅ FOUND 676-582-6170 in children of 359-352-3038!")
                        else:
                            logger.warning(f"❌ 676-582-6170 NOT found in children of 359-352-3038")
                            # Search through raw data for this account ID
                            for result in data.get('results', []):
                                if "676-582-6170" in str(result):
                                    logger.warning(f"Found 676-582-6170 in raw data: {json.dumps(result)}")
                    
                    # Log whether we actually found any valid child accounts
                    if not valid_child_accounts_found:
                        logger.warning(f"⚠️ Manager {manager['id']} ({manager['name']}) has NO VALID CHILD ACCOUNTS. This will cause display issues in the modal.")
                        
                    logger.info(f"Manager {manager['id']} now has {len(child_accounts)} child accounts")
                    
                    # Log a few sample child accounts for debugging
                    if child_accounts:
                        sample_accounts = child_accounts[:3] if len(child_accounts) > 3 else child_accounts
                        logger.info(f"Sample child accounts for manager {manager['id']}: {[a.get('id') for a in sample_accounts]}")
                    
                    # Recursively process sub-managers
                    for sub_manager in sub_managers:
                        process_manager(sub_manager, depth+1)
                    
                except Exception as e:
                    logger.warning(f"Error enhancing manager account {manager['id']}: {str(e)}")
                    logger.warning(traceback.format_exc())
            
            # Process each top-level manager
            for manager in managers_list:
                process_manager(manager)
                
        except Exception as e:
            logger.warning(f"Error enhancing accounts hierarchy: {str(e)}")
            logger.warning(traceback.format_exc())
            # Continue with the basic account information

    def _enhance_account_information(self, client, accounts):
        """
        Enhance account information with descriptive names and additional details.
        
        Args:
            client: GoogleAdsClient instance
            accounts: List of account dictionaries
        """
        try:
            # Only process if we have accounts
            if not accounts:
                return
            
            # Get the first account to use as a login customer ID
            login_customer_id = accounts[0]["id"].replace("-", "")
            
            # Create a GoogleAdsService client
            ga_service = client.get_service("GoogleAdsService")
            
            # Process each account to get more details
            for account in accounts:
                try:
                    # Remove hyphens for API call
                    customer_id = account["id"].replace("-", "")
                    
                    # Create query to get account information
                    query = """
                        SELECT
                            customer.id,
                            customer.descriptive_name,
                            customer.currency_code,
                            customer.time_zone,
                            customer.auto_tagging_enabled
                        FROM customer
                        WHERE customer.id = %s
                    """ % customer_id
                    
                    # Create the search request
                    search_request = client.get_type("SearchGoogleAdsRequest")
                    search_request.customer_id = login_customer_id
                    search_request.query = query
                    
                    # Execute the query
                    response = ga_service.search(request=search_request)
                    
                    # Update account information if we get results
                    for row in response:
                        customer = row.customer
                        if customer.descriptive_name:
                            account["name"] = customer.descriptive_name
                        break
                        
                except Exception as account_error:
                    # Log error but continue with next account
                    logger.warning(f"Error enhancing account {account['id']}: {str(account_error)}")
                    continue
        
        except Exception as e:
            logger.warning(f"Error enhancing account information: {str(e)}")
            # Continue with basic account information

    def get_accessible_accounts(self, connection):
        return self.get_adwords_customer_ids(connection)