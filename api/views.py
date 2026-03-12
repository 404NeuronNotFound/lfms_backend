from django.contrib.auth import get_user_model
import re
from rest_framework import permissions, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken

from .models import UserProfile
from .serializers import (
    RegisterSerializer,
    LoginSerializer,
    UserSerializer,
    UserListSerializer,
)
from .permissions import IsAdminUserRole
from django.db import models

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
        from django.utils import timezone
        from django.db.models import Count, Avg, Q
        from collections import defaultdict
        import datetime

        User = get_user_model()
        now  = timezone.now()

        # ── Time windows ──────────────────────────────────────────────────────
        start_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start_last_month = (start_this_month - datetime.timedelta(days=1)).replace(day=1)
        week_start       = now - datetime.timedelta(days=6)   # last 7 days incl. today

        # ── Lazy import models (registered below the auth section) ────────────
        from .models import LostReport, ClaimRequest

        # ─── REPORT STATS ────────────────────────────────────────────────────
        total_reports_all     = LostReport.objects.count()
        total_reports_this    = LostReport.objects.filter(date_reported__gte=start_this_month).count()
        total_reports_last    = LostReport.objects.filter(
            date_reported__gte=start_last_month,
            date_reported__lt=start_this_month,
        ).count()

        # Recovery = claimed reports
        claimed_all    = LostReport.objects.filter(status="claimed").count()
        claimed_this   = LostReport.objects.filter(status="claimed", date_reported__gte=start_this_month).count()
        claimed_last   = LostReport.objects.filter(
            status="claimed",
            date_reported__gte=start_last_month,
            date_reported__lt=start_this_month,
        ).count()

        # Pending claims
        pending_claims_now  = ClaimRequest.objects.filter(status="pending").count()
        pending_claims_last = ClaimRequest.objects.filter(
            status="pending",
            date_submitted__gte=start_last_month,
            date_submitted__lt=start_this_month,
        ).count()

        # Active users
        active_users_now  = User.objects.filter(status="active").count()
        active_users_last = User.objects.filter(
            status="active",
            date_joined__gte=start_last_month,
            date_joined__lt=start_this_month,
        ).count()

        def delta(current, previous):
            if previous == 0:
                return 100.0 if current > 0 else 0.0
            return round((current - previous) / previous * 100, 1)

        # ── WEEKLY ACTIVITY (last 7 days) ────────────────────────────────────
        day_labels = []
        day_counts = defaultdict(int)
        for i in range(6, -1, -1):
            d = (now - datetime.timedelta(days=i)).date()
            day_labels.append(d)

        reports_last_week = LostReport.objects.filter(
            date_reported__date__gte=day_labels[0],
        ).values_list("date_reported", flat=True)

        for dt in reports_last_week:
            day_counts[dt.date()] += 1

        weekly_activity = [
            {
                "day":   d.strftime("%a"),
                "count": day_counts.get(d, 0),
            }
            for d in day_labels
        ]

        # ── TOP LOCATIONS (top 5 by report count) ────────────────────────────
        top_locs_qs = (
            LostReport.objects
            .values("location")
            .annotate(count=Count("id"))
            .order_by("-count")[:5]
        )
        top_locations = [{"name": row["location"], "count": row["count"]} for row in top_locs_qs]

        # ── RECENT REPORTS (last 7) ───────────────────────────────────────────
        recent_qs = LostReport.objects.select_related("user").order_by("-date_reported")[:7]
        recent_reports = []
        for r in recent_qs:
            # Best match score from pending suggestions
            best_score = None
            try:
                from .models import MatchSuggestion
                suggestion = MatchSuggestion.objects.filter(
                    Q(lost_report=r) | Q(found_report=r),
                    status="pending",
                ).order_by("-score").first()
                if suggestion:
                    best_score = round(suggestion.score * 100)
            except Exception:
                pass

            recent_reports.append({
                "id":            r.id,
                "item_name":     r.item_name,
                "report_type":   r.report_type,
                "location":      r.location,
                "date_reported": r.date_reported.isoformat(),
                "status":        r.status,
                "match_score":   best_score,
                "username":      r.user.username if r.user else "—",
            })

        # ── RECENT USERS (last 4 joined) ──────────────────────────────────────
        recent_users_qs = User.objects.select_related("profile").order_by("-date_joined")[:4]
        recent_users = []
        for u in recent_users_qs:
            avatar = None
            try:
                if u.profile and u.profile.avatar:
                    avatar = request.build_absolute_uri(u.profile.avatar.url)
            except Exception:
                pass
            recent_users.append({
                "id":          u.id,
                "full_name":   f"{u.first_name} {u.last_name}".strip() or u.username,
                "username":    u.username,
                "role":        u.role,
                "date_joined": u.date_joined.isoformat(),
                "reports":     LostReport.objects.filter(user=u).count(),
                "avatar":      avatar,
            })

        # ── RECOVERY BREAKDOWN ────────────────────────────────────────────────
        matched_count = LostReport.objects.filter(status="matched").count()
        open_count    = LostReport.objects.filter(status__in=["open", "under_review"]).count()
        recovery_rate = round(claimed_all / total_reports_all * 100, 1) if total_reports_all else 0

        return Response({
            "stats": {
                "total_reports": {
                    "label":     "Total Reports",
                    "value":     total_reports_all,
                    "delta_pct": delta(total_reports_this, total_reports_last),
                    "sub":       "vs last month",
                },
                "items_recovered": {
                    "label":     "Items Recovered",
                    "value":     claimed_all,
                    "delta_pct": delta(claimed_this, claimed_last),
                    "sub":       "vs last month",
                },
                "pending_claims": {
                    "label":     "Pending Claims",
                    "value":     pending_claims_now,
                    "delta_pct": delta(pending_claims_now, pending_claims_last),
                    "sub":       "needs review",
                },
                "active_users": {
                    "label":     "Active Users",
                    "value":     active_users_now,
                    "delta_pct": delta(active_users_now, active_users_last),
                    "sub":       "registered accounts",
                },
            },
            "weekly_activity":    weekly_activity,
            "top_locations":      top_locations,
            "recent_reports":     recent_reports,
            "recent_users":       recent_users,
            "recovery_rate":      recovery_rate,
            "recovery_breakdown": {
                "claimed": claimed_all,
                "matched": matched_count,
                "pending": open_count,
            },
            "total_reports": total_reports_all,
        })


class UserDashboard(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.status == "banned":
            return Response({"detail": "Your account has been banned."}, status=403)
        if request.user.status == "inactive":
            return Response({"detail": "Your account is deactivated."}, status=403)

        from django.utils import timezone
        from .models import LostReport, ClaimRequest, Notification
        import datetime

        user = request.user
        now  = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # ── Report counts ──────────────────────────────────────────────────
        user_reports       = LostReport.objects.filter(user=user)
        total_reports      = user_reports.count()
        open_reports       = user_reports.filter(status__in=["open", "under_review"]).count()
        matched_reports    = user_reports.filter(status="matched").count()
        claimed_reports    = user_reports.filter(status="claimed").count()
        reports_this_month = user_reports.filter(date_reported__gte=month_start).count()

        # ── Claim counts ───────────────────────────────────────────────────
        user_claims     = ClaimRequest.objects.filter(claimant=user)
        total_claims    = user_claims.count()
        pending_claims  = user_claims.filter(status="pending").count()
        approved_claims = user_claims.filter(status="approved").count()

        # ── Unread notifications ───────────────────────────────────────────
        unread_notifs = Notification.objects.filter(user=user, is_read=False).count()

        # ── Recent reports (last 5) ────────────────────────────────────────
        recent_reports_qs = user_reports.order_by("-date_reported")[:5]
        recent_reports = []
        for r in recent_reports_qs:
            best_score = None
            try:
                from .models import MatchSuggestion
                from django.db.models import Q
                sugg = MatchSuggestion.objects.filter(
                    Q(lost_report=r) | Q(found_report=r), status="pending"
                ).order_by("-score").first()
                if sugg:
                    best_score = round(sugg.score * 100)
            except Exception:
                pass

            recent_reports.append({
                "id":             r.id,
                "item_name":      r.item_name,
                "report_type":    r.report_type,
                "category":       r.category,
                "location":       r.location,
                "status":         r.status,
                "date_reported":  r.date_reported.isoformat(),
                "is_urgent":      r.is_urgent,
                "match_score":    best_score,
            })

        # ── Recent claims (last 3) ─────────────────────────────────────────
        recent_claims_qs = user_claims.select_related("report").order_by("-date_submitted")[:3]
        recent_claims = []
        for c in recent_claims_qs:
            recent_claims.append({
                "id":             c.id,
                "item_name":      c.report.item_name if c.report else "—",
                "report_type":    c.report.report_type if c.report else "found",
                "status":         c.status,
                "date_submitted": c.date_submitted.isoformat(),
                "admin_response": c.admin_response,
            })

        # ── Recent notifications (last 4, unread first) ───────────────────
        recent_notifs_qs = Notification.objects.filter(
            user=user
        ).order_by("is_read", "-created_at")[:4]
        recent_notifs = [
            {
                "id":         n.id,
                "type":       n.notif_type,
                "title":      n.title,
                "message":    n.message,
                "is_read":    n.is_read,
                "created_at": n.created_at.isoformat(),
            }
            for n in recent_notifs_qs
        ]

        # ── Avatar ─────────────────────────────────────────────────────────
        avatar = None
        try:
            if user.profile and user.profile.avatar:
                avatar = request.build_absolute_uri(user.profile.avatar.url)
        except Exception:
            pass

        return Response({
            "user": {
                "id":          user.id,
                "username":    user.username,
                "full_name":   f"{user.first_name} {user.last_name}".strip() or user.username,
                "first_name":  user.first_name,
                "email":       user.email,
                "date_joined": user.date_joined.isoformat(),
                "avatar":      avatar,
            },
            "stats": {
                "total_reports":      total_reports,
                "open_reports":       open_reports,
                "matched_reports":    matched_reports,
                "claimed_reports":    claimed_reports,
                "reports_this_month": reports_this_month,
                "total_claims":       total_claims,
                "pending_claims":     pending_claims,
                "approved_claims":    approved_claims,
                "unread_notifs":      unread_notifs,
            },
            "recent_reports": recent_reports,
            "recent_claims":  recent_claims,
            "recent_notifs":  recent_notifs,
        })


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

        # Notify all admins: new report submitted
        for admin_user in User.objects.filter(role='ADMIN'):
            _fire_notification(
                user=admin_user,
                notif_type='new_report',
                title=f'New {type_label} Report',
                message=f'{request.user.get_full_name() or request.user.username} submitted a {report.report_type} report for \"{report.item_name}\" at {report.location}.',
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
            report = LostReport.objects.select_related('user').get(pk=pk)
        except LostReport.DoesNotExist:
            return Response({'detail': 'Report not found.'}, status=404)

        if report.report_type != 'found':
            return Response(
                {'detail': 'Claims can only be submitted for found item reports.'},
                status=400,
            )

        if report.user_id == request.user.pk:
            return Response(
                {'detail': 'You cannot claim an item you reported as found.'},
                status=400,
            )

        if report.status != LostReport.STATUS_MATCHED:
            return Response(
                {'detail': 'This item can only be claimed once an admin has matched it with a lost report.'},
                status=400,
            )

        # Prevent duplicate claims — block only if a pending or approved claim exists
        existing = ClaimRequest.objects.filter(
            report=report,
            claimant=request.user,
            status__in=[ClaimRequest.STATUS_PENDING, ClaimRequest.STATUS_APPROVED],
        ).exists()
        if existing:
            return Response(
                {'detail': 'You already have an active claim for this report.'},
                status=400,
            )

        serializer = ClaimRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        claim = serializer.save(report=report, claimant=request.user)

        # Auto-set status to under_review when a claim comes in:
        # - open → under_review (standard flow)
        # - matched → under_review (claim submitted after admin matched, keep matched_report link)
        # under_review stays as-is (already in review)
        if report.status in (LostReport.STATUS_OPEN, LostReport.STATUS_MATCHED):
            LostReport.objects.filter(pk=report.pk).update(status=LostReport.STATUS_UNDER_REVIEW)

            # If matched, also set the partner to under_review so admin sees both need review
            # The matched_report FK is preserved — link is NOT broken
            if report.status == LostReport.STATUS_MATCHED and report.matched_report_id:
                LostReport.objects.filter(pk=report.matched_report_id).update(
                    status=LostReport.STATUS_UNDER_REVIEW
                )

        # Notify the claimant
        _fire_notification(
            user=request.user,
            notif_type='claim_received',
            title='Claim Submitted',
            message=f'Your claim for "{report.item_name}" has been submitted and is pending admin review.',
            report=report,
            claim=claim,
        )

        # Notify all admins: new claim needs review
        for admin_user in User.objects.filter(role='ADMIN'):
            _fire_notification(
                user=admin_user,
                notif_type='new_claim',
                title='New Claim Requires Review',
                message=f'{request.user.get_full_name() or request.user.username} submitted a claim for \"{report.item_name}\". Review it in Admin Claims.',
                report=report,
                claim=claim,
            )

        return Response(ClaimRequestSerializer(claim, context={'request': request}).data, status=201)


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

            # Sync certain status changes to the matched partner report
            # matched → partner also becomes matched (keeps them in sync)
            # claimed → partner also becomes claimed
            # closed  → partner also becomes closed
            # under_review → do NOT sync (each report reviewed independently)
            SYNC_TO_PARTNER = {
                LostReport.STATUS_MATCHED: LostReport.STATUS_MATCHED,
                LostReport.STATUS_CLAIMED: LostReport.STATUS_CLAIMED,
                LostReport.STATUS_CLOSED:  LostReport.STATUS_CLOSED,
            }
            if new_status in SYNC_TO_PARTNER and report.matched_report_id:
                try:
                    partner = LostReport.objects.get(pk=report.matched_report_id)
                    if partner.status != new_status:
                        partner.status = new_status
                        partner.save(update_fields=['status', 'date_updated'])
                        _handle_status_notification(partner, new_status)
                except LostReport.DoesNotExist:
                    pass

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
        qs = ClaimRequest.objects.select_related('report', 'claimant', 'claimant__profile').order_by('-date_submitted')
        status_f = request.query_params.get('status')
        if status_f in ('pending', 'approved', 'rejected'):
            qs = qs.filter(status=status_f)
        serializer = ClaimRequestSerializer(qs, many=True, context={'request': request})
        return Response({'count': qs.count(), 'results': serializer.data})


class AdminClaimDetailView(APIView):
    """
    GET   /api/admin/claims/<id>/
    PATCH /api/admin/claims/<id>/   — approve or reject
    """
    permission_classes = [IsAdminUserRole]

    def _get_claim(self, pk):
        try:
            return ClaimRequest.objects.select_related('report', 'claimant', 'claimant__profile').get(pk=pk)
        except ClaimRequest.DoesNotExist:
            return None

    def get(self, request, pk):
        claim = self._get_claim(pk)
        if not claim:
            return Response({'detail': 'Claim not found.'}, status=404)
        return Response(ClaimRequestSerializer(claim, context={'request': request}).data)

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
            # Set the found report to claimed
            found_report = claim.report
            found_report.status = LostReport.STATUS_CLAIMED
            found_report.save(update_fields=['status', 'date_updated'])

            # If there's a matched lost report, also set it to claimed (stays linked)
            if found_report.matched_report_id:
                try:
                    lost_report = LostReport.objects.get(pk=found_report.matched_report_id)
                    if lost_report.status != LostReport.STATUS_CLAIMED:
                        lost_report.status = LostReport.STATUS_CLAIMED
                        lost_report.save(update_fields=['status', 'date_updated'])
                        _fire_notification(
                            user=lost_report.user,
                            notif_type='claim_approved',
                            title='Your Lost Item Has Been Returned!',
                            message=f'The claim for your lost "{lost_report.item_name}" has been approved. Please coordinate with the admin.',
                            report=lost_report,
                        )
                except LostReport.DoesNotExist:
                    pass

            _fire_notification(
                user=claim.claimant,
                notif_type='claim_approved',
                title='Claim Approved!',
                message=f'Your claim for "{found_report.item_name}" has been approved. Please coordinate with the finder.',
                report=found_report,
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

        return Response({'message': f'Claim {new_status}.', 'claim': ClaimRequestSerializer(claim, context={'request': request}).data})


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ADMIN — AI MATCHING ENGINE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AdminMatchSuggestionsView(APIView):
    """
    GET /api/admin/match/suggestions/<report_id>/
    Returns existing (non-dismissed) suggestions for a report without re-running the engine.
    Useful to restore the panel state after opening/closing the drawer.
    """
    permission_classes = [IsAdminUserRole]

    def get(self, request, pk):
        try:
            report = LostReport.objects.get(pk=pk)
        except LostReport.DoesNotExist:
            return Response({'detail': 'Report not found.'}, status=404)

        if report.report_type == 'lost':
            suggestions = MatchSuggestion.objects.filter(
                lost_report=report,
            ).exclude(status=MatchSuggestion.STATUS_DISMISSED).select_related(
                'lost_report', 'found_report'
            ).order_by('-score')
        else:
            suggestions = MatchSuggestion.objects.filter(
                found_report=report,
            ).exclude(status=MatchSuggestion.STATUS_DISMISSED).select_related(
                'lost_report', 'found_report'
            ).order_by('-score')

        results = MatchSuggestionSerializer(suggestions, many=True).data
        return Response({
            'report_id': pk,
            'report_type': report.report_type,
            'matches_found': len(results),
            'suggestions': results,
        })


class AdminMatchRunView(APIView):
    """
    POST /api/admin/match/run/<report_id>/
    Uses Claude AI to score candidate reports against the given report.
    Returns up to 5 suggestions with scores — NO DB writes until admin confirms.
    """
    permission_classes = [IsAdminUserRole]

    def post(self, request, pk):
        import json, os, urllib.request, urllib.error

        try:
            report = LostReport.objects.get(pk=pk)
        except LostReport.DoesNotExist:
            return Response({'detail': 'Report not found.'}, status=404)

        # ── Fetch candidates ──────────────────────────────────────────────
        ACTIVE = [LostReport.STATUS_OPEN, LostReport.STATUS_UNDER_REVIEW, LostReport.STATUS_MATCHED]
        if report.report_type == LostReport.TYPE_LOST:
            candidates = LostReport.objects.filter(report_type=LostReport.TYPE_FOUND, status__in=ACTIVE).exclude(pk=pk)
        else:
            candidates = LostReport.objects.filter(report_type=LostReport.TYPE_LOST, status__in=ACTIVE).exclude(pk=pk)

        if not candidates.exists():
            return Response({'report_id': pk, 'report_type': report.report_type, 'matches_found': 0, 'suggestions': []})

        # ── Build prompt ──────────────────────────────────────────────────
        def report_block(r):
            return (
                f"ID: {r.id}\n"
                f"Type: {r.report_type}\n"
                f"Item: {r.item_name}\n"
                f"Category: {r.category}\n"
                f"Description: {getattr(r, 'description', '') or ''}\n"
                f"Location: {r.location}\n"
                f"Date: {r.date_event}\n"
                f"Status: {r.status}"
            )

        candidates_text = "\n\n".join(
            f"--- Candidate {i+1} ---\n{report_block(c)}"
            for i, c in enumerate(candidates[:20])  # cap at 20 to keep prompt small
        )

        system_prompt = """You are a lost-and-found matching assistant for a Filipino university/mall system.
Your job is to compare a query report against candidate reports and score how likely they are the same item.

Reports may be written in English, Bisaya (Cebuano), Tagalog, or a mix.
Common Bisaya terms: nawala=lost, nakita/nakit-an=found, selpon/telepono=phone, pitaka=wallet,
susi/yabi=key, pula=red, itom=black, puti=white, asul=blue, berde=green, gamay=small, dako=big,
bag-o=new, daan/luma=old, guba/sira=broken, eskwelahan=school, palengke=market, simbahan=church.

Score each candidate 0.0–1.0 based on:
- category: same type of item? (0 or 1)
- name: how similar are the item names? (0–1)
- description: how similar are the descriptions? (0–1, use 0.3 if either is blank)
- location: same or nearby location? (0–1)
- date: how close are the dates? same day=1.0, each day apart reduces score, >10 days=0

Return ONLY valid JSON — no markdown, no explanation — in this exact format:
{
  "suggestions": [
    {
      "candidate_id": <int>,
      "score": <float 0-1>,
      "confidence": "<high|medium|low>",
      "reasoning": "<one short sentence in English>",
      "breakdown": {
        "category": <float>,
        "name": <float>,
        "description": <float>,
        "location": <float>,
        "date": <float>
      }
    }
  ]
}

Rules:
- Include only candidates with score >= 0.25
- Sort by score descending
- Return at most 5 suggestions
- confidence: high >= 0.72, medium >= 0.48, low < 0.48
- If category is different, cap total score at 0.42"""

        user_prompt = f"""QUERY REPORT (the one we are matching FOR):
{report_block(report)}

CANDIDATES (possible matches):
{candidates_text}

Score each candidate against the query report and return JSON."""

        # ── Call Claude API ───────────────────────────────────────────────
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return Response({
                'report_id': pk,
                'report_type': report.report_type,
                'matches_found': 0,
                'suggestions': [],
                'ai_error': 'ANTHROPIC_API_KEY is not configured on the server. Set the environment variable and restart Django.',
            }, status=503)

        payload = json.dumps({
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 1024,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }).encode()

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = json.loads(resp.read())
            ai_text = raw["content"][0]["text"].strip()
            # Strip any accidental markdown fences
            ai_text = re.sub(r"^```[a-z]*\n?", "", ai_text, flags=re.MULTILINE)
            ai_text = re.sub(r"\n?```$", "", ai_text, flags=re.MULTILINE)
            ai_result = json.loads(ai_text)
        except Exception as e:
            return Response({
                'report_id': pk,
                'report_type': report.report_type,
                'matches_found': 0,
                'suggestions': [],
                'ai_error': f'Claude API error: {str(e)}',
            }, status=502)

        # ── Build response in the same shape as MatchSuggestionSerializer ─
        # We DON'T write to DB here — only write on confirm.
        # We map candidate_id back to real report objects for summaries.
        candidate_map = {c.id: c for c in candidates[:20]}

        def report_summary(r):
            return {
                'id': r.id, 'item_name': r.item_name,
                'category': r.category, 'location': r.location,
                'date_event': str(r.date_event), 'status': r.status,
            }

        suggestions_out = []
        for s in ai_result.get("suggestions", [])[:5]:
            cid = s.get("candidate_id")
            candidate = candidate_map.get(cid)
            if not candidate:
                continue

            lost_r  = report   if report.report_type   == LostReport.TYPE_LOST  else candidate
            found_r = candidate if report.report_type   == LostReport.TYPE_LOST  else report

            # Look up existing MatchSuggestion row (if any) so confirm still works
            existing = MatchSuggestion.objects.filter(
                lost_report=lost_r, found_report=found_r
            ).first()

            suggestions_out.append({
                'id':                  existing.pk if existing else None,
                'lost_report':         lost_r.pk,
                'found_report':        found_r.pk,
                'lost_report_summary':  report_summary(lost_r),
                'found_report_summary': report_summary(found_r),
                'score':               round(float(s.get("score", 0)), 4),
                'confidence':          s.get("confidence", "low"),
                'reasoning':           s.get("reasoning", ""),
                'score_breakdown':     s.get("breakdown", {}),
                'status':              existing.status if existing else 'pending',
            })

        return Response({
            'report_id':     pk,
            'report_type':   report.report_type,
            'matches_found': len(suggestions_out),
            'suggestions':   suggestions_out,
        })


class AdminMatchConfirmView(APIView):
    """
    POST /api/admin/match/confirm/<suggestion_id>/
    Two modes:
    A) pk > 0  -> normal: look up existing MatchSuggestion by PK
    B) pk == 0 -> AI path: body must contain lost_report_id, found_report_id,
                  score, confidence, score_breakdown. Creates the row on-the-fly.
    """
    permission_classes = [IsAdminUserRole]

    def post(self, request, pk):
        from django.db import transaction

        with transaction.atomic():
            if pk == 0:
                lost_id  = request.data.get('lost_report_id')
                found_id = request.data.get('found_report_id')
                if not lost_id or not found_id:
                    return Response({'detail': 'lost_report_id and found_report_id required.'}, status=400)
                try:
                    lost  = LostReport.objects.select_related('user').get(pk=lost_id)
                    found = LostReport.objects.select_related('user').get(pk=found_id)
                except LostReport.DoesNotExist:
                    return Response({'detail': 'Report not found.'}, status=404)
                suggestion, _ = MatchSuggestion.objects.get_or_create(
                    lost_report=lost,
                    found_report=found,
                    defaults={
                        'score':           float(request.data.get('score', 1.0)),
                        'score_breakdown': request.data.get('score_breakdown', {}),
                        'confidence':      request.data.get('confidence', 'high'),
                        'status':          MatchSuggestion.STATUS_PENDING,
                    },
                )
            else:
                try:
                    suggestion = MatchSuggestion.objects.select_related(
                        'lost_report__user', 'found_report__user'
                    ).get(pk=pk)
                except MatchSuggestion.DoesNotExist:
                    return Response({'detail': 'Suggestion not found.'}, status=404)
                lost  = suggestion.lost_report
                found = suggestion.found_report

            if suggestion.status == MatchSuggestion.STATUS_CONFIRMED:
                return Response({'detail': 'Already confirmed.'}, status=400)

            suggestion.status = MatchSuggestion.STATUS_CONFIRMED
            suggestion.save(update_fields=['status', 'updated_at'])

            lost.status         = LostReport.STATUS_MATCHED
            lost.matched_report = found
            lost.save(update_fields=['status', 'matched_report', 'date_updated'])

            found.status         = LostReport.STATUS_MATCHED
            found.matched_report = lost
            found.save(update_fields=['status', 'matched_report', 'date_updated'])

        _fire_notification(
            user=lost.user, notif_type='matched',
            title='Match Found for Your Lost Item!',
            message=f'A found item matching your "{lost.item_name}" has been identified. An admin will contact you.',
            report=lost,
        )
        _fire_notification(
            user=found.user, notif_type='matched',
            title='Owner Found for the Item You Reported!',
            message=f'We matched your found "{found.item_name}" with its owner. An admin will contact you shortly.',
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



class AdminManualMatchView(APIView):
    """
    POST /api/admin/match/manual/
    Admin manually links a lost report and a found report as a confirmed match.
    No AI suggestion needed — admin does it directly from AllReports.

    Body: { lost_report_id: int, found_report_id: int }

    - Sets both reports status → 'matched'
    - Links them via matched_report FK
    - Creates a MatchSuggestion record (confirmed) for audit trail
    - Fires notifications to both owners
    """
    permission_classes = [IsAdminUserRole]

    def post(self, request):
        lost_id  = request.data.get('lost_report_id')
        found_id = request.data.get('found_report_id')

        if not lost_id or not found_id:
            return Response({'detail': 'Both lost_report_id and found_report_id are required.'}, status=400)

        try:
            lost = LostReport.objects.select_related('user').get(pk=lost_id, report_type='lost')
        except LostReport.DoesNotExist:
            return Response({'detail': 'Lost report not found.'}, status=404)

        try:
            found = LostReport.objects.select_related('user').get(pk=found_id, report_type='found')
        except LostReport.DoesNotExist:
            return Response({'detail': 'Found report not found.'}, status=404)

        if lost.status == LostReport.STATUS_MATCHED:
            return Response({'detail': 'This lost report is already matched.'}, status=400)

        if found.status == LostReport.STATUS_MATCHED:
            return Response({'detail': 'This found report is already matched.'}, status=400)

        # Link both reports
        lost.status         = LostReport.STATUS_MATCHED
        lost.matched_report = found
        lost.save(update_fields=['status', 'matched_report', 'date_updated'])

        found.status         = LostReport.STATUS_MATCHED
        found.matched_report = lost
        found.save(update_fields=['status', 'matched_report', 'date_updated'])

        # Create a MatchSuggestion record for audit trail (score=1.0 = manual/confirmed)
        suggestion = MatchSuggestion.objects.create(
            lost_report=lost,
            found_report=found,
            score=1.0,
            status=MatchSuggestion.STATUS_CONFIRMED,
        )

        # Notify the owner of the lost item
        _fire_notification(
            user=lost.user,
            notif_type='matched',
            title='Match Found for Your Lost Item!',
            message=f'A found item matching your "{lost.item_name}" has been identified. Check Browse Items to submit your claim.',
            report=lost,
        )

        # Notify the finder
        _fire_notification(
            user=found.user,
            notif_type='matched',
            title='Owner Found for the Item You Reported!',
            message=f'We have matched your found "{found.item_name}" report with its owner. An admin will contact you shortly.',
            report=found,
        )

        return Response({
            'message': 'Reports manually matched successfully.',
            'lost_report_id':  lost.pk,
            'found_report_id': found.pk,
            'suggestion_id':   suggestion.pk,
        }, status=201)


class AdminUnmatchView(APIView):
    """
    POST /api/admin/match/unmatch/
    Admin undoes a manual or AI match, resetting both reports back to open.

    Body: { report_id: int }  — either the lost or found report id
    """
    permission_classes = [IsAdminUserRole]

    def post(self, request):
        report_id = request.data.get('report_id')
        if not report_id:
            return Response({'detail': 'report_id is required.'}, status=400)

        try:
            report = LostReport.objects.select_related('matched_report').get(pk=report_id)
        except LostReport.DoesNotExist:
            return Response({'detail': 'Report not found.'}, status=404)

        if report.status != LostReport.STATUS_MATCHED:
            return Response({'detail': 'Report is not currently matched.'}, status=400)

        partner = report.matched_report

        report.status         = LostReport.STATUS_OPEN
        report.matched_report = None
        report.save(update_fields=['status', 'matched_report', 'date_updated'])

        if partner:
            partner.status         = LostReport.STATUS_OPEN
            partner.matched_report = None
            partner.save(update_fields=['status', 'matched_report', 'date_updated'])

        return Response({'message': 'Match undone. Both reports reset to open.'})

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  PUBLIC — BROWSE FOUND ITEMS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class BrowseFoundItemsView(APIView):
    """
    GET /api/found-items/
    Public listing of all found reports with status=open/under_review/matched.
    ?category=  ?search=  ?ordering=
    Authentication optional — if a valid token is present, my_claim_status
    is populated per item. Invalid/expired tokens are ignored gracefully.

    IMPORTANT: For AllowAny + JWT to coexist without 401 on bad tokens,
    add to settings.py REST_FRAMEWORK:
      'DEFAULT_AUTHENTICATION_CLASSES': [
          'rest_framework_simplejwt.authentication.JWTAuthentication',
      ]
    and in SIMPLE_JWT:
      'AUTH_HEADER_TYPES': ('Bearer',),
    DRF will skip auth (not reject) if no/invalid token when AllowAny is set,
    AS LONG AS you don't have UNAUTHENTICATED_USER raising exceptions.
    """
    permission_classes    = [permissions.AllowAny]
    authentication_classes = [JWTAuthentication]  # Optional auth — populates request.user if token present

    def get(self, request):
        qs = (
            LostReport.objects
            .filter(report_type='found', status__in=['open', 'under_review', 'matched'])
            .prefetch_related('images')
            .select_related('user')
            .order_by('-date_reported')
        )

        category_f = request.query_params.get('category', '').strip()
        search_f   = request.query_params.get('search',   '').strip()
        ordering_f = request.query_params.get('ordering', '-date_reported')

        if category_f:
            qs = qs.filter(category=category_f)
        if search_f:
            from django.db.models import Q
            qs = qs.filter(
                Q(item_name__icontains=search_f) |
                Q(location__icontains=search_f)  |
                Q(description__icontains=search_f)
            )

        allowed = {'-date_reported', 'date_reported', '-views', 'views', 'item_name'}
        if ordering_f in allowed:
            qs = qs.order_by(ordering_f)

        # Increment views counter tracked per session (simple approach)
        total = qs.count()
        serializer = ReportListSerializer(qs, many=True, context={'request': request})
        data = serializer.data

        # If authenticated, annotate whether user already has a pending claim
        if request.user and request.user.is_authenticated:
            # Get the most recent claim status per report for this user
            user_claims = (
                ClaimRequest.objects
                .filter(claimant=request.user)
                .order_by('-date_submitted')
                .values('report_id', 'status')
            )
            # Keep only the latest claim per report_id
            claim_status_map = {}
            for c in user_claims:
                if c['report_id'] not in claim_status_map:
                    claim_status_map[c['report_id']] = c['status']
            for item in data:
                item['my_claim_status'] = claim_status_map.get(item['id'], None)
                item['is_own_report']   = (item.get('user_info', {}).get('id') == request.user.id)
        else:
            for item in data:
                item['my_claim_status'] = None
                item['is_own_report']   = False

        return Response({'count': total, 'results': data})


class BrowseFoundItemDetailView(APIView):
    """
    GET /api/found-items/<id>/
    Public detail view of a single found report.
    Increments view counter.
    """
    permission_classes    = [permissions.AllowAny]
    authentication_classes = [JWTAuthentication]  # Optional auth — populates request.user if token present

    def get(self, request, pk):
        try:
            report = (
                LostReport.objects
                .filter(report_type='found', status__in=['open', 'under_review', 'matched'])
                .prefetch_related('images')
                .select_related('user')
                .get(pk=pk)
            )
        except LostReport.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=404)

        # Increment view count
        LostReport.objects.filter(pk=pk).update(views=models.F('views') + 1)

        serializer = ReportSerializer(report, context={'request': request})
        data = serializer.data

        if request.user and request.user.is_authenticated:
            latest_claim = (
                ClaimRequest.objects
                .filter(report=report, claimant=request.user)
                .order_by('-date_submitted')
                .first()
            )
            data['my_claim_status'] = latest_claim.status if latest_claim else None
            data['is_own_report']   = (report.user_id == request.user.id)
        else:
            data['my_claim_status'] = None
            data['is_own_report']   = False

        return Response(data)