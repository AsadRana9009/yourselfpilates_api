from rest_framework.permissions import BasePermission, SAFE_METHODS

class IsAdminOrReadOnly(BasePermission):
    """
    - Anyone can READ (GET, HEAD, OPTIONS)
    - Only admin can WRITE (POST, PUT, PATCH, DELETE)
    """

    def has_permission(self, request, view):
        # Allow read-only methods for everyone
        if request.method in SAFE_METHODS:
            return True

        user = request.user
        return bool(user and user.is_authenticated and getattr(user, "role", None) == "admin")
