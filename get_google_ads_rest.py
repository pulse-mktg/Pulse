#!/usr/bin/env python
"""
Standalone script to get Google Ads accounts using the REST API directly.
"""

import os
import sys
import json
import logging
import requests
import django

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PulseProject.settings')
django.setup()

# Import Django models
from django.conf import settings
from website.models import PlatformConnection, PlatformType

def get_google_ads_accounts(connection_id=None, test_customer_id=None):
    """
    Get Google Ads accounts using the REST API directly.
    
    Args:
        connection_id: Optional connection ID to use
        test_customer_id: Optional test account customer ID
        
    Returns:
        List of account dictionaries
    """
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
        
        # Check and format test customer ID
        if test_customer_id:
            # Remove dashes if present
            test_customer_id = test_customer_id.replace('-', '')
            
        # First approach: Try to get the test account itself
        if test_customer_id:
            logger.info(f"Getting information for test account {test_customer_id}")
            
            # Format API URL for test account
            api_url = f"https://googleads.googleapis.com/v14/customers/{test_customer_id}"
            
            headers = {
                "Authorization": f"Bearer {connection.access_token}",
                "developer-token": settings.GOOGLE_ADS_DEVELOPER_TOKEN
            }
            
            logger.info(f"Making REST API call to {api_url}")
            response = requests.get(api_url, headers=headers)
            
            if response.status_code == 200:
                account_data = response.json()
                logger.info(f"Test account data: {account_data}")
                
                # Return the account details
                return [{
                    'id': test_customer_id,
                    'name': account_data.get('descriptiveName', f"Account {test_customer_id}"),
                    'currencyCode': account_data.get('currencyCode', 'Unknown'),
                    'timeZone': account_data.get('timeZone', 'Unknown'),
                    'test_account': True
                }]
            else:
                logger.error(f"Error accessing test account: {response.status_code}, {response.text}")
        
        # Second approach: Try using customer list endpoint if direct access failed or no test ID
        logger.info("Trying customer list endpoint")
        
        # If we have a test customer ID, use it to access the manager account
        customer_id_to_use = test_customer_id if test_customer_id else None
        
        # Build API URL based on whether we have a customer ID
        if customer_id_to_use:
            api_url = f"https://googleads.googleapis.com/v14/customers/{customer_id_to_use}/customerClients"
            logger.info(f"Using manager account endpoint: {api_url}")
        else:
            api_url = "https://googleads.googleapis.com/v14/customers:listAccessibleCustomers"
            logger.info(f"Using list accessible customers endpoint: {api_url}")
        
        headers = {
            "Authorization": f"Bearer {connection.access_token}",
            "developer-token": settings.GOOGLE_ADS_DEVELOPER_TOKEN
        }
        
        response = requests.get(api_url, headers=headers)
        
        if response.status_code == 200:
            account_data = response.json()
            logger.info(f"API Response: {account_data}")
            
            if "resourceNames" in account_data:
                # Format from list accessible customers endpoint
                accounts = []
                for resource_name in account_data.get("resourceNames", []):
                    customer_id = resource_name.split('/')[-1]
                    
                    # Format with dashes for display
                    formatted_id = customer_id
                    if len(customer_id) == 10:
                        formatted_id = f"{customer_id[:3]}-{customer_id[3:6]}-{customer_id[6:]}"
                    
                    accounts.append({
                        'id': formatted_id,
                        'name': f"Account {formatted_id}"
                    })
                return accounts
                
            elif "results" in account_data:
                # Format from customer clients endpoint
                accounts = []
                for client in account_data.get("results", []):
                    customer_id = client.get("resourceName", "").split('/')[-1]
                    
                    # Format with dashes for display
                    formatted_id = customer_id
                    if len(customer_id) == 10:
                        formatted_id = f"{customer_id[:3]}-{customer_id[3:6]}-{customer_id[6:]}"
                    
                    accounts.append({
                        'id': formatted_id,
                        'name': client.get("descriptiveName", f"Account {formatted_id}"),
                        'status': client.get("status", "UNKNOWN"),
                        'level': client.get("level", 0),
                        'manager': client.get("manager", False)
                    })
                return accounts
            else:
                logger.warning("Unexpected response format, no accounts found")
                return []
        else:
            logger.error(f"API error: {response.status_code}, {response.text}")
        
        # Last approach: Try a direct REST API call to the Google Ads API
        logger.info("Trying alternative direct REST API methods")
        
        # Try using Google My Business API as a fallback
        try:
            gmb_url = "https://mybusiness.googleapis.com/v4/accounts"
            headers = {"Authorization": f"Bearer {connection.access_token}"}
            
            response = requests.get(gmb_url, headers=headers)
            if response.status_code == 200:
                accounts_data = response.json()
                logger.info(f"GMB API Response: {accounts_data}")
                
                if 'accounts' in accounts_data and accounts_data['accounts']:
                    return [
                        {'id': account.get('name', '').split('/')[-1], 
                         'name': account.get('accountName', 'GMB Account'),
                         'type': 'Google My Business'}
                        for account in accounts_data['accounts']
                    ]
        except Exception as e:
            logger.error(f"GMB API error: {str(e)}")
        
        # Third approach: Try to get the user's email profile to show something
        try:
            userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
            headers = {"Authorization": f"Bearer {connection.access_token}"}
            
            response = requests.get(userinfo_url, headers=headers)
            if response.status_code == 200:
                user_data = response.json()
                logger.info(f"User info: {user_data}")
                
                # Return a placeholder account with user info
                return [{
                    'id': 'NO_ACCOUNTS',
                    'name': f"No Ads accounts for {user_data.get('email', 'User')}",
                    'type': 'User Info',
                    'email': user_data.get('email', 'Unknown')
                }]
        except Exception as e:
            logger.error(f"User info API error: {str(e)}")
        
        return []
        
    except Exception as e:
        logger.error(f"Error getting Google Ads accounts: {str(e)}")
        return []

if __name__ == "__main__":
    print("\n==== Google Ads Account Fetcher (REST API) ====")
    print("Using Django credentials from your Pulse project\n")
    
    # Get connection ID from command line if provided
    connection_id = int(sys.argv[1]) if len(sys.argv) > 1 else None
    
    # Make test_customer_id optional
    test_customer_id = None
    use_test_id = input("Do you want to specify a test account ID? (y/n): ").strip().lower()
    
    if use_test_id == 'y':
        test_customer_id = input("Enter your test account customer ID (with or without dashes): ").strip()
        print(f"Using test account customer ID: {test_customer_id}")
    else:
        print("Attempting to access accounts without a specific test account ID")
    
    if connection_id:
        print(f"Using connection ID: {connection_id}")
    else:
        print("Using most recent active connection")
    
    # Get all accessible accounts
    accounts = get_google_ads_accounts(connection_id, test_customer_id)
    print(f"\nFound {len(accounts)} Google Ads accounts:")
    for account in accounts:
        print(f"  - {account['id']}: {account['name']}")
        
        # Print additional details if available
        for key, value in account.items():
            if key not in ['id', 'name']:
                print(f"    {key}: {value}")
    
    if not accounts:
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