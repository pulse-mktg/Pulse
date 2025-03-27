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
        return (self.amount * self.days_elapsed) / self.days_in_period


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