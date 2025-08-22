from django.core.management.base import BaseCommand
from website.models import ClientGroup, Client, Tenant

class Command(BaseCommand):
    help = 'Repopulates auto-generated groups with the correct clients'

    def handle(self, *args, **options):
        # Get all tenants
        tenants = Tenant.objects.filter(is_active=True)
        
        for tenant in tenants:
            self.stdout.write(f"Repopulating groups for tenant: {tenant.name}")
            
            # Get all auto-generated groups for this tenant
            auto_groups = ClientGroup.objects.filter(
                tenant=tenant, 
                is_auto_generated=True
            )
            
            self.stdout.write(f"Found {auto_groups.count()} auto-generated groups")
            
            # Clear all clients from auto-generated groups first
            for group in auto_groups:
                previous_count = group.clients.count()
                group.clients.clear()
                self.stdout.write(f"Cleared {previous_count} clients from '{group.name}'")
            
            # Repopulate groups based on their category type
            for group in auto_groups:
                if group.category_type == 'company_size':
                    matching_clients = Client.objects.filter(
                        tenant=tenant,
                        is_active=True,
                        company_size=group.category_value
                    )
                    group.clients.add(*matching_clients)
                    self.stdout.write(f"Added {matching_clients.count()} clients to '{group.name}'")
                    
                elif group.category_type == 'revenue_range':
                    matching_clients = Client.objects.filter(
                        tenant=tenant,
                        is_active=True,
                        revenue_range=group.category_value
                    )
                    group.clients.add(*matching_clients)
                    self.stdout.write(f"Added {matching_clients.count()} clients to '{group.name}'")
                    
                elif group.category_type == 'geographic_focus':
                    matching_clients = Client.objects.filter(
                        tenant=tenant,
                        is_active=True,
                        geographic_focus=group.category_value
                    )
                    group.clients.add(*matching_clients)
                    self.stdout.write(f"Added {matching_clients.count()} clients to '{group.name}'")
                    
                elif group.category_type == 'marketing_maturity':
                    matching_clients = Client.objects.filter(
                        tenant=tenant,
                        is_active=True,
                        marketing_maturity=group.category_value
                    )
                    group.clients.add(*matching_clients)
                    self.stdout.write(f"Added {matching_clients.count()} clients to '{group.name}'")
                    
                elif group.category_type == 'business_model':
                    matching_clients = Client.objects.filter(
                        tenant=tenant,
                        is_active=True,
                        business_model_types__contains=group.category_value
                    )
                    group.clients.add(*matching_clients)
                    self.stdout.write(f"Added {matching_clients.count()} clients to '{group.name}'")
            
        self.stdout.write(self.style.SUCCESS("Successfully repopulated all auto-generated groups"))