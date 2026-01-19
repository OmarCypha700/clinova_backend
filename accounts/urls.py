from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    LoginView, 
    LogoutView, 
    current_user,
    export_examiners,
    import_examiners
)
from .school_views import SchoolViewSet

router = DefaultRouter()
router.register(r'schools', SchoolViewSet, basename='school')

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path('me/', current_user, name='current-user'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('examiners/export/', export_examiners, name='export-examiners'),
    path('examiners/import/', import_examiners, name='import-examiners'),
    path('', include(router.urls)),
]