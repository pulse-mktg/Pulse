"""
Platform services package for Pulse.
This package contains service classes for handling integrations with
advertising platforms like Google Ads, Facebook Ads, etc.
"""

from .base import PlatformService
from .google_ads import GoogleAdsService
from .google_ads_data import GoogleAdsDataService
from .google_ads_account_service import GoogleAdsAccountService
from .google_ads_client_service import GoogleAdsClientService

# Factory function to get the appropriate platform service
def get_platform_service(tenant, platform_slug):
    """
    Factory function to get the appropriate platform service
    
    Args:
        tenant: The tenant model instance
        platform_slug: The slug of the platform type
        
    Returns:
        An instance of a PlatformService subclass
    """
    if platform_slug == 'google-ads':
        return GoogleAdsService(tenant)
    elif platform_slug == 'facebook-ads':
        # Placeholder for future implementation
        # return FacebookAdsService(tenant)
        raise NotImplementedError("Facebook Ads integration is not yet implemented")
    elif platform_slug == 'linkedin-ads':
        # Placeholder for future implementation
        # return LinkedInAdsService(tenant)
        raise NotImplementedError("LinkedIn Ads integration is not yet implemented")
    elif platform_slug == 'tiktok-ads':
        # Placeholder for future implementation
        # return TikTokAdsService(tenant)
        raise NotImplementedError("TikTok Ads integration is not yet implemented")
    
    raise ValueError(f"Unsupported platform: {platform_slug}")