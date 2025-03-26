from django.core.management.base import BaseCommand
from django.db import transaction
from website.models import ClientPlatformAccount

class Command(BaseCommand):
    help = 'Clears all ClientPlatformAccount data while preserving the schema'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirms deletion without prompting',
        )

    def handle(self, *args, **options):
        # Get count of records to be deleted
        count = ClientPlatformAccount.objects.count()
        
        if count == 0:
            self.stdout.write(self.style.SUCCESS('No ClientPlatformAccount records found. Table is already empty.'))
            return
            
        # Ask for confirmation unless --confirm is provided
        if not options['confirm']:
            confirm = input(f'\nYou are about to delete {count} ClientPlatformAccount records. This cannot be undone.\nAre you sure? (yes/no): ')
            if confirm.lower() != 'yes':
                self.stdout.write(self.style.WARNING('Operation cancelled.'))
                return
        
        # Delete all records with a transaction for safety
        with transaction.atomic():
            ClientPlatformAccount.objects.all().delete()
            
        # Verify deletion
        new_count = ClientPlatformAccount.objects.count()
        if new_count == 0:
            self.stdout.write(self.style.SUCCESS(f'Successfully deleted {count} ClientPlatformAccount records.'))
        else:
            self.stdout.write(self.style.ERROR(f'Error: {new_count} records still remain.'))