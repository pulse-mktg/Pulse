# website/management/commands/create_default_groups.py
from django.core.management.base import BaseCommand
from django.db import transaction
from website.models import Tenant, ClientGroup, Client

class Command(BaseCommand):
    help = 'Creates default client groups based on categorizations'

    @transaction.atomic
    def handle(self, *args, **options):
        # Get all tenants
        tenants = Tenant.objects.filter(is_active=True)
        
        for tenant in tenants:
            self.stdout.write(f"Creating default groups for tenant: {tenant.name}")
            
            # Create company size groups
            for size_code, size_name in Client.COMPANY_SIZE_CHOICES:
                group, created = ClientGroup.objects.get_or_create(
                    tenant=tenant,
                    name=f"Size: {size_name}",
                    defaults={
                        'description': f"Clients with company size: {size_name}",
                        'color': '#3c4b64',  # Default dark blue
                        'icon_class': 'bi-building',
                        'is_active': True,
                        'is_auto_generated': True,  # New field to indicate auto-generated group
                        'category_type': 'company_size',  # New field to track category type
                        'category_value': size_code,  # Store the value to match clients
                    }
                )
                if created:
                    self.stdout.write(f"  Created group: {group.name}")
                    
                    # Add existing matching clients to this group
                    matching_clients = Client.objects.filter(
                        tenant=tenant, 
                        is_active=True,
                        company_size=size_code
                    )
                    group.clients.add(*matching_clients)
                    self.stdout.write(f"  Added {matching_clients.count()} clients to this group")
            # Inside your create_default_groups command

            # Create revenue range groups
            for revenue_code, revenue_name in Client.REVENUE_RANGE_CHOICES:
                group, created = ClientGroup.objects.get_or_create(
                    tenant=tenant,
                    name=f"Revenue: {revenue_name}",
                    defaults={
                        'description': f"Clients with revenue range: {revenue_name}",
                        'color': '#2eb85c',  # Use different colors for different categories
                        'icon_class': 'bi-cash-coin',
                        'is_active': True,
                        'is_auto_generated': True,
                        'category_type': 'revenue_range',
                        'category_value': revenue_code,
                    }
                )
                if created:
                    self.stdout.write(f"  Created group: {group.name}")
                    
                    # Add existing matching clients to this group
                    matching_clients = Client.objects.filter(
                        tenant=tenant, 
                        is_active=True,
                        revenue_range=revenue_code
                    )
                    group.clients.add(*matching_clients)

            # Create geographic focus groups
            for geo_code, geo_name in Client.GEO_FOCUS_CHOICES:
                group, created = ClientGroup.objects.get_or_create(
                    tenant=tenant,
                    name=f"Location: {geo_name}",
                    defaults={
                        'description': f"Clients with geographic focus: {geo_name}",
                        'color': '#321fdb',  # Different color
                        'icon_class': 'bi-geo-alt',
                        'is_active': True,
                        'is_auto_generated': True,
                        'category_type': 'geographic_focus',
                        'category_value': geo_code,
                    }
                )
                if created:
                    self.stdout.write(f"  Created group: {group.name}")
                    
                    # Add existing matching clients
                    matching_clients = Client.objects.filter(
                        tenant=tenant, 
                        is_active=True,
                        geographic_focus=geo_code
                    )
                    group.clients.add(*matching_clients)

            # Create marketing maturity groups
            for maturity_code, maturity_name in Client.MARKETING_MATURITY_CHOICES:
                group, created = ClientGroup.objects.get_or_create(
                    tenant=tenant,
                    name=f"Marketing: {maturity_name.split(' (')[0]}",  # Just the first part of the name
                    defaults={
                        'description': f"Clients with marketing maturity: {maturity_name}",
                        'color': '#e55353',  # Different color
                        'icon_class': 'bi-graph-up',
                        'is_active': True,
                        'is_auto_generated': True, 
                        'category_type': 'marketing_maturity',
                        'category_value': maturity_code,
                    }
                )
                if created:
                    self.stdout.write(f"  Created group: {group.name}")
                    
                    # Add existing matching clients
                    matching_clients = Client.objects.filter(
                        tenant=tenant, 
                        is_active=True,
                        marketing_maturity=maturity_code
                    )
                    group.clients.add(*matching_clients)

            # Handle business model types (multi-select field)
            # This is more complex because one client can have multiple business models
            for model_code, model_name in Client.BUSINESS_MODEL_CHOICES:
                # Get a cleaner name for the group
                model_display = model_name.split(' (')[0] if ' (' in model_name else model_name
                
                group, created = ClientGroup.objects.get_or_create(
                    tenant=tenant,
                    name=f"Business: {model_display}",
                    defaults={
                        'description': f"Clients with business model: {model_name}",
                        'color': '#f9b115',  # Different color
                        'icon_class': 'bi-briefcase',
                        'is_active': True,
                        'is_auto_generated': True,
                        'category_type': 'business_model',
                        'category_value': model_code,
                    }
                )
                if created:
                    self.stdout.write(f"  Created group: {group.name}")
                    
                    # For MultiSelectField, we need to find clients that have this value
                    # in their business_model_types array
                    matching_clients = Client.objects.filter(
                        tenant=tenant,
                        is_active=True,
                        business_model_types__contains=model_code
                    )
                    group.clients.add(*matching_clients)
            # Create similar blocks for other categories:
            # - Revenue range groups
            # - Geographic focus groups 
            # - Marketing maturity groups
            # - Business model groups (these will need special handling since it's multi-select)

        self.stdout.write(self.style.SUCCESS("Successfully created default groups"))