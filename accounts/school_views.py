from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db import transaction
from .models import School, User
from .serializers import SchoolSerializer
from django.contrib.auth.hashers import make_password


class SchoolViewSet(viewsets.ModelViewSet):
    """
    CRUD operations for schools
    Note: In production, you'd restrict this to superadmins only
    """
    queryset = School.objects.all()
    serializer_class = SchoolSerializer
    
    def get_permissions(self):
        if self.action == 'list':
            return [AllowAny()]
        return [IsAuthenticated()]
    
    @transaction.atomic
    @action(detail=True, methods=['post'])
    def create_admin(self, request, pk=None):
        """Create an admin user for a school"""
        school = self.get_object()
        
        username = request.data.get('username')
        password = request.data.get('password')
        email = request.data.get('email')
        first_name = request.data.get('first_name', '')
        last_name = request.data.get('last_name', '')
        
        if not username or not password:
            return Response(
                {'error': 'Username and password are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if user already exists
        if User.objects.filter(school=school, username=username).exists():
            return Response(
                {'error': 'Username already exists in this school'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create admin user
        user = User.objects.create(
            school=school,
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            role='admin',
            is_staff=True,
            password=make_password(password)
        )
        
        return Response({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role,
            'school': school.name,
        }, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Get statistics for a school"""
        school = self.get_object()
        
        # Import here to avoid circular imports
        from exams.models import Student, Procedure, StudentProcedure
        
        stats = {
            'total_users': school.users.count(),
            'total_admins': school.users.filter(role='admin').count(),
            'total_examiners': school.users.filter(role='examiner').count(),
            'total_students': Student.objects.filter(school=school).count(),
            'total_procedures': Procedure.objects.filter(school=school).count(),
            'total_assessments': StudentProcedure.objects.filter(school=school).count(),
            'pending_assessments': StudentProcedure.objects.filter(
                school=school, 
                status='pending'
            ).count(),
        }
        
        return Response(stats)