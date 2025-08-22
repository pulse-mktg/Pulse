from django.core.management.base import BaseCommand
from website.models import ClientPlatformAccount, Client

class Command(BaseCommand):
    help = 'Activates all inactive client platform accounts'

    def handle(self, *args, **options):
        # Get all inactive accounts across all clients
        inactive_accounts = ClientPlatformAccount.objects.filter(
            is_active=True
        )
        
        # Print and activate each account
        count = 0
        client_counts = {}
        
        for account in inactive_accounts:
            client_name = account.client.name
            self.stdout.write(f"Found inactive account: ID {account.id}, Client: {client_name}, Name: {account.platform_client_name}, Platform ID: {account.platform_client_id}")
            
            account.is_active = False
            account.save()
            
            count += 1
            client_counts[client_name] = client_counts.get(client_name, 0) + 1
            self.stdout.write(f"Activated account: {account.platform_client_name}")
        
        # Print summary
        self.stdout.write(self.style.SUCCESS(f"\nSummary:"))
        self.stdout.write(self.style.SUCCESS(f"Activated {count} accounts total"))
        for client_name, client_count in client_counts.items():
            self.stdout.write(self.style.SUCCESS(f"- {client_name}: {client_count} accounts activated"))