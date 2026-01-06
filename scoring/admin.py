from django.contrib import admin
from .models import Score

@admin.register(Score)
class ScoreAdmin(admin.ModelAdmin):
    list_display = ("student_procedure", "procedure_step", "examiner", "score", "score_type", "created_at")
    list_filter = ("score_type", "created_at")
    search_fields = (
        "student_procedure__student__full_name",
        "student_procedure__procedure__name",
        "procedure_step__description",
        "examiner__username"
    )
