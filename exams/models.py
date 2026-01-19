from django.db import models
from accounts.models import User
from django.db.models import Sum
from core.managers import TenantModel


class Program(TenantModel):
    name = models.CharField(max_length=100)
    abbreviation = models.CharField(max_length=20, null=True, blank=True)

    class Meta:
        unique_together = [['school', 'name']]
        ordering = ['name']
        indexes = [
            models.Index(fields=['school', 'name']),
        ]

    def __str__(self):
        return f"{self.name} ({self.school.name})"


class Student(TenantModel):
    LEVEL_CHOICES = [
        ('100', 'Level 100'),
        ('200', 'Level 200'),
        ('300', 'Level 300'),
        ('400', 'Level 400'),
    ]
    
    index_number = models.CharField(max_length=50)
    full_name = models.CharField(max_length=255)
    program = models.ForeignKey(Program, on_delete=models.PROTECT)
    level = models.CharField(max_length=3, choices=LEVEL_CHOICES, default='100')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["level", "index_number"]
        unique_together = [['school', 'index_number']]
        indexes = [
            models.Index(fields=['school', 'index_number']),
            models.Index(fields=['school', 'program']),
            models.Index(fields=['school', 'level']),
        ]

    def __str__(self):
        return f"{self.index_number} - {self.full_name}"


class Procedure(TenantModel):
    program = models.ForeignKey(Program, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    total_score = models.PositiveIntegerField()

    class Meta:
        unique_together = [['school', 'program', 'name']]
        indexes = [
            models.Index(fields=['school', 'program']),
        ]

    def __str__(self):
        return f"{self.name} ({self.program})"


class ProcedureStep(models.Model):
    """
    Note: ProcedureStep doesn't need school FK as it's already
    linked through Procedure which has school FK
    """
    procedure = models.ForeignKey(
        Procedure,
        on_delete=models.CASCADE,
        related_name="steps"
    )
    description = models.TextField()
    step_order = models.PositiveIntegerField()

    class Meta:
        ordering = ["step_order"]
        unique_together = [['procedure', 'step_order']]

    def __str__(self):
        return f"{self.procedure.name} - Step {self.step_order}"


class StudentProcedure(TenantModel):
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
    
    reconciled_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="reconciled_procedures",
        null=True,
        blank=True
    )
    reconciled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [['school', 'student', 'procedure']]
        indexes = [
            models.Index(fields=['school', 'status']),
            models.Index(fields=['school', 'student']),
        ]

    def __str__(self):
        return f"{self.student} - {self.procedure}"
    
    def get_total_reconciled_score(self):
        """Get total reconciled score for this procedure"""
        return self.reconciled_scores.aggregate(
            total=Sum('score')
        )['total'] or 0
    
    def get_reconciliation_percentage(self):
        """Get reconciliation percentage"""
        total = self.get_total_reconciled_score()
        max_score = self.procedure.total_score
        return (total / max_score * 100) if max_score > 0 else 0


class ProcedureStepScore(models.Model):
    """
    Note: Linked through StudentProcedure which has school FK
    """
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
    score = models.PositiveSmallIntegerField()  # 0-4
    
    is_reconciled = models.BooleanField(default=False)
    
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['student_procedure', 'step', 'examiner', 'is_reconciled']]

    def __str__(self):
        return f"{self.step} = {self.score}"


class ReconciledScore(models.Model):
    """Final reconciled scores - linked through StudentProcedure"""
    student_procedure = models.ForeignKey(
        StudentProcedure,
        on_delete=models.CASCADE,
        related_name="reconciled_scores"
    )
    step = models.ForeignKey(
        ProcedureStep,
        on_delete=models.CASCADE
    )
    score = models.PositiveSmallIntegerField()  # 0-4
    reconciled_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="scores_reconciled"
    )
    reconciled_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = [['student_procedure', 'step']]
        ordering = ['step__step_order']
    
    def __str__(self):
        return f"{self.student_procedure.student} - {self.step} = {self.score} (reconciled)"
    

class CarePlan(TenantModel):
    """Care Plan assessment - single examiner scoring"""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='care_plans')
    program = models.ForeignKey(Program, on_delete=models.CASCADE)
    examiner = models.ForeignKey(User, on_delete=models.PROTECT, related_name='care_plan_assessments')
    score = models.PositiveSmallIntegerField()  # 0-20
    max_score = models.PositiveIntegerField(default=20)
    comments = models.TextField(blank=True, null=True)
    assessed_at = models.DateTimeField(auto_now_add=True)
    is_locked = models.BooleanField(default=True)
    
    class Meta:
        unique_together = [['school', 'student', 'program']]
        ordering = ['-assessed_at']
        indexes = [
            models.Index(fields=['school', 'student']),
        ]
    
    def __str__(self):
        return f"{self.student} - Care Plan ({self.score}/{self.max_score})"
    
    def get_percentage(self):
        return (self.score / self.max_score * 100) if self.max_score > 0 else 0