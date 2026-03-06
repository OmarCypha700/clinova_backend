from django.contrib import admin
from import_export import fields, resources, widgets
from import_export.admin import ExportActionMixin, ImportExportModelAdmin
from unfold.admin import ModelAdmin
from unfold.contrib.import_export.forms import ExportForm, ImportForm
from unfold.paginator import InfinitePaginator
# from accounts.models import User
from .models import (CarePlan, Procedure, ProcedureStep, ProcedureStepScore,
                     Program, ReconciledScore, Student, StudentProcedure)


# ============== RESOURCES ==============
class ProgramResource(resources.ModelResource):
    class Meta:
        model = Program
        fields = ('id', 'name', 'abbreviation')
        export_order = ('id', 'name', 'abbreviation')

class StudentResource(resources.ModelResource):
    program_name = fields.Field(
        column_name='program_name',
        attribute='program',
        widget=widgets.ForeignKeyWidget(Program, 'name')
    )
    level_display = fields.Field(
        column_name='level_display',
        attribute='get_level_display'
    )
    
    class Meta:
        model = Student
        fields = ('id', 'index_number', 'full_name', 'program_name', 'level', 'level_display', 'is_active')
        export_order = ('id', 'index_number', 'full_name', 'program_name', 'level', 'level_display', 'is_active')
        import_id_fields = ['index_number']

class ProcedureResource(resources.ModelResource):
    program_name = fields.Field(
        column_name='program_name',
        attribute='program',
        widget=widgets.ForeignKeyWidget(Program, 'name')
    )
    
    class Meta:
        model = Procedure
        fields = ('id', 'program_name', 'name', 'total_score')
        export_order = ('id', 'program_name', 'name', 'total_score')
        import_id_fields = ['program_name', 'name']

class ProcedureStepResource(resources.ModelResource):
    procedure_name = fields.Field(column_name='procedure_name')
    program_name = fields.Field(column_name='program_name')
    
    class Meta:
        model = ProcedureStep
        fields = ('id', 'procedure_name', 'program_name', 'description', 'step_order')
        export_order = ('id', 'procedure_name', 'program_name', 'description', 'step_order')
    
    def before_import_row(self, row, **kwargs):
        """Resolve procedure using both name and program"""
        procedure_name = row.get('procedure_name')
        program_name = row.get('program_name')
        
        if not procedure_name or not program_name:
            raise ValueError("Both procedure_name and program_name are required")
        
        try:
            program = Program.objects.get(name=program_name)
            procedure = Procedure.objects.get(name=procedure_name, program=program)
            # Don't set procedure directly - we'll handle it in skip_row or import_obj
            self._procedure_cache = procedure
        except Program.DoesNotExist:
            raise ValueError(f"Program '{program_name}' not found")
        except Procedure.DoesNotExist:
            raise ValueError(f"Procedure '{procedure_name}' not found in program '{program_name}'")
    
    def import_obj(self, obj, data, dry_run, **kwargs):
        """Set the procedure from our cache"""
        if hasattr(self, '_procedure_cache'):
            obj.procedure = self._procedure_cache
        return super().import_obj(obj, data, dry_run, **kwargs)
    
    def dehydrate_procedure_name(self, step):
        return step.procedure.name
    
    def dehydrate_program_name(self, step):
        return step.procedure.program.name

class StudentProcedureResource(resources.ModelResource):
    student_index = fields.Field(
        column_name='student_index',
        attribute='student',
        widget=widgets.ForeignKeyWidget(Student, 'index_number')
    )
    procedure_name = fields.Field(
        column_name='procedure_name',
        attribute='procedure',
        widget=widgets.ForeignKeyWidget(Procedure, 'name')
    )
    examiner_a_username = fields.Field(
        column_name='examiner_a_username',
        attribute='examiner_a__username'
    )
    examiner_b_username = fields.Field(
        column_name='examiner_b_username',
        attribute='examiner_b__username'
    )
    
    class Meta:
        model = StudentProcedure
        fields = (
            'id', 'student_index', 'procedure_name', 
            'examiner_a_username', 'examiner_b_username', 
            'status', 'assessed_at'
        )
        export_order = (
            'id', 'student_index', 'procedure_name',
            'examiner_a_username', 'examiner_b_username',
            'status', 'assessed_at'
        )

# ============== ADMIN CLASSES ==============

@admin.register(Program)
class ProgramAdmin(ModelAdmin, ImportExportModelAdmin):
    import_form_class = ImportForm
    export_form_class = ExportForm
    list_display = ('name', 'abbreviation')
    search_fields = ('name', 'abbreviation')

@admin.register(Student)
class StudentAdmin(ModelAdmin, ImportExportModelAdmin):
    import_form_class = ImportForm
    export_form_class = ExportForm
    paginator = InfinitePaginator
    show_full_result_count = False
    resource_class = StudentResource
    list_display = ('index_number', 'full_name', 'program', 'level', 'is_active')
    list_filter = ('program', 'level', 'is_active')
    search_fields = ('index_number', 'full_name')
    ordering = ('level', 'index_number')

class ProcedureStepInline(admin.TabularInline):
    model = ProcedureStep
    extra = 1
    fields = ('step_order', 'description')
    ordering = ('step_order',)

@admin.register(Procedure)
class ProcedureAdmin(ModelAdmin, ImportExportModelAdmin):
    import_form_class = ImportForm
    export_form_class = ExportForm
    resource_class = ProcedureResource
    list_display = ('name', 'program', 'total_score', 'get_steps_count')
    list_filter = ('program',)
    search_fields = ('name',)
    inlines = [ProcedureStepInline]
    
    def get_steps_count(self, obj):
        return obj.steps.count()
    get_steps_count.short_description = 'Steps Count'

@admin.register(ProcedureStep)
class ProcedureStepAdmin(ModelAdmin, ImportExportModelAdmin):
    import_form_class = ImportForm
    export_form_class = ExportForm
    resource_class = ProcedureStepResource
    list_display = ('procedure', 'step_order', 'description_preview')
    list_filter = ('procedure',)
    ordering = ('procedure', 'step_order')
    
    def description_preview(self, obj):
        return obj.description[:50] + '...' if len(obj.description) > 50 else obj.description
    description_preview.short_description = 'Description'

@admin.register(StudentProcedure)
class StudentProcedureAdmin(ModelAdmin, ImportExportModelAdmin, ExportActionMixin):
    import_form_class = ImportForm
    export_form_class = ExportForm
    resource_class = StudentProcedureResource
    list_display = (
        'student', 'procedure', 'examiner_a', 'examiner_b', 
        'status', 'assigned_reconciler', 'reconciled_by', 'assessed_at'
    )
    list_filter = ('status', 'procedure', 'assessed_at')
    search_fields = (
        'student__index_number', 'student__full_name',
        'procedure__name'
    )
    date_hierarchy = 'assessed_at'
    readonly_fields = ('assigned_reconciler',)

@admin.register(ProcedureStepScore)
class ProcedureStepScoreAdmin(ModelAdmin):
    list_display = (
        'student_procedure', 'step', 'examiner', 'score', 'updated_at', 'is_reconciled'
    )
    list_filter = ('score', 'examiner', 'updated_at', 'is_reconciled')
    search_fields = (
        'student_procedure__student__index_number',
        'student_procedure__student__full_name',
        'step__description'
    )
    date_hierarchy = 'updated_at'

@admin.register(ReconciledScore)
class ReconciledScoreAdmin(ModelAdmin):
    list_display = (
        'student_procedure', 'step', 'score', 
        'reconciled_by', 'reconciled_at'
    )
    list_filter = ('reconciled_by', 'reconciled_at')
    search_fields = (
        'student_procedure__student__index_number',
        'student_procedure__student__full_name',
        'step__description'
    )
    date_hierarchy = 'reconciled_at'

# Care Plan Admin
@admin.register(CarePlan)
class CarePlanAdmin(ModelAdmin):
    list_display = ('student', 'program', 'examiner', 'score', 'max_score', 'assessed_at', 'is_locked')
    list_filter = ('program', 'is_locked', 'assessed_at')
    search_fields = ('student__index_number', 'student__full_name', 'examiner__username')
    date_hierarchy = 'assessed_at'
    readonly_fields = ('assessed_at',)
