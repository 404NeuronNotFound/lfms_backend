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

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  AUTH
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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
            pass
        return Response({"message": "Logged out successfully."}, status=205)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DASHBOARDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  PROFILE & SETTINGS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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
        current = request.data.get("current_password")
        new     = request.data.get("new_password")
        confirm = request.data.get("confirm_new_password")

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

        return Response({"message": "Your account has been deactivated."}, status=200)


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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ADMIN — USER MANAGEMENT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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
        return Response({"count": queryset.count(), "users": serializer.data})


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

        now         = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        return Response({
            "total":          User.objects.count(),
            "admins":         User.objects.filter(role="ADMIN").count(),
            "active":         User.objects.filter(status="active").count(),
            "inactive":       User.objects.filter(status="inactive").count(),
            "banned":         User.objects.filter(status="banned").count(),
            "new_this_month": User.objects.filter(date_joined__gte=month_start).count(),
        })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  USER — REPORTS (LOST + FOUND)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from .models import LostReport, ReportImage, MatchSuggestion, ClaimRequest, Notification
from .serializers import (
    ReportSerializer,
    ReportListSerializer,
    AdminReportSerializer,
    MatchSuggestionSerializer,
    ClaimRequestSerializer,
)


def _fire_notification(user, notif_type, title, message, report=None, claim=None):
    """Helper — creates a Notification row."""
    Notification.objects.create(
        user=user,
        notif_type=notif_type,
        title=title,
        message=message,
        report=report,
        claim=claim,
    )


class UserReportListCreateView(APIView):
    """
    GET  /api/reports/          — current user's reports (?type=lost|found, ?status=)
    POST /api/reports/          — submit a lost OR found report
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = (
            LostReport.objects
            .filter(user=request.user)
            .prefetch_related('images')
            .order_by('-date_reported')
        )
        type_filter   = request.query_params.get('type')
        status_filter = request.query_params.get('status')
        if type_filter in ('lost', 'found'):
            qs = qs.filter(report_type=type_filter)
        if status_filter:
            qs = qs.filter(status=status_filter)

        serializer = ReportListSerializer(qs, many=True, context={'request': request})
        return Response({'count': qs.count(), 'results': serializer.data})

    def post(self, request):
        serializer = ReportSerializer(data=request.data, context={'request': request})
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
                is_main=(idx == 0),
                order=idx,
            )

        # Notify user: report received
        type_label = "Lost" if report.report_type == "lost" else "Found"
        _fire_notification(
            user=request.user,
            notif_type='report_received',
            title=f'{type_label} Report Submitted',
            message=f'Your report for "{report.item_name}" has been received and is now open for review.',
            report=report,
        )

        output = ReportSerializer(report, context={'request': request})
        return Response(output.data, status=201)


class UserReportDetailView(APIView):
    """
    GET    /api/reports/<id>/   — view own report
    PATCH  /api/reports/<id>/   — edit own report (open or under_review only)
    DELETE /api/reports/<id>/   — delete own report (open only)
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
        LostReport.objects.filter(pk=pk).update(views=report.views + 1)
        serializer = ReportSerializer(report, context={'request': request})
        return Response(serializer.data)

    def patch(self, request, pk):
        report = self._get_report(pk, request.user)
        if not report:
            return Response({'detail': 'Report not found.'}, status=404)
        if report.status not in (LostReport.STATUS_OPEN, LostReport.STATUS_UNDER_REVIEW):
            return Response(
                {'detail': f"Reports with status '{report.status}' cannot be edited."},
                status=403,
            )

        serializer = ReportSerializer(
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
        if report.status != LostReport.STATUS_OPEN:
            return Response({'detail': 'Only open reports can be deleted.'}, status=403)
        report.delete()
        return Response({'message': 'Report deleted.'}, status=200)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  USER — CLAIM REQUESTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class UserClaimCreateView(APIView):
    """
    POST /api/reports/<id>/claim/
    Authenticated user submits a claim request for a found item.
    The report must be in 'matched' status.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            report = LostReport.objects.get(pk=pk)
        except LostReport.DoesNotExist:
            return Response({'detail': 'Report not found.'}, status=404)

        if report.status != LostReport.STATUS_MATCHED:
            return Response(
                {'detail': 'Claims can only be submitted for matched reports.'},
                status=400,
            )

        # Prevent duplicate pending claims from the same user
        existing = ClaimRequest.objects.filter(
            report=report,
            claimant=request.user,
            status=ClaimRequest.STATUS_PENDING,
        ).exists()
        if existing:
            return Response(
                {'detail': 'You already have a pending claim for this report.'},
                status=400,
            )

        serializer = ClaimRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        claim = serializer.save(report=report, claimant=request.user)

        # Notify the claimant
        _fire_notification(
            user=request.user,
            notif_type='claim_received',
            title='Claim Submitted',
            message=f'Your claim for "{report.item_name}" has been submitted and is pending admin review.',
            report=report,
            claim=claim,
        )

        return Response(ClaimRequestSerializer(claim).data, status=201)


class UserClaimListView(APIView):
    """
    GET /api/claims/
    Returns all claim requests filed by the current user.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        claims = ClaimRequest.objects.filter(claimant=request.user).select_related('report')
        serializer = ClaimRequestSerializer(claims, many=True)
        return Response({'count': claims.count(), 'results': serializer.data})


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  USER — NOTIFICATIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class UserNotificationListView(APIView):
    """
    GET /api/notifications/   — returns user's notifications (newest first)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notifs = Notification.objects.filter(user=request.user)
        unread = notifs.filter(is_read=False).count()
        data = [
            {
                'id':         n.id,
                'type':       n.notif_type,
                'title':      n.title,
                'message':    n.message,
                'is_read':    n.is_read,
                'report_id':  n.report_id,
                'claim_id':   n.claim_id,
                'created_at': n.created_at.isoformat(),
            }
            for n in notifs[:50]
        ]
        return Response({'unread_count': unread, 'results': data})


class UserNotificationReadView(APIView):
    """
    POST /api/notifications/<id>/read/   — mark one notification as read
    POST /api/notifications/read-all/    — mark all as read
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk=None):
        if pk:
            try:
                n = Notification.objects.get(pk=pk, user=request.user)
                n.is_read = True
                n.save(update_fields=['is_read'])
            except Notification.DoesNotExist:
                return Response({'detail': 'Not found.'}, status=404)
        else:
            Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({'message': 'Marked as read.'})


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ADMIN — REPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AdminReportListView(APIView):
    """
    GET /api/admin/reports/
    ?type=lost|found  ?status=  ?category=  ?urgent=true  ?search=  ?ordering=
    """
    permission_classes = [IsAdminUserRole]

    def get(self, request):
        qs = (
            LostReport.objects
            .select_related('user')
            .prefetch_related('images')
            .order_by('-date_reported')
        )

        type_f     = request.query_params.get('type')
        status_f   = request.query_params.get('status')
        category_f = request.query_params.get('category')
        urgent_f   = request.query_params.get('urgent')
        search_f   = request.query_params.get('search', '').strip()
        ordering_f = request.query_params.get('ordering', '-date_reported')

        if type_f in ('lost', 'found'):
            qs = qs.filter(report_type=type_f)
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

        serializer = AdminReportSerializer(qs, many=True, context={'request': request})
        return Response({'count': qs.count(), 'results': serializer.data})


class AdminReportDetailView(APIView):
    """
    GET    /api/admin/reports/<id>/
    PATCH  /api/admin/reports/<id>/   — update status, admin_notes, matched_report
    DELETE /api/admin/reports/<id>/
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
        serializer = AdminReportSerializer(report, context={'request': request})
        return Response(serializer.data)

    def patch(self, request, pk):
        report = self._get_report(pk)
        if not report:
            return Response({'detail': 'Report not found.'}, status=404)

        new_status = request.data.get('status')
        if new_status:
            valid_statuses = [s[0] for s in LostReport.STATUS_CHOICES]
            if new_status not in valid_statuses:
                return Response(
                    {'status': [f"Must be one of: {', '.join(valid_statuses)}"]},
                    status=400,
                )

        old_status = report.status

        serializer = AdminReportSerializer(
            report, data=request.data, partial=True,
            context={'request': request},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)
        serializer.save()

        # Fire notifications on status transitions
        if new_status and new_status != old_status:
            _handle_status_notification(report, new_status)

        return Response({'message': 'Report updated.', 'report': serializer.data})

    def delete(self, request, pk):
        report = self._get_report(pk)
        if not report:
            return Response({'detail': 'Report not found.'}, status=404)
        report.delete()
        return Response({'message': f"Report #{pk} deleted."}, status=200)


def _handle_status_notification(report, new_status):
    """Fire the right notification when admin changes a report status."""
    notif_map = {
        'under_review': (
            'under_review',
            'Report Under Review',
            f'Your report for "{report.item_name}" is now being reviewed by our team.',
        ),
        'matched': (
            'matched',
            'Possible Match Found!',
            f'Great news! A possible match was found for your "{report.item_name}" report. An admin will reach out shortly.',
        ),
        'claimed': (
            'claim_approved',
            'Item Claimed',
            f'Your item "{report.item_name}" has been marked as claimed.',
        ),
        'closed': (
            'report_closed',
            'Report Closed',
            f'Your report for "{report.item_name}" has been closed.',
        ),
        'rejected': (
            'report_rejected',
            'Report Rejected',
            f'Your report for "{report.item_name}" was rejected. Please check admin notes for details.',
        ),
    }
    if new_status in notif_map:
        notif_type, title, message = notif_map[new_status]
        _fire_notification(
            user=report.user,
            notif_type=notif_type,
            title=title,
            message=message,
            report=report,
        )


class AdminReportStatsView(APIView):
    """GET /api/admin/reports/stats/"""
    permission_classes = [IsAdminUserRole]

    def get(self, request):
        from django.utils import timezone as tz

        now         = tz.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        return Response({
            'total':          LostReport.objects.count(),
            'lost':           LostReport.objects.filter(report_type='lost').count(),
            'found':          LostReport.objects.filter(report_type='found').count(),
            'open':           LostReport.objects.filter(status='open').count(),
            'under_review':   LostReport.objects.filter(status='under_review').count(),
            'matched':        LostReport.objects.filter(status='matched').count(),
            'claimed':        LostReport.objects.filter(status='claimed').count(),
            'closed':         LostReport.objects.filter(status='closed').count(),
            'rejected':       LostReport.objects.filter(status='rejected').count(),
            'urgent':         LostReport.objects.filter(is_urgent=True).count(),
            'new_this_month': LostReport.objects.filter(date_reported__gte=month_start).count(),
        })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ADMIN — CLAIMS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AdminClaimListView(APIView):
    """GET /api/admin/claims/   ?status=pending|approved|rejected"""
    permission_classes = [IsAdminUserRole]

    def get(self, request):
        qs = ClaimRequest.objects.select_related('report', 'claimant').order_by('-date_submitted')
        status_f = request.query_params.get('status')
        if status_f in ('pending', 'approved', 'rejected'):
            qs = qs.filter(status=status_f)
        serializer = ClaimRequestSerializer(qs, many=True)
        return Response({'count': qs.count(), 'results': serializer.data})


class AdminClaimDetailView(APIView):
    """
    GET   /api/admin/claims/<id>/
    PATCH /api/admin/claims/<id>/   — approve or reject
    """
    permission_classes = [IsAdminUserRole]

    def _get_claim(self, pk):
        try:
            return ClaimRequest.objects.select_related('report', 'claimant').get(pk=pk)
        except ClaimRequest.DoesNotExist:
            return None

    def get(self, request, pk):
        claim = self._get_claim(pk)
        if not claim:
            return Response({'detail': 'Claim not found.'}, status=404)
        return Response(ClaimRequestSerializer(claim).data)

    def patch(self, request, pk):
        claim = self._get_claim(pk)
        if not claim:
            return Response({'detail': 'Claim not found.'}, status=404)

        new_status     = request.data.get('status')
        admin_response = request.data.get('admin_response', '')

        if new_status not in ('approved', 'rejected'):
            return Response(
                {'status': ['Must be "approved" or "rejected".']},
                status=400,
            )

        claim.status         = new_status
        claim.admin_response = admin_response
        claim.save(update_fields=['status', 'admin_response', 'date_updated'])

        if new_status == 'approved':
            # Set the report to claimed
            claim.report.status = LostReport.STATUS_CLAIMED
            claim.report.save(update_fields=['status', 'date_updated'])

            _fire_notification(
                user=claim.claimant,
                notif_type='claim_approved',
                title='Claim Approved!',
                message=f'Your claim for "{claim.report.item_name}" has been approved. Please coordinate with the finder.',
                report=claim.report,
                claim=claim,
            )
        else:
            _fire_notification(
                user=claim.claimant,
                notif_type='claim_rejected',
                title='Claim Rejected',
                message=f'Your claim for "{claim.report.item_name}" was rejected. Reason: {admin_response or "See admin notes."}',
                report=claim.report,
                claim=claim,
            )

        return Response({'message': f'Claim {new_status}.', 'claim': ClaimRequestSerializer(claim).data})


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ADMIN — AI MATCHING ENGINE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AdminMatchRunView(APIView):
    """
    POST /api/admin/match/run/<report_id>/
    Runs the AI matching engine against a single report.
    Works for both lost and found reports:
      - If report is lost  → searches found reports for matches
      - If report is found → searches lost reports for matches
    Returns up to 5 scored suggestions.
    """
    permission_classes = [IsAdminUserRole]

    def post(self, request, pk):
        try:
            report = LostReport.objects.get(pk=pk)
        except LostReport.DoesNotExist:
            return Response({'detail': 'Report not found.'}, status=404)

        from .matching import find_matches
        suggestions = find_matches(report, top_n=5)

        results = MatchSuggestionSerializer(suggestions, many=True).data
        return Response({
            'report_id': pk,
            'report_type': report.report_type,
            'matches_found': len(results),
            'suggestions': results,
        })


class AdminMatchConfirmView(APIView):
    """
    POST /api/admin/match/confirm/<suggestion_id>/
    Admin confirms a match suggestion.
    - Sets suggestion status to 'confirmed'
    - Sets both reports to 'matched'
    - Links them via matched_report FK
    - Fires notifications to both report owners
    """
    permission_classes = [IsAdminUserRole]

    def post(self, request, pk):
        try:
            suggestion = MatchSuggestion.objects.select_related(
                'lost_report__user', 'found_report__user'
            ).get(pk=pk)
        except MatchSuggestion.DoesNotExist:
            return Response({'detail': 'Suggestion not found.'}, status=404)

        if suggestion.status == MatchSuggestion.STATUS_CONFIRMED:
            return Response({'detail': 'Already confirmed.'}, status=400)

        # Update suggestion
        suggestion.status = MatchSuggestion.STATUS_CONFIRMED
        suggestion.save(update_fields=['status', 'updated_at'])

        # Link and update both reports
        lost  = suggestion.lost_report
        found = suggestion.found_report

        lost.status         = LostReport.STATUS_MATCHED
        lost.matched_report = found
        lost.save(update_fields=['status', 'matched_report', 'date_updated'])

        found.status         = LostReport.STATUS_MATCHED
        found.matched_report = lost
        found.save(update_fields=['status', 'matched_report', 'date_updated'])

        # Notify the owner of the lost item
        _fire_notification(
            user=lost.user,
            notif_type='matched',
            title='Match Found for Your Lost Item!',
            message=f'A found item matching your "{lost.item_name}" report has been identified. An admin will contact you to arrange the return.',
            report=lost,
        )

        # Notify the finder
        _fire_notification(
            user=found.user,
            notif_type='matched',
            title='Owner Found for the Item You Reported!',
            message = f'We have matched your found item "{found.item_name}" with its owner. An admin will contact you shortly.',
            report=found,
        )

        return Response({
            'message': 'Match confirmed. Both reports updated to matched.',
            'suggestion': MatchSuggestionSerializer(suggestion).data,
        })


class AdminMatchDismissView(APIView):
    """
    POST /api/admin/match/dismiss/<suggestion_id>/
    Admin dismisses a suggestion — marks it as not a real match.
    """
    permission_classes = [IsAdminUserRole]

    def post(self, request, pk):
        try:
            suggestion = MatchSuggestion.objects.get(pk=pk)
        except MatchSuggestion.DoesNotExist:
            return Response({'detail': 'Suggestion not found.'}, status=404)

        suggestion.status = MatchSuggestion.STATUS_DISMISSED
        suggestion.save(update_fields=['status', 'updated_at'])
        return Response({'message': 'Suggestion dismissed.'})