from django.urls import path
# from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    LoginView,
    LogoutView,
    RefreshTokenView,
    change_password,
    current_user,
    download_examiner_template,
    export_examiners,
    import_examiners,
)

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("token/refresh/", RefreshTokenView.as_view(), name="token_refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", current_user, name="current-user"),
    path("examiners/export/", export_examiners, name="export-examiners"),
    path("examiners/import/", import_examiners, name="import-examiners"),
    path(
        "examiners/template/",
        download_examiner_template,
        name="download-examiner-template",
    ),
    path("change-password/", change_password, name="change-password"),
]
