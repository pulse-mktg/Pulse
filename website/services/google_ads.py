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
            
            # Check if this Google account is already connected (regardless of active status)
            existing_connection = PlatformConnection.objects.filter(
                tenant=self.tenant,
                platform_type=self.platform_type,
                platform_account_email=user_info.get('email')
            ).first()
            
            # If the account exists (active or disconnected), reactivate and update it
            if existing_connection:
                # Reactivate and update the existing connection
                existing_connection.is_active = True  # Reactivate if it was disconnected
                existing_connection.access_token = credentials.token
                existing_connection.refresh_token = credentials.refresh_token
                existing_connection.token_expiry = datetime.datetime.fromtimestamp(credentials.expiry.timestamp()) if hasattr(credentials, 'expiry') and credentials.expiry else None
                existing_connection.connection_status = 'active'
                existing_connection.status_message = 'Reconnected successfully'
                existing_connection.last_synced = timezone.now()  # Update sync timestamp
                
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
        logger.warning(f"--------- TOKEN REFRESH STARTED ---------")
        logger.warning(f"Connection ID: {connection.id}")
        logger.warning(f"Platform Type: {connection.platform_type.name}")
        logger.warning(f"Account Email: {connection.platform_account_email}")
        logger.warning(f"Environment: {settings.ENVIRONMENT}")
        logger.warning(f"Is Token Expired: {connection.is_token_expired()}")
        
        if not connection.refresh_token:
            error_msg = "No refresh token available"
            logger.error(f"TOKEN REFRESH ERROR: {error_msg}")
            connection.set_connection_error(error_msg)
            return False
        
        # Check if required settings are available
        if not settings.GOOGLE_OAUTH_CLIENT_ID or not settings.GOOGLE_OAUTH_CLIENT_SECRET:
            error_msg = "Google OAuth client ID or secret not configured"
            logger.error(f"TOKEN REFRESH ERROR: {error_msg}")
            logger.error(f"GOOGLE_OAUTH_CLIENT_ID present: {bool(settings.GOOGLE_OAUTH_CLIENT_ID)}")
            logger.error(f"GOOGLE_OAUTH_CLIENT_SECRET present: {bool(settings.GOOGLE_OAUTH_CLIENT_SECRET)}")
            connection.set_connection_error(error_msg)
            return False
        
        try:
            # Log token details before refresh
            logger.warning(f"--------- TOKEN REFRESH DETAILS ---------")
            logger.warning(f"OAuth Client ID: {settings.GOOGLE_OAUTH_CLIENT_ID[:10]}...{settings.GOOGLE_OAUTH_CLIENT_ID[-5:] if settings.GOOGLE_OAUTH_CLIENT_ID else 'None'}")
            logger.warning(f"OAuth Client Secret length: {len(settings.GOOGLE_OAUTH_CLIENT_SECRET) if settings.GOOGLE_OAUTH_CLIENT_SECRET else 0} chars")
            logger.warning(f"Current Access Token: {connection.access_token[:5]}...{connection.access_token[-5:] if connection.access_token else 'None'}")
            logger.warning(f"Refresh Token (partial): {connection.refresh_token[:5]}...{connection.refresh_token[-5:] if connection.refresh_token else 'None'}")
            logger.warning(f"Token Expiry: {connection.token_expiry}")
            logger.warning(f"Scopes: {settings.GOOGLE_OAUTH_SCOPES}")
            
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
            logger.warning("Initiating token refresh request...")
            request = google.auth.transport.requests.Request()
            
            try:
                credentials.refresh(request)
                logger.warning("Token refresh successful!")
                logger.warning(f"New Access Token: {credentials.token[:5]}...{credentials.token[-5:] if credentials.token else 'None'}")
                logger.warning(f"New Expiry: {credentials.expiry if hasattr(credentials, 'expiry') else 'None'}")
            except Exception as refresh_error:
                logger.error(f"TOKEN REFRESH REQUEST ERROR: {str(refresh_error)}")
                logger.error(traceback.format_exc())
                
                # More detailed error analysis
                error_str = str(refresh_error)
                if "invalid_grant" in error_str:
                    logger.error("ERROR DETAILS: The refresh token is invalid or expired. The user may need to reconnect the account.")
                elif "invalid_client" in error_str:
                    logger.error("ERROR DETAILS: Client credentials (ID/secret) are invalid.")
                elif "unauthorized_client" in error_str:
                    logger.error("ERROR DETAILS: Client is not authorized to use the refresh token grant type.")
                
                connection.set_connection_error(f"Failed to refresh token: {str(refresh_error)}")
                return False
            
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
            
            logger.warning(f"--------- TOKEN REFRESH COMPLETED SUCCESSFULLY ---------")
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
            api_url = f"https://googleads.googleapis.com/v14/customers/{customer_id}/googleAds:search"
            
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
                api_url = f"https://googleads.googleapis.com/v14/customers/{customer_id}/googleAds:search"
                
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

    def get_google_ads_client(self, connection):
        """
        Build Google Ads Client with OAuth Credentials
        
        Args:
            connection: PlatformConnection instance
            
        Returns:
            GoogleAdsClient: Configured Google Ads client
        """
        try:
            # Check if token needs refresh
            if connection.is_token_expired():
                success = self.refresh_token(connection)
                if not success:
                    raise Exception("OAuth token refresh failed")
            
            # Import required classes
            try:
                from google.oauth2.credentials import Credentials
                from google.ads.googleads.client import GoogleAdsClient
                logger.info("Successfully imported Google Ads client classes")
            except ImportError as e:
                logger.error(f"Failed to import Google Ads client: {e}")
                raise Exception(f"Google Ads client library not available: {e}")
            
            # Create client configuration with all required credentials
            config = {
                "developer_token": settings.GOOGLE_ADS_DEVELOPER_TOKEN,
                "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                "refresh_token": connection.refresh_token,
                "use_proto_plus": True,
            }
            
            # Debug logging (with sanitized values)
            logger.info(f"Config debug: developer_token present: {bool(config.get('developer_token'))}")
            logger.info(f"Config debug: client_id present: {bool(config.get('client_id'))}")
            logger.info(f"Config debug: client_secret present: {bool(config.get('client_secret'))}")
            logger.info(f"Config debug: refresh_token present: {bool(config.get('refresh_token'))}")
            
            # Create Google Ads client (credentials are handled internally)
            # Use v14 since that's what the library supports
            try:
                logger.info("Attempting to create Google Ads client v14...")
                client = GoogleAdsClient.load_from_dict(config, version="v14")
                logger.info("Successfully created Google Ads client v14")
            except Exception as e:
                logger.warning(f"Failed to create v14 client: {e}, trying v13")
                try:
                    client = GoogleAdsClient.load_from_dict(config, version="v13")
                    logger.info("Successfully created Google Ads client v13")
                except Exception as e2:
                    logger.error(f"Failed to create Google Ads client with available versions: v14({e}), v13({e2})")
                    raise Exception(f"Could not create Google Ads client: {e2}")
            
            return client
            
        except Exception as e:
            logger.error(f"Error creating Google Ads client: {str(e)}")
            raise
    
    def list_accessible_customer_ids(self, connection, client=None):
        """
        Get Accessible Account IDs using direct requests to Google Ads API
        
        Args:
            connection: PlatformConnection instance
            client: Optional pre-created GoogleAdsClient instance (unused in this implementation)
            
        Returns:
            List[str]: List of accessible customer IDs
        """
        try:
            logger.info("🔗 API: Using direct requests approach for accessible customer IDs")
            
            # Check if token needs refresh
            if connection.is_token_expired():
                success = self.refresh_token(connection)
                if not success:
                    logger.error("TOKEN REFRESH FAILED during account retrieval")
                    return []
            
            # Use a direct approach to find customer IDs
            # We'll use the AdWords API reporting method to discover accounts
            import requests
            
            # Set up request headers
            headers = {
                'Authorization': f'Bearer {connection.access_token}',
                'developer-token': settings.GOOGLE_ADS_DEVELOPER_TOKEN,
                'Content-Type': 'application/json'
            }
            
            # Method 1: Try to get account info directly from Google MyBusiness/AdWords API
            logger.info("🔗 API: Trying to discover accounts via direct search")
            
            # Let's try a different approach - use the cached accounts if available
            # and then verify them by making individual API calls
            from ..models import GoogleAdsAccount
            
            cached_accounts = GoogleAdsAccount.objects.filter(
                platform_connection=connection,
                sync_status='active'
            ).values_list('raw_account_id', flat=True)
            
            if cached_accounts:
                logger.info(f"📋 CACHE: Found {len(cached_accounts)} cached account IDs")
                
                # Verify these accounts are still accessible
                verified_accounts = []
                
                for account_id in cached_accounts[:10]:  # Test first 10 accounts
                    try:
                        # Try to make a simple API call to verify the account exists
                        api_url = f"https://googleads.googleapis.com/v14/customers/{account_id}/googleAds:search"
                        
                        # Simple query to check if account is accessible
                        query = {
                            'query': 'SELECT customer.id FROM customer LIMIT 1'
                        }
                        
                        response = requests.post(api_url, headers=headers, json=query)
                        
                        if response.status_code == 200:
                            verified_accounts.append(account_id)
                            logger.info(f"✅ API: Verified account {account_id} is accessible")
                        else:
                            logger.warning(f"⚠️ API: Account {account_id} not accessible: {response.status_code}")
                            
                    except Exception as e:
                        logger.warning(f"⚠️ API: Error verifying account {account_id}: {str(e)}")
                        continue
                
                if verified_accounts:
                    logger.info(f"✅ API: Verified {len(verified_accounts)} accounts are accessible")
                    # Return all cached accounts if some are verified
                    return list(cached_accounts)
                else:
                    logger.warning("⚠️ API: No cached accounts could be verified")
            
            # Method 2: Manual account discovery using known patterns
            logger.info("🔗 API: Attempting manual account discovery")
            
            # If we have cached accounts, use them as a starting point
            if cached_accounts:
                logger.info(f"📋 FALLBACK: Using {len(cached_accounts)} cached account IDs")
                return list(cached_accounts)
            
            # If no cached accounts, return empty list and let the system handle it
            logger.warning("⚠️ API: No accounts found via direct API calls")
            return []
                
        except Exception as e:
            logger.error(f"Error getting accessible customer IDs: {str(e)}")
            # Log the specific error details
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            
            # Final fallback - try to use cached accounts
            try:
                from ..models import GoogleAdsAccount
                cached_accounts = GoogleAdsAccount.objects.filter(
                    platform_connection=connection,
                    sync_status='active'
                ).values_list('raw_account_id', flat=True)
                
                if cached_accounts:
                    logger.info(f"📋 EMERGENCY FALLBACK: Using {len(cached_accounts)} cached account IDs")
                    return list(cached_accounts)
                    
            except Exception as fallback_error:
                logger.error(f"Even fallback failed: {str(fallback_error)}")
                
            return []
    
    def _get_account_details_direct(self, customer_id, connection):
        """
        Get account details using direct API requests
        
        Args:
            customer_id: Customer ID to query
            connection: PlatformConnection instance
            
        Returns:
            dict: Account details or None if failed
        """
        try:
            if not connection:
                return None
            
            # Set up request headers
            headers = {
                'Authorization': f'Bearer {connection.access_token}',
                'developer-token': settings.GOOGLE_ADS_DEVELOPER_TOKEN,
                'Content-Type': 'application/json'
            }
            
            # API endpoint
            api_url = f"https://googleads.googleapis.com/v14/customers/{customer_id}/googleAds:search"
            
            # Query for account details
            query = {
                'query': '''
                    SELECT 
                        customer.id, 
                        customer.descriptive_name, 
                        customer.manager,
                        customer.currency_code,
                        customer.time_zone,
                        customer.test_account,
                        customer.status
                    FROM customer
                    LIMIT 1
                '''
            }
            
            response = requests.post(api_url, headers=headers, json=query)
            
            if response.status_code == 200:
                data = response.json()
                
                if 'results' in data and len(data['results']) > 0:
                    result = data['results'][0]
                    if 'customer' in result:
                        customer = result['customer']
                        
                        # Format customer ID with hyphens
                        formatted_id = f"{customer_id[:3]}-{customer_id[3:6]}-{customer_id[6:]}" if len(customer_id) >= 9 else customer_id
                        
                        # Extract account details
                        account_data = {
                            "id": formatted_id,
                            "name": customer.get('descriptive_name', f"Google Ads Account {formatted_id}"),
                            "raw_id": customer_id,
                            "is_manager": customer.get('manager', False),
                            "is_test": customer.get('test_account', False),
                            "currency_code": customer.get('currency_code', 'USD'),
                            "time_zone": customer.get('time_zone', 'UTC'),
                            "status": customer.get('status', 'ACTIVE')
                        }
                        
                        logger.info(f"✅ Direct API: Retrieved details for account {customer_id}")
                        return account_data
                        
                logger.warning(f"⚠️ Direct API: No customer data found for {customer_id}")
                return None
                
            else:
                logger.warning(f"⚠️ Direct API: Request failed for {customer_id}: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting account details for {customer_id}: {str(e)}")
            return None
    
    def discover_account_hierarchy_direct(self, accounts, manager_accounts, connection):
        """
        Discover parent-child relationships using direct API requests
        
        Args:
            accounts: List of all accounts
            manager_accounts: List of manager accounts
            connection: PlatformConnection instance
            
        Returns:
            List[dict]: Accounts with hierarchy information
        """
        try:
            if not manager_accounts or not connection:
                print("   ℹ️  No manager accounts found or no connection - skipping hierarchy discovery")
                return accounts
            
            print(f"   🔍 Checking {len(manager_accounts)} manager accounts for child relationships")
            
            # Create a mapping of customer_id to account for easy lookup
            account_map = {acc['raw_id']: acc for acc in accounts}
            
            # Set up request headers
            headers = {
                'Authorization': f'Bearer {connection.access_token}',
                'developer-token': settings.GOOGLE_ADS_DEVELOPER_TOKEN,
                'Content-Type': 'application/json'
            }
            
            for manager in manager_accounts:
                try:
                    print(f"\n   📁 Checking Manager: {manager['name']} ({manager['id']})")
                    
                    # API endpoint for this manager
                    api_url = f"https://googleads.googleapis.com/v14/customers/{manager['raw_id']}/googleAds:search"
                    
                    # Query to find child accounts under this manager
                    query = {
                        'query': '''
                            SELECT
                                customer_client.id,
                                customer_client.descriptive_name,
                                customer_client.manager,
                                customer_client.level,
                                customer_client.status
                            FROM customer_client
                            WHERE customer_client.level <= 1
                        '''
                    }
                    
                    response = requests.post(api_url, headers=headers, json=query)
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        child_accounts = []
                        if 'results' in data:
                            for result in data['results']:
                                if 'customerClient' in result:
                                    client_data = result['customerClient']
                                    child_id = str(client_data.get('id', ''))
                                    child_name = client_data.get('descriptive_name', f"Account {child_id}")
                                    child_level = client_data.get('level', 0)
                                    
                                    # Format child ID
                                    formatted_child_id = f"{child_id[:3]}-{child_id[3:6]}-{child_id[6:]}" if len(child_id) >= 9 else child_id
                                    
                                    print(f"      └── Child: {child_name} ({formatted_child_id}) - Level {child_level}")
                                    
                                    # Update the child account in our accounts list
                                    if child_id in account_map:
                                        account_map[child_id]['parent_id'] = manager['id']
                                        account_map[child_id]['parent_name'] = manager['name']
                                        account_map[child_id]['level'] = child_level
                                        account_map[child_id]['name'] = child_name
                                        print(f"         ✅ Updated parent relationship and name")
                                        logger.info(f"🔄 HIERARCHY: Updated account {child_id} with name '{child_name}'")
                                    
                                    child_accounts.append({
                                        'id': formatted_child_id,
                                        'name': child_name,
                                        'raw_id': child_id,
                                        'level': child_level
                                    })
                        
                        # Add child accounts to manager
                        if child_accounts:
                            manager['child_accounts'] = child_accounts
                            print(f"      📊 Added {len(child_accounts)} child accounts to manager")
                        else:
                            print(f"      ℹ️  No child accounts found")
                    else:
                        print(f"      ❌ API request failed: {response.status_code}")
                        
                except Exception as e:
                    print(f"      ❌ Error checking manager {manager['name']}: {str(e)}")
                    continue
            
            # Update the accounts list with hierarchy info
            updated_accounts = list(account_map.values())
            
            # Count hierarchy stats
            accounts_with_parents = len([acc for acc in updated_accounts if acc.get('parent_id')])
            managers_with_children = len([acc for acc in updated_accounts if acc.get('child_accounts')])
            
            print(f"\n   📊 HIERARCHY DISCOVERY SUMMARY")
            print(f"   Accounts with Parents: {accounts_with_parents}")
            print(f"   Managers with Children: {managers_with_children}")
            
            return updated_accounts
            
        except Exception as e:
            print(f"   ❌ Error in hierarchy discovery: {str(e)}")
            logger.error(f"Error discovering account hierarchy: {str(e)}")
            return accounts
    
    def get_customer_details_with_hierarchy(self, client, customer_ids):
        """
        Get Account Details with Hierarchy Information using direct API requests
        
        Args:
            client: GoogleAdsClient instance (may be None for direct requests)
            customer_ids: List of customer IDs
            
        Returns:
            List[dict]: List of account dictionaries with hierarchy info
        """
        try:
            # Use the output function if available, otherwise use print
            output = getattr(self, '_output', None)
            if not output:
                output = lambda msg: print(msg, flush=True)
            
            output(f"\n🔍 RETRIEVING ACCOUNT DETAILS FOR {len(customer_ids)} ACCOUNTS")
            output("=" * 60)
            
            accounts = []
            manager_accounts = []
            
            # Get the connection to use for direct API calls
            connection = getattr(self, '_current_connection', None)
            
            for i, customer_id in enumerate(customer_ids, 1):
                try:
                    output(f"\n📋 Processing Account {i}/{len(customer_ids)}: {customer_id}")
                    
                    # Try direct API request first
                    account_data = self._get_account_details_direct(customer_id, connection)
                    
                    if account_data:
                        account_name = account_data.get('name', f"Google Ads Account {customer_id}")
                        is_manager = account_data.get('is_manager', False)
                        
                        # Console logging for each account
                        output(f"   ✅ Account Found: {account_name}")
                        output(f"   🏢 Type: {'Manager Account' if is_manager else 'Client Account'}")
                        output(f"   💰 Currency: {account_data.get('currency_code', 'USD')}")
                        output(f"   🌍 Timezone: {account_data.get('time_zone', 'UTC')}")
                        output(f"   📊 Status: {account_data.get('status', 'ACTIVE')}")
                        if account_data.get('is_test'):
                            output(f"   🧪 Test Account: Yes")
                        
                        # Store manager accounts separately for hierarchy processing
                        if is_manager:
                            manager_accounts.append(account_data)
                            output(f"   📁 Added to manager accounts list")
                        
                        accounts.append(account_data)
                    else:
                        # Fallback to basic account info
                        formatted_id = f"{customer_id[:3]}-{customer_id[3:6]}-{customer_id[6:]}" if len(customer_id) >= 9 else customer_id
                        basic_account = {
                            "id": formatted_id,
                            "name": f"Google Ads Account {formatted_id}",
                            "raw_id": customer_id,
                            "is_manager": False,
                            "is_test": False,
                            "currency_code": "USD",
                            "time_zone": "UTC",
                            "status": "UNKNOWN"
                        }
                        accounts.append(basic_account)
                        output(f"   ⚠️  Added with basic info only")
                        
                except Exception as e:
                    output(f"   ❌ Error fetching account {customer_id}: {str(e)}")
                    # Add account with basic info if individual lookup fails
                    formatted_id = f"{customer_id[:3]}-{customer_id[3:6]}-{customer_id[6:]}" if len(customer_id) >= 9 else customer_id
                    accounts.append({
                        "id": formatted_id,
                        "name": f"Google Ads Account {formatted_id}",
                        "raw_id": customer_id,
                        "is_manager": False,
                        "is_test": False,
                        "currency_code": "USD",
                        "time_zone": "UTC",
                        "status": "ERROR"
                    })
                    output(f"   ⚠️  Added with basic info due to error")
            
            output(f"\n📈 ACCOUNT PROCESSING SUMMARY")
            output("=" * 40)
            output(f"Total Accounts Processed: {len(accounts)}")
            output(f"Manager Accounts Found: {len(manager_accounts)}")
            output(f"Client Accounts Found: {len(accounts) - len(manager_accounts)}")
            
            # Now try to discover parent-child relationships using direct API calls
            output(f"\n🔗 DISCOVERING PARENT-CHILD RELATIONSHIPS")
            output("=" * 50)
            
            accounts_with_hierarchy = self.discover_account_hierarchy_direct(accounts, manager_accounts, connection)
            
            logger.info(f"Successfully retrieved details for {len(accounts_with_hierarchy)} accounts")
            return accounts_with_hierarchy
            
        except Exception as e:
            print(f"\n❌ CRITICAL ERROR in get_customer_details_with_hierarchy: {str(e)}")
            logger.error(f"Error getting customer details: {str(e)}")
            raise
    
    def discover_account_hierarchy(self, client, accounts, manager_accounts):
        """
        Discover parent-child relationships between accounts
        
        Args:
            client: GoogleAdsClient instance
            accounts: List of all accounts
            manager_accounts: List of manager accounts
            
        Returns:
            List[dict]: Accounts with hierarchy information
        """
        try:
            if not manager_accounts:
                print("   ℹ️  No manager accounts found - skipping hierarchy discovery")
                return accounts
            
            print(f"   🔍 Checking {len(manager_accounts)} manager accounts for child relationships")
            
            # Create a mapping of customer_id to account for easy lookup
            account_map = {acc['raw_id']: acc for acc in accounts}
            
            for manager in manager_accounts:
                try:
                    print(f"\n   📁 Checking Manager: {manager['name']} ({manager['id']})")
                    
                    # Query to find child accounts under this manager
                    query = """
                        SELECT
                            customer_client.id,
                            customer_client.descriptive_name,
                            customer_client.manager,
                            customer_client.level,
                            customer_client.status
                        FROM customer_client
                        WHERE customer_client.level <= 1
                    """
                    
                    ga_service = client.get_service("GoogleAdsService")
                    response = ga_service.search(customer_id=manager['raw_id'], query=query)
                    
                    child_accounts = []
                    for row in response:
                        child_id = str(row.customer_client.id)
                        
                        # Get the actual descriptive name from the API
                        descriptive_name = row.customer_client.descriptive_name if hasattr(row.customer_client, 'descriptive_name') else None
                        if descriptive_name:
                            child_name = descriptive_name
                            logger.info(f"✅ HIERARCHY: Found descriptive name for child {child_id}: '{descriptive_name}'")
                        else:
                            child_name = f"Account {child_id}"
                            logger.warning(f"⚠️ HIERARCHY: No descriptive name found for child {child_id}, using fallback")
                        
                        child_level = row.customer_client.level if hasattr(row.customer_client, 'level') else 0
                        
                        # Format child ID
                        formatted_child_id = f"{child_id[:3]}-{child_id[3:6]}-{child_id[6:]}" if len(child_id) >= 9 else child_id
                        
                        print(f"      └── Child: {child_name} ({formatted_child_id}) - Level {child_level}")
                        
                        # Update the child account in our accounts list
                        if child_id in account_map:
                            account_map[child_id]['parent_id'] = manager['id']
                            account_map[child_id]['parent_name'] = manager['name']
                            account_map[child_id]['level'] = child_level
                            # CRITICAL: Update the name in the main account map
                            account_map[child_id]['name'] = child_name
                            print(f"         ✅ Updated parent relationship and name")
                            logger.info(f"🔄 HIERARCHY: Updated account {child_id} with name '{child_name}'")
                        
                        child_accounts.append({
                            'id': formatted_child_id,
                            'name': child_name,
                            'raw_id': child_id,
                            'level': child_level
                        })
                    
                    # Add child accounts to manager
                    if child_accounts:
                        manager['child_accounts'] = child_accounts
                        print(f"      📊 Added {len(child_accounts)} child accounts to manager")
                    else:
                        print(f"      ℹ️  No child accounts found")
                        
                except Exception as e:
                    print(f"      ❌ Error checking manager {manager['name']}: {str(e)}")
                    continue
            
            # Update the accounts list with hierarchy info
            updated_accounts = list(account_map.values())
            
            # Count hierarchy stats
            accounts_with_parents = len([acc for acc in updated_accounts if acc.get('parent_id')])
            managers_with_children = len([acc for acc in updated_accounts if acc.get('child_accounts')])
            
            print(f"\n   📊 HIERARCHY DISCOVERY SUMMARY")
            print(f"   Accounts with Parents: {accounts_with_parents}")
            print(f"   Managers with Children: {managers_with_children}")
            
            return updated_accounts
            
        except Exception as e:
            print(f"   ❌ Error in hierarchy discovery: {str(e)}")
            logger.error(f"Error discovering account hierarchy: {str(e)}")
            return accounts
    
    def cache_account_hierarchy(self, connection, accounts):
        """
        Cache account hierarchy information to database
        
        Args:
            connection: PlatformConnection instance
            accounts: List of accounts with hierarchy info
        """
        try:
            print(f"\n💾 CACHING ACCOUNT HIERARCHY")
            print("=" * 35)
            
            from ..models import GoogleAdsAccount
            
            # Clear existing accounts for this connection
            existing_count = GoogleAdsAccount.objects.filter(platform_connection=connection).count()
            GoogleAdsAccount.objects.filter(platform_connection=connection).delete()
            print(f"   🗑️  Cleared {existing_count} existing cached accounts")
            
            # Cache each account
            cached_accounts = []
            parent_map = {}  # To resolve parent relationships after all accounts are created
            
            for account in accounts:
                try:
                    # Create the account record
                    cached_account = GoogleAdsAccount.objects.create(
                        platform_connection=connection,
                        account_id=account['id'],
                        raw_account_id=account['raw_id'],
                        name=account['name'],
                        is_manager=account.get('is_manager', False),
                        is_test=account.get('is_test', False),
                        currency_code=account.get('currency_code', 'USD'),
                        time_zone=account.get('time_zone', 'UTC'),
                        status=account.get('status', 'UNKNOWN'),
                        level=account.get('level', 0),
                        sync_status='active'
                    )
                    
                    cached_accounts.append(cached_account)
                    
                    # Store parent relationship info for later processing
                    if account.get('parent_id'):
                        parent_map[account['id']] = account['parent_id']
                    
                    print(f"   ✅ Cached: {account['name']} ({account['id']})")
                    
                except Exception as e:
                    print(f"   ❌ Error caching account {account.get('name', 'Unknown')}: {str(e)}")
                    continue
            
            # Now update parent relationships
            print(f"\n   🔗 Updating parent relationships...")
            for child_id, parent_id in parent_map.items():
                try:
                    child_account = GoogleAdsAccount.objects.get(
                        platform_connection=connection,
                        account_id=child_id
                    )
                    parent_account = GoogleAdsAccount.objects.get(
                        platform_connection=connection,
                        account_id=parent_id
                    )
                    
                    child_account.parent_account = parent_account
                    child_account.save()
                    
                    print(f"      ✅ {child_account.name} → {parent_account.name}")
                    
                except Exception as e:
                    print(f"      ❌ Error updating parent relationship for {child_id}: {str(e)}")
                    continue
            
            print(f"\n   📊 CACHING SUMMARY")
            print(f"   Total Accounts Cached: {len(cached_accounts)}")
            print(f"   Parent Relationships: {len(parent_map)}")
            
            logger.info(f"Successfully cached {len(cached_accounts)} accounts with hierarchy")
            
        except Exception as e:
            print(f"\n❌ CRITICAL ERROR in cache_account_hierarchy: {str(e)}")
            logger.error(f"Error caching account hierarchy: {str(e)}")
    
    def get_adwords_customer_ids(self, connection, force_refresh=False, stdout=None):
        """
        Get all accessible Google Ads accounts using the new Google Ads API approach with hierarchy
        
        Args:
            connection: PlatformConnection instance
            force_refresh: If True, forces fresh API call (used for sync operations)
            stdout: Optional stdout for management commands
            
        Returns:
            List[dict]: List of account dictionaries with hierarchy information
        """
        try:
            import sys
            
            # Helper function to output to both terminal and management command stdout
            def output(message, flush=True):
                print(message, flush=flush)
                if stdout:
                    stdout.write(message)
                if flush:
                    sys.stdout.flush()
            
            mode_text = "SYNC MODE" if force_refresh else "NORMAL MODE"
            output(f"\n🚀 STARTING GOOGLE ADS ACCOUNT RETRIEVAL ({mode_text})")
            output("=" * 55)
            output(f"Connection ID: {connection.id}")
            output(f"Platform Account: {connection.platform_account_email}")
            output(f"Tenant: {connection.tenant.name}")
            if force_refresh:
                output("🔄 FORCE REFRESH: Bypassing cache and forcing fresh API calls")
            
            # Log API connection attempt
            logger.info(f"🔗 API CONNECTION: Attempting to connect to Google Ads API")
            logger.info(f"🔗 Connection details: ID={connection.id}, Email={connection.platform_account_email}")
            logger.info(f"🔗 OAuth token status: {'Valid' if not connection.is_token_expired() else 'Expired'}")
            
            # Also log to Django logger for debugging
            logger.info(f"Using new Google Ads API approach for account retrieval (force_refresh={force_refresh})")
            
            # Store output function and connection for use in other methods
            self._output = output
            self._current_connection = connection
            
            # Verify required credentials exist
            if not settings.GOOGLE_OAUTH_CLIENT_ID or not settings.GOOGLE_OAUTH_CLIENT_SECRET:
                output("❌ Missing OAuth credentials in environment variables")
                logger.error("Missing OAuth credentials in environment variables")
                return [{"id": "ERROR", "name": "Google OAuth credentials not configured"}]
                
            if not settings.GOOGLE_ADS_DEVELOPER_TOKEN:
                output("❌ Missing Google Ads developer token in environment variables")
                logger.error("Missing Google Ads developer token in environment variables")
                return [{"id": "ERROR", "name": "Google Ads developer token not configured"}]
            
            output("✅ All credentials verified")
            
            # Step 1: Build Google Ads Client
            output(f"\n🔧 STEP 1: Building Google Ads Client")
            output("-" * 40)
            client = self.get_google_ads_client(connection)
            output("✅ Google Ads Client created successfully")
            
            # Step 2: Get Accessible Account IDs
            output(f"\n📋 STEP 2: Getting Accessible Account IDs")
            output("-" * 45)
            
            # Log the API call attempt
            logger.info(f"🔗 API CALL: Fetching accessible customer IDs from Google Ads API")
            customer_ids = self.list_accessible_customer_ids(connection, client)
            
            if not customer_ids:
                output("❌ No accessible customer IDs found")
                logger.warning("🔗 API RESPONSE: No accessible customer IDs found")
                return []
            
            output(f"✅ Found {len(customer_ids)} accessible customer IDs")
            logger.info(f"🔗 API RESPONSE: Retrieved {len(customer_ids)} accessible customer IDs")
            for i, customer_id in enumerate(customer_ids, 1):
                output(f"   {i}. {customer_id}")
                logger.info(f"🔗 Account ID {i}: {customer_id}")
            
            # Step 3: Get Account Details with Hierarchy
            output(f"\n📊 STEP 3: Getting Account Details with Hierarchy")
            output("-" * 55)
            accounts = self.get_customer_details_with_hierarchy(client, customer_ids)
            
            # Step 4: Cache Account Hierarchy
            output(f"\n💾 STEP 4: Caching Account Hierarchy")
            output("-" * 40)
            self.cache_account_hierarchy(connection, accounts)
            
            output(f"\n🎉 ACCOUNT RETRIEVAL COMPLETE!")
            output("=" * 35)
            output(f"Total Accounts Retrieved: {len(accounts)}")
            manager_count = len([acc for acc in accounts if acc.get('is_manager', False)])
            client_count = len(accounts) - manager_count
            output(f"Manager Accounts: {manager_count}")
            output(f"Client Accounts: {client_count}")
            
            logger.info(f"Successfully retrieved {len(accounts)} Google Ads accounts with hierarchy")
            return accounts
            
        except Exception as e:
            output(f"\n❌ CRITICAL ERROR in get_adwords_customer_ids: {str(e)}")
            logger.error(f"Error getting Google Ads accounts: {str(e)}")
            return [{"id": "ERROR", "name": f"Account retrieval error: {str(e)}"}]
        
    
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
                    
                    # Use the v14 API endpoint
                    api_url = f"https://googleads.googleapis.com/v14/customers/{manager_id}/googleAds:search"
                    
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
        """
        DEPRECATED: Account retrieval method - to be replaced with new implementation
        """
        logger.info("Account retrieval method disabled - awaiting new implementation")
        return []