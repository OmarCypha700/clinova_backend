from django.conf import settings
from rest_framework_simplejwt.authentication import JWTAuthentication


class CookieJWTAuthentication(JWTAuthentication):
    """
    Reads the access token from the HttpOnly cookie instead of
    the Authorization header.
    """

    def authenticate(self, request):
        access_token = request.COOKIES.get(settings.AUTH_COOKIE_ACCESS)

        if not access_token:
            return None  # Let DRF return 401 naturally

        validated_token = self.get_validated_token(access_token)
        return self.get_user(validated_token), validated_token