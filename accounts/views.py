import logging

# accounts/views.py
from django.conf import settings

# from rest_framework.views import APIView
# from rest_framework.response import Response
# from rest_framework import status
# from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from django.contrib.auth import authenticate

import openpyxl
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.styles import Font
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated  # , AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User
from .permissions import IsAdmin
from .serializers import ChangePasswordSerializer
# from .serializers import LoginSerializer, UserSerializer

logger = logging.getLogger(__name__)


# class LoginView(APIView):
#     permission_classes = [AllowAny]

#     def post(self, request):
#         serializer = LoginSerializer(data=request.data)
#         serializer.is_valid(raise_exception=True)

#         user = serializer.validated_data["user"]

#         # Generate JWT tokens
#         refresh = RefreshToken.for_user(user)
#         access_token = str(refresh.access_token)
#         refresh_token = str(refresh)

#         return Response(
#             {
#                 "access": access_token,
#                 "refresh": refresh_token,
#                 "user": UserSerializer(user).data,
#             },
#             status=status.HTTP_200_OK,
#         )


# class LogoutView(APIView):
#     permission_classes = [IsAuthenticated]

#     def post(self, request):
#         refresh_token = request.data.get("refresh")

#         if not refresh_token:
#             return Response(
#                 {"error": "Refresh token is required"},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         try:
#             token = RefreshToken(refresh_token)
#             token.blacklist()
#         except Exception as e:
#             logger.warning("Logout blacklist failed: %s", e)
#             return Response(
#                 {"error": "Invalid or expired token"},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         return Response(
#             {"detail": "Successfully logged out"},
#             status=status.HTTP_200_OK,
#         )


def set_auth_cookies(response, access_token, refresh_token=None):
    """Helper to attach HttpOnly auth cookies to any response."""
    response.set_cookie(
        key=settings.AUTH_COOKIE_ACCESS,
        value=access_token,
        max_age=settings.AUTH_COOKIE_ACCESS_MAX_AGE,
        secure=settings.AUTH_COOKIE_SECURE,
        httponly=settings.AUTH_COOKIE_HTTPONLY,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        path="/",
    )
    if refresh_token:
        response.set_cookie(
            key=settings.AUTH_COOKIE_REFRESH,
            value=refresh_token,
            max_age=settings.AUTH_COOKIE_REFRESH_MAX_AGE,
            secure=settings.AUTH_COOKIE_SECURE,
            httponly=settings.AUTH_COOKIE_HTTPONLY,
            samesite=settings.AUTH_COOKIE_SAMESITE,
            path="/",
        )


def _delete_auth_cookies(response):
    """Mirror the exact attributes used in set_cookie() so browsers honour the deletion."""
    for key in [settings.AUTH_COOKIE_ACCESS, settings.AUTH_COOKIE_REFRESH]:
        response.delete_cookie(
            key,
            path="/",
            samesite=settings.AUTH_COOKIE_SAMESITE,
        )
        # Explicitly expire for older browsers that ignore delete_cookie's max-age=0
        response.cookies[key]["secure"] = settings.AUTH_COOKIE_SECURE


class LoginView(APIView):
    permission_classes = []

    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")

        user = authenticate(username=username, password=password)
        if not user:
            return Response(
                {"detail": "Invalid credentials."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        # Return only safe, non-sensitive user info in the body
        response = Response(
            {
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "role": user.role,
                }
            },
            status=status.HTTP_200_OK,
        )

        set_auth_cookies(response, access_token, refresh_token)
        return response


class RefreshTokenView(APIView):
    permission_classes = []

    def post(self, request):
        refresh_token = request.COOKIES.get(settings.AUTH_COOKIE_REFRESH)
        if not refresh_token:
            return Response({"detail": "No refresh token."}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            refresh = RefreshToken(refresh_token)
            access_token = str(refresh.access_token)
            new_refresh_token = str(refresh)
        except TokenError:
            return Response({"detail": "Invalid or expired refresh token."}, status=status.HTTP_401_UNAUTHORIZED)

        response = Response({"detail": "Token refreshed."})
        set_auth_cookies(response, access_token, new_refresh_token)  # send both
        return response


class LogoutView(APIView):
    """Blacklist the refresh token and clear both cookies."""

    def post(self, request):
        refresh_token = request.COOKIES.get(settings.AUTH_COOKIE_REFRESH)
        response = Response({"detail": "Logged out."})

        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()  # Requires simplejwt BLACKLIST app
            except TokenError:
                pass 

        _delete_auth_cookies(response)
        return response


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def change_password(request):
    """Change password for authenticated user"""
    serializer = ChangePasswordSerializer(
        data=request.data, context={"request": request}
    )

    if serializer.is_valid():
        serializer.save()
        return Response(
            {"detail": "Password changed successfully"}, status=status.HTTP_200_OK
        )

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def current_user(request):
    """Get current authenticated user info"""
    user = request.user
    return Response(
        {
            "id": user.pk,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
        }
    )


@api_view(["GET"])
@permission_classes([IsAdmin])
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
        "Date Joined",
    ]

    ws.append(headers)

    for cell in ws[1]:
        cell.font = Font(bold=True)

    def sanitize(val):
        if val and str(val)[0] in ("=", "+", "-", "@", "\t", "\r"):
            return "'" + str(val)
        return val

    for examiner in examiners:
        ws.append(
            [
                sanitize(examiner.username),
                sanitize(examiner.email),
                sanitize(examiner.first_name),
                sanitize(examiner.last_name),
                examiner.is_active,
                examiner.date_joined.strftime("%Y-%m-%d %H:%M:%S"),
            ]
        )

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    response["Content-Disposition"] = 'attachment; filename="examiners.xlsx"'

    wb.save(response)

    return response


@api_view(["POST"])
@permission_classes([IsAdmin])
def import_examiners(request):
    """Import examiners from Excel (.xlsx)"""

    if "file" not in request.FILES:
        return Response(
            {"error": "No file provided"}, status=status.HTTP_400_BAD_REQUEST
        )

    excel_file = request.FILES["file"]

    ALLOWED_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if excel_file.content_type != ALLOWED_MIME or not excel_file.name.endswith(".xlsx"):
        return Response(
            {"error": "File must be a valid Excel (.xlsx) file"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    MAX_UPLOAD_MB = 5
    if excel_file.size > MAX_UPLOAD_MB * 1024 * 1024:
        return Response(
            {"error": f"File too large. Maximum size is {MAX_UPLOAD_MB} MB."},
            status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
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
                    status=status.HTTP_400_BAD_REQUEST,
                )

        created_count = 0
        errors = []

        header_index = {header: idx for idx, header in enumerate(headers)}

        with transaction.atomic():
            for row_number, row in enumerate(
                sheet.iter_rows(min_row=2, values_only=True), start=2
            ):
                try:
                    username = row[header_index["Username"]]

                    if not username:
                        errors.append(f"Row {row_number}: Username is required")
                        continue

                    if User.objects.filter(username=username).exists():
                        errors.append(
                            f"Row {row_number}: Username '{username}' already exists"
                        )
                        continue

                    email = row[header_index.get("Email")]
                    first_name = row[header_index.get("First Name")]
                    last_name = row[header_index.get("Last Name")]
                    password = row[header_index.get("Password")]

                    if not password:
                        errors.append(f"Row {row_number}: Password is required")
                        continue
                    try:
                        validate_password(str(password))
                    except ValidationError as e:
                        errors.append(f"Row {row_number}: {'; '.join(e.messages)}")
                        continue

                    User.objects.create(
                        username=username,
                        email=email,
                        first_name=first_name,
                        last_name=last_name,
                        role="examiner",
                        password=make_password(password),
                    )

                    created_count += 1

                except Exception as e:
                    logger.error(
                        "Import error row %s: %s", row_number, e, exc_info=True
                    )
                    errors.append(
                        f"Row {row_number}: Unexpected error, please check the data."
                    )

        return Response(
            {"created": created_count, "errors": errors},
            status=status.HTTP_201_CREATED
            if created_count > 0
            else status.HTTP_400_BAD_REQUEST,
        )

    except Exception as e:
        logger.error("Excel parsing failed: %s", e, exc_info=True)
        return Response(
            {
                "error": "Could not process the uploaded file. Check the format and try again."
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


@api_view(["GET"])
@permission_classes([IsAdmin])
def download_examiner_template(request):
    """Download Excel template for importing examiners"""

    wb = Workbook()
    ws = wb.active
    ws.title = "Examiner Import Template"

    headers = ["Username", "Email", "First Name", "Last Name", "Password"]

    ws.append(headers)

    # Style header row
    for cell in ws[1]:
        cell.font = Font(bold=True)

    # Example row (helps users understand format)
    ws.append(
        [
            "examiner01",
            "examiner01@example.com",
            "John",
            "Doe",
            "<set-a-strong-password>",
        ]
    )

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

    response["Content-Disposition"] = (
        'attachment; filename="examiner_import_template.xlsx"'
    )

    wb.save(response)

    return response
