# from django.http import JsonResponse
# from accounts.models import School
# import threading

# _thread_locals = threading.local()


# def get_current_school():
#     return getattr(_thread_locals, "school", None)


# def set_current_school(school):
#     _thread_locals.school = school


# class TenantMiddleware:
#     def __init__(self, get_response):
#         self.get_response = get_response

#     def __call__(self, request):

#         # 1. Allow Django admin completely
#         if request.path.startswith("/admin/"):
#             return self.get_response(request)

#         user = getattr(request, "user", None)

#         # 2. Allow superusers to bypass tenancy
#         if user and user.is_authenticated and user.is_superuser:
#             return self.get_response(request)

#         school = None

#         # 3. Resolve tenant from header (API clients)
#         school_id = request.headers.get("X-School-ID")
#         if school_id:
#             try:
#                 # If numeric, use ID
#                 if school_id.isdigit():
#                     school = School.objects.get(id=int(school_id), is_active=True)
#                 else:
#                     # Otherwise treat as subdomain
#                     school = School.objects.get(subdomain=school_id, is_active=True)
#             except School.DoesNotExist:
#                 return JsonResponse(
#                     {"error": "Invalid X-School-ID"},
#                     status=400
#                 )

#         # 4. Resolve tenant from subdomain
#         if not school:
#             host = request.get_host().split(":")[0]
#             parts = host.split(".")

#             if len(parts) > 2:
#                 subdomain = parts[0]
#                 try:
#                     school = School.objects.get(
#                         subdomain=subdomain,
#                         is_active=True
#                     )
#                 except School.DoesNotExist:
#                     pass

#         # 5. Resolve tenant from authenticated user
#         if not school and user and user.is_authenticated:
#             school = getattr(user, "school", None)

#         # 6. Public endpoints
#         public_paths = (
#             "/api/auth/",
#             "/api/schools/",
#         )

#         is_public = request.path.startswith(public_paths)

#         if not school and not is_public:
#             return JsonResponse(
#                 {
#                     "error": "School not identified. Provide X-School-ID header or use subdomain."
#                 },
#                 status=400
#             )

#         # 7. Attach tenant context
#         request.school = school
#         set_current_school(school)

#         try:
#             response = self.get_response(request)
#         finally:
#             # 8. Always clear thread-local
#             set_current_school(None)

#         return response


from django.http import JsonResponse
from accounts.models import School
import threading

# Thread-local storage for current tenant
_thread_locals = threading.local()


def get_current_school():
    """Get the current school from thread-local storage"""
    return getattr(_thread_locals, 'school', None)


def set_current_school(school):
    """Set the current school in thread-local storage"""
    _thread_locals.school = school


class TenantMiddleware:
    """
    Middleware to identify tenant (school) from:
    1. Subdomain (e.g., schoolname.yourdomain.com)
    2. Custom header (X-School-ID) - useful for API clients
    3. User's school (fallback if authenticated)
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        school = None
        
        # 1. Allow Django admin completely (no tenant required)
        if request.path.startswith("/admin/"):
            # For admin, we still set school context if user has one
            if hasattr(request, 'user') and request.user.is_authenticated:
                school = getattr(request.user, 'school', None)
                set_current_school(school)
            return self.get_response(request)
        
        # 2. Check if user is superuser (can bypass tenancy)
        user = getattr(request, 'user', None)
        if user and user.is_authenticated and user.is_superuser:
            # Superusers can optionally set school via header
            school_id = request.headers.get('X-School-ID')
            if school_id:
                try:
                    if school_id.isdigit():
                        school = School.objects.get(id=int(school_id), is_active=True)
                    else:
                        school = School.objects.get(subdomain=school_id, is_active=True)
                except School.DoesNotExist:
                    pass
            
            # Set school context for superuser
            request.school = school
            set_current_school(school)
            
            response = self.get_response(request)
            
            # Clear after response for superusers
            set_current_school(None)
            return response
        
        # 3. Method 1: Get school from custom header (for API)
        school_id = request.headers.get('X-School-ID')
        print("Middleware school:", school_id) #getattr(request, "school", None)

        if school_id:
            try:
                # Support both numeric ID and subdomain string
                if school_id.isdigit():
                    school = School.objects.get(id=int(school_id), is_active=True)
                else:
                    school = School.objects.get(subdomain=school_id, is_active=True)
            except School.DoesNotExist:
                return JsonResponse({
                    'error': f'Invalid school identifier: {school_id}'
                }, status=400)
        
        # 4. Method 2: Get school from subdomain
        if not school:
            host = request.get_host().split(':')[0]  # Remove port
            parts = host.split('.')
            
            # If subdomain exists (e.g., school1.example.com)
            if len(parts) > 2:
                subdomain = parts[0]
                try:
                    school = School.objects.get(subdomain=subdomain, is_active=True)
                except School.DoesNotExist:
                    pass
        
        # 5. Method 3: Get school from authenticated user
        if not school and user and user.is_authenticated:
            school = getattr(user, 'school', None)
        
        # 6. Public endpoints that don't require a school
        public_paths = [
            '/api/auth/login/',
            '/api/auth/schools/',
            '/api/auth/token/refresh/',
        ]
        is_public = any(request.path.startswith(path) for path in public_paths)
        
        # 7. If no school found and not a public endpoint, return error
        if not school and not is_public:
            return JsonResponse({
                'error': 'School not identified. Please provide X-School-ID header or use subdomain.'
            }, status=400)
        
        # 8. Set the school in thread-local storage and request
        set_current_school(school)
        request.school = school
        
        # 9. Process request
        response = self.get_response(request)
        
        # 10. Clear thread-local after request completes
        # This is important to prevent memory leaks in thread pools
        set_current_school(None)
        
        return response
    
    
    def process_exception(self, request, exception):
        """Clear thread-local storage even if an exception occurs"""
        set_current_school(None)
        return None