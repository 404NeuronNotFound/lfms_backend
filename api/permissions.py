from rest_framework.permissions import BasePermission

class IsAdminUserRole(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'ADMIN'


class IsNormalUserRole(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'USER'