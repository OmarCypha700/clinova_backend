from rest_framework.generics import ListAPIView, RetrieveAPIView
from .models import (Program, Student, Procedure, 
                     ProcedureStepScore, StudentProcedure, ProcedureStep)
from .serializers import (ProgramSerializer, StudentSerializer, ProcedureDetailSerializer, 
                          ProcedureListSerializer, ReconciliationSerializer,
                          DashboardStatsSerializer, UserSerializer, UserCreateSerializer,
                          StudentCreateUpdateSerializer, ProcedureCreateUpdateSerializer,
                          ProcedureStepCreateUpdateSerializer)
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets, status
from django.db import transaction
from accounts.models import User
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.contrib.auth import get_user_model
from django.db.models import Count, Q

# User = get_user_model()



class ProgramListView(ListAPIView):
    queryset = Program.objects.all()
    serializer_class = ProgramSerializer


class StudentByProgramView(ListAPIView):
    serializer_class = StudentSerializer

    def get_queryset(self):
        program_id = self.kwargs["program_id"]
        return Student.objects.filter(program_id=program_id)
    

class ProcedureByProgramView(ListAPIView):
    serializer_class = ProcedureListSerializer

    def get_queryset(self):
        return Procedure.objects.filter(
            program_id=self.kwargs["program_id"]
        )
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        # Get student_id from query params
        context["student_id"] = self.request.query_params.get("student_id")
        return context
    

class ProcedureDetailView(RetrieveAPIView):
    queryset = Procedure.objects.all()
    serializer_class = ProcedureDetailSerializer

    def retrieve(self, request, *args, **kwargs):
        student_id = self.kwargs.get("student_id")
        procedure = self.get_object()
        
        # Get or create StudentProcedure
        sp, created = StudentProcedure.objects.get_or_create(
            student_id=student_id,
            procedure=procedure,
            defaults={
                "examiner_a": request.user,
                "examiner_b": request.user,
            }
        )
        
        # Auto-assign examiners intelligently
        if sp.examiner_a == sp.examiner_b and sp.examiner_a != request.user:
            # First examiner was set, now a different user is accessing
            sp.examiner_b = request.user
            sp.save()
        elif request.user not in [sp.examiner_a, sp.examiner_b]:
            return Response(
                {
                    "detail": "You are not assigned as an examiner for this procedure.",
                    "examiner_a": sp.examiner_a.get_full_name(),
                    "examiner_b": sp.examiner_b.get_full_name(),
                },
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Continue with normal serialization
        return super().retrieve(request, *args, **kwargs)
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["student_id"] = self.kwargs.get("student_id")
        return context


class AutosaveStepScoreView(APIView):
    """
    Autosave the score for a single step.
    Expects POST data: { student_procedure: int, step: int, score: int }
    """

    def post(self, request, *args, **kwargs):
        data = request.data
        student_procedure_id = data.get("student_procedure")
        step_id = data.get("step")
        score = data.get("score")

        # Validate
        if not all([student_procedure_id, step_id, score is not None]):
            return Response(
                {"detail": "student_procedure, step, and score are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            sp = StudentProcedure.objects.get(id=student_procedure_id)
            step = ProcedureStep.objects.get(id=step_id)
        except StudentProcedure.DoesNotExist:
            return Response({"detail": "StudentProcedure not found."}, status=404)
        except ProcedureStep.DoesNotExist:
            return Response({"detail": "ProcedureStep not found."}, status=404)

        # Verify current user is one of the assigned examiners
        if request.user not in [sp.examiner_a, sp.examiner_b]:
            return Response(
                {"detail": "You are not authorized to score this procedure."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Save the step score
        step_score, created = ProcedureStepScore.objects.update_or_create(
            student_procedure=sp,
            step=step,
            examiner=request.user,
            defaults={"score": score},
        )

        # ✅ Update status logic - Check if BOTH examiners have scored ALL steps
        total_steps = sp.procedure.steps.count()
        examiner_a_scores = sp.step_scores.filter(examiner=sp.examiner_a).count()
        examiner_b_scores = sp.step_scores.filter(examiner=sp.examiner_b).count()

        # If both examiners have scored all steps, mark as "scored"
        if examiner_a_scores == total_steps and examiner_b_scores == total_steps:
            if sp.status != "reconciled":  # Don't change if already reconciled
                sp.status = "scored"
                sp.save()
        # Otherwise keep as pending
        elif sp.status == "pending":
            pass  # Keep as pending

        return Response(
            {
                "step": step.id, 
                "score": step_score.score, 
                "created": created,
                "status": sp.status,
                "examiner_a_complete": examiner_a_scores == total_steps,
                "examiner_b_complete": examiner_b_scores == total_steps,
            },
            status=status.HTTP_200_OK,
        )


class ReconciliationView(RetrieveAPIView):
    """
    GET endpoint to fetch StudentProcedure with both examiners' scores for reconciliation
    """
    serializer_class = ReconciliationSerializer
    
    def get_queryset(self):
        return StudentProcedure.objects.filter(
            student_id=self.kwargs['student_id'],
            procedure_id=self.kwargs['procedure_id']
        )
    
    def get_object(self):
        queryset = self.get_queryset()
        obj = queryset.first()
        
        if not obj:
            # Create if doesn't exist
            obj = StudentProcedure.objects.create(
                student_id=self.kwargs['student_id'],
                procedure_id=self.kwargs['procedure_id'],
                examiner_a=self.request.user,
                examiner_b=self.request.user,
            )
        
        return obj


class SaveReconciliationView(APIView):
    """
    POST endpoint to save reconciled scores
    Expects: { student_procedure_id: int, reconciled_scores: [{step_id: int, score: int}] }
    """
    
    @transaction.atomic
    def post(self, request, *args, **kwargs):
        student_procedure_id = request.data.get('student_procedure_id')
        reconciled_scores = request.data.get('reconciled_scores', [])
        
        if not student_procedure_id or not reconciled_scores:
            return Response(
                {"detail": "student_procedure_id and reconciled_scores are required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            sp = StudentProcedure.objects.get(id=student_procedure_id)
        except StudentProcedure.DoesNotExist:
            return Response(
                {"detail": "StudentProcedure not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Verify all steps are provided
        total_steps = sp.procedure.steps.count()
        if len(reconciled_scores) != total_steps:
            return Response(
                {"detail": f"Expected {total_steps} scores, got {len(reconciled_scores)}."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Delete existing reconciled scores for this student procedure
        sp.step_scores.filter(examiner=request.user).delete()
        
        # Save reconciled scores
        for score_data in reconciled_scores:
            step_id = score_data.get('step_id')
            score = score_data.get('score')
            
            if step_id is None or score is None:
                return Response(
                    {"detail": "Each score must have step_id and score."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                step = ProcedureStep.objects.get(id=step_id, procedure=sp.procedure)
            except ProcedureStep.DoesNotExist:
                return Response(
                    {"detail": f"Step {step_id} not found in this procedure."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            ProcedureStepScore.objects.create(
                student_procedure=sp,
                step=step,
                examiner=request.user,
                score=score
            )
        
        # Update status to reconciled
        sp.status = 'reconciled'
        sp.save()
        
        return Response(
            {"detail": "Reconciliation saved successfully.", "status": sp.status},
            status=status.HTTP_200_OK
        )
    

class AssignExaminersView(APIView):
    """
    POST endpoint to create/update StudentProcedure with assigned examiners
    Expects: { student_id: int, procedure_id: int, examiner_a_id: int, examiner_b_id: int }
    """
    
    def post(self, request, *args, **kwargs):
        data = request.data
        student_id = data.get("student_id")
        procedure_id = data.get("procedure_id")
        examiner_a_id = data.get("examiner_a_id")
        examiner_b_id = data.get("examiner_b_id")

        if not all([student_id, procedure_id, examiner_a_id, examiner_b_id]):
            return Response(
                {"detail": "All fields are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            student = Student.objects.get(id=student_id)
            procedure = Procedure.objects.get(id=procedure_id)
            examiner_a = User.objects.get(id=examiner_a_id)
            examiner_b = User.objects.get(id=examiner_b_id)
        except (Student.DoesNotExist, Procedure.DoesNotExist, User.DoesNotExist) as e:
            return Response(
                {"detail": f"Invalid reference: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create or update StudentProcedure
        sp, created = StudentProcedure.objects.update_or_create(
            student=student,
            procedure=procedure,
            defaults={
                "examiner_a": examiner_a,
                "examiner_b": examiner_b,
            }
        )

        return Response(
            {
                "id": sp.id,
                "created": created,
                "examiner_a": examiner_a.get_full_name(),
                "examiner_b": examiner_b.get_full_name(),
            },
            status=status.HTTP_200_OK
        )
    

class StudentDetailView(RetrieveAPIView):
    """Get student details by ID"""
    queryset = Student.objects.all()
    serializer_class = StudentSerializer


# ================ ADMIN DASHBOARD VIEWS ==============

class DashboardStatsView(APIView):
    """Get dashboard statistics"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        stats = {
            'total_students': Student.objects.count(),
            'active_students': Student.objects.filter(is_active=True).count(),
            'total_examiners': User.objects.filter(role="examiner").count(),
            'total_procedures': Procedure.objects.count(),
            'pending_assessments': StudentProcedure.objects.filter(status='pending').count(),
            'scored_assessments': StudentProcedure.objects.filter(status='scored').count(),
            'reconciled_assessments': StudentProcedure.objects.filter(status='reconciled').count(),
            'total_programs': Program.objects.count(),
        }
        
        serializer = DashboardStatsSerializer(stats)
        return Response(serializer.data)


class ExaminerViewSet(viewsets.ModelViewSet):
    """CRUD operations for examiners (users)"""
    queryset = User.objects.filter(role="examiner")
    permission_classes = [IsAuthenticated, IsAdminUser]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        return UserSerializer
    
    @action(detail=True, methods=['post'])
    def toggle_active(self, request, pk=None):
        user = self.get_object()
        user.is_active = not user.is_active
        user.save()
        return Response({'is_active': user.is_active})


class StudentViewSet(viewsets.ModelViewSet):
    """CRUD operations for students"""
    queryset = Student.objects.select_related('program').all()
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return StudentCreateUpdateSerializer
        return StudentSerializer
    
    @action(detail=False, methods=['get'])
    def by_program(self, request):
        program_id = request.query_params.get('program_id')
        if program_id:
            students = self.queryset.filter(program_id=program_id)
        else:
            students = self.queryset
        
        serializer = self.get_serializer(students, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def toggle_active(self, request, pk=None):
        student = self.get_object()
        student.is_active = not student.is_active
        student.save()
        return Response({'is_active': student.is_active})


class ProcedureViewSet(viewsets.ModelViewSet):
    """CRUD operations for procedures"""
    queryset = Procedure.objects.select_related('program').prefetch_related('steps').all()
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ProcedureCreateUpdateSerializer
        elif self.action == 'retrieve':
            return ProcedureDetailSerializer
        return ProcedureListSerializer


class ProcedureStepViewSet(viewsets.ModelViewSet):
    """CRUD operations for procedure steps"""
    queryset = ProcedureStep.objects.select_related('procedure').all()
    serializer_class = ProcedureStepCreateUpdateSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        procedure_id = self.request.query_params.get('procedure_id')
        if procedure_id:
            queryset = queryset.filter(procedure_id=procedure_id)
        return queryset


class ProgramViewSet(viewsets.ModelViewSet):
    """CRUD operations for programs"""
    queryset = Program.objects.all()
    serializer_class = ProgramSerializer
    permission_classes = [IsAuthenticated]