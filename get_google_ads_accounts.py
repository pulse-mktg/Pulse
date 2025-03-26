#!/usr/bin/env python
"""
Standalone script to get Google Ads accounts under a manager account.
Uses Django's existing credentials.
"""

import os
import sys
import logging
import django
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
import google.oauth2.credentials

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PulseProject.settings')
django.setup()

# Import Django models
from django.conf import settings
from website.models import PlatformConnection, PlatformType

# Get connection ID from command line arguments or use the most recent one
connection_id = int(sys.argv[1]) if len(sys.argv) > 1 else None

def get_google_ads_accounts(test_customer_id=None):
    """Get all accessible Google Ads accounts using credentials from Django."""
    try:
        # Get Google Ads connection from database
        if connection_id:
            connection = PlatformConnection.objects.get(id=connection_id)
            logger.info(f"Using connection ID: {connection_id} ({connection.platform_account_email})")
        else:
            # Get the most recent Google Ads connection
            platform_type = PlatformType.objects.get(slug='google-ads')
            connection = PlatformConnection.objects.filter(
                platform_type=platform_type,
                is_active=True
            ).order_by('-created_at').first()
            
            if not connection:
                logger.error("No active Google Ads connections found")
                return []
            
            logger.info(f"Using most recent connection: {connection.id} ({connection.platform_account_email})")
        
        # Check if token needs refresh
        if hasattr(connection, 'is_token_expired') and connection.is_token_expired():
            logger.info("Token expired, attempting to refresh...")
            # This would use your refresh_token method, but we'll do it manually here
            from google.auth.transport.requests import Request as GoogleRequest
            
            # Create credentials for refreshing
            credentials = google.oauth2.credentials.Credentials(
                token=connection.access_token,
                refresh_token=connection.refresh_token,
                token_uri='https://oauth2.googleapis.com/token',
                client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
                client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET
            )
            
            # Refresh token
            request = GoogleRequest()
            credentials.refresh(request)
            
            # Update connection with new token
            connection.access_token = credentials.token
            if hasattr(credentials, 'expiry'):
                from django.utils import timezone
                import datetime
                connection.token_expiry = timezone.make_aware(
                    datetime.datetime.fromtimestamp(credentials.expiry.timestamp())
                )
            connection.save()
            logger.info("Token refreshed successfully")
        
        # Create credentials using connection from database
        credentials = google.oauth2.credentials.Credentials(
            token=connection.access_token,
            refresh_token=connection.refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
            client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET
        )
        
        # Initialize the Google Ads client
        # Try with different API versions if needed
        for version in ["v14", "v13"]:
            try:
                logger.info(f"Trying Google Ads API version {version}")
                
                # Create client based on whether we have a test_customer_id
                client_kwargs = {
                    'credentials': credentials,
                    'developer_token': settings.GOOGLE_ADS_DEVELOPER_TOKEN,
                    'use_proto_plus': True,
                    'version': version
                }
                
                # For test developer tokens, add login_customer_id if provided
                if test_customer_id:
                    client_kwargs['login_customer_id'] = test_customer_id
                    logger.info(f"Using test account ID: {test_customer_id}")
                
                client = GoogleAdsClient(**client_kwargs)
                
                # Get customer service
                logger.info("Getting CustomerService...")
                customer_service = client.get_service("CustomerService")
                
                # Create an empty request
                request = client.get_type("ListAccessibleCustomersRequest")
                
                # List accessible customers
                logger.info("Calling list_accessible_customers API...")
                try:
                    response = customer_service.list_accessible_customers(request=request)
                    # If we get here, the call was successful
                    break
                except Exception as e:
                    logger.warning(f"Version {version} failed: {str(e)}")
                    continue
            except Exception as e:
                logger.warning(f"Could not initialize client with version {version}: {str(e)}")
                continue
        else:
            # If we get here, all versions failed
            logger.error("All API versions failed")
            return []
        
        # Format results
        logger.info(f"Found {len(response.resource_names)} accounts")
        customer_accounts = []
        for resource_name in response.resource_names:
            # Extract customer ID from resource name
            customer_id = resource_name.split('/')[-1]
            logger.info(f"Found customer ID: {customer_id}")
            
            # Format customer ID with hyphens (XXX-XXX-XXXX)
            formatted_id = customer_id
            if len(customer_id) == 10:
                formatted_id = f"{customer_id[:3]}-{customer_id[3:6]}-{customer_id[6:]}"
            
            customer_accounts.append({
                'id': formatted_id,
                'name': f"Account {formatted_id}"
            })
        
        return customer_accounts
        
    except GoogleAdsException as gae:
        logger.error(f"Google Ads API Exception: {gae.error.message}")
        for error in gae.failure.errors:
            logger.error(f"Error detail: {error.message}")
            logger.error(f"Error code: {error.error_code.name}")
            if hasattr(error, 'location'):
                logger.error(f"Error location: {error.location.field_path_elements}")
        return []
        
    except Exception as e:
        logger.error(f"Error getting Google Ads customer IDs: {str(e)}")
        logger.error(f"Error type: {type(e).__name__}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return []

def get_account_details(customer_id):
    """Get detailed information about a specific account."""
    try:
        # Get Google Ads connection from database
        if connection_id:
            connection = PlatformConnection.objects.get(id=connection_id)
        else:
            # Get the most recent Google Ads connection
            platform_type = PlatformType.objects.get(slug='google-ads')
            connection = PlatformConnection.objects.filter(
                platform_type=platform_type,
                is_active=True
            ).order_by('-created_at').first()
            
            if not connection:
                logger.error("No active Google Ads connections found")
                return []
        
        # Create credentials using connection from database
        credentials = google.oauth2.credentials.Credentials(
            token=connection.access_token,
            refresh_token=connection.refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
            client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET
        )
        
        # Initialize the Google Ads client
        # For Test developer tokens, you MUST specify your test account's customer ID
        test_customer_id = "1234567890"  # REPLACE THIS with your actual test account customer ID (no dashes)
        
        client = GoogleAdsClient(
            credentials=credentials,
            developer_token=settings.GOOGLE_ADS_DEVELOPER_TOKEN,
            login_customer_id=test_customer_id,  # Required for test accounts
            use_proto_plus=True,
            version="v14"  # Use v14 or change as needed
        )
        
        # Get GoogleAdsService
        ga_service = client.get_service("GoogleAdsService")
        
        # Remove hyphens from customer ID if present
        customer_id = customer_id.replace('-', '')
        
        # Create a query to get customer details
        query = """
            SELECT
              customer.id,
              customer.descriptive_name,
              customer.currency_code,
              customer.time_zone,
              customer.tracking_url_template,
              customer_client.level,
              customer_client.status
            FROM customer_client
            WHERE customer_client.status != 'REMOVED'
        """
        
        # Issue the search request
        search_request = client.get_type("SearchGoogleAdsRequest")
        search_request.customer_id = customer_id
        search_request.query = query
        
        # Execute the query
        response = ga_service.search(request=search_request)
        
        # Process each row
        accounts = []
        for row in response:
            customer = row.customer
            client = row.customer_client
            accounts.append({
                'id': customer.id.value,
                'name': customer.descriptive_name.value,
                'currency': customer.currency_code.value,
                'timezone': customer.time_zone.value,
                'level': client.level.value,
                'status': client.status.name,
            })
        
        return accounts
        
    except Exception as e:
        logger.error(f"Error getting account details: {str(e)}")
        return []

if __name__ == "__main__":
    print("\n==== Google Ads Account Fetcher ====")
    print("Using Django credentials from your Pulse project\n")
    
    # Make test_customer_id optional
    test_customer_id = None
    use_test_id = input("Do you want to specify a test account ID? (y/n): ").strip().lower()
    
    if use_test_id == 'y':
        test_customer_id = input("Enter your test account customer ID (numbers only, no dashes): ").strip()
        if not test_customer_id or not test_customer_id.isdigit():
            print("Error: You must enter a valid numeric customer ID")
            sys.exit(1)
        print(f"Using test account customer ID: {test_customer_id}")
    else:
        print("Attempting to access accounts without a specific test account ID")
        print("Note: This may not work with a test developer token")
    
    if len(sys.argv) > 1:
        print(f"Using connection ID: {sys.argv[1]}")
    else:
        print("Using most recent active connection")
    
    # Get all accessible accounts
    accounts = get_google_ads_accounts(test_customer_id)
    print(f"\nFound {len(accounts)} Google Ads accounts:")
    for account in accounts:
        print(f"  - {account['id']}: {account['name']}")
    
    # If accounts were found, get details for the first one as an example
    if accounts:
        print(f"\nGetting details for account {accounts[0]['id']}...")
        details = get_account_details(accounts[0]['id'], test_customer_id)
        for account_detail in details:
            print("\nAccount details:")
            for key, value in account_detail.items():
                print(f"  {key}: {value}")
    else:
        print("\nNo accounts found. Possible issues:")
        if test_customer_id:
            print("  1. The test account customer ID is incorrect")
            print("  2. Your developer token doesn't have access to this test account")
            print("  3. You haven't created any sub-accounts under this test account")
        else:
            print("  1. You may need to specify a test account ID with a test developer token")
            print("  2. Your Google account doesn't have access to any Google Ads accounts")
            print("  3. Your developer token doesn't have the correct permissions")
        
        print("  4. Your OAuth credentials don't include the necessary scopes")
        
    print("\nCheck the log output above for detailed error messages that can help troubleshoot.")
    print("======================================")