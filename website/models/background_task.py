"""
Background task models for async processing
"""
import json
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from .base import BaseModel


class BackgroundTask(BaseModel):
    """
    Model to track background tasks
    """
    TASK_TYPES = [
        ('google_ads_sync', 'Google Ads Data Sync'),
        ('google_ads_backfill', 'Google Ads Data Backfill'),
        ('bulk_refresh', 'Bulk Data Refresh'),
    ]
    
    TASK_STATUS = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    # Task identification
    task_type = models.CharField(max_length=50, choices=TASK_TYPES)
    task_id = models.CharField(max_length=100, unique=True)  # UUID for tracking
    
    # Task ownership
    tenant = models.ForeignKey('Tenant', on_delete=models.CASCADE, related_name='background_tasks')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_tasks')
    
    # Task status and timing
    status = models.CharField(max_length=20, choices=TASK_STATUS, default='pending')
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Task configuration and results
    parameters = models.JSONField(default=dict, blank=True)  # Task parameters
    progress = models.JSONField(default=dict, blank=True)    # Progress tracking
    result = models.JSONField(default=dict, blank=True)      # Final results
    error_message = models.TextField(blank=True)
    
    # Metadata
    estimated_duration = models.IntegerField(null=True, blank=True)  # seconds
    actual_duration = models.IntegerField(null=True, blank=True)     # seconds
    
    class Meta:
        db_table = 'website_backgroundtask'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['task_type', 'status']),
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.get_task_type_display()} - {self.status}"
    
    def start(self):
        """Mark task as started"""
        self.status = 'running'
        self.started_at = timezone.now()
        self.save(update_fields=['status', 'started_at'])
    
    def complete(self, result_data=None):
        """Mark task as completed"""
        self.status = 'completed'
        self.completed_at = timezone.now()
        if result_data:
            self.result = result_data
        
        # Calculate actual duration
        if self.started_at:
            duration = (self.completed_at - self.started_at).total_seconds()
            self.actual_duration = int(duration)
        
        self.save(update_fields=['status', 'completed_at', 'result', 'actual_duration'])
    
    def fail(self, error_message):
        """Mark task as failed"""
        self.status = 'failed'
        self.completed_at = timezone.now()
        self.error_message = error_message
        
        # Calculate actual duration
        if self.started_at:
            duration = (self.completed_at - self.started_at).total_seconds()
            self.actual_duration = int(duration)
        
        self.save(update_fields=['status', 'completed_at', 'error_message', 'actual_duration'])
    
    def update_progress(self, progress_data):
        """Update task progress"""
        self.progress = progress_data
        self.save(update_fields=['progress'])
    
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
        return self.status in ['pending', 'running']
    
    @property
    def is_completed(self):
        """Check if task is finished (success or failure)"""
        return self.status in ['completed', 'failed', 'cancelled']


class GoogleAdsDataFreshness(BaseModel):
    """
    Model to track Google Ads data freshness for intelligent refresh decisions
    """
    tenant = models.ForeignKey('Tenant', on_delete=models.CASCADE)
    client = models.ForeignKey('Client', on_delete=models.CASCADE)
    client_account = models.ForeignKey('ClientPlatformAccount', on_delete=models.CASCADE)
    
    # Date range of data
    date_start = models.DateField()
    date_end = models.DateField()
    
    # Freshness tracking
    last_synced = models.DateTimeField(auto_now=True)
    data_source = models.CharField(max_length=50, default='google_ads_api')
    sync_duration = models.IntegerField(null=True, blank=True)  # seconds
    
    # Data quality metrics
    campaigns_synced = models.IntegerField(default=0)
    metrics_records_created = models.IntegerField(default=0)
    has_data = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'website_googleadsdatafreshness'
        unique_together = ['client_account', 'date_start', 'date_end']
        indexes = [
            models.Index(fields=['tenant', 'last_synced']),
            models.Index(fields=['client', 'date_start', 'date_end']),
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
            return float('inf')
        
        delta = timezone.now() - self.last_synced
        return delta.total_seconds() / 3600