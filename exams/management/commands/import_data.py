from django.core.management.base import BaseCommand, CommandError
from tablib import Dataset
from exams.admin import (
    StudentResource, ProgramResource,
    ProcedureResource, ProcedureStepResource
)
import os


class Command(BaseCommand):
    help = 'Import students, programs, procedures, and procedure steps from Excel/CSV files'

    def add_arguments(self, parser):
        parser.add_argument(
            '--programs',
            type=str,
            help='Path to programs file'
        )
        parser.add_argument(
            '--students',
            type=str,
            help='Path to students file'
        )
        parser.add_argument(
            '--procedures',
            type=str,
            help='Path to procedures file'
        )
        parser.add_argument(
            '--steps',
            type=str,
            help='Path to procedure steps file'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Perform a dry run without saving to database'
        )

    def import_file(self, file_path, resource_class, resource_name, dry_run=False):
        """Generic import function"""
        if not file_path:
            self.stdout.write(self.style.WARNING(f'Skipping {resource_name} - no file provided'))
            return
        
        if not os.path.exists(file_path):
            raise CommandError(f'{resource_name} file not found: {file_path}')
        
        self.stdout.write(f'Importing {resource_name} from {file_path}...')
        
        # Read file
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        # Determine format from file extension
        file_ext = os.path.splitext(file_path)[1].lower()
        if file_ext == '.xlsx':
            dataset = Dataset().load(file_data, format='xlsx')
        elif file_ext == '.csv':
            dataset = Dataset().load(file_data.decode('utf-8'), format='csv')
        elif file_ext == '.json':
            dataset = Dataset().load(file_data.decode('utf-8'), format='json')
        else:
            raise CommandError(f'Unsupported file format: {file_ext}')
        
        # Import data
        resource = resource_class()
        result = resource.import_data(dataset, dry_run=dry_run)
        
        # Display results
        if result.has_errors():
            self.stdout.write(self.style.ERROR(f'✗ {resource_name} import failed with errors:'))
            for row_errors in result.row_errors():
                row_number, errors = row_errors
                for error in errors:
                    self.stdout.write(self.style.ERROR(f'  Row {row_number}: {error.error}'))
        else:
            mode = 'would be' if dry_run else 'were'
            self.stdout.write(self.style.SUCCESS(
                f'✓ {resource_name} import successful: '
                f'{result.total_rows} rows processed, '
                f'{result.totals.get("new", 0)} new, '
                f'{result.totals.get("update", 0)} updated, '
                f'{result.totals.get("skip", 0)} skipped'
            ))
            
            if dry_run:
                self.stdout.write(self.style.WARNING('  (Dry run - no changes saved)'))

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('=== DRY RUN MODE - No changes will be saved ===\n'))
        
        # Import in correct order (respecting foreign key dependencies)
        try:
            # 1. Programs (no dependencies)
            self.import_file(
                options['programs'],
                ProgramResource,
                'Programs',
                dry_run
            )
            
            # 2. Students (depends on Programs)
            self.import_file(
                options['students'],
                StudentResource,
                'Students',
                dry_run
            )
            
            # 3. Procedures (depends on Programs)
            self.import_file(
                options['procedures'],
                ProcedureResource,
                'Procedures',
                dry_run
            )
            
            # 4. Procedure Steps (depends on Procedures)
            self.import_file(
                options['steps'],
                ProcedureStepResource,
                'Procedure Steps',
                dry_run
            )
            
            self.stdout.write(self.style.SUCCESS('\n✓ Import process completed'))
            
            if dry_run:
                self.stdout.write(self.style.WARNING(
                    '\nThis was a dry run. To actually import the data, '
                    'run the command again without --dry-run'
                ))
        
        except Exception as e:
            raise CommandError(f'Import failed: {str(e)}')