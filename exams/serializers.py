from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import (
    CarePlan, Level, Procedure, ProcedureStep, ProcedureStepScore,
    Program, ReconciledScore, SiteSettings, Student, StudentProcedure,
)

User = get_user_model()


# ─────────────────────────────────────────────
# SITE SETTINGS
# ─────────────────────────────────────────────

class SiteSettingsSerializer(serializers.ModelSerializer):
    updated_by_name = serializers.SerializerMethodField()
 
    class Meta:
        model = SiteSettings
        fields = [
            "care_plan_lock_on_submit",
            "updated_at",
            "updated_by_name",
        ]
        read_only_fields = ["updated_at", "updated_by_name"]
 
    def get_updated_by_name(self, obj):
        if obj.updated_by:
            name = obj.updated_by.get_full_name()
            return name if name.strip() else obj.updated_by.username
        return None


# ─────────────────────────────────────────────
# MIXINS
# ─────────────────────────────────────────────

class StudentProcedureMixin:
    """
    Resolves StudentProcedure for a given Procedure object.

    Prefers a pre-built lookup map (student_procedures_map) injected via
    serializer context, which avoids per-object DB queries (N+1 prevention).
    Falls back to a single DB query only when the map is absent.
    """

    def _get_student_procedure(self, obj):
        # Fast path: use pre-fetched map from context
        sp_map = self.context.get("student_procedures_map")
        if sp_map is not None:
            return sp_map.get(obj.id)

        # Slow path: single DB hit per procedure (only when map not provided)
        student_id = self.context.get("student_id")
        if not student_id:
            return None

        cache = getattr(self, "_sp_cache", {})
        if obj.id not in cache:
            cache[obj.id] = (
                StudentProcedure.objects
                .select_related("examiner_a", "examiner_b", "assigned_reconciler")
                .filter(student_id=student_id, procedure=obj)
                .first()
            )
            self._sp_cache = cache

        return cache[obj.id]


# ─────────────────────────────────────────────
# USER / DASHBOARD
# ─────────────────────────────────────────────

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name",
            "role", "is_active", "date_joined",
        ]
        read_only_fields = ["date_joined"]


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True, required=True, style={"input_type": "password"}
    )

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name", "role", "password"]

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class DashboardStatsSerializer(serializers.Serializer):
    total_students = serializers.IntegerField()
    active_students = serializers.IntegerField()
    total_examiners = serializers.IntegerField()
    total_procedures = serializers.IntegerField()
    pending_assessments = serializers.IntegerField()
    scored_assessments = serializers.IntegerField()
    reconciled_assessments = serializers.IntegerField()
    total_programs = serializers.IntegerField()


# ─────────────────────────────────────────────
# LEVEL
# ─────────────────────────────────────────────

class LevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Level
        fields = "__all__"


# ─────────────────────────────────────────────
# PROGRAM
# ─────────────────────────────────────────────

class ProgramSerializer(serializers.ModelSerializer):
    class Meta:
        model = Program
        fields = ["id", "name", "abbreviation"]


# ─────────────────────────────────────────────
# STUDENT
# ─────────────────────────────────────────────

class StudentSerializer(serializers.ModelSerializer):
    program = ProgramSerializer(read_only=True)
    level_name = serializers.CharField(source="level.name", read_only=True)

    class Meta:
        model = Student
        fields = ["id", "index_number", "full_name", "program", "level", "level_name", "is_active"]


class StudentCreateUpdateSerializer(serializers.ModelSerializer):
    program_id = serializers.PrimaryKeyRelatedField(
        queryset=Program.objects.all(),
        source="program",
        write_only=True,
    )
    level_name = serializers.CharField(source="level.name", read_only=True)

    class Meta:
        model = Student
        fields = ["id", "index_number", "full_name", "program_id", "level", "level_name", "is_active"]


# ─────────────────────────────────────────────
# PROCEDURE (Admin)
# ─────────────────────────────────────────────

class ProcedureCreateUpdateSerializer(serializers.ModelSerializer):
    program_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = Procedure
        fields = ["id", "name", "program_id", "total_score"]

    def create(self, validated_data):
        program_id = validated_data.pop("program_id")
        validated_data["program_id"] = program_id
        return Procedure.objects.create(**validated_data)


class ProcedureAdminListSerializer(serializers.ModelSerializer):
    program = serializers.CharField(source="program.name", read_only=True)
    program_id = serializers.IntegerField(source="program.id", read_only=True)
    # Expects queryset annotated with step_count=Count("steps")
    step_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Procedure
        fields = ["id", "name", "program", "program_id", "total_score", "step_count"]


class ProcedureStepCreateUpdateSerializer(serializers.ModelSerializer):
    procedure_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = ProcedureStep
        fields = ["id", "procedure_id", "description", "step_order"]


# ─────────────────────────────────────────────
# PROCEDURE STEP (Examiner)
# ─────────────────────────────────────────────

class ProcedureStepSerializer(serializers.ModelSerializer):
    score = serializers.SerializerMethodField()

    class Meta:
        model = ProcedureStep
        fields = ["id", "description", "score"]

    def get_score(self, step):
        request = self.context.get("request")
        sp = self.context.get("student_procedure")
        if not request or not sp:
            return None
        score_obj = sp.step_scores.filter(step=step, examiner=request.user).first()
        return score_obj.score if score_obj else None


class ProcedureStepScoreSerializer(serializers.ModelSerializer):
    step = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = ProcedureStepScore
        fields = ["step", "score"]


# ─────────────────────────────────────────────
# PROCEDURE LIST (Examiner view – per student)
# ─────────────────────────────────────────────

class ProcedureListSerializer(StudentProcedureMixin, serializers.ModelSerializer):
    program_name = serializers.CharField(source="program.name", read_only=True)
    program_abbreviation = serializers.CharField(source="program.abbreviation", read_only=True)
    program_id = serializers.IntegerField(source="program.id", read_only=True)
    # Expects queryset annotated with step_count=Count("steps")
    step_count = serializers.IntegerField(read_only=True)
    status = serializers.SerializerMethodField()
    can_reconcile = serializers.SerializerMethodField()
    display_status = serializers.SerializerMethodField()

    class Meta:
        model = Procedure
        fields = [
            "id", "name", "total_score", "program_id", "program_name",
            "program_abbreviation", "status", "step_count",
            "can_reconcile", "display_status",
        ]

    def get_status(self, obj):
        sp = self._get_student_procedure(obj)
        if not sp or sp.examiner_a == sp.examiner_b:
            return "pending"
        return sp.status

    def get_can_reconcile(self, obj):
        request = self.context.get("request")
        if not request:
            return False
        sp = self._get_student_procedure(obj)
        if not sp or sp.status != "scored":
            return False
        return sp.can_user_reconcile(request.user)

    def get_display_status(self, obj):
        request = self.context.get("request")
        sp = self._get_student_procedure(obj)
        if not sp or not request:
            return "pending"
        if sp.examiner_a == sp.examiner_b:
            return "pending"
        if sp.status == "reconciled":
            return "reconciled"
        if sp.status == "scored":
            return "ready_to_reconcile" if sp.can_user_reconcile(request.user) else "scored"
        return "pending"


# ─────────────────────────────────────────────
# RECONCILIATION
# ─────────────────────────────────────────────

class ReconciledScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReconciledScore
        fields = ["step", "score", "reconciled_by", "reconciled_at"]


class ReconciliationSerializer(serializers.ModelSerializer):
    steps = serializers.SerializerMethodField()
    student = StudentSerializer(read_only=True)
    examiner_a_name = serializers.CharField(source="examiner_a.get_full_name", read_only=True)
    examiner_b_name = serializers.CharField(source="examiner_b.get_full_name", read_only=True)
    reconciled_by_name = serializers.SerializerMethodField()
    is_already_reconciled = serializers.SerializerMethodField()
    can_user_reconcile = serializers.SerializerMethodField()

    class Meta:
        model = StudentProcedure
        fields = [
            "id", "student", "procedure", "status",
            "examiner_a_name", "examiner_b_name",
            "reconciled_by_name", "reconciled_at",
            "is_already_reconciled", "can_user_reconcile", "steps",
        ]

    def get_reconciled_by_name(self, obj):
        return obj.reconciled_by.get_full_name() if obj.reconciled_by else None

    def get_is_already_reconciled(self, obj):
        return obj.status == "reconciled"

    def get_can_user_reconcile(self, obj):
        request = self.context.get("request")
        if not request:
            return False
        return obj.get_last_scoring_examiner() == request.user

    def get_steps(self, obj):
        """
        Build step data from prefetched relations – O(1) DB hits when the view
        prefetches step_scores and reconciled_scores.
        """
        # Build lookup maps from prefetched data (no extra queries)
        score_map = {}
        for score in obj.step_scores.all():
            score_map[(score.step_id, score.examiner_id)] = score

        reconciled_map = {}
        for rs in obj.reconciled_scores.all():
            reconciled_map[rs.step_id] = rs

        steps_data = []
        for step in obj.procedure.steps.all():
            score_a_obj = score_map.get((step.id, obj.examiner_a_id))
            score_b_obj = score_map.get((step.id, obj.examiner_b_id))
            reconciled_obj = reconciled_map.get(step.id)

            score_a = score_a_obj.score if score_a_obj else None
            score_b = score_b_obj.score if score_b_obj else None

            valid_scores = []
            if score_a is not None and score_b is not None:
                lo, hi = min(score_a, score_b), max(score_a, score_b)
                valid_scores = list(range(lo, hi + 1))

            steps_data.append({
                "id": step.id,
                "description": step.description,
                "step_order": step.step_order,
                "examiner_a_score": score_a,
                "examiner_b_score": score_b,
                "reconciled_score": reconciled_obj.score if reconciled_obj else None,
                "valid_scores": valid_scores,
            })

        return steps_data


# ─────────────────────────────────────────────
# PROCEDURE DETAIL (Examiner scoring view)
# ─────────────────────────────────────────────

class ProcedureDetailSerializer(StudentProcedureMixin, serializers.ModelSerializer):
    steps = serializers.SerializerMethodField()
    studentProcedureId = serializers.SerializerMethodField()
    scores = serializers.SerializerMethodField()
    is_examiner = serializers.SerializerMethodField()
    examiner_role = serializers.SerializerMethodField()
    both_examiners_assigned = serializers.SerializerMethodField()
    can_modify_scores = serializers.SerializerMethodField()
    is_locked = serializers.SerializerMethodField()

    class Meta:
        model = Procedure
        fields = [
            "id", "name", "total_score", "steps", "studentProcedureId",
            "scores", "is_examiner", "examiner_role", "both_examiners_assigned",
            "can_modify_scores", "is_locked",
        ]

    def get_steps(self, obj):
        return [
            {"id": s.id, "description": s.description, "step_order": s.step_order}
            for s in obj.steps.all()
        ]

    def get_studentProcedureId(self, obj):
        sp = self._get_student_procedure(obj)
        return sp.id if sp else None

    def get_scores(self, obj):
        request = self.context.get("request")
        sp = self._get_student_procedure(obj)
        if not request or not sp:
            return []
        scores = sp.step_scores.filter(examiner=request.user)
        return ProcedureStepScoreSerializer(scores, many=True).data

    def get_is_examiner(self, obj):
        request = self.context.get("request")
        sp = self._get_student_procedure(obj)
        if not request or not sp:
            return False
        return request.user in (sp.examiner_a, sp.examiner_b)

    def get_examiner_role(self, obj):
        request = self.context.get("request")
        sp = self._get_student_procedure(obj)
        if not request or not sp:
            return None
        if request.user == sp.examiner_a:
            return "A"
        if request.user == sp.examiner_b:
            return "B"
        return None

    def get_both_examiners_assigned(self, obj):
        sp = self._get_student_procedure(obj)
        return bool(sp and sp.examiner_a != sp.examiner_b)

    def get_can_modify_scores(self, obj):
        request = self.context.get("request")
        sp = self._get_student_procedure(obj)
        if not request:
            return False
        if not sp:
            return True  # New procedure, can score
        if sp.status == "reconciled":
            return False
        if not sp.is_user_assigned_examiner(request.user):
            return False
        if sp.assigned_reconciler:
            return False
        return True

    def get_is_locked(self, obj):
        sp = self._get_student_procedure(obj)
        if not sp:
            return False
        return sp.assigned_reconciler is not None or sp.status == "reconciled"


# ─────────────────────────────────────────────
# CARE PLAN
# ─────────────────────────────────────────────

class CarePlanSerializer(serializers.ModelSerializer):
    student = StudentSerializer(read_only=True)
    examiner_name = serializers.CharField(source="examiner.get_full_name", read_only=True)
    percentage = serializers.SerializerMethodField()

    class Meta:
        model = CarePlan
        fields = [
            "id", "student", "program", "examiner", "examiner_name",
            "score", "max_score", "percentage", "comments",
            "assessed_at", "is_locked",
        ]
        read_only_fields = ["examiner", "assessed_at", "is_locked"]

    def get_percentage(self, obj):
        return obj.get_percentage()


class CarePlanCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CarePlan
        fields = ["student", "program", "score", "comments"]

    def validate_score(self, value):
        if not (0 <= value <= 20):
            raise serializers.ValidationError("Score must be between 0 and 20.")
        return value

    def validate(self, data):
        if CarePlan.objects.filter(
            student=data["student"], program=data["program"]
        ).exists():
            raise serializers.ValidationError("Care plan already exists for this student.")
        return data