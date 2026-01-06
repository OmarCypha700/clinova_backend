# from django.contrib import admin
# from .models import Program, Student, Procedure, ProcedureStep, StudentProcedure

# # ----------------------------
# # Program
# # ----------------------------
# @admin.register(Program)
# class ProgramAdmin(admin.ModelAdmin):
#     list_display = ("id", "name", "abbreviation")
#     search_fields = ("name", "abbreviation")

# # ----------------------------
# # Student
# # ----------------------------
# @admin.register(Student)
# class StudentAdmin(admin.ModelAdmin):
#     list_display = ("index_number", "full_name", "program", "is_active")
#     list_filter = ("program", "is_active")
#     search_fields = ("index_number", "full_name")

# # ----------------------------
# # ProcedureStep inline for Procedure
# # ----------------------------
# class ProcedureStepInline(admin.TabularInline):
#     model = ProcedureStep
#     extra = 1

# # ----------------------------
# # Procedure
# # ----------------------------
# @admin.register(Procedure)
# class ProcedureAdmin(admin.ModelAdmin):
#     list_display = ("name", "program", "total_score")
#     list_filter = ("program",)
#     inlines = [ProcedureStepInline]

# # ----------------------------
# # StudentProcedure
# # ----------------------------
# @admin.register(StudentProcedure)
# class StudentProcedureAdmin(admin.ModelAdmin):
#     list_display = ("student", "procedure", "examiner_a", "examiner_b", "status", "assessed_at")
#     list_filter = ("procedure", "status")
#     search_fields = ("student__full_name", "student__index_number")


from django.contrib import admin
from import_export import resources, fields, widgets
from import_export.admin import ImportExportModelAdmin, ExportActionMixin
from accounts.models import User
from .models import Program, Student, Procedure, ProcedureStep, StudentProcedure, ProcedureStepScore
from import_export.admin import ImportExportModelAdmin

# # Monkey patch to fix Django 5.x compatibility
# from import_export import admin as import_export_admin

# original_create_log_entry = import_export_admin.ImportMixin._create_log_entry

# def patched_create_log_entry(self, request, obj, object_id, object_repr, change_message=""):
#     from django.contrib.admin.models import LogEntry
#     from django.contrib.contenttypes.models import ContentType
    
#     # Remove the 'single_object' parameter that Django 5.x doesn't accept
#     return LogEntry.objects.log_action(
#         user_id=request.user.pk,
#         content_type_id=ContentType.objects.get_for_model(obj).pk,
#         object_id=object_id,
#         object_repr=object_repr,
#         # action_flag=action_flag,
#         change_message=change_message,
#     )

# import_export_admin.ImportMixin._create_log_entry = patched_create_log_entry


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
    
    class Meta:
        model = Student
        fields = ('id', 'index_number', 'full_name', 'program_name', 'is_active')
        export_order = ('id', 'index_number', 'full_name', 'program_name', 'is_active')
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
        import_id_fields = ['program', 'name']


class ProcedureStepResource(resources.ModelResource):
    procedure_name = fields.Field(
        column_name='procedure_name',
        attribute='procedure',
        widget=widgets.ForeignKeyWidget(Procedure, 'name')
    )
    
    class Meta:
        model = ProcedureStep
        fields = ('id', 'procedure_name', 'description', 'step_order')
        export_order = ('id', 'procedure_name', 'description', 'step_order')


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
class ProgramAdmin(ImportExportModelAdmin):
    resource_class = ProgramResource
    list_display = ('name', 'abbreviation')
    search_fields = ('name', 'abbreviation')

    # Disable logging to avoid Django 5.x incompatibility
    def log_addition(self, request, object, message):
        pass
    
    def log_change(self, request, object, message):
        pass
    
    def log_deletion(self, request, object, object_repr):
        pass


@admin.register(Student)
class StudentAdmin(ImportExportModelAdmin):
    resource_class = StudentResource
    list_display = ('index_number', 'full_name', 'program', 'is_active')
    list_filter = ('program', 'is_active')
    search_fields = ('index_number', 'full_name')

    # Disable logging to avoid Django 5.x incompatibility
    def log_addition(self, request, object, message):
        pass
    
    def log_change(self, request, object, message):
        pass
    
    def log_deletion(self, request, object, object_repr):
        pass


class ProcedureStepInline(admin.TabularInline):
    model = ProcedureStep
    extra = 1
    fields = ('step_order', 'description')
    ordering = ('step_order',)


@admin.register(Procedure)
class ProcedureAdmin(ImportExportModelAdmin):
    resource_class = ProcedureResource
    list_display = ('name', 'program', 'total_score', 'get_steps_count')
    list_filter = ('program',)
    search_fields = ('name',)
    inlines = [ProcedureStepInline]
    
    def get_steps_count(self, obj):
        return obj.steps.count()
    get_steps_count.short_description = 'Steps Count'

    # Disable logging to avoid Django 5.x incompatibility
    def log_addition(self, request, object, message):
        pass
    
    def log_change(self, request, object, message):
        pass
    
    def log_deletion(self, request, object, object_repr):
        pass


@admin.register(ProcedureStep)
class ProcedureStepAdmin(ImportExportModelAdmin):
    resource_class = ProcedureStepResource
    list_display = ('procedure', 'step_order', 'description_preview')
    list_filter = ('procedure',)
    ordering = ('procedure', 'step_order')
    
    def description_preview(self, obj):
        return obj.description[:50] + '...' if len(obj.description) > 50 else obj.description
    description_preview.short_description = 'Description'

    # Disable logging to avoid Django 5.x incompatibility
    def log_addition(self, request, object, message):
        pass
    
    def log_change(self, request, object, message):
        pass
    
    def log_deletion(self, request, object, object_repr):
        pass


@admin.register(StudentProcedure)
class StudentProcedureAdmin(ImportExportModelAdmin, ExportActionMixin):
    resource_class = StudentProcedureResource
    list_display = (
        'student', 'procedure', 'examiner_a', 'examiner_b', 
        'status', 'assessed_at'
    )
    list_filter = ('status', 'procedure', 'assessed_at')
    search_fields = (
        'student__index_number', 'student__full_name',
        'procedure__name'
    )
    date_hierarchy = 'assessed_at'

    # Disable logging to avoid Django 5.x incompatibility
    def log_addition(self, request, object, message):
        pass
    
    def log_change(self, request, object, message):
        pass
    
    def log_deletion(self, request, object, object_repr):
        pass


@admin.register(ProcedureStepScore)
class ProcedureStepScoreAdmin(admin.ModelAdmin):
    list_display = (
        'student_procedure', 'step', 'examiner', 'score', 'updated_at'
    )
    list_filter = ('score', 'examiner', 'updated_at')
    search_fields = (
        'student_procedure__student__index_number',
        'student_procedure__student__full_name',
        'step__description'
    )
    date_hierarchy = 'updated_at'