from django.core.validators import MaxValueValidator
from django.db import models
from django.db.models import Sum

from accounts.models import User


class Program(models.Model):
    name = models.CharField(max_length=100, unique=True)
    abbreviation = models.CharField(max_length=20, unique=True, null=True, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.name


class Level(models.Model):
    number = models.PositiveSmallIntegerField(unique=True, blank=True, null=True)
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        ordering = ["number"]

    def __str__(self):
        return self.name


class Student(models.Model):
    index_number = models.CharField(max_length=50, unique=True, db_index=True)
    full_name = models.CharField(max_length=255, db_index=True)
    program = models.ForeignKey(Program, on_delete=models.PROTECT, related_name="students", db_index=True)
    level = models.ForeignKey(
        Level, on_delete=models.PROTECT, related_name="students", db_index=True
    )
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["level", "index_number"]
        indexes = [
            models.Index(fields=["program", "level", "is_active"]),
        ]

    def __str__(self):
        return f"{self.index_number} - {self.full_name} ({self.level})"


class Category(models.Model):
    """
    Procedure grouping (e.g. "Basic Nursing Procedures", "Midwifery-Specific
    Procedures"). Global/shared across programs — the same category can be
    reused by procedures in RGN, RM, PHN, NAP, etc.
    """

    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name


class Procedure(models.Model):
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name="procedures")
    name = models.CharField(max_length=255)
    total_score = models.PositiveIntegerField()
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="procedures",
    )

    class Meta:
        unique_together = ("program", "name")
        ordering = ['id']

    def __str__(self):
        return f"{self.name} ({self.program})"


class ProcedureStep(models.Model):
    procedure = models.ForeignKey(
        Procedure, on_delete=models.CASCADE, related_name="steps"
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
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="examiner_a_assignments",
    )
    examiner_b = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="examiner_b_assignments",
    )

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True
    )

    assessed_at = models.DateTimeField(auto_now_add=True)

    reconciled_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="reconciled_procedures",
        null=True,
        blank=True,
    )
    reconciled_at = models.DateTimeField(null=True, blank=True)

    assigned_reconciler = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="assigned_reconciliations",
        null=True,
        blank=True,
        help_text="The examiner assigned to perform reconciliation (locked once set)",
    )

    class Meta:
        unique_together = ("student", "procedure")
        indexes = [
            models.Index(fields=["student", "status"]),
        ]

    def __str__(self):
        return f"{self.student} - {self.procedure}"

    def get_total_reconciled_score(self):
        """Get total reconciled score for this procedure"""
        return self.reconciled_scores.aggregate(total=Sum("score"))["total"] or 0

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
        examiner_a_last_update = (
            self.step_scores.filter(examiner=self.examiner_a)
            .order_by("-updated_at")
            .first()
        )

        examiner_b_last_update = (
            self.step_scores.filter(examiner=self.examiner_b)
            .order_by("-updated_at")
            .first()
        )

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
        if self.status != "scored":
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
        "StudentProcedure", on_delete=models.CASCADE, related_name="step_scores"
    )
    step = models.ForeignKey(ProcedureStep, on_delete=models.CASCADE)
    examiner = models.ForeignKey(User, on_delete=models.PROTECT)
    score = models.PositiveSmallIntegerField(validators=[MaxValueValidator(4)])  # 0-4

    is_reconciled = models.BooleanField(default=False)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("student_procedure", "step", "examiner", "is_reconciled")
        indexes = [
            models.Index(fields=["step", "student_procedure", "examiner"]),
        ]

    def __str__(self):
        return f"{self.step} = {self.score}"


class ReconciledScore(models.Model):
    """Final reconciled scores - separate from examiner scores"""

    student_procedure = models.ForeignKey(
        StudentProcedure, on_delete=models.CASCADE, related_name="reconciled_scores"
    )
    step = models.ForeignKey(ProcedureStep, on_delete=models.CASCADE)
    score = models.PositiveSmallIntegerField()  # 0-4
    reconciled_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="scores_reconciled"
    )
    reconciled_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("student_procedure", "step")
        ordering = ["step__step_order"]
        indexes = [
            models.Index(fields=["student_procedure"]),
        ]

    def __str__(self):
        return f"{self.student_procedure.student} - {self.step} = {self.score} (reconciled)"


class CarePlan(models.Model):
    """Care Plan assessment - single examiner scoring"""

    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="care_plans", db_index=True
    )
    program = models.ForeignKey(Program, on_delete=models.CASCADE, db_index=True)
    examiner = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="care_plan_assessments"
    )
    score = models.PositiveSmallIntegerField(validators=[MaxValueValidator(20)])  # 0-20
    max_score = models.PositiveIntegerField(default=20)
    comments = models.TextField(blank=True, null=True)
    assessed_at = models.DateTimeField(auto_now_add=True)
    is_locked = models.BooleanField(default=True)  # Locked after submission

    class Meta:
        unique_together = ("student", "program")
        ordering = ["-assessed_at"]

    def __str__(self):
        return f"{self.student} - Care Plan ({self.score}/{self.max_score})"

    def get_percentage(self):
        return (self.score / self.max_score * 100) if self.max_score > 0 else 0


# ─────────────────────────────────────────────────────────────────────────────
# SITE SETTINGS
# ─────────────────────────────────────────────────────────────────────────────


class SiteSettings(models.Model):
    """
    Application-wide feature flags and configuration.
    Only one row ever exists (pk=1). Use SiteSettings.get() everywhere.
    """

    # ── Care Plan ─────────────────────────────────────────────────────────────
    care_plan_lock_on_submit = models.BooleanField(
        default=True,
        verbose_name="Lock care plan after submission",
        help_text=(
            "When ON (default): a care plan is locked immediately after an "
            "examiner submits it and cannot be changed. "
            "When OFF: any examiner can overwrite a previously submitted care "
            "plan score."
        ),
    )

    # ── Placeholder for future flags ──────────────────────────────────────────
    # allow_examiner_reassignment = models.BooleanField(default=False, ...)
    # reconciliation_required     = models.BooleanField(default=True,  ...)

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="settings_updates",
    )

    class Meta:
        verbose_name = "Site Settings"
        verbose_name_plural = "Site Settings"

    def __str__(self):
        return "Site Settings"

    # Enforce singleton: always save to pk=1
    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass  # settings row must not be deleted

    @classmethod
    def get(cls):
        """Return the single settings instance, creating it with defaults if needed."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
