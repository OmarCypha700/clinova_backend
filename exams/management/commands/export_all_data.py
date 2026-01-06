from django.core.management.base import BaseCommand
from django.utils import timezone
from tablib import Dataset
from exams.admin import (
    StudentResource, ProgramResource, 
    ProcedureResource, ProcedureStepResource
)
import os


class Command(BaseCommand):
    help = 'Export all students, programs, procedures, and procedure steps to Excel/CSV'

    def add_arguments(self, parser):
        parser.add_argument(
            '--format',
            type=str,
            default='xlsx',
            choices=['xlsx', 'csv', 'json'],
            help='Export format (xlsx, csv, or json)'
        )
        parser.add_argument(
            '--output-dir',
            type=str,
            default='exports',
            help='Output directory for export files'
        )

    def handle(self, *args, **options):
        export_format = options['format']
        output_dir = options['output_dir']
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate timestamp for filenames
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        
        # Export Programs
        self.stdout.write('Exporting programs...')
        program_resource = ProgramResource()
        program_dataset = program_resource.export()
        program_file = os.path.join(output_dir, f'programs_{timestamp}.{export_format}')
        with open(program_file, 'wb') as f:
            f.write(getattr(program_dataset, export_format))
        self.stdout.write(self.style.SUCCESS(f'Programs exported to {program_file}'))
        
        # Export Students
        self.stdout.write('Exporting students...')
        student_resource = StudentResource()
        student_dataset = student_resource.export()
        student_file = os.path.join(output_dir, f'students_{timestamp}.{export_format}')
        with open(student_file, 'wb') as f:
            f.write(getattr(student_dataset, export_format))
        self.stdout.write(self.style.SUCCESS(f'Students exported to {student_file}'))
        
        # Export Procedures
        self.stdout.write('Exporting procedures...')
        procedure_resource = ProcedureResource()
        procedure_dataset = procedure_resource.export()
        procedure_file = os.path.join(output_dir, f'procedures_{timestamp}.{export_format}')
        with open(procedure_file, 'wb') as f:
            f.write(getattr(procedure_dataset, export_format))
        self.stdout.write(self.style.SUCCESS(f'Procedures exported to {procedure_file}'))
        
        # Export Procedure Steps
        self.stdout.write('Exporting procedure steps...')
        step_resource = ProcedureStepResource()
        step_dataset = step_resource.export()
        step_file = os.path.join(output_dir, f'procedure_steps_{timestamp}.{export_format}')
        with open(step_file, 'wb') as f:
            f.write(getattr(step_dataset, export_format))
        self.stdout.write(self.style.SUCCESS(f'Procedure steps exported to {step_file}'))
        
        self.stdout.write(self.style.SUCCESS(f'\n✓ All data exported successfully to {output_dir}/'))