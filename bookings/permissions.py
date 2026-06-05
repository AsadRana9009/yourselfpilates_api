from rest_framework import permissions

class IsAdminOrProfessor(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False
            
        # Check for admin role or professor/teacher role
        return user.role == 'admin' or user.role in ['professor', 'teacher']
    
    def has_object_permission(self, request, view, obj):
        user = request.user
        # Admin can access all, professors only their own bookings
        return user.role == 'admin' or (user.role in ['professor', 'teacher'] and obj.professor == user)
    

class IsAdminUser(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False
            
        return user.role == 'admin'
    
    def has_object_permission(self, request, view, obj):
        user = request.user
        return user.role == 'admin'
