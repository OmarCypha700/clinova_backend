import csv
import io

from django.contrib.auth.hashers import make_password
from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
import openpyxl
from openpyxl import Workbook
from openpyxl.styles import Font

from .models import User
from .serializers import (ChangePasswordSerializer, ExaminerSerializer,
                          LoginSerializer, UserSerializer)


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
    """Export all examiners to Excel"""

    examiners = User.objects.filter(role="examiner")

    wb = Workbook()
    ws = wb.active
    ws.title = "Examiners"

    headers = [
        "Username",
        "Email",
        "First Name",
        "Last Name",
        "Is Active",
        "Date Joined"
    ]

    ws.append(headers)

    for cell in ws[1]:
        cell.font = Font(bold=True)

    for examiner in examiners:
        ws.append([
            examiner.username,
            examiner.email,
            examiner.first_name,
            examiner.last_name,
            examiner.is_active,
            examiner.date_joined.strftime('%Y-%m-%d %H:%M:%S')
        ])

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    response["Content-Disposition"] = 'attachment; filename="examiners.xlsx"'

    wb.save(response)

    return response

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def import_examiners(request):
    """Import examiners from Excel (.xlsx)"""

    if "file" not in request.FILES:
        return Response(
            {"error": "No file provided"},
            status=status.HTTP_400_BAD_REQUEST
        )

    excel_file = request.FILES["file"]

    if not excel_file.name.endswith(".xlsx"):
        return Response(
            {"error": "File must be Excel (.xlsx) format"},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        workbook = openpyxl.load_workbook(excel_file)
        sheet = workbook.active

        headers = [cell.value for cell in sheet[1]]

        required_columns = ["Username", "Email", "First Name", "Last Name", "Password"]

        for col in required_columns:
            if col not in headers:
                return Response(
                    {"error": f"Missing column: {col}"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        created_count = 0
        errors = []

        header_index = {header: idx for idx, header in enumerate(headers)}

        for row_number, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):

            try:
                username = row[header_index["Username"]]

                if not username:
                    errors.append(f"Row {row_number}: Username is required")
                    continue

                if User.objects.filter(username=username).exists():
                    errors.append(f"Row {row_number}: Username '{username}' already exists")
                    continue

                email = row[header_index.get("Email")]
                first_name = row[header_index.get("First Name")]
                last_name = row[header_index.get("Last Name")]
                password = row[header_index.get("Password")]

                User.objects.create(
                    username=username,
                    email=email,
                    first_name=first_name,
                    last_name=last_name,
                    role="examiner",
                    password=make_password(password)
                )

                created_count += 1

            except Exception as e:
                errors.append(f"Row {row_number}: {str(e)}")

        return Response({
            "created": created_count,
            "errors": errors
        },
        status=status.HTTP_201_CREATED if created_count > 0 else status.HTTP_400_BAD_REQUEST
        )

    except Exception as e:
        return Response(
            {"error": f"Error processing Excel file: {str(e)}"},
            status=status.HTTP_400_BAD_REQUEST
        )    
    

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def download_examiner_template(request):
    """Download Excel template for importing examiners"""

    wb = Workbook()
    ws = wb.active
    ws.title = "Examiner Import Template"

    headers = [
        "Username",
        "Email",
        "First Name",
        "Last Name",
        "Password"
    ]

    ws.append(headers)

    # Style header row
    for cell in ws[1]:
        cell.font = Font(bold=True)

    # Example row (helps users understand format)
    ws.append([
        "examiner01",
        "examiner01@example.com",
        "John",
        "Doe",
        "changeme123"
    ])

    # Adjust column width
    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter

        for cell in column:
            if cell.value:
                max_length = max(max_length, len(str(cell.value)))

        ws.column_dimensions[column_letter].width = max_length + 3

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    response["Content-Disposition"] = 'attachment; filename="examiner_import_template.xlsx"'

    wb.save(response)

    return response

