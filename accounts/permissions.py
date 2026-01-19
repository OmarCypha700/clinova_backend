from rest_framework.permissions import BasePermission


class IsSchoolAdmin(BasePermission):
    """
    Allows access only to users with role=admin
    """

    def has_permission(self, request, view):
        user = request.user

        return (
            user
            and user.is_authenticated
            and user.role == "admin"
        )


class IsSchoolExaminer(BasePermission):
    """
    Allows access only to users with role=examiner
    """

    def has_permission(self, request, view):
        user = request.user

        return (
            user
            and user.is_authenticated
            and user.role == "examiner"
        )