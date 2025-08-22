from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from multiselectfield import MultiSelectField
from cryptography.fernet import Fernet
import base64
import os
import json


class Tenant(models.Model):
    """
    Represents a marketing agency using the platform.
    """
    name = models.CharField(max_length=100)
    logo = models.ImageField(upload_to='tenant_logos/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    # Typically you'd want to associate users with a tenant
    users = models.ManyToManyField(User, related_name='tenants')
    
    class Meta:
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return self.name

class Client(models.Model):
    """
    Represents a specific brand or business being managed.
    """
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='clients')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    logo = models.ImageField(upload_to='client_logos/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    
    # Industry choices
    INDUSTRY_CHOICES = [
        ('retail', 'Retail'),
        ('healthcare', 'Healthcare'),
        ('technology', 'Technology'),
        ('finance', 'Finance & Banking'),
        ('education', 'Education'),
        ('manufacturing', 'Manufacturing'),
        ('food_beverage', 'Food & Beverage'),
        ('real_estate', 'Real Estate'),
        ('hospitality', 'Hospitality & Tourism'),
        ('entertainment', 'Entertainment & Media'),
        ('automotive', 'Automotive'),
        ('ecommerce', 'E-Commerce'),
        ('agriculture', 'Agriculture'),
        ('construction', 'Construction'),
        ('professional_services', 'Professional Services'),
        ('nonprofit', 'Non-profit & NGO'),
        ('energy', 'Energy & Utilities'),
        ('logistics', 'Logistics & Transportation'),
        ('telecom', 'Telecommunications'),
        ('government', 'Government'),
        ('other', 'Other')
    ]
    industry = models.CharField(max_length=30, choices=INDUSTRY_CHOICES, blank=True, null=True)
    
    # Existing fields continue below...
    COMPANY_SIZE_CHOICES = [
        ('startup', 'Startup (1-10 employees)'),
        ('small', 'Small Business (11-50 employees)'),
        ('medium', 'Medium Business (51-200 employees)'),
        ('mid_market', 'Mid-Market (201-500 employees)'),
        ('large', 'Large Enterprise (501-1000 employees)'),
        ('enterprise', 'Enterprise (1000+ employees)'),
    ]
    company_size = models.CharField(max_length=20, choices=COMPANY_SIZE_CHOICES, blank=True, null=True)
    
    # Revenue Range
    REVENUE_RANGE_CHOICES = [
        ('pre_revenue', 'Pre-revenue'),
        ('under_500k', 'Under $500K'),
        ('500k_1m', '$500K - $1M'),
        ('1m_5m', '$1M - $5M'),
        ('5m_10m', '$5M - $10M'),
        ('10m_50m', '$10M - $50M'),
        ('50m_100m', '$50M - $100M'),
        ('100m_500m', '$100M - $500M'),
        ('500m_1b', '$500M - $1B'),
        ('over_1b', 'Over $1B'),
    ]
    revenue_range = models.CharField(max_length=20, choices=REVENUE_RANGE_CHOICES, blank=True, null=True)
    
    # Geographic Focus
    GEO_FOCUS_CHOICES = [
        ('local', 'Local (single city/metropolitan area)'),
        ('regional', 'Regional (multi-city within state/province)'),
        ('state', 'State/Province-wide'),
        ('national', 'National'),
        ('multinational', 'Multi-national (select regions)'),
        ('global', 'Global'),
    ]
    geographic_focus = models.CharField(max_length=20, choices=GEO_FOCUS_CHOICES, blank=True, null=True)
    
    # Business Model Type (Multiple Selection)
    BUSINESS_MODEL_CHOICES = [
        ('ecommerce', 'E-commerce (online product sales)'),
        ('lead_gen', 'Lead Generation (form submissions, calls, inquiries)'),
        ('marketplace', 'Marketplace (platform connecting buyers/sellers)'),
        ('subscription', 'Subscription/SaaS (recurring revenue model)'),
        ('brick_mortar', 'Brick & Mortar with Digital Presence'),
        ('service', 'Service-based Business (hourly/project billing)'),
        ('content', 'Content/Media (ad-supported)'),
        ('freemium', 'Freemium (free base product with paid upgrades)'),
        ('nonprofit', 'Non-profit/Donation-based'),
        ('b2b', 'B2B (business to business)'),
        ('b2c', 'B2C (business to consumer)'),
        ('b2g', 'B2G (business to government)'),
        ('d2c', 'D2C (direct to consumer)'),
    ]
    business_model_types = MultiSelectField(choices=BUSINESS_MODEL_CHOICES, blank=True, null=True)
    
    # Marketing Maturity
    MARKETING_MATURITY_CHOICES = [
        ('beginner', 'Beginner (new to digital marketing)'),
        ('building', 'Building (established basics, developing strategy)'),
        ('intermediate', 'Intermediate (consistent execution, basic analytics)'),
        ('advanced', 'Advanced (data-driven, multi-channel strategy)'),
        ('expert', 'Expert (sophisticated testing, integration, attribution)'),
    ]
    marketing_maturity = models.CharField(max_length=20, choices=MARKETING_MATURITY_CHOICES, blank=True, null=True)
    
    # Website field
    website = models.URLField(max_length=255, blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=['tenant', 'is_active']),  # You frequently query active clients for a tenant
            models.Index(fields=['name']),                 # For searching and sorting
            models.Index(fields=['created_at']),           # For sorting by creation date
            models.Index(fields=['company_size']),         # For filtering by company size
            models.Index(fields=['revenue_range']),        # For filtering by revenue
            models.Index(fields=['geographic_focus']),     # For filtering by geography
            models.Index(fields=['marketing_maturity']),   # For filtering by maturity
            models.Index(fields=['industry']),             # For filtering by industry
            models.Index(fields=['website', 'tenant', 'is_active']), # For lookup by website
        ]

    def __str__(self):
        return f"{self.name} ({self.tenant.name})"


# New model for tracking client competitors
class Competitor(models.Model):
    """
    Represents a competitor to a client
    """
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='competitors')
    name = models.CharField(max_length=100)
    website = models.URLField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True)
    
    # Competitor strength
    STRENGTH_CHOICES = [
        ('low', 'Low threat'),
        ('medium', 'Medium threat'),
        ('high', 'High threat'),
        ('direct', 'Direct competitor'),
        ('indirect', 'Indirect competitor'),
    ]
    strength = models.CharField(max_length=20, choices=STRENGTH_CHOICES, default='medium')
    
    # Key advantages (what makes the competitor strong)
    advantages = models.TextField(blank=True, help_text="Key advantages of this competitor")
    
    # Track when competitor was added and updated
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = [['client', 'name']]
        ordering = ['name']
        indexes = [
            models.Index(fields=['client', 'is_active']),
            models.Index(fields=['strength']),
        ]
    
    def __str__(self):
        return f"{self.name} (competitor of {self.client.name})"
    
class PlatformType(models.Model):
    """
    Defines available advertising platforms
    """
    name = models.CharField(max_length=100, unique=True)  # e.g., 'Google Ads', 'Facebook Ads'
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    icon_class = models.CharField(max_length=50, default="bi-box")  # Bootstrap icon class
    is_available = models.BooleanField(default=True)  # Controls whether platform is available for connection
    required_scopes = models.JSONField(default=list, blank=True)  # OAuth scopes needed for this platform
    platform_url = models.URLField(blank=True)  # URL to the platform's website/dashboard
    position = models.PositiveIntegerField(default=100, help_text="Display order (lower numbers appear first)")
    
    class Meta:
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['is_available']),
            models.Index(fields=['position']),  # For ordering
        ]
    
    def __str__(self):
        return self.name

class PlatformConnection(models.Model):
    """
    Represents a connection to an advertising platform at the tenant level
    """
    tenant = models.ForeignKey('Tenant', on_delete=models.CASCADE, related_name='platform_connections')
    platform_type = models.ForeignKey(PlatformType, on_delete=models.CASCADE)
    
    # Unique identifier from the platform
    platform_account_id = models.CharField(max_length=255, null=True, blank=True)
    platform_account_name = models.CharField(max_length=255, null=True, blank=True)
    platform_account_email = models.EmailField(null=True, blank=True)  # Email associated with the platform account
    
    # User who initially created the connection
    connected_user = models.ForeignKey(User, on_delete=models.CASCADE)
    
    # Sensitive data fields
    access_token = models.TextField(null=True, blank=True)
    refresh_token = models.TextField(null=True, blank=True)
    token_metadata = models.JSONField(default=dict, blank=True)  # Store additional token info
    
    # Tracking fields
    created_at = models.DateTimeField(auto_now_add=True)
    token_expiry = models.DateTimeField(null=True, blank=True)
    last_synced = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    connection_status = models.CharField(max_length=20, default="active",
                                         choices=[
                                             ("active", "Active"),
                                             ("expired", "Token Expired"),
                                             ("disconnected", "Disconnected"),
                                             ("error", "Error")
                                         ])
    status_message = models.TextField(blank=True)  # For storing error messages or status details
    
    class Meta:
        unique_together = [['tenant', 'platform_type', 'platform_account_id']]
        indexes = [
            models.Index(fields=['tenant', 'platform_type', 'is_active']),
            models.Index(fields=['connection_status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['token_expiry']),  # For checking expired tokens
        ]
        
    def __str__(self):
        return f"{self.platform_type.name} - {self.platform_account_name or 'Unnamed Connection'}"
    
    def is_token_expired(self):
        """Check if the access token has expired"""
        if not self.token_expiry:
            return False
        
        # Make sure both datetimes are timezone-aware for comparison
        now = timezone.now()
        expiry = self.token_expiry
        
        # If expiry is naive (no timezone), make it aware using the default timezone
        if timezone.is_naive(expiry):
            expiry = timezone.make_aware(expiry)
            
        return now >= expiry
    
    def set_token_expired(self):
        """Mark the connection as having an expired token"""
        self.connection_status = "expired"
        self.save(update_fields=['connection_status'])
    
    def set_connection_error(self, message):
        """Mark the connection as having an error"""
        self.connection_status = "error"
        self.status_message = message
        self.save(update_fields=['connection_status', 'status_message'])

# New model for platform-specific settings
class PlatformSettings(models.Model):
    """
    Stores platform-specific settings for a tenant
    """
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="platform_settings")
    platform_type = models.ForeignKey(PlatformType, on_delete=models.CASCADE)
    settings = models.JSONField(default=dict, blank=True)  # Flexible JSON storage for settings
    
    class Meta:
        unique_together = [['tenant', 'platform_type']]
        
    def __str__(self):
        return f"{self.tenant.name} - {self.platform_type.name} Settings"

# New model for client-specific platform associations
class ClientPlatformAccount(models.Model):
    """
    Associates specific platform accounts with clients
    """
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="platform_accounts")
    platform_connection = models.ForeignKey(PlatformConnection, on_delete=models.CASCADE, related_name="client_associations")
    platform_client_id = models.CharField(max_length=255, help_text="Client ID in the advertising platform")
    platform_client_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = [['client', 'platform_connection', 'platform_client_id']]
        indexes = [
            models.Index(fields=['client', 'is_active']),
            models.Index(fields=['platform_connection', 'is_active']),
            models.Index(fields=['platform_client_id']),
        ]
        
    def __str__(self):
        return f"{self.client.name} - {self.platform_connection.platform_type.name} Account"
    

# Google Ads Models
class GoogleAdsCampaign(models.Model):
    """
    Represents a Google Ads campaign
    """
    client_account = models.ForeignKey('ClientPlatformAccount', on_delete=models.CASCADE, related_name='google_ads_campaigns')
    campaign_id = models.CharField(max_length=50)
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=50)
    
    # Campaign settings
    campaign_type = models.CharField(max_length=50, null=True, blank=True)
    budget_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    budget_type = models.CharField(max_length=50, null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    targeting_locations = models.TextField(blank=True, null=True)
    ad_rotation = models.CharField(max_length=50, null=True, blank=True)
    
    # Tracking fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced = models.DateTimeField(default=timezone.now)
    
    class Meta:
        unique_together = [['client_account', 'campaign_id']]
        indexes = [
            models.Index(fields=['client_account', 'status']),
            models.Index(fields=['campaign_type']),
            models.Index(fields=['start_date']),
            models.Index(fields=['end_date']),
            models.Index(fields=['last_synced']),
        ]
        
    def __str__(self):
        return f"{self.name} ({self.campaign_id})"
    
    @property
    def budget_utilization(self):
        """Calculate budget utilization for the current period"""
        metrics = self.metrics.first()
        if not metrics or not self.budget_amount:
            return 0
        
        # For daily budget, calculate average daily spend vs budget
        avg_daily_spend = metrics.cost / metrics.date_range_days
        return min(100, (avg_daily_spend / float(self.budget_amount)) * 100)

class GoogleAdsAdGroup(models.Model):
    """
    Represents a Google Ads ad group
    """
    campaign = models.ForeignKey(GoogleAdsCampaign, on_delete=models.CASCADE, related_name='ad_groups')
    ad_group_id = models.CharField(max_length=50)
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=50)
    
    # Ad group settings
    ad_group_type = models.CharField(max_length=50, null=True, blank=True)
    
    # Tracking fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced = models.DateTimeField(default=timezone.now)
    
    class Meta:
        unique_together = [['campaign', 'ad_group_id']]
        indexes = [
            models.Index(fields=['campaign', 'status']),
            models.Index(fields=['ad_group_type']),
            models.Index(fields=['last_synced']),
        ]
        
    def __str__(self):
        return f"{self.name} ({self.ad_group_id})"

class GoogleAdsMetrics(models.Model):
    """
    Performance metrics for campaigns and ad groups
    """
    # Can be linked to either a campaign or an ad group
    campaign = models.ForeignKey(GoogleAdsCampaign, on_delete=models.CASCADE, related_name='metrics', null=True, blank=True)
    ad_group = models.ForeignKey(GoogleAdsAdGroup, on_delete=models.CASCADE, related_name='metrics', null=True, blank=True)
    
    # Date range for the metrics
    date_start = models.DateField()
    date_end = models.DateField()
    date_range = models.CharField(max_length=50, default='LAST_30_DAYS')
    date_range_days = models.IntegerField(default=30)
    
    # Basic performance metrics
    impressions = models.IntegerField(default=0)
    clicks = models.IntegerField(default=0)
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    conversions = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Calculated metrics
    ctr = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # Click Through Rate
    avg_cpc = models.DecimalField(max_digits=6, decimal_places=2, default=0)  # Average Cost Per Click
    conversion_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    avg_daily_spend = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Performance change metrics (compared to previous period)
    impressions_change = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    clicks_change = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    ctr_change = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    cost_change = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    avg_cpc_change = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    conversions_change = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    
    # Tracking fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = [['campaign', 'ad_group', 'date_range']]
        indexes = [
            models.Index(fields=['campaign']),
            models.Index(fields=['ad_group']),
            models.Index(fields=['date_range']),
            models.Index(fields=['date_start', 'date_end']),
        ]
        
    def __str__(self):
        if self.campaign:
            return f"Metrics for campaign {self.campaign.name} ({self.date_range})"
        else:
            return f"Metrics for ad group {self.ad_group.name} ({self.date_range})"

class GoogleAdsDailyMetrics(models.Model):
    """
    Daily performance metrics for campaigns
    """
    campaign = models.ForeignKey(GoogleAdsCampaign, on_delete=models.CASCADE, related_name='daily_metrics')
    date = models.DateField()
    
    # Performance metrics
    impressions = models.IntegerField(default=0)
    clicks = models.IntegerField(default=0)
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    conversions = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Calculated metrics
    ctr = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    avg_cpc = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    
    # Tracking fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = [['campaign', 'date']]
        indexes = [
            models.Index(fields=['campaign', 'date']),
            models.Index(fields=['date']),  # For time-series analysis
        ]
        
    def __str__(self):
        return f"Daily metrics for {self.campaign.name} on {self.date}"


class CampaignTag(models.Model):
    """
    Tags for organizing campaigns
    """
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='campaign_tags')
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    color = models.CharField(max_length=20, default="#6c757d")  # Default gray color
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_tags')
    
    class Meta:
        unique_together = [['tenant', 'name']]
        ordering = ['name']
        indexes = [
            models.Index(fields=['tenant']),
        ]
        
    def __str__(self):
        return f"{self.name} ({self.tenant.name})"

    
class CampaignTagAssignment(models.Model):
    """
    Association between campaigns and tags
    """
    tag = models.ForeignKey(CampaignTag, on_delete=models.CASCADE, related_name='assignments')
    campaign = models.ForeignKey(GoogleAdsCampaign, on_delete=models.CASCADE, related_name='tag_assignments')
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        unique_together = [['tag', 'campaign']]
        indexes = [
            models.Index(fields=['tag']),
            models.Index(fields=['campaign']),
        ]
        
    def __str__(self):
        return f"{self.tag.name} - {self.campaign.name}"
    
# Add to models.py

class ClientGroup(models.Model):
    """
    Represents a group of clients within a tenant.
    Allows for organizing clients into logical collections.
    """
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='client_groups')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    icon_class = models.CharField(max_length=50, default="bi-collection", help_text="Bootstrap icon class")
    color = models.CharField(max_length=20, default="#6c757d", help_text="Group color (HEX code)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    is_auto_generated = models.BooleanField(default=False, 
        help_text="Whether this group was automatically generated from client categories")
    category_type = models.CharField(max_length=50, blank=True, null=True,
        help_text="Category type this group is based on (company_size, revenue_range, etc.)")
    category_value = models.CharField(max_length=50, blank=True, null=True,
        help_text="Value of the category this group matches")
    # Many-to-many relationship with Client
    clients = models.ManyToManyField(Client, related_name='groups', blank=True)
    
    class Meta:
        unique_together = [['tenant', 'name']]
        ordering = ['name']
        indexes = [
            models.Index(fields=['tenant', 'is_active']),
            models.Index(fields=['is_auto_generated']),
            models.Index(fields=['category_type', 'category_value']),
            models.Index(fields=['tenant', 'is_active', 'is_auto_generated']),  # Combined index for filtering
        ]
        
    def __str__(self):
        return f"{self.name} ({self.tenant.name})"
    
    @property
    def client_count(self):
        """Return the number of active clients in this group"""
        return self.clients.filter(is_active=True).count()
    

# New Budget Models for models.py

class Budget(models.Model):
    """
    Represents a budget allocation for a specific client or client group
    """
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='budgets')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    
    # Budget can be associated with either a client, a client group, or neither (tenant-level budget)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='budgets', null=True, blank=True)
    client_group = models.ForeignKey(ClientGroup, on_delete=models.CASCADE, related_name='budgets', null=True, blank=True)
    
    # Budget attributes
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    start_date = models.DateField()
    end_date = models.DateField()
    
    # Optional: allocation frequency for recurring budgets
    FREQUENCY_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('annual', 'Annual'),
        ('custom', 'Custom Period'),
    ]
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='monthly')
    
    # Status fields
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_budgets')
    
    class Meta:
        indexes = [
            models.Index(fields=['tenant', 'is_active']),
            models.Index(fields=['client']),
            models.Index(fields=['client_group']),
            models.Index(fields=['start_date', 'end_date']),
        ]
    
    def __str__(self):
        entity = self.client.name if self.client else (self.client_group.name if self.client_group else "Tenant-level")
        return f"{self.name} - {entity} ({self.start_date} to {self.end_date})"
    
    @property
    def days_in_period(self):
        """Calculate the number of days in the budget period"""
        return (self.end_date - self.start_date).days + 1
    
    @property
    def days_elapsed(self):
        """Calculate days elapsed in the current budget period"""
        today = timezone.now().date()
        if today < self.start_date:
            return 0
        elif today > self.end_date:
            return self.days_in_period
        else:
            return (today - self.start_date).days + 1
    
    @property
    def expected_spend_to_date(self):
        """Calculate the expected spend based on elapsed time"""
        if self.days_in_period == 0:
            return 0
        return float((self.amount * self.days_elapsed) / self.days_in_period)


class BudgetAllocation(models.Model):
    """
    Represents a specific allocation of budget to a platform, campaign, etc.
    """
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name='allocations')
    
    # Allocations can be at different levels
    platform_type = models.ForeignKey(PlatformType, on_delete=models.CASCADE, null=True, blank=True)
    platform_account = models.ForeignKey(ClientPlatformAccount, on_delete=models.CASCADE, 
                                        related_name='budget_allocations', null=True, blank=True)
    campaign = models.ForeignKey('GoogleAdsCampaign', on_delete=models.CASCADE, 
                                related_name='budget_allocations', null=True, blank=True)
    
    # Allocation amount and percentage
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    
    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['budget']),
            models.Index(fields=['platform_type']),
            models.Index(fields=['platform_account']),
            models.Index(fields=['campaign']),
        ]
    
    def __str__(self):
        allocation_to = "Unspecified"
        if self.campaign:
            allocation_to = f"Campaign: {self.campaign.name}"
        elif self.platform_account:
            allocation_to = f"Account: {self.platform_account.platform_client_name}"
        elif self.platform_type:
            allocation_to = f"Platform: {self.platform_type.name}"
        
        return f"${self.amount} to {allocation_to}"


class BudgetAlert(models.Model):
    """
    Configurable alerts for budget thresholds
    """
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name='alerts')
    
    # Alert types
    ALERT_TYPE_CHOICES = [
        ('underspend', 'Underspend Alert'),
        ('overspend', 'Overspend Alert'),
        ('forecast', 'Forecast Alert'),
    ]
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPE_CHOICES)
    
    # Threshold (percentage of budget)
    threshold = models.DecimalField(max_digits=5, decimal_places=2)
    
    # Alert delivery method
    is_email_enabled = models.BooleanField(default=True)
    is_dashboard_enabled = models.BooleanField(default=True)
    
    # User to notify
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='budget_alerts')
    
    # Status
    is_active = models.BooleanField(default=True)
    last_triggered = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['budget', 'alert_type']),
            models.Index(fields=['is_active']),
            models.Index(fields=['user']),
        ]
    
    def __str__(self):
        return f"{self.get_alert_type_display()} at {self.threshold}% for {self.budget.name}"


class SpendSnapshot(models.Model):
    """
    Daily snapshot of spend for reporting and historical analysis
    """
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name='spend_snapshots')
    date = models.DateField()
    
    # Actual spend data
    spend_amount = models.DecimalField(max_digits=12, decimal_places=2)
    expected_amount = models.DecimalField(max_digits=12, decimal_places=2)
    variance_amount = models.DecimalField(max_digits=12, decimal_places=2)
    variance_percentage = models.DecimalField(max_digits=6, decimal_places=2)
    
    # Spend by platform (stored as JSON)
    platform_breakdown = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = [['budget', 'date']]
        indexes = [
            models.Index(fields=['budget', 'date']),
            models.Index(fields=['date']),
        ]
    
    def __str__(self):
        return f"Spend snapshot for {self.budget.name} on {self.date}"


# Google Ads Cache Models
class GoogleAdsAccount(models.Model):
    """
    Cached Google Ads account information
    """
    platform_connection = models.ForeignKey(
        PlatformConnection, 
        on_delete=models.CASCADE, 
        related_name='google_ads_accounts'
    )
    
    # Account identifiers
    account_id = models.CharField(max_length=20, help_text="Google Ads customer ID (with hyphens)")
    raw_account_id = models.CharField(max_length=20, help_text="Google Ads customer ID (without hyphens)")
    
    # Account information
    name = models.CharField(max_length=255, blank=True)
    is_manager = models.BooleanField(default=False)
    status = models.CharField(max_length=20, default='ACTIVE')
    currency_code = models.CharField(max_length=10, blank=True)
    time_zone = models.CharField(max_length=50, blank=True)
    
    # Hierarchy information
    parent_account = models.ForeignKey(
        'self', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='child_accounts'
    )
    level = models.IntegerField(default=0, help_text="Hierarchy level (0 = top level)")
    
    # Sync tracking
    last_synced = models.DateTimeField(auto_now=True)
    sync_status = models.CharField(
        max_length=20, 
        default='active',
        choices=[
            ('active', 'Active'),
            ('sync_error', 'Sync Error'),
            ('permission_denied', 'Permission Denied'),
            ('inactive', 'Inactive')
        ]
    )
    sync_error_message = models.TextField(blank=True)
    
    # Permission tracking
    can_be_login_customer = models.BooleanField(default=False)
    accessible_account_count = models.IntegerField(default=0)
    
    class Meta:
        unique_together = [['platform_connection', 'account_id']]
        indexes = [
            models.Index(fields=['platform_connection', 'is_manager']),
            models.Index(fields=['platform_connection', 'parent_account']),
            models.Index(fields=['account_id']),
            models.Index(fields=['raw_account_id']),
            models.Index(fields=['can_be_login_customer']),
            models.Index(fields=['last_synced']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.account_id})"
    
    def get_all_child_accounts(self):
        """Get all descendant accounts recursively"""
        children = []
        for child in self.child_accounts.all():
            children.append(child)
            children.extend(child.get_all_child_accounts())
        return children
    
    def get_hierarchy_path(self):
        """Get the full hierarchy path from root to this account"""
        path = [self]
        current = self.parent_account
        while current:
            path.insert(0, current)
            current = current.parent_account
        return path


class GoogleAdsAccountSync(models.Model):
    """
    Track sync operations for Google Ads accounts
    """
    platform_connection = models.ForeignKey(
        PlatformConnection, 
        on_delete=models.CASCADE, 
        related_name='google_ads_syncs'
    )
    
    # Sync details
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Results
    accounts_discovered = models.IntegerField(default=0)
    accounts_updated = models.IntegerField(default=0)
    accounts_added = models.IntegerField(default=0)
    accounts_deactivated = models.IntegerField(default=0)
    
    # Status
    sync_status = models.CharField(
        max_length=20,
        choices=[
            ('running', 'Running'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
            ('partial', 'Partial Success')
        ],
        default='running'
    )
    
    error_message = models.TextField(blank=True)
    sync_details = models.JSONField(default=dict, blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['platform_connection', 'started_at']),
            models.Index(fields=['sync_status']),
        ]
    
    def __str__(self):
        return f"Sync {self.id} - {self.platform_connection} ({self.sync_status})"
    
    def mark_completed(self):
        """Mark sync as completed"""
        self.completed_at = timezone.now()
        self.sync_status = 'completed'
        self.save(update_fields=['completed_at', 'sync_status'])
    
    def mark_failed(self, error_message):
        """Mark sync as failed"""
        self.completed_at = timezone.now()
        self.sync_status = 'failed'
        self.error_message = error_message
        self.save(update_fields=['completed_at', 'sync_status', 'error_message'])


class ClientPerformanceGoal(models.Model):
    """
    Performance goals for clients (CTR and conversion rate targets)
    """
    client = models.OneToOneField(
        Client, 
        on_delete=models.CASCADE, 
        related_name='performance_goals'
    )
    
    # CTR Goal
    ctr_goal = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Target CTR percentage (e.g., 2.50 for 2.5%)"
    )
    
    # Conversion Rate Goal
    conversion_rate_goal = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Target conversion rate percentage (e.g., 3.25 for 3.25%)"
    )
    
    # Additional rate metrics goals
    cost_per_click_goal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Target cost per click (e.g., 1.50 for $1.50)"
    )
    
    cost_per_conversion_goal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Target cost per conversion (e.g., 25.00 for $25.00)"
    )
    
    # Override global goals preference
    use_global_goals = models.BooleanField(
        default=False,
        help_text="Use tenant's global goals instead of client-specific goals"
    )
    
    # Tracking fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    # Goal status
    is_active = models.BooleanField(default=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['client', 'is_active']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        goals = []
        if self.ctr_goal:
            goals.append(f"CTR: {self.ctr_goal}%")
        if self.conversion_rate_goal:
            goals.append(f"Conv Rate: {self.conversion_rate_goal}%")
        if self.cost_per_click_goal:
            goals.append(f"CPC: ${self.cost_per_click_goal}")
        if self.cost_per_conversion_goal:
            goals.append(f"CPA: ${self.cost_per_conversion_goal}")
        
        suffix = " (using global)" if self.use_global_goals else ""
        return f"{self.client.name} - {', '.join(goals) if goals else 'No goals set'}{suffix}"
    
    def get_ctr_performance_status(self, current_ctr):
        """
        Get performance status for CTR compared to goal
        Returns: 'excellent', 'good', 'warning', 'poor', 'no_goal'
        """
        if not self.ctr_goal:
            return 'no_goal'
        
        if current_ctr == 0:
            return 'poor'
        
        performance_ratio = current_ctr / float(self.ctr_goal)
        
        if performance_ratio >= 1.2:  # 120% or more of goal
            return 'excellent'
        elif performance_ratio >= 1.0:  # 100% - 119% of goal
            return 'good'
        elif performance_ratio >= 0.8:  # 80% - 99% of goal
            return 'warning'
        else:  # Less than 80% of goal
            return 'poor'
    
    def get_conversion_rate_performance_status(self, current_conversion_rate):
        """
        Get performance status for conversion rate compared to goal
        Returns: 'excellent', 'good', 'warning', 'poor', 'no_goal'
        """
        if not self.conversion_rate_goal:
            return 'no_goal'
        
        if current_conversion_rate == 0:
            return 'poor'
        
        performance_ratio = current_conversion_rate / float(self.conversion_rate_goal)
        
        if performance_ratio >= 1.2:  # 120% or more of goal
            return 'excellent'
        elif performance_ratio >= 1.0:  # 100% - 119% of goal
            return 'good'
        elif performance_ratio >= 0.8:  # 80% - 99% of goal
            return 'warning'
        else:  # Less than 80% of goal
            return 'poor'
    
    def get_performance_status(self, metric_type, current_value):
        """
        Get performance status for any metric compared to goal
        Returns: 'excellent', 'good', 'warning', 'poor', 'no_goal'
        """
        goal_mapping = {
            'ctr': self.ctr_goal,
            'conversion_rate': self.conversion_rate_goal,
            'cost_per_click': self.cost_per_click_goal,
            'cost_per_conversion': self.cost_per_conversion_goal
        }
        
        goal = goal_mapping.get(metric_type)
        if not goal:
            return 'no_goal'
        
        if current_value == 0:
            return 'poor'
        
        # For cost metrics, lower is better
        if metric_type in ['cost_per_click', 'cost_per_conversion']:
            performance_ratio = float(goal) / current_value
        else:
            # For rate metrics, higher is better
            performance_ratio = current_value / float(goal)
        
        if performance_ratio >= 1.2:  # 120% or more of goal
            return 'excellent'
        elif performance_ratio >= 1.0:  # 100% - 119% of goal
            return 'good'
        elif performance_ratio >= 0.8:  # 80% - 99% of goal
            return 'warning'
        else:  # Less than 80% of goal
            return 'poor'
    
    def get_effective_goals(self):
        """
        Get effective goals for this client (either client-specific or global fallback)
        Returns dict with all available goals
        """
        goals = {
            'ctr_goal': self.ctr_goal,
            'conversion_rate_goal': self.conversion_rate_goal,
            'cost_per_click_goal': getattr(self, 'cost_per_click_goal', None),
            'cost_per_conversion_goal': getattr(self, 'cost_per_conversion_goal', None),
            'source': 'client'
        }
        
        # If using global goals or client goals are not set, fall back to global
        try:
            use_global = getattr(self, 'use_global_goals', False)
            if use_global or not any([self.ctr_goal, self.conversion_rate_goal, 
                                    getattr(self, 'cost_per_click_goal', None), 
                                    getattr(self, 'cost_per_conversion_goal', None)]):
                try:
                    global_goals = self.client.tenant.global_performance_goals
                    if global_goals.is_active:
                        goals.update({
                            'ctr_goal': goals['ctr_goal'] or global_goals.ctr_goal,
                            'conversion_rate_goal': goals['conversion_rate_goal'] or global_goals.conversion_rate_goal,
                            'cost_per_click_goal': goals['cost_per_click_goal'] or global_goals.cost_per_click_goal,
                            'cost_per_conversion_goal': goals['cost_per_conversion_goal'] or global_goals.cost_per_conversion_goal,
                            'source': 'global' if use_global else 'mixed'
                        })
                except Exception:
                    pass  # No global goals set or model doesn't exist yet
        except Exception:
            pass  # use_global_goals field doesn't exist yet
        
        return goals


class TenantPerformanceGoals(models.Model):
    """
    Global performance goals for a tenant (applied to all clients unless overridden)
    """
    tenant = models.OneToOneField(
        Tenant,
        on_delete=models.CASCADE,
        related_name='global_performance_goals'
    )
    
    # CTR Goal
    ctr_goal = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Global CTR target percentage (e.g., 2.50 for 2.5%)"
    )
    
    # Conversion Rate Goal
    conversion_rate_goal = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Global conversion rate target percentage (e.g., 3.25 for 3.25%)"
    )
    
    # Additional rate metrics goals
    cost_per_click_goal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Target cost per click (e.g., 1.50 for $1.50)"
    )
    
    cost_per_conversion_goal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Target cost per conversion (e.g., 25.00 for $25.00)"
    )
    
    # Goal mode preference
    GOAL_MODE_CHOICES = [
        ('global', 'Use global goals for all clients'),
        ('client_specific', 'Use client-specific goals'),
        ('mixed', 'Use client-specific where set, global as fallback')
    ]
    goal_mode = models.CharField(
        max_length=20,
        choices=GOAL_MODE_CHOICES,
        default='mixed',
        help_text="How to apply goals across clients"
    )
    
    # Tracking fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['tenant', 'is_active']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        goals = []
        if self.ctr_goal:
            goals.append(f"CTR: {self.ctr_goal}%")
        if self.conversion_rate_goal:
            goals.append(f"Conv Rate: {self.conversion_rate_goal}%")
        if self.cost_per_click_goal:
            goals.append(f"CPC: ${self.cost_per_click_goal}")
        if self.cost_per_conversion_goal:
            goals.append(f"CPA: ${self.cost_per_conversion_goal}")
        
        return f"{self.tenant.name} Global Goals - {', '.join(goals) if goals else 'No goals set'}"
    
    def get_performance_status(self, metric_type, current_value):
        """
        Get performance status for any metric compared to goal
        Returns: 'excellent', 'good', 'warning', 'poor', 'no_goal'
        """
        goal_mapping = {
            'ctr': self.ctr_goal,
            'conversion_rate': self.conversion_rate_goal,
            'cost_per_click': self.cost_per_click_goal,
            'cost_per_conversion': self.cost_per_conversion_goal
        }
        
        goal = goal_mapping.get(metric_type)
        if not goal:
            return 'no_goal'
        
        if current_value == 0:
            return 'poor'
        
        # For cost metrics, lower is better
        if metric_type in ['cost_per_click', 'cost_per_conversion']:
            performance_ratio = float(goal) / current_value
        else:
            # For rate metrics, higher is better
            performance_ratio = current_value / float(goal)
        
        if performance_ratio >= 1.2:  # 120% or more of goal
            return 'excellent'
        elif performance_ratio >= 1.0:  # 100% - 119% of goal
            return 'good'
        elif performance_ratio >= 0.8:  # 80% - 99% of goal
            return 'warning'
        else:  # Less than 80% of goal
            return 'poor'


class BackgroundTask(models.Model):
    """
    Model to track background tasks
    """
    TASK_TYPES = [
        ("google_ads_sync", "Google Ads Data Sync"),
        ("google_ads_backfill", "Google Ads Data Backfill"),
        ("bulk_refresh", "Bulk Data Refresh"),
    ]
    
    TASK_STATUS = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]
    
    # Task identification
    task_type = models.CharField(max_length=50, choices=TASK_TYPES)
    task_id = models.CharField(max_length=100, unique=True)  # UUID for tracking
    
    # Task ownership
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="background_tasks")
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="created_tasks")
    
    # Task status and timing
    status = models.CharField(max_length=20, choices=TASK_STATUS, default="pending")
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Task configuration and results
    parameters = models.JSONField(default=dict, blank=True)  # Task parameters
    progress = models.JSONField(default=dict, blank=True)    # Progress tracking
    result = models.JSONField(default=dict, blank=True)      # Final results
    error_message = models.TextField(blank=True)
    
    # Metadata
    estimated_duration = models.IntegerField(null=True, blank=True)  # seconds
    actual_duration = models.IntegerField(null=True, blank=True)     # seconds
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["task_type", "status"]),
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["created_at"]),
        ]
    
    def __str__(self):
        return f"{self.get_task_type_display()} - {self.status}"
    
    def start(self):
        """Mark task as started"""
        self.status = "running"
        self.started_at = timezone.now()
        self.save(update_fields=["status", "started_at"])
    
    def complete(self, result_data=None):
        """Mark task as completed"""
        self.status = "completed"
        self.completed_at = timezone.now()
        if result_data:
            self.result = result_data
        
        # Calculate actual duration
        if self.started_at:
            duration = (self.completed_at - self.started_at).total_seconds()
            self.actual_duration = int(duration)
        
        self.save(update_fields=["status", "completed_at", "result", "actual_duration"])
    
    def fail(self, error_message):
        """Mark task as failed"""
        self.status = "failed"
        self.completed_at = timezone.now()
        self.error_message = error_message
        
        # Calculate actual duration
        if self.started_at:
            duration = (self.completed_at - self.started_at).total_seconds()
            self.actual_duration = int(duration)
        
        self.save(update_fields=["status", "completed_at", "error_message", "actual_duration"])
    
    def update_progress(self, progress_data):
        """Update task progress"""
        self.progress = progress_data
        self.save(update_fields=["progress"])
    
    @property
    def duration_display(self):
        """Human readable duration"""
        if self.actual_duration:
            minutes, seconds = divmod(self.actual_duration, 60)
            if minutes:
                return f"{minutes}m {seconds}s"
            else:
                return f"{seconds}s"
        return "Unknown"
    
    @property
    def is_active(self):
        """Check if task is currently active"""
        return self.status in ["pending", "running"]
    
    @property
    def is_completed(self):
        """Check if task is finished (success or failure)"""
        return self.status in ["completed", "failed", "cancelled"]


class GoogleAdsDataFreshness(models.Model):
    """
    Model to track Google Ads data freshness for intelligent refresh decisions
    """
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    client_account = models.ForeignKey(ClientPlatformAccount, on_delete=models.CASCADE)
    
    # Date range of data
    date_start = models.DateField()
    date_end = models.DateField()
    
    # Freshness tracking
    last_synced = models.DateTimeField(auto_now=True)
    data_source = models.CharField(max_length=50, default="google_ads_api")
    sync_duration = models.IntegerField(null=True, blank=True)  # seconds
    
    # Data quality metrics
    campaigns_synced = models.IntegerField(default=0)
    metrics_records_created = models.IntegerField(default=0)
    has_data = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ["client_account", "date_start", "date_end"]
        indexes = [
            models.Index(fields=["tenant", "last_synced"]),
            models.Index(fields=["client", "date_start", "date_end"]),
        ]
    
    def __str__(self):
        return f"{self.client.name} - {self.date_start} to {self.date_end}"
    
    @property
    def is_fresh(self, hours=24):
        """Check if data is fresh within specified hours"""
        if not self.last_synced:
            return False
        
        cutoff = timezone.now() - timezone.timedelta(hours=hours)
        return self.last_synced > cutoff
    
    @property
    def age_hours(self):
        """Get age of data in hours"""
        if not self.last_synced:
            return float("inf")
        
        delta = timezone.now() - self.last_synced
        return delta.total_seconds() / 3600

