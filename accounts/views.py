from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework_simplejwt.tokens import RefreshToken
from django.http import HttpResponse
import csv
import io
from django.contrib.auth.hashers import make_password
from .serializers import ChangePasswordSerializer, LoginSerializer, UserSerializer, ExaminerSerializer
from .models import User


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        return Response(
            {
                "access": access_token,
                "refresh": refresh_token,
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
        except Exception:
            pass

        return Response(
            {"detail": "Successfully logged out"},
            status=status.HTTP_200_OK,
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    """Change password for authenticated user"""
    serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
    
    if serializer.is_valid():
        serializer.save()
        return Response(
            {'detail': 'Password changed successfully'},
            status=status.HTTP_200_OK
        )
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def current_user(request):
    """Get current authenticated user info"""
    user = request.user
    return Response({
        'id': user.pk,
        'username': user.username,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'role': user.role,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_examiners(request):
    """Export all examiners to CSV"""
    examiners = User.objects.filter(role='examiner')
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="examiners.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Username', 'Email', 'First Name', 'Last Name', 'Is Active', 'Date Joined'])
    
    for examiner in examiners:
        writer.writerow([
            examiner.username,
            examiner.email,
            examiner.first_name,
            examiner.last_name,
            examiner.is_active,
            examiner.date_joined.strftime('%Y-%m-%d %H:%M:%S')
        ])
    
    return response


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def import_examiners(request):
    """Import examiners from CSV file"""
    if 'file' not in request.FILES:
        return Response(
            {'error': 'No file provided'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    csv_file = request.FILES['file']
    
    if not csv_file.name.endswith('.csv'):
        return Response(
            {'error': 'File must be CSV format'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        decoded_file = csv_file.read().decode('utf-8')
        io_string = io.StringIO(decoded_file)
        reader = csv.DictReader(io_string)
        
        created_count = 0
        errors = []
        
        for row_number, row in enumerate(reader, start=2):
            try:
                # Check if username already exists
                if User.objects.filter(username=row['Username']).exists():
                    errors.append(f"Row {row_number}: Username '{row['Username']}' already exists")
                    continue
                
                # Create examiner
                User.objects.create(
                    username=row['Username'],
                    email=row['Email'],
                    first_name=row['First Name'],
                    last_name=row['Last Name'],
                    role='examiner',
                    is_active=row.get('Is Active', 'True').lower() in ['true', '1', 'yes'],
                    password=make_password(row.get('Password', 'changeme123'))  # Default password if not provided
                )
                created_count += 1
            except KeyError as e:
                errors.append(f"Row {row_number}: Missing required field {str(e)}")
            except Exception as e:
                errors.append(f"Row {row_number}: {str(e)}")
        
        return Response({
            'created': created_count,
            'errors': errors
        }, status=status.HTTP_201_CREATED if created_count > 0 else status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        return Response(
            {'error': f'Error processing file: {str(e)}'},
            status=status.HTTP_400_BAD_REQUEST
        )