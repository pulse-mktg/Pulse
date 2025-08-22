"""
Base service classes for platform integrations.
"""

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class PlatformService(ABC):
    """
    Abstract base class for platform service handlers.
    All platform-specific service classes should inherit from this.
    """
    
    def __init__(self, tenant):
        """
        Initialize the service with a tenant.
        
        Args:
            tenant: The tenant model instance
        """
        self.tenant = tenant
    
    @abstractmethod
    def get_authorized_connections(self):
        """
        Get all active connections for the platform type.
        
        Returns:
            QuerySet of active PlatformConnection objects
        """
        pass
    
    @abstractmethod
    def initialize_oauth_flow(self, redirect_uri):
        """
        Initialize the OAuth flow for this platform.
        
        Args:
            redirect_uri: The URL to redirect to after authorization
            
        Returns:
            tuple: (authorization_url, state)
        """
        pass
    
    @abstractmethod
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
        pass
    
    @abstractmethod
    def refresh_token(self, connection):
        """
        Refresh the access token for a platform connection.
        
        Args:
            connection: The PlatformConnection object to refresh
            
        Returns:
            bool: True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def disconnect(self, connection):
        """
        Disconnect/revoke the platform connection.
        
        Args:
            connection: The PlatformConnection object to disconnect
            
        Returns:
            bool: True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def get_account_info(self, connection):
        """
        Get information about the connected account.
        
        Args:
            connection: The PlatformConnection object
            
        Returns:
            dict: Account information or None if unavailable
        """
        pass

class TokenManager:
    """
    Helper class for managing OAuth tokens.
    Can be used by platform services for common token operations.
    """
    
    @staticmethod
    def is_token_valid(token_expiry):
        """
        Check if a token is still valid based on expiry time.
        
        Args:
            token_expiry: datetime object of token expiry
            
        Returns:
            bool: True if valid, False if expired or None
        """
        from django.utils import timezone
        
        if not token_expiry:
            return False
        return token_expiry > timezone.now()
    
    @staticmethod
    def format_token_for_storage(token_data):
        """
        Prepare token data for storage in the database.
        Override in subclasses if needed for platform-specific formatting.
        
        Args:
            token_data: Raw token data from OAuth provider
            
        Returns:
            dict: Formatted token data ready for storage
        """
        return token_data