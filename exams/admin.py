from django.contrib import admin
from import_export import resources, fields, widgets
from import_export.admin import ImportExportModelAdmin, ExportActionMixin
from .models import Program, Student, Procedure, ProcedureStep, StudentProcedure, ProcedureStepScore, ReconciledScore, CarePlan


class TenantAdminMixin:
    """Mixin to automatically filter by school in admin"""
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, 'school') and request.user.school:
            # Use all_objects to bypass tenant filtering, then filter manually
            if hasattr(self.model, 'all_objects'):
                return self.model.all_objects.filter(school=request.user.school)
            return qs.filter(school=request.user.school)
        return qs.none()
    
    def save_model(self, request, obj, form, change):
        """Auto-assign school to new objects"""
        if not change and hasattr(obj, 'school') and not obj.school_id:
            if hasattr(request.user, 'school'):
                obj.school = request.user.school
        super().save_model(request, obj, form, change)


# ============== RESOURCES ==============

class ProgramResource(resources.ModelResource):
    class Meta:
        model = Program
        fields = ('id', 'name', 'abbreviation', 'school__name')
        export_order = ('id', 'name', 'abbreviation', 'school__name')


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
        fields = ('id', 'index_number', 'full_name', 'program_name', 'level', 'level_display', 'is_active', 'school__name')
        export_order = ('id', 'index_number', 'full_name', 'program_name', 'level', 'level_display', 'is_active', 'school__name')
        import_id_fields = ['index_number', 'school']


class ProcedureResource(resources.ModelResource):
    program_name = fields.Field(
        column_name='program_name',
        attribute='program',
        widget=widgets.ForeignKeyWidget(Program, 'name')
    )
    
    class Meta:
        model = Procedure
        fields = ('id', 'program_name', 'name', 'total_score', 'school__name')
        export_order = ('id', 'program_name', 'name', 'total_score', 'school__name')


# ============== ADMIN CLASSES ==============

@admin.register(Program)
class ProgramAdmin(TenantAdminMixin, ImportExportModelAdmin):
    resource_class = ProgramResource
    list_display = ('name', 'abbreviation', 'school')
    list_filter = ('school',)
    search_fields = ('name', 'abbreviation', 'school__name')
    def get_queryset(self, request):
        return Program.all_objects.all()


@admin.register(Student)
class StudentAdmin(TenantAdminMixin, ImportExportModelAdmin):
    resource_class = StudentResource
    list_display = ('index_number', 'full_name', 'program', 'level', 'school', 'is_active')
    list_filter = ('school', 'program', 'level', 'is_active')
    search_fields = ('index_number', 'full_name', 'school__name')
    ordering = ('school', 'level', 'index_number')
    def get_queryset(self, request):
        return Student.all_objects.all()


class ProcedureStepInline(admin.TabularInline):
    model = ProcedureStep
    extra = 1
    fields = ('step_order', 'description')
    ordering = ('step_order',)


@admin.register(Procedure)
class ProcedureAdmin(TenantAdminMixin, ImportExportModelAdmin):
    resource_class = ProcedureResource
    list_display = ('name', 'program', 'school', 'total_score', 'get_steps_count')
    list_filter = ('school', 'program')
    search_fields = ('name', 'school__name')
    inlines = [ProcedureStepInline]

    def get_queryset(self, request):
        return Procedure.all_objects.all()
    
    def get_steps_count(self, obj):
        return obj.steps.count()
    get_steps_count.short_description = 'Steps Count'


@admin.register(ProcedureStep)
class ProcedureStepAdmin(admin.ModelAdmin):
    list_display = ('procedure', 'step_order', 'description_preview', 'get_school')
    list_filter = ('procedure__school', 'procedure')
    ordering = ('procedure__school', 'procedure', 'step_order')
    
    def description_preview(self, obj):
        return obj.description[:50] + '...' if len(obj.description) > 50 else obj.description
    description_preview.short_description = 'Description'

    def get_queryset(self, request):
        return ProcedureStep.all_objects.all()
    
    def get_school(self, obj):
        return obj.procedure.school
    get_school.short_description = 'School'


@admin.register(StudentProcedure)
class StudentProcedureAdmin(TenantAdminMixin, ImportExportModelAdmin, ExportActionMixin):
    list_display = (
        'student', 'procedure', 'school', 'examiner_a', 'examiner_b', 
        'status', 'assessed_at'
    )
    list_filter = ('school', 'status', 'procedure', 'assessed_at')
    search_fields = (
        'student__index_number', 'student__full_name',
        'procedure__name', 'school__name'
    )
    date_hierarchy = 'assessed_at'

    def get_queryset(self, request):
        return StudentProcedure.all_objects.all()


@admin.register(ProcedureStepScore)
class ProcedureStepScoreAdmin(admin.ModelAdmin):
    list_display = (
        'student_procedure', 'step', 'examiner', 'score', 
        'updated_at', 'is_reconciled', 'get_school'
    )
    list_filter = ('score', 'examiner', 'updated_at', 'is_reconciled')
    search_fields = (
        'student_procedure__student__index_number',
        'student_procedure__student__full_name',
        'step__description'
    )
    date_hierarchy = 'updated_at'

    def get_queryset(self, request):
        return ProcedureStepScore.all_objects.all()
    
    def get_school(self, obj):
        return obj.student_procedure.school
    get_school.short_description = 'School'


@admin.register(ReconciledScore)
class ReconciledScoreAdmin(admin.ModelAdmin):
    list_display = (
        'student_procedure', 'step', 'score', 
        'reconciled_by', 'reconciled_at', 'get_school'
    )
    list_filter = ('reconciled_by', 'reconciled_at')
    search_fields = (
        'student_procedure__student__index_number',
        'student_procedure__student__full_name',
        'step__description'
    )
    date_hierarchy = 'reconciled_at'

    def get_queryset(self, request):
        return ReconciledScore.all_objects.all()
    
    def get_school(self, obj):
        return obj.student_procedure.school
    get_school.short_description = 'School'


@admin.register(CarePlan)
class CarePlanAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ('student', 'program', 'school', 'examiner', 'score', 'max_score', 'assessed_at', 'is_locked')
    list_filter = ('school', 'program', 'is_locked', 'assessed_at')
    search_fields = ('student__index_number', 'student__full_name', 'examiner__username', 'school__name')
    date_hierarchy = 'assessed_at'
    readonly_fields = ('assessed_at',)

    def get_queryset(self, request):
        return CarePlan.all_objects.all()