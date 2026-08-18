from rest_framework.permissions import BasePermission

ADMIN_ROLES = {'admin'}
STAFF_ROLES = {'admin', 'professor', 'teacher'}


class IsAdminOrRegionStaff(BasePermission):
    """
    Admins can do everything. Professors/teachers may read and manage the
    media of their own region only (object-level check below + queryset
    scoping in the viewset).
    """

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and getattr(user, 'role', None) in STAFF_ROLES
        )

    def has_object_permission(self, request, view, obj):
        user = request.user
        if getattr(user, 'role', None) in ADMIN_ROLES:
            return True
        return bool(user.region_id and obj.region_id == user.region_id)
