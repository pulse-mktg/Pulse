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
        flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
            settings.GOOGLE_OAUTH_CLIENT_SECRET_PATH,
            scopes=settings.GOOGLE_OAUTH_SCOPES
        )
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
            # Create a flow from client secrets
            flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
                settings.GOOGLE_OAUTH_CLIENT_SECRET_PATH,
                scopes=settings.GOOGLE_OAUTH_SCOPES,
                state=state
            )
            
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
                
                # Handle token_type attribute safely
                token_metadata = existing_connection.token_metadata or {}
                token_metadata['created_at'] = timezone.now().isoformat()
                
                if hasattr(credentials, 'id_token'):
                    token_metadata['id_token'] = credentials.id_token
                    
                if hasattr(credentials, 'token_type'):
                    token_metadata['token_type'] = credentials.token_type
                    
                existing_connection.token_metadata = token_metadata
                existing_connection.save()
                
                return existing_connection
            else:
                # Handle token_type attribute safely
                token_metadata = {
                    'created_at': timezone.now().isoformat()
                }
                
                if hasattr(credentials, 'id_token'):
                    token_metadata['id_token'] = credentials.id_token
                    
                if hasattr(credentials, 'token_type'):
                    token_metadata['token_type'] = credentials.token_type
                
                # Create a new connection
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
                    connection_status='active'
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
        
        try:
            # Create credentials from stored tokens
            credentials = google.oauth2.credentials.Credentials(
                token=connection.access_token,
                refresh_token=connection.refresh_token,
                token_uri='https://oauth2.googleapis.com/token',
                client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
                client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET
            )
            
            # Force token refresh
            request = google.auth.transport.requests.Request()
            credentials.refresh(request)
            
            # Update the connection with new token info
            connection.access_token = credentials.token
            connection.token_expiry = datetime.datetime.fromtimestamp(credentials.expiry.timestamp()) if hasattr(credentials, 'expiry') and credentials.expiry else None
            connection.connection_status = 'active'
            connection.status_message = ''
            connection.save()
            
            return True
            
        except Exception as e:
            connection.set_connection_error(f"Failed to refresh token: {str(e)}")
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
            
    def get_adwords_customer_ids(self, connection):
        try:
            # Check if token needs refresh
            if connection.is_token_expired():
                success = self.refresh_token(connection)
                if not success:
                    return [{"id": "ERROR", "name": "OAuth token refresh failed"}]
            
            # Create credentials
            credentials = google.oauth2.credentials.Credentials(
                token=connection.access_token,
                refresh_token=connection.refresh_token,
                token_uri='https://oauth2.googleapis.com/token',
                client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
                client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET
            )
            
            all_accounts = []
            
            try:
                logger.info("Using Google Ads API v19...")
                
                # Create Google Ads client with v19 version
                client = GoogleAdsClient(
                    credentials=credentials,
                    developer_token=settings.GOOGLE_ADS_DEVELOPER_TOKEN,
                    use_proto_plus=True,
                    version="v19"
                )
                
                # Get the CustomerService
                customer_service = client.get_service("CustomerService")
                
                # Create a proper request object for v19
                request = client.get_type("ListAccessibleCustomersRequest")
                
                # Make the API call
                accessible_customers = customer_service.list_accessible_customers(request=request)
                
                # Process resource names
                for resource_name in accessible_customers.resource_names:
                    customer_id = resource_name.split('/')[-1]
                    # Format with hyphens for readability
                    if len(customer_id) >= 10:
                        formatted_id = f"{customer_id[:3]}-{customer_id[3:6]}-{customer_id[6:]}"
                    else:
                        formatted_id = customer_id
                    all_accounts.append({"id": formatted_id, "name": f"Account {formatted_id}"})
                
                if all_accounts:
                    logger.info(f"Successfully found {len(all_accounts)} accounts via API v19")
                    
                    # Try to enhance account information with descriptive names
                    self._enhance_account_information(client, all_accounts)
                    return all_accounts
                else:
                    logger.warning("No accounts found with API v19")
            
            except Exception as api_error:
                logger.warning(f"API v19 method failed: {str(api_error)}")
            
            # Fallback to REST API method if client library approach fails
            try:
                logger.info("Falling back to REST API with v19...")
                
                headers = {
                    'Authorization': f'Bearer {credentials.token}',
                    'developer-token': settings.GOOGLE_ADS_DEVELOPER_TOKEN
                }
                
                # Use the current v19 API endpoint
                list_url = 'https://googleads.googleapis.com/v19/customers:listAccessibleCustomers'
                
                response = requests.get(list_url, headers=headers)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if 'resourceNames' in data and data['resourceNames']:
                        for resource_name in data['resourceNames']:
                            customer_id = resource_name.split('/')[-1]
                            # Format with hyphens for readability
                            if len(customer_id) >= 10:
                                formatted_id = f"{customer_id[:3]}-{customer_id[3:6]}-{customer_id[6:]}"
                            else:
                                formatted_id = customer_id
                            all_accounts.append({"id": formatted_id, "name": f"Account {formatted_id}"})
                        
                        logger.info(f"Successfully found {len(all_accounts)} accounts via REST API v19")
                        return all_accounts
                    else:
                        logger.warning("No accounts found with REST API v19")
                else:
                    logger.warning(f"REST API v19 failed: {response.status_code} - {response.text}")
            
            except Exception as rest_error:
                logger.warning(f"REST API v19 approach failed: {str(rest_error)}")
            
            # If all API methods fail but we have a valid token, return empty list
            if all_accounts:
                return all_accounts
            else:
                return []
                
        except Exception as e:
            logger.error(f"Error getting Google Ads customer IDs: {str(e)}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            
            return []

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