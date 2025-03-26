# In website/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Client, ClientGroup

@receiver(post_save, sender=Client)
def update_client_category_groups(sender, instance, created, **kwargs):
    """Update auto-generated category groups when client is saved/updated"""
    if not instance.is_active:
        return  # Skip inactive clients
    
    tenant = instance.tenant
    
    # Get all auto-generated groups for this tenant
    auto_groups = ClientGroup.objects.filter(
        tenant=tenant,
        is_active=True,
        is_auto_generated=True
    )
    
    # Remove client from all auto-generated groups first to handle changes
    for group in auto_groups:
        group.clients.remove(instance)
    
    # Then add to matching groups
    
    # Handle company size groups
    if instance.company_size:
        size_groups = auto_groups.filter(
            category_type='company_size',
            category_value=instance.company_size
        )
        for group in size_groups:
            group.clients.add(instance)
    
    # Handle revenue range groups
    if instance.revenue_range:
        revenue_groups = auto_groups.filter(
            category_type='revenue_range',
            category_value=instance.revenue_range
        )
        for group in revenue_groups:
            group.clients.add(instance)
    
    # Handle geographic focus groups
    if instance.geographic_focus:
        geo_groups = auto_groups.filter(
            category_type='geographic_focus',
            category_value=instance.geographic_focus
        )
        for group in geo_groups:
            group.clients.add(instance)
    
    # Handle marketing maturity groups
    if instance.marketing_maturity:
        maturity_groups = auto_groups.filter(
            category_type='marketing_maturity',
            category_value=instance.marketing_maturity
        )
        for group in maturity_groups:
            group.clients.add(instance)
    
    # Handle business model types (multi-select)
    if instance.business_model_types:
        for model_type in instance.business_model_types:
            model_groups = auto_groups.filter(
                category_type='business_model',
                category_value=model_type
            )
            for group in model_groups:
                group.clients.add(instance)