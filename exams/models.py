from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Sum
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

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


# Every step is scored 0–4, so a procedure's maximum is its step count × 4.
POINTS_PER_STEP = 4


class Procedure(models.Model):
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name="procedures")
    name = models.CharField(max_length=255)
    # Derived, never entered: kept equal to steps × POINTS_PER_STEP by the
    # ProcedureStep signals below. Stored (not computed on read) because grade
    # and export queries sum it in the database.
    total_score = models.PositiveIntegerField(default=0, editable=False)
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

    def save(self, *args, **kwargs):
        # Never write back a stale total held in memory: an existing procedure
        # always saves the total its steps add up to right now.
        if self.pk:
            self.total_score = self.steps.count() * POINTS_PER_STEP
        super().save(*args, **kwargs)


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


def recalculate_total_score(procedure_id):
    """Set a procedure's total_score from its current number of steps."""
    count = ProcedureStep.objects.filter(procedure_id=procedure_id).count()
    # update() rather than save(): no signals, and harmless if the procedure
    # is itself being deleted (the cascade deletes its steps first).
    Procedure.objects.filter(pk=procedure_id).update(total_score=count * POINTS_PER_STEP)


# Keep total_score in step with the steps however they change: admin screens,
# spreadsheet imports, the Django admin and management commands all go
# through save()/delete(). (bulk_create/update would bypass these; call
# recalculate_total_score() yourself if you ever use them on steps.)
@receiver(pre_save, sender=ProcedureStep)
def _remember_previous_procedure(sender, instance, **kwargs):
    instance._previous_procedure_id = (
        sender.objects.filter(pk=instance.pk).values_list("procedure_id", flat=True).first()
        if instance.pk
        else None
    )


@receiver(post_save, sender=ProcedureStep)
def _step_saved(sender, instance, **kwargs):
    recalculate_total_score(instance.procedure_id)
    previous = getattr(instance, "_previous_procedure_id", None)
    if previous and previous != instance.procedure_id:  # step moved
        recalculate_total_score(previous)


@receiver(post_delete, sender=ProcedureStep)
def _step_deleted(sender, instance, **kwargs):
    recalculate_total_score(instance.procedure_id)


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
            models.Index(fields=["-assessed_at"], name="sp_assessed_at_desc"),
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


CARE_PLAN_MAX_SCORE = 20
CARE_PLAN_MAX_SLOTS = 2


class CarePlan(models.Model):
    """Care Plan assessment - single examiner scoring.

    A student normally has one care plan per program (slot 1). When enabled in
    SiteSettings for the student's program/level, a second one (slot 2) may be added.
    """

    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="care_plans", db_index=True
    )
    program = models.ForeignKey(Program, on_delete=models.CASCADE, db_index=True)
    examiner = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="care_plan_assessments"
    )
    slot = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(CARE_PLAN_MAX_SLOTS)],
    )
    score = models.PositiveSmallIntegerField(
        validators=[MaxValueValidator(CARE_PLAN_MAX_SCORE)]
    )  # 0-20
    max_score = models.PositiveIntegerField(default=CARE_PLAN_MAX_SCORE)
    comments = models.TextField(blank=True, null=True)
    assessed_at = models.DateTimeField(auto_now_add=True)
    is_locked = models.BooleanField(default=True)  # Locked after submission

    class Meta:
        unique_together = ("student", "program", "slot")
        ordering = ["slot", "-assessed_at"]

    def __str__(self):
        return f"{self.student} - Care Plan {self.slot} ({self.score}/{self.max_score})"

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

    multiple_care_plans_enabled = models.BooleanField(
        default=False,
        verbose_name="Allow a second care plan",
        help_text=(
            "When ON: examiners may add a second care plan for eligible students "
            "(see Care Plan Eligibility). If no eligibility rows exist, all "
            "programs and levels are eligible."
        ),
    )

    # ── Institution branding ──────────────────────────────────────────────────
    # Shown on the login page, browser title, installed-app name and admin header.
    institution_name = models.CharField(
        max_length=150,
        blank=True,
        default="",
        help_text="Full institution name, e.g. 'Nursing and Midwifery Training College, Tanoso'.",
    )
    short_name = models.CharField(
        max_length=30,
        blank=True,
        default="",
        help_text="Short name or code, e.g. 'CNMT'. Used where space is tight.",
    )
    brand_color = models.CharField(
        max_length=7,
        blank=True,
        default="",
        validators=[RegexValidator(r"^#[0-9a-fA-F]{6}$", "Use a hex colour such as #0b3b6f.")],
        help_text="Accent colour for buttons, selected navigation and badges. Blank uses the ClinOva default.",
    )
    # The logo lives in the database (not on disk) so it survives redeploys on
    # hosts with ephemeral storage and is included in database backups. It is
    # always a re-encoded PNG produced by exams.branding.process_logo().
    logo = models.BinaryField(null=True, blank=True, editable=False)
    logo_content_type = models.CharField(max_length=50, blank=True, default="", editable=False)
    logo_updated_at = models.DateTimeField(null=True, blank=True, editable=False)

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

    def allows_second_care_plan(self, student):
        """True if a second care plan may be added for this student."""
        if not self.multiple_care_plans_enabled:
            return False
        rules = CarePlanEligibility.objects.all()
        if not rules.exists():
            return True
        return rules.filter(program_id=student.program_id).filter(
            models.Q(level__isnull=True) | models.Q(level_id=student.level_id)
        ).exists()


class CarePlanEligibility(models.Model):
    """Program/level combinations allowed a second care plan. level=None means all levels."""

    program = models.ForeignKey(
        Program, on_delete=models.CASCADE, related_name="care_plan_eligibility"
    )
    level = models.ForeignKey(
        Level,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="care_plan_eligibility",
    )

    class Meta:
        unique_together = ("program", "level")
        ordering = ["program_id", "level_id"]
        verbose_name_plural = "Care Plan Eligibility"

    def __str__(self):
        return f"{self.program} - {self.level or 'All levels'}"
