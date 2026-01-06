from django.core.management.base import BaseCommand
from tablib import Dataset
import os


class Command(BaseCommand):
    help = 'Create sample import templates for students, programs, procedures, and steps'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output-dir',
            type=str,
            default='import_templates',
            help='Output directory for template files'
        )
        parser.add_argument(
            '--format',
            type=str,
            default='xlsx',
            choices=['xlsx', 'csv'],
            help='Template format (xlsx or csv)'
        )

    def handle(self, *args, **options):
        output_dir = options['output_dir']
        file_format = options['format']
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Programs template
        programs_dataset = Dataset()
        programs_dataset.headers = ['id', 'name', 'abbreviation']
        programs_dataset.append(['', 'Bachelor of Science in Nursing', 'BSN'])
        programs_dataset.append(['', 'Diploma in Nursing', 'DipNurs'])
        
        programs_file = os.path.join(output_dir, f'programs_template.{file_format}')
        with open(programs_file, 'wb') as f:
            f.write(getattr(programs_dataset, file_format))
        self.stdout.write(self.style.SUCCESS(f'✓ Programs template created: {programs_file}'))
        
        # Students template
        students_dataset = Dataset()
        students_dataset.headers = [
            'id', 'index_number', 'full_name', 'program_name', 'is_active'
        ]
        students_dataset.append([
            '', 'NS001', 'John Doe', 'Bachelor of Science in Nursing', 'True'
        ])
        students_dataset.append([
            '', 'NS002', 'Jane Smith', 'Bachelor of Science in Nursing', 'True'
        ])
        students_dataset.append([
            '', 'NS003', 'Michael Johnson', 'Diploma in Nursing', 'True'
        ])
        
        students_file = os.path.join(output_dir, f'students_template.{file_format}')
        with open(students_file, 'wb') as f:
            f.write(getattr(students_dataset, file_format))
        self.stdout.write(self.style.SUCCESS(f'✓ Students template created: {students_file}'))
        
        # Procedures template
        procedures_dataset = Dataset()
        procedures_dataset.headers = ['id', 'program_name', 'name', 'total_score']
        procedures_dataset.append([
            '', 'Bachelor of Science in Nursing', 'Vital Signs Assessment', '20'
        ])
        procedures_dataset.append([
            '', 'Bachelor of Science in Nursing', 'IV Catheter Insertion', '20'
        ])
        procedures_dataset.append([
            '', 'Diploma in Nursing', 'Basic Wound Care', '20'
        ])
        
        procedures_file = os.path.join(output_dir, f'procedures_template.{file_format}')
        with open(procedures_file, 'wb') as f:
            f.write(getattr(procedures_dataset, file_format))
        self.stdout.write(self.style.SUCCESS(f'✓ Procedures template created: {procedures_file}'))
        
        # Procedure Steps template
        steps_dataset = Dataset()
        steps_dataset.headers = ['id', 'procedure_name', 'description', 'step_order']
        steps_dataset.append([
            '', 'Vital Signs Assessment', 'Introduce yourself and explain the procedure', '1'
        ])
        steps_dataset.append([
            '', 'Vital Signs Assessment', 'Wash hands and put on gloves', '2'
        ])
        steps_dataset.append([
            '', 'Vital Signs Assessment', 'Take temperature reading', '3'
        ])
        steps_dataset.append([
            '', 'Vital Signs Assessment', 'Take pulse reading', '4'
        ])
        steps_dataset.append([
            '', 'Vital Signs Assessment', 'Take blood pressure reading', '5'
        ])
        
        steps_file = os.path.join(output_dir, f'procedure_steps_template.{file_format}')
        with open(steps_file, 'wb') as f:
            f.write(getattr(steps_dataset, file_format))
        self.stdout.write(self.style.SUCCESS(f'✓ Procedure steps template created: {steps_file}'))
        
        # Create README
        readme_content = f"""# Import Templates

These template files can be used to import data into the Nursing Practical App.

## Files Included:
1. programs_template.{file_format} - Program definitions
2. students_template.{file_format} - Student records
3. procedures_template.{file_format} - Assessment procedures
4. procedure_steps_template.{file_format} - Individual procedure steps

## Import Order:
Import files in this order to maintain data integrity:
1. Programs (no dependencies)
2. Students (depends on Programs)
3. Procedures (depends on Programs)
4. Procedure Steps (depends on Procedures)

## Using Django Admin:
1. Go to Django Admin panel
2. Select the model you want to import (e.g., Students)
3. Click "Import" button at the top
4. Choose your file and click "Submit"
5. Review the preview and confirm import

## Using Management Command:
Run dry-run first to check for errors:
```bash
python manage.py import_data \\
    --programs=import_templates/programs_template.{file_format} \\
    --students=import_templates/students_template.{file_format} \\
    --procedures=import_templates/procedures_template.{file_format} \\
    --steps=import_templates/procedure_steps_template.{file_format} \\
    --dry-run
```

Then run actual import:
```bash
python manage.py import_data \\
    --programs=import_templates/programs_template.{file_format} \\
    --students=import_templates/students_template.{file_format} \\
    --procedures=import_templates/procedures_template.{file_format} \\
    --steps=import_templates/procedure_steps_template.{file_format}
```

## Field Descriptions:

### Programs:
- id: Leave empty for new records
- name: Full program name (unique)
- abbreviation: Short code for the program (unique, optional)

### Students:
- id: Leave empty for new records
- index_number: Student ID (unique)
- full_name: Student's full name
- program_name: Must match an existing program name
- is_active: True or False

### Procedures:
- id: Leave empty for new records
- program_name: Must match an existing program name
- name: Procedure name (unique within program)
- total_score: Maximum possible score

### Procedure Steps:
- id: Leave empty for new records
- procedure_name: Must match an existing procedure name
- description: Step description/instructions
- step_order: Sequential number (1, 2, 3, etc.)

## Notes:
- Leave 'id' field empty for new records
- Foreign key fields use the name/identifier, not the ID
- Boolean fields accept: True/False, Yes/No, 1/0
- Update existing records by providing the correct identifier (index_number for students, etc.)
"""
        
        readme_file = os.path.join(output_dir, 'README.md')
        with open(readme_file, 'w') as f:
            f.write(readme_content)
        self.stdout.write(self.style.SUCCESS(f'✓ README created: {readme_file}'))
        
        self.stdout.write(self.style.SUCCESS(
            f'\n✓ All templates created successfully in {output_dir}/'
        ))
        self.stdout.write(f'  Format: {file_format.upper()}')