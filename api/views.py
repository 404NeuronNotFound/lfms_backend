from django.contrib.auth import get_user_model
from rest_framework import permissions, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken

from .models import UserProfile
from .serializers import (
    RegisterSerializer,
    LoginSerializer,
    UserSerializer,
    UserListSerializer,
)
from .permissions import IsAdminUserRole

User = get_user_model()

class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "User registered successfully."}, status=201)
        return Response(serializer.errors, status=400)


class LoginView(APIView):

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            return Response(serializer.validated_data, status=200)
        return Response(serializer.errors, status=400)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response({"detail": "Refresh token is required."}, status=400)
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except (TokenError, InvalidToken):
            pass  # already invalid / expired — still treat as logged out
        return Response({"message": "Logged out successfully."}, status=205)




class AdminDashboard(APIView):
    permission_classes = [IsAdminUserRole]

    def get(self, request):
        return Response({"message": "Welcome Admin!"})


class UserDashboard(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.status == "banned":
            return Response({"detail": "Your account has been banned."}, status=403)
        if request.user.status == "inactive":
            return Response({"detail": "Your account is deactivated."}, status=403)
        return Response({"message": "Welcome!"})



class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        UserProfile.objects.get_or_create(user=request.user)
        serializer = UserSerializer(request.user, context={"request": request})
        return Response(serializer.data)

    def patch(self, request):
        UserProfile.objects.get_or_create(user=request.user)

        data = {
            "first_name": request.data.get("first_name", request.user.first_name),
            "last_name":  request.data.get("last_name",  request.user.last_name),
            "email":      request.data.get("email",      request.user.email),
        }

        profile_fields = {}
        for key in ("phone_number", "address", "bio"):
            bracket_key = f"profile[{key}]"
            dot_key     = f"profile.{key}"
            if bracket_key in request.data:
                profile_fields[key] = request.data[bracket_key]
            elif dot_key in request.data:
                profile_fields[key] = request.data[dot_key]

        for file_key in (f"profile[avatar]", "profile.avatar", "avatar"):
            if file_key in request.FILES:
                profile_fields["avatar"] = request.FILES[file_key]
                break

        if profile_fields:
            data["profile"] = profile_fields

        serializer = UserSerializer(
            request.user, data=data, partial=True,
            context={"request": request},
        )
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Profile updated successfully.", "user": serializer.data})
        return Response(serializer.errors, status=400)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        current         = request.data.get("current_password")
        new             = request.data.get("new_password")
        confirm         = request.data.get("confirm_new_password")

        if not current:
            return Response({"current_password": ["Current password is required."]}, status=400)
        if not new:
            return Response({"new_password": ["New password is required."]}, status=400)
        if len(new) < 6:
            return Response({"new_password": ["Password must be at least 6 characters."]}, status=400)
        if new != confirm:
            return Response({"confirm_new_password": ["Passwords do not match."]}, status=400)
        if not request.user.check_password(current):
            return Response({"current_password": ["Current password is incorrect."]}, status=400)

        request.user.set_password(new)
        request.user.save()
        return Response({"message": "Password changed successfully."}, status=200)

class DeactivateAccountView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        if user.status == "banned":
            return Response({"detail": "Banned accounts cannot be modified."}, status=403)

        user.status = "inactive"
        user.save(update_fields=["status"])

        refresh_token = request.data.get("refresh")
        if refresh_token:
            try:
                RefreshToken(refresh_token).blacklist()
            except (TokenError, InvalidToken):
                pass

        return Response({"message": "Your account has been deactivated. Log in any time to reactivate."}, status=200)


class ReactivateAccountView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        if user.status == "banned":
            return Response(
                {"detail": "Your account has been banned. Contact support to appeal."},
                status=403,
            )
        if user.status == "active":
            return Response({"detail": "Your account is already active."}, status=200)

        user.status = "active"
        user.save(update_fields=["status"])
        return Response({"message": "Your account has been reactivated."}, status=200)




class AdminUserListView(APIView):

    permission_classes = [IsAdminUserRole]

    def get(self, request):
        queryset = User.objects.select_related("profile").all().order_by("-date_joined")

        status_filter = request.query_params.get("status")
        role_filter   = request.query_params.get("role")
        search        = request.query_params.get("search", "").strip()

        if status_filter in ("active", "inactive", "banned"):
            queryset = queryset.filter(status=status_filter)
        if role_filter in ("ADMIN", "USER"):
            queryset = queryset.filter(role=role_filter)
        if search:
            queryset = queryset.filter(
                username__icontains=search
            ) | queryset.filter(
                first_name__icontains=search
            ) | queryset.filter(
                last_name__icontains=search
            ) | queryset.filter(
                email__icontains=search
            )

        serializer = UserListSerializer(queryset, many=True, context={"request": request})
        return Response({
            "count": queryset.count(),
            "users": serializer.data,
        })


class AdminUserDetailView(APIView):
    permission_classes = [IsAdminUserRole]

    def _get_user(self, pk):
        try:
            return User.objects.select_related("profile").get(pk=pk)
        except User.DoesNotExist:
            return None

    def get(self, request, pk):
        user = self._get_user(pk)
        if not user:
            return Response({"detail": "User not found."}, status=404)
        serializer = UserSerializer(user, context={"request": request})
        return Response(serializer.data)

    def patch(self, request, pk):
        user = self._get_user(pk)
        if not user:
            return Response({"detail": "User not found."}, status=404)

        if user == request.user:
            return Response({"detail": "Admins cannot modify their own account via this endpoint."}, status=403)

        allowed_fields = {"role", "status", "first_name", "last_name", "email"}
        update_data    = {k: v for k, v in request.data.items() if k in allowed_fields}


        if "status" in update_data and update_data["status"] not in ("active", "inactive", "banned"):
            return Response({"status": ["Must be one of: active, inactive, banned."]}, status=400)

        if "role" in update_data and update_data["role"] not in ("ADMIN", "USER"):
            return Response({"role": ["Must be one of: ADMIN, USER."]}, status=400)

        for attr, value in update_data.items():
            setattr(user, attr, value)
        user.save()

        serializer = UserSerializer(user, context={"request": request})
        return Response({"message": "User updated.", "user": serializer.data})

    def delete(self, request, pk):
        user = self._get_user(pk)
        if not user:
            return Response({"detail": "User not found."}, status=404)
        if user == request.user:
            return Response({"detail": "You cannot delete your own account via admin."}, status=403)
        username = user.username
        user.delete()
        return Response({"message": f"User '{username}' has been deleted."}, status=200)


class AdminBanUserView(APIView):
    permission_classes = [IsAdminUserRole]

    def post(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=404)

        if user == request.user:
            return Response({"detail": "You cannot ban yourself."}, status=403)
        if user.role == "ADMIN":
            return Response({"detail": "Admin accounts cannot be banned."}, status=403)
        if user.status == "banned":
            return Response({"detail": "User is already banned."}, status=400)

        user.status = "banned"
        user.save(update_fields=["status"])
        return Response({"message": f"User '{user.username}' has been banned."}, status=200)


class AdminUnbanUserView(APIView):
    permission_classes = [IsAdminUserRole]

    def post(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=404)

        if user.status != "banned":
            return Response({"detail": "User is not banned."}, status=400)

        user.status = "active"
        user.save(update_fields=["status"])
        return Response({"message": f"User '{user.username}' has been unbanned."}, status=200)


class AdminUserStatsView(APIView):
    permission_classes = [IsAdminUserRole]

    def get(self, request):
        from django.utils import timezone
        from datetime import timedelta

        now            = timezone.now()
        month_start    = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        total          = User.objects.count()
        admins         = User.objects.filter(role="ADMIN").count()
        active         = User.objects.filter(status="active").count()
        inactive       = User.objects.filter(status="inactive").count()
        banned         = User.objects.filter(status="banned").count()
        new_this_month = User.objects.filter(date_joined__gte=month_start).count()

        return Response({
            "total":          total,
            "admins":         admins,
            "active":         active,
            "inactive":       inactive,
            "banned":         banned,
            "new_this_month": new_this_month,
        })