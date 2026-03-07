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
    

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  LOST REPORTS — USER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from .models import LostReport, ReportImage
from .serializers import (
    LostReportSerializer,
    LostReportListSerializer,
    AdminLostReportSerializer,
)


class UserReportListCreateView(APIView):
    """
    GET  /api/reports/         — list the current user's own reports
    POST /api/reports/         — create a new lost report (+ optional images)

    Images are accepted as multipart/form-data via:
      images[0], images[1], … images[4]   (up to 5 files)
    The first uploaded image is automatically flagged as is_main=True.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = (
            LostReport.objects
            .filter(user=request.user)
            .prefetch_related('images')
            .order_by('-date_reported')
        )
        # Optional status filter  ?status=open
        status_filter = request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        serializer = LostReportListSerializer(qs, many=True, context={'request': request})
        return Response({'count': qs.count(), 'results': serializer.data})

    def post(self, request):
        serializer = LostReportSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        report = serializer.save(user=request.user)

        # Handle uploaded images (up to 5)
        uploaded_images = []
        for i in range(5):
            key = f'images[{i}]'
            if key in request.FILES:
                uploaded_images.append(request.FILES[key])

        for idx, img_file in enumerate(uploaded_images[:5]):
            ReportImage.objects.create(
                report=report,
                image=img_file,
                is_main=(idx == 0),   # first image is the main thumbnail
                order=idx,
            )

        # Return full detail serializer so the client gets image URLs
        output = LostReportSerializer(report, context={'request': request})
        return Response(output.data, status=201)


class UserReportDetailView(APIView):
    """
    GET    /api/reports/<id>/   — view a single report (owner or admin)
    PATCH  /api/reports/<id>/   — update own report fields (owner only, while open/under_review)
    DELETE /api/reports/<id>/   — delete own report (owner only, while open)
    """
    permission_classes = [IsAuthenticated]

    def _get_report(self, pk, user):
        try:
            return LostReport.objects.prefetch_related('images').get(pk=pk, user=user)
        except LostReport.DoesNotExist:
            return None

    def get(self, request, pk):
        report = self._get_report(pk, request.user)
        if not report:
            return Response({'detail': 'Report not found.'}, status=404)
        # Increment view counter
        LostReport.objects.filter(pk=pk).update(views=report.views + 1)
        serializer = LostReportSerializer(report, context={'request': request})
        return Response(serializer.data)

    def patch(self, request, pk):
        report = self._get_report(pk, request.user)
        if not report:
            return Response({'detail': 'Report not found.'}, status=404)

        # Users can only edit while the report is still open or under review
        if report.status not in (LostReport.STATUS_OPEN, LostReport.STATUS_UNDER_REVIEW):
            return Response(
                {'detail': f"Reports with status '{report.status}' cannot be edited."},
                status=403,
            )

        serializer = LostReportSerializer(
            report, data=request.data, partial=True,
            context={'request': request},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        serializer.save()
        return Response({'message': 'Report updated.', 'report': serializer.data})

    def delete(self, request, pk):
        report = self._get_report(pk, request.user)
        if not report:
            return Response({'detail': 'Report not found.'}, status=404)

        # Only allow deletion while report is still open
        if report.status != LostReport.STATUS_OPEN:
            return Response(
                {'detail': 'Only open reports can be deleted.'},
                status=403,
            )

        report.delete()
        return Response({'message': 'Report deleted.'}, status=200)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  LOST REPORTS — ADMIN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AdminReportListView(APIView):
    """
    GET /api/admin/reports/
    Returns all reports across all users with optional filters:
      ?status=open|under_review|matched|claimed|closed|rejected
      ?category=Electronics|Keys|…
      ?urgent=true
      ?search=<text>   (searches item_name, location, username)
      ?ordering=date|-date|views|-views
    """
    permission_classes = [IsAdminUserRole]

    def get(self, request):
        qs = (
            LostReport.objects
            .select_related('user')
            .prefetch_related('images')
            .order_by('-date_reported')
        )

        # Filters
        status_f   = request.query_params.get('status')
        category_f = request.query_params.get('category')
        urgent_f   = request.query_params.get('urgent')
        search_f   = request.query_params.get('search', '').strip()
        ordering_f = request.query_params.get('ordering', '-date_reported')

        if status_f:
            qs = qs.filter(status=status_f)
        if category_f:
            qs = qs.filter(category=category_f)
        if urgent_f and urgent_f.lower() == 'true':
            qs = qs.filter(is_urgent=True)
        if search_f:
            from django.db.models import Q
            qs = qs.filter(
                Q(item_name__icontains=search_f) |
                Q(location__icontains=search_f)  |
                Q(user__username__icontains=search_f)
            )

        allowed_orderings = {'date_reported', '-date_reported', 'views', '-views', 'item_name'}
        if ordering_f in allowed_orderings:
            qs = qs.order_by(ordering_f)

        serializer = AdminLostReportSerializer(qs, many=True, context={'request': request})
        return Response({'count': qs.count(), 'results': serializer.data})


class AdminReportDetailView(APIView):
    """
    GET    /api/admin/reports/<id>/   — view any report in full
    PATCH  /api/admin/reports/<id>/   — update status, admin_notes, or any field
    DELETE /api/admin/reports/<id>/   — hard-delete a report
    """
    permission_classes = [IsAdminUserRole]

    def _get_report(self, pk):
        try:
            return LostReport.objects.select_related('user').prefetch_related('images').get(pk=pk)
        except LostReport.DoesNotExist:
            return None

    def get(self, request, pk):
        report = self._get_report(pk)
        if not report:
            return Response({'detail': 'Report not found.'}, status=404)
        serializer = AdminLostReportSerializer(report, context={'request': request})
        return Response(serializer.data)

    def patch(self, request, pk):
        report = self._get_report(pk)
        if not report:
            return Response({'detail': 'Report not found.'}, status=404)

        # Validate status if provided
        new_status = request.data.get('status')
        if new_status:
            valid_statuses = [s[0] for s in LostReport.STATUS_CHOICES]
            if new_status not in valid_statuses:
                return Response(
                    {'status': [f"Must be one of: {', '.join(valid_statuses)}"]},
                    status=400,
                )

        serializer = AdminLostReportSerializer(
            report, data=request.data, partial=True,
            context={'request': request},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        serializer.save()
        return Response({'message': 'Report updated.', 'report': serializer.data})

    def delete(self, request, pk):
        report = self._get_report(pk)
        if not report:
            return Response({'detail': 'Report not found.'}, status=404)
        report.delete()
        return Response({'message': f"Report #{pk} deleted."}, status=200)


class AdminReportStatsView(APIView):
    """
    GET /api/admin/reports/stats/
    Returns aggregate counts for the reports dashboard stat cards.
    """
    permission_classes = [IsAdminUserRole]

    def get(self, request):
        from django.utils import timezone as tz

        now         = tz.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        total          = LostReport.objects.count()
        open_count     = LostReport.objects.filter(status='open').count()
        under_review   = LostReport.objects.filter(status='under_review').count()
        matched        = LostReport.objects.filter(status='matched').count()
        claimed        = LostReport.objects.filter(status='claimed').count()
        closed         = LostReport.objects.filter(status='closed').count()
        rejected       = LostReport.objects.filter(status='rejected').count()
        urgent         = LostReport.objects.filter(is_urgent=True).count()
        new_this_month = LostReport.objects.filter(date_reported__gte=month_start).count()

        return Response({
            'total':          total,
            'open':           open_count,
            'under_review':   under_review,
            'matched':        matched,
            'claimed':        claimed,
            'closed':         closed,
            'rejected':       rejected,
            'urgent':         urgent,
            'new_this_month': new_this_month,
        })
