from django.db import models
from accounts.models import User


class Program(models.Model):
    name = models.CharField(max_length=100, unique=True)
    abbreviation = models.CharField(max_length=20, unique=True, null=True, blank=True)

    def __str__(self):
        return self.name


class Student(models.Model):
    index_number = models.CharField(max_length=50, unique=True)
    full_name = models.CharField(max_length=255)
    program = models.ForeignKey(Program, on_delete=models.PROTECT)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["index_number"]

    def __str__(self):
        return f"{self.index_number} - {self.full_name}"


class Procedure(models.Model):
    program = models.ForeignKey(Program, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    total_score = models.PositiveIntegerField()

    class Meta:
        unique_together = ("program", "name")

    def __str__(self):
        return f"{self.name} ({self.program})"


class ProcedureStep(models.Model):
    procedure = models.ForeignKey(
        Procedure,
        on_delete=models.CASCADE,
        related_name="steps"
    )
    description = models.TextField()
    # max_score = models.PositiveIntegerField()
    step_order = models.PositiveIntegerField()

    class Meta:
        ordering = ["step_order"]
        unique_together = ("procedure", "step_order")

    def __str__(self):
        return f"{self.procedure.name} - Step {self.step_order}"


class StudentProcedure(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("scored", "Scored"),
        ("reconciled", "Reconciled"),
    )

    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    procedure = models.ForeignKey(Procedure, on_delete=models.CASCADE)

    examiner_a = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="examiner_a_assignments"
    )
    examiner_b = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="examiner_b_assignments"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )

    assessed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("student", "procedure")

    def __str__(self):
        return f"{self.student} - {self.procedure}"


class ProcedureStepScore(models.Model):
    student_procedure = models.ForeignKey(
        "StudentProcedure",
        on_delete=models.CASCADE,
        related_name="step_scores"
    )
    step = models.ForeignKey(
        ProcedureStep,
        on_delete=models.CASCADE
    )
    examiner = models.ForeignKey(
        User,
        on_delete=models.PROTECT
    )
    score = models.PositiveSmallIntegerField()  # 0–4
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("student_procedure", "step", "examiner")

    def __str__(self):
        return f"{self.step} = {self.score}"
