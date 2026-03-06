from django.db import models
from django.db.models import Sum
from accounts.models import User


class Program(models.Model):
    name = models.CharField(max_length=100, unique=True)
    abbreviation = models.CharField(max_length=20, unique=True, null=True, blank=True)

    def __str__(self):
        return self.name

class Student(models.Model):
    LEVEL_CHOICES = [
        ('100', 'Level 100'),
        ('200', 'Level 200'),
        ('300', 'Level 300'),
        ('400', 'Level 400'),
    ]
    
    index_number = models.CharField(max_length=50, unique=True, db_index=True)
    full_name = models.CharField(max_length=255, db_index=True)
    program = models.ForeignKey(Program, on_delete=models.PROTECT, db_index=True)
    level = models.CharField(max_length=3, choices=LEVEL_CHOICES, default='100', db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["level", "index_number"]

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

    student = models.ForeignKey(Student, on_delete=models.CASCADE, db_index=True)
    procedure = models.ForeignKey(Procedure, on_delete=models.CASCADE, db_index=True)

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
        default="pending",
        db_index=True
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
    
    assigned_reconciler = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="assigned_reconciliations",
        null=True,
        blank=True,
        help_text="The examiner assigned to perform reconciliation (locked once set)"
    )

    class Meta:
        unique_together = ("student", "procedure")

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
    
    def get_last_scoring_examiner(self):
        """
        Returns the examiner who completed scoring last, or None if scoring incomplete.
        Only returns an examiner if BOTH examiners have completed all steps.
        """
        if self.examiner_a == self.examiner_b:
            return None
            
        total_steps = self.procedure.steps.count()
        
        # Check if both examiners completed all steps
        examiner_a_scores = self.step_scores.filter(examiner=self.examiner_a).count()
        examiner_b_scores = self.step_scores.filter(examiner=self.examiner_b).count()
        
        if examiner_a_scores != total_steps or examiner_b_scores != total_steps:
            return None
        
        # Get the most recent score update for each examiner
        examiner_a_last_update = self.step_scores.filter(
            examiner=self.examiner_a
        ).order_by('-updated_at').first()
        
        examiner_b_last_update = self.step_scores.filter(
            examiner=self.examiner_b
        ).order_by('-updated_at').first()
        
        if not examiner_a_last_update or not examiner_b_last_update:
            return None
        
        # Return the examiner who updated last
        if examiner_a_last_update.updated_at > examiner_b_last_update.updated_at:
            return self.examiner_a
        else:
            return self.examiner_b
    
    def can_user_reconcile(self, user):
        """
        Check if a user can reconcile this procedure.
        Once assigned_reconciler is set, only that user can reconcile.
        """
        if self.status != 'scored':
            return False
        
        # If reconciler already assigned, only that user can reconcile
        if self.assigned_reconciler:
            return self.assigned_reconciler == user
        
        # If not assigned yet, check if user is the last examiner to complete
        last_examiner = self.get_last_scoring_examiner()
        return last_examiner == user
    
    def is_user_assigned_examiner(self, user):
        """Check if user is one of the assigned examiners"""
        return user in [self.examiner_a, self.examiner_b]

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
    score = models.PositiveSmallIntegerField()  # 0-4
    
    is_reconciled = models.BooleanField(default=False)
    
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("student_procedure", "step", "examiner", "is_reconciled")

    def __str__(self):
        return f"{self.step} = {self.score}"

class ReconciledScore(models.Model):
    """Final reconciled scores - separate from examiner scores"""
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
        unique_together = ("student_procedure", "step")
        ordering = ['step__step_order']
    
    def __str__(self):
        return f"{self.student_procedure.student} - {self.step} = {self.score} (reconciled)"
    
class CarePlan(models.Model):
    """Care Plan assessment - single examiner scoring"""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='care_plans', db_index=True)
    program = models.ForeignKey(Program, on_delete=models.CASCADE, db_index=True)
    examiner = models.ForeignKey(User, on_delete=models.PROTECT, related_name='care_plan_assessments')
    score = models.PositiveSmallIntegerField()  # 0-20
    max_score = models.PositiveIntegerField(default=20)
    comments = models.TextField(blank=True, null=True)
    assessed_at = models.DateTimeField(auto_now_add=True)
    is_locked = models.BooleanField(default=True)  # Locked after submission
    
    class Meta:
        unique_together = ('student', 'program')
        ordering = ['-assessed_at']
    
    def __str__(self):
        return f"{self.student} - Care Plan ({self.score}/{self.max_score})"
    
    def get_percentage(self):
        return (self.score / self.max_score * 100) if self.max_score > 0 else 0
