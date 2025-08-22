from django.core.management.base import BaseCommand
from website.models import ClientGroup, Client
from django.db.models import Q

class Command(BaseCommand):
    help = 'Cleans up groups that were incorrectly added as clients to other groups'

    def handle(self, *args, **options):
        # Get all auto-generated groups
        auto_groups = ClientGroup.objects.filter(is_auto_generated=True)
        self.stdout.write(f"Found {auto_groups.count()} auto-generated groups to check")
        
        # Find clients that have names matching our auto-generated group pattern
        group_patterns = [
            Q(name__startswith='Size: '),
            Q(name__startswith='Revenue: '),
            Q(name__startswith='Location: '),
            Q(name__startswith='Marketing: '),
            Q(name__startswith='Business: ')
        ]
        
        # Combine all patterns with OR
        filter_condition = group_patterns[0]
        for pattern in group_patterns[1:]:
            filter_condition |= pattern
            
        # Find any clients with suspicious names
        suspicious_clients = Client.objects.filter(filter_condition)
        
        if suspicious_clients.exists():
            self.stdout.write(f"Found {suspicious_clients.count()} clients with names that look like auto-generated groups:")
            for client in suspicious_clients:
                self.stdout.write(f"  {client.id}: {client.name}")
                
            # These may be actual clients that just happen to have similar names
            self.stdout.write("These could be legitimate clients with similar names. No changes made.")
        else:
            self.stdout.write("No suspicious clients found with names like auto-generated groups.")
            
        # Find groups that appear inside other groups' client lists
        for group in auto_groups:
            # Step 1: Get all client IDs that this group has
            client_ids_in_group = set(group.clients.values_list('id', flat=True))
            
            # Step 2: Get all auto-generated group IDs
            auto_group_ids = set(auto_groups.values_list('id', flat=True))
            
            # Step 3: Find if any auto_group_ids appear as client IDs in this group
            overlapping_ids = client_ids_in_group.intersection(auto_group_ids.difference({group.id}))
            
            if overlapping_ids:
                self.stdout.write(f"Found {len(overlapping_ids)} other groups that appear as clients in '{group.name}'")
                
                # Step 4: Print detailed information about each relationship
                for overlap_id in overlapping_ids:
                    try:
                        other_group = ClientGroup.objects.get(id=overlap_id)
                        client_with_same_id = Client.objects.filter(id=overlap_id).first()
                        
                        self.stdout.write(f"  Group '{other_group.name}' (ID: {overlap_id}) appears as a client in '{group.name}'")
                        if client_with_same_id:
                            self.stdout.write(f"    Note: This ID also belongs to a real client named '{client_with_same_id.name}'")
                        
                    except ClientGroup.DoesNotExist:
                        self.stdout.write(f"  Group with ID {overlap_id} not found, but it appears in client list")
            else:
                self.stdout.write(f"No issues found with '{group.name}'")
                
        self.stdout.write(self.style.SUCCESS("Analysis complete - no changes made."))