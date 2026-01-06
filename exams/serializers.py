from rest_framework import serializers
from .models import Program, Student, Procedure, ProcedureStep, ProcedureStepScore, StudentProcedure
from django.contrib.auth import get_user_model

User = get_user_model()

# ================ ADMIN DASHBOARD SERIALIZERS ==============

class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'full_name', 'is_active', 'date_joined']
        read_only_fields = ['date_joined']
    
    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    password_confirm = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password', 'password_confirm']
    
    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        return attrs
    
    def create(self, validated_data):
        validated_data.pop('password_confirm')
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
        fields = ['id', 'index_number', 'full_name', 'program_id', 'is_active']
    
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

    class Meta:
        model = Student
        fields = ["id", "index_number", "full_name", "program"]


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


class ProcedureListSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    step_count = serializers.SerializerMethodField()
    program = serializers.CharField(source="program.abbreviation")
    
    class Meta:
        model = Procedure
        fields = ["id", "program", "name", "total_score", "status", "step_count"]
    
    def get_status(self, obj):
        student_id = self.context.get("student_id")
        if not student_id:
            return "pending"
        
        sp = obj.studentprocedure_set.filter(student_id=student_id).first()
        return sp.status if sp else "pending"
    
    def get_step_count(self, obj): return obj.steps.count()


class ProcedureDetailSerializer(serializers.ModelSerializer):
    steps = serializers.SerializerMethodField()
    studentProcedureId = serializers.SerializerMethodField()
    scores = serializers.SerializerMethodField()
    is_examiner = serializers.SerializerMethodField()
    examiner_role = serializers.SerializerMethodField()

    class Meta:
        model = Procedure
        fields = ["id", "name", "total_score", "steps", "studentProcedureId", "scores", "is_examiner", "examiner_role"]

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


class ReconciliationSerializer(serializers.ModelSerializer):
    steps = serializers.SerializerMethodField()
    student = StudentSerializer(read_only=True)
    examiner_a_name = serializers.CharField(source='examiner_a.get_full_name', read_only=True)
    examiner_b_name = serializers.CharField(source='examiner_b.get_full_name', read_only=True)

    class Meta:
        model = StudentProcedure
        fields = [
            "id", "student", "procedure", "status",
            "examiner_a_name", "examiner_b_name", "steps"
        ]

    def get_steps(self, obj):
        steps_data = []
        for step in obj.procedure.steps.all():
            # Get scores from both examiners
            examiner_a_score = obj.step_scores.filter(
                step=step, examiner=obj.examiner_a
            ).first()
            examiner_b_score = obj.step_scores.filter(
                step=step, examiner=obj.examiner_b
            ).first()

            steps_data.append({
                "id": step.id,
                "description": step.description,
                "step_order": step.step_order,
                "examiner_a_score": examiner_a_score.score if examiner_a_score else None,
                "examiner_b_score": examiner_b_score.score if examiner_b_score else None,
            })
        return steps_data
    