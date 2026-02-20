from rest_framework import serializers
from .models import (Program, Student, Procedure, 
                     ProcedureStep, ProcedureStepScore, StudentProcedure, 
                     ReconciledScore, CarePlan)
from django.contrib.auth import get_user_model

User = get_user_model()

# ================ ADMIN DASHBOARD SERIALIZERS ==============

class UserSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'role', 'is_active', 'date_joined']
        read_only_fields = ['date_joined']

class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'role', 'password',] #'password_confirm'
    
    
    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user

class DashboardStatsSerializer(serializers.Serializer):
    total_students = serializers.IntegerField()
    active_students = serializers.IntegerField()
    total_examiners = serializers.IntegerField()
    total_procedures = serializers.IntegerField()
    pending_assessments = serializers.IntegerField()
    scored_assessments = serializers.IntegerField()
    reconciled_assessments = serializers.IntegerField()
    total_programs = serializers.IntegerField()

class StudentCreateUpdateSerializer(serializers.ModelSerializer):
    program_id = serializers.IntegerField(write_only=True)
    
    class Meta:
        model = Student
        fields = ['id', 'index_number', 'full_name', 'program_id', 'level', 'is_active']
    
    def create(self, validated_data):
        program_id = validated_data.pop('program_id')
        validated_data['program_id'] = program_id
        return Student.objects.create(**validated_data)
    
    def update(self, instance, validated_data):
        if 'program_id' in validated_data:
            instance.program_id = validated_data.pop('program_id')
        return super().update(instance, validated_data)

class ProcedureCreateUpdateSerializer(serializers.ModelSerializer):
    program_id = serializers.IntegerField(write_only=True)
    
    class Meta:
        model = Procedure
        fields = ['id', 'name', 'program_id', 'total_score']
    
    def create(self, validated_data):
        program_id = validated_data.pop('program_id')
        validated_data['program_id'] = program_id
        return Procedure.objects.create(**validated_data)

class ProcedureStepCreateUpdateSerializer(serializers.ModelSerializer):
    procedure_id = serializers.IntegerField(write_only=True)
    
    class Meta:
        model = ProcedureStep
        fields = ['id', 'procedure_id', 'description', 'step_order']


# ================ EXAMINATION PROCESS SERIALIZERS ==============

class ProgramSerializer(serializers.ModelSerializer):
    class Meta:
        model = Program
        fields = ["id", "name", "abbreviation"]

class StudentSerializer(serializers.ModelSerializer):
    program = ProgramSerializer(read_only=True)
    level_display = serializers.CharField(source='get_level_display', read_only=True)

    class Meta:
        model = Student
        fields = ["id", "index_number", "full_name", "program", "level", "level_display", "is_active"]

class ProcedureStepSerializer(serializers.ModelSerializer):
    score = serializers.SerializerMethodField()

    class Meta:
        model = ProcedureStep
        fields = ["id", "description", "score"]

    def get_score(self, step):
        request = self.context.get("request")
        student_procedure = self.context.get("student_procedure")

        if not request or not student_procedure:
            return None

        score = step.procedure.steps.filter(
            id=step.id
        ).first()

        step_score = student_procedure.step_scores.filter(
            step=step,
            examiner=request.user
        ).first()

        return step_score.score if step_score else None
    
class ProcedureStepScoreSerializer(serializers.ModelSerializer):
    step = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = ProcedureStepScore
        fields = ["step", "score"]

class ProcedureAdminListSerializer(serializers.ModelSerializer):
    program = serializers.CharField(source="program.name", read_only=True)
    program_id = serializers.IntegerField(source="program.id", read_only=True)
    step_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Procedure
        fields = ["id", "name", "program", "program_id", "total_score", "step_count"]
    
    def get_step_count(self, obj):
        return obj.steps.count()

class ReconciledScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReconciledScore
        fields = ['step', 'score', 'reconciled_by', 'reconciled_at']

# ================ CARE PLAN SERIALIZERS ==============
class CarePlanSerializer(serializers.ModelSerializer):
    student = StudentSerializer(read_only=True)
    examiner_name = serializers.CharField(source='examiner.get_full_name', read_only=True)
    percentage = serializers.SerializerMethodField()
    
    class Meta:
        model = CarePlan
        fields = ['id', 'student', 'program', 'examiner', 'examiner_name', 
                  'score', 'max_score', 'percentage', 'comments', 
                  'assessed_at', 'is_locked']
        read_only_fields = ['examiner', 'assessed_at', 'is_locked']
    
    def get_percentage(self, obj):
        return obj.get_percentage()

class CarePlanCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CarePlan
        fields = ['student', 'program', 'score', 'comments']
    
    def validate_score(self, value):
        if value < 0 or value > 20:
            raise serializers.ValidationError("Score must be between 0 and 20")
        return value
    
    def validate(self, data):
        # Check if care plan already exists
        if CarePlan.objects.filter(
            student=data['student'], 
            program=data['program']
        ).exists():
            raise serializers.ValidationError("Care plan already exists for this student")
        return data
    
class ProcedureListSerializer(serializers.ModelSerializer):
    program_name = serializers.CharField(source="program.name", read_only=True)
    program_abbreviation = serializers.CharField(source="program.abbreviation", read_only=True)
    program_id = serializers.IntegerField(source="program.id", read_only=True)
    step_count = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    can_reconcile = serializers.SerializerMethodField()
    display_status = serializers.SerializerMethodField()
    
    class Meta:
        model = Procedure
        fields = ["id", "name", "total_score", "program_id", "program_name", 
                  "program_abbreviation", "status", "step_count", "can_reconcile", "display_status"]
    
    def get_status(self, obj):
        student_id = self.context.get("student_id")
        if not student_id:
            return "pending"
        
        sp = obj.studentprocedure_set.filter(student_id=student_id).first()
        if not sp:
            return "pending"
        
        # If both examiners are the same (not yet fully assigned), return pending
        if sp.examiner_a == sp.examiner_b:
            return "pending"
        
        return sp.status
    
    def get_step_count(self, obj):
        return obj.steps.count()
    
    def get_can_reconcile(self, obj):
        """Check if current user can reconcile this procedure"""
        student_id = self.context.get("student_id")
        request = self.context.get("request")
        
        if not student_id or not request:
            return False
        
        sp = obj.studentprocedure_set.filter(student_id=student_id).first()
        if not sp or sp.status != "scored":
            return False
        
        # Use the model's can_user_reconcile method
        return sp.can_user_reconcile(request.user)
    
    def get_display_status(self, obj):
        """
        Return the display status for the current user:
        - 'pending': Not all examiners have scored
        - 'ready_to_reconcile': Current user can reconcile
        - 'scored': Scored but current user cannot reconcile
        - 'reconciled': Already reconciled
        """
        student_id = self.context.get("student_id")
        request = self.context.get("request")
        
        if not student_id or not request:
            return "pending"
        
        sp = obj.studentprocedure_set.filter(student_id=student_id).first()
        if not sp:
            return "pending"
        
        if sp.examiner_a == sp.examiner_b:
            return "pending"
        
        if sp.status == "reconciled":
            return "reconciled"
        
        if sp.status == "scored":
            # Check if current user can reconcile
            if sp.can_user_reconcile(request.user):
                return "ready_to_reconcile"
            else:
                return "scored"
        
        return "pending"

class ReconciliationSerializer(serializers.ModelSerializer):
    steps = serializers.SerializerMethodField()
    student = StudentSerializer(read_only=True)
    examiner_a_name = serializers.CharField(source='examiner_a.get_full_name', read_only=True)
    examiner_b_name = serializers.CharField(source='examiner_b.get_full_name', read_only=True)
    reconciled_by_name = serializers.SerializerMethodField()
    is_already_reconciled = serializers.SerializerMethodField()
    can_user_reconcile = serializers.SerializerMethodField()  # NEW FIELD

    class Meta:
        model = StudentProcedure
        fields = [
            "id", "student", "procedure", "status",
            "examiner_a_name", "examiner_b_name", 
            "reconciled_by_name", "reconciled_at",
            "is_already_reconciled", "can_user_reconcile", "steps"
        ]
    
    def get_reconciled_by_name(self, obj):
        return obj.reconciled_by.get_full_name() if obj.reconciled_by else None
    
    def get_is_already_reconciled(self, obj):
        return obj.status == 'reconciled'
    
    def get_can_user_reconcile(self, obj):
        """Check if the current user can reconcile"""
        request = self.context.get('request')
        if not request:
            return False
        
        last_examiner = obj.get_last_scoring_examiner()
        return last_examiner == request.user

    def get_steps(self, obj):
        steps_data = []
        for step in obj.procedure.steps.all():
            # Get scores from both examiners
            examiner_a_score = obj.step_scores.filter(
                step=step, 
                examiner=obj.examiner_a
            ).first()
            examiner_b_score = obj.step_scores.filter(
                step=step, 
                examiner=obj.examiner_b
            ).first()
            
            # Get existing reconciled score if already reconciled
            reconciled_score = obj.reconciled_scores.filter(step=step).first()
            
            # Calculate valid score range
            score_a = examiner_a_score.score if examiner_a_score else None
            score_b = examiner_b_score.score if examiner_b_score else None
            
            valid_scores = []
            if score_a is not None and score_b is not None:
                min_score = min(score_a, score_b)
                max_score = max(score_a, score_b)
                valid_scores = list(range(min_score, max_score + 1))

            steps_data.append({
                "id": step.id,
                "description": step.description,
                "step_order": step.step_order,
                "examiner_a_score": score_a,
                "examiner_b_score": score_b,
                "reconciled_score": reconciled_score.score if reconciled_score else None,
                "valid_scores": valid_scores,  # NEW FIELD
            })
        return steps_data
    
class ProcedureDetailSerializer(serializers.ModelSerializer):
    steps = serializers.SerializerMethodField()
    studentProcedureId = serializers.SerializerMethodField()
    scores = serializers.SerializerMethodField()
    is_examiner = serializers.SerializerMethodField()
    examiner_role = serializers.SerializerMethodField()
    both_examiners_assigned = serializers.SerializerMethodField()
    can_modify_scores = serializers.SerializerMethodField()  # NEW
    is_locked = serializers.SerializerMethodField()  # NEW

    class Meta:
        model = Procedure
        fields = [
            "id", "name", "total_score", "steps", "studentProcedureId", 
            "scores", "is_examiner", "examiner_role", "both_examiners_assigned",
            "can_modify_scores", "is_locked"
        ]

    def get_steps(self, obj):
        steps = obj.steps.all()
        return [{"id": s.id, "description": s.description, "step_order": s.step_order} for s in steps]

    def get_studentProcedureId(self, obj):
        student_id = self.context.get("student_id")
        if not student_id:
            return None
        sp = obj.studentprocedure_set.filter(student_id=student_id).first()
        return sp.id if sp else None

    def get_scores(self, obj):
        """Only return scores for the current logged-in user"""
        student_id = self.context.get("student_id")
        request = self.context.get("request")
        
        if not student_id or not request:
            return []
        
        sp = obj.studentprocedure_set.filter(student_id=student_id).first()
        if not sp:
            return []
        
        # Only fetch scores for the current user (examiner)
        scores = sp.step_scores.filter(examiner=request.user)
        return ProcedureStepScoreSerializer(scores, many=True).data
    
    def get_is_examiner(self, obj):
        """Check if current user is an assigned examiner"""
        student_id = self.context.get("student_id")
        request = self.context.get("request")
        
        if not student_id or not request:
            return False
        
        sp = obj.studentprocedure_set.filter(student_id=student_id).first()
        if not sp:
            return False
        
        return request.user in [sp.examiner_a, sp.examiner_b]
    
    def get_examiner_role(self, obj):
        """Return which examiner the current user is (A or B)"""
        student_id = self.context.get("student_id")
        request = self.context.get("request")
        
        if not student_id or not request:
            return None
        
        sp = obj.studentprocedure_set.filter(student_id=student_id).first()
        if not sp:
            return None
        
        if request.user == sp.examiner_a:
            return "A"
        elif request.user == sp.examiner_b:
            return "B"
        return None
    
    def get_both_examiners_assigned(self, obj):
        """Check if both different examiners are assigned"""
        student_id = self.context.get("student_id")
        if not student_id:
            return False
        
        sp = obj.studentprocedure_set.filter(student_id=student_id).first()
        if not sp:
            return False
        
        return sp.examiner_a != sp.examiner_b
    
    def get_can_modify_scores(self, obj):
        """
        Check if current user can modify their scores.
        Cannot modify if:
        1. Not an assigned examiner
        2. Reconciler has been assigned (locked)
        3. Already reconciled
        """
        student_id = self.context.get("student_id")
        request = self.context.get("request")
        
        if not student_id or not request:
            return False
        
        sp = obj.studentprocedure_set.filter(student_id=student_id).first()
        if not sp:
            return True  # New procedure, can score
        
        # Cannot modify if reconciled
        if sp.status == "reconciled":
            return False
        
        # Cannot modify if not an assigned examiner
        if not sp.is_user_assigned_examiner(request.user):
            return False
        
        # Cannot modify if reconciler has been assigned (locked)
        if sp.assigned_reconciler:
            return False
        
        return True
    
    def get_is_locked(self, obj):
        """Check if procedure is locked (reconciler assigned or reconciled)"""
        student_id = self.context.get("student_id")
        if not student_id:
            return False
        
        sp = obj.studentprocedure_set.filter(student_id=student_id).first()
        if not sp:
            return False
        
        return sp.assigned_reconciler is not None or sp.status == "reconciled"
