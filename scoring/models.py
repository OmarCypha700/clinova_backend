from django.db import models
from accounts.models import User
from exams.models import StudentProcedure, ProcedureStep


class Score(models.Model):
    SCORE_TYPE_CHOICES = (
        ("examiner", "Examiner"),
        ("reconciled", "Reconciled"),
    )

    student_procedure = models.ForeignKey(
        StudentProcedure,
        on_delete=models.CASCADE,
        related_name="scores"
    )

    procedure_step = models.ForeignKey(
        ProcedureStep,
        on_delete=models.CASCADE
    )

    examiner = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT
    )

    score = models.PositiveIntegerField()
    remark = models.TextField(blank=True)

    score_type = models.CharField(
        max_length=20,
        choices=SCORE_TYPE_CHOICES
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (
            "student_procedure",
            "procedure_step",
            "examiner",
            "score_type",
        )

    def __str__(self):
        return (
            f"{self.student_procedure} | "
            f"{self.procedure_step} | "
            f"{self.score_type}"
        )
