from django.core.management.base import BaseCommand
from website.models import PlatformType
from django.utils.text import slugify

class Command(BaseCommand):
    help = 'Initialize platform types in the database'

    def handle(self, *args, **options):
        # Define the platform types to create
        platform_types = [
            {
                'name': 'Google Ads',
                'slug': 'google-ads',
                'description': 'Connect to Google Ads to manage and optimize your advertising campaigns.',
                'icon_class': 'bi-google',
                'position': 100,
                'is_available': True,
                'required_scopes': [
                    'https://www.googleapis.com/auth/adwords',
                    'https://www.googleapis.com/auth/userinfo.email'
                ],
                'platform_url': 'https://ads.google.com/'
            },
            {
                'name': 'Facebook Ads',
                'slug': 'facebook-ads',
                'description': 'Connect to Facebook Ads to manage your social media advertising.',
                'icon_class': 'bi-facebook',
                'position': 200,
                'is_available': True,  # Not yet implemented
                'required_scopes': [],
                'platform_url': 'https://business.facebook.com/'
            },
            {
                'name': 'LinkedIn Ads',
                'slug': 'linkedin-ads',
                'description': 'Connect to LinkedIn Ads for B2B advertising campaigns.',
                'icon_class': 'bi-linkedin',
                'position': 300,
                'is_available': True,  # Not yet implemented
                'required_scopes': [],
                'platform_url': 'https://www.linkedin.com/campaignmanager/'
            },
            {
                'name': 'Twitter Ads',
                'slug': 'twitter-ads',
                'description': 'Connect to Twitter Ads for social media advertising metrics.',
                'icon_class': 'bi-twitter',
                'position': 350,
                'is_available': True,  # Currently showing as available
                'required_scopes': [],
                'platform_url': 'https://ads.twitter.com/'
            },
            {
                'name': 'TikTok Ads',
                'slug': 'tiktok-ads',
                'description': 'Connect to TikTok Ads for short-form video advertising.',
                'icon_class': 'bi-tiktok',
                'position': 400,
                'is_available': False,  # Not yet implemented
                'required_scopes': [],
                'platform_url': 'https://ads.tiktok.com/'
            },
            {
                'name': 'Bing Ads',
                'slug': 'bing-ads',
                'description': 'Connect to Microsoft Bing Ads for search advertising.',
                'icon_class': 'bi-microsoft',
                'position': 150,
                'is_available': False,  # Set to True when ready to implement
                'required_scopes': [],
                'platform_url': 'https://ads.microsoft.com/'
            }
        ]
        
        # Create or update the platform types
        for platform_data in platform_types:
            platform, created = PlatformType.objects.update_or_create(
                slug=platform_data['slug'],
                defaults={
                    'name': platform_data['name'],
                    'description': platform_data['description'],
                    'icon_class': platform_data['icon_class'],
                    'position': platform_data['position'], 
                    'is_available': platform_data['is_available'],
                    'required_scopes': platform_data['required_scopes'],
                    'platform_url': platform_data['platform_url'],
                }
            )
            
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created platform type: {platform.name}'))
            else:
                self.stdout.write(self.style.SUCCESS(f'Updated platform type: {platform.name}'))
                
        self.stdout.write(self.style.SUCCESS('Platform types initialization complete!'))