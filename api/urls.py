from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from .views import (
    # Auth
    AdminAuditLogView,
    AdminMatchSuggestionsView,
    RegisterView,
    LoginView,
    LogoutView,
    # Dashboards
    AdminDashboard,
    UserDashboard,
    # Profile & password (self)
    ProfileView,
    ChangePasswordView,
    # Account status (self)
    DeactivateAccountView,
    ReactivateAccountView,
    # Admin — user management
    AdminUserListView,
    AdminUserDetailView,
    AdminBanUserView,
    AdminUnbanUserView,
    AdminUserStatsView,
    # User — reports (lost + found)
    UserReportListCreateView,
    UserReportDetailView,
    # User — claims
    UserClaimCreateView,
    UserClaimListView,
    # User — notifications
    UserNotificationListView,
    UserNotificationReadView,
    # Admin — reports
    AdminReportListView,
    AdminReportDetailView,
    AdminReportStatsView,
    # Admin — claims
    AdminClaimListView,
    AdminClaimDetailView,
    # Admin — AI matching
    AdminMatchRunView,
    AdminMatchConfirmView,
    AdminMatchDismissView,
    # Public — browse found items
    BrowseFoundItemsView,
    BrowseFoundItemDetailView,
    # Admin — manual match
    AdminManualMatchView,
    AdminUnmatchView,
    #Public
    PublicStatsView
)

urlpatterns = [

    # ── Auth ──────────────────────────────────────────────────────────────
    path("register/",      RegisterView.as_view(),  name="register"),
    path("login/",         LoginView.as_view(),      name="login"),
    path("logout/",        LogoutView.as_view(),     name="logout"),

    # ── JWT token management ──────────────────────────────────────────────
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("token/verify/",  TokenVerifyView.as_view(),  name="token_verify"),

    # ── Dashboards ────────────────────────────────────────────────────────
    path("admin-dashboard/", AdminDashboard.as_view(), name="admin_dashboard"),
    path("user-dashboard/",  UserDashboard.as_view(),  name="user_dashboard"),

    # ── Profile & password (self) ─────────────────────────────────────────
    path("profile/",          ProfileView.as_view(),        name="profile"),
    path("change-password/",  ChangePasswordView.as_view(), name="change_password"),

    # ── Account status self-service ───────────────────────────────────────
    path("account/deactivate/", DeactivateAccountView.as_view(), name="account_deactivate"),
    path("account/reactivate/", ReactivateAccountView.as_view(), name="account_reactivate"),

    # ── Admin: user management ────────────────────────────────────────────
    path("admin/users/",                AdminUserListView.as_view(),   name="admin_user_list"),
    path("admin/users/stats/",          AdminUserStatsView.as_view(),  name="admin_user_stats"),
    path("admin/users/<int:pk>/",       AdminUserDetailView.as_view(), name="admin_user_detail"),
    path("admin/users/<int:pk>/ban/",   AdminBanUserView.as_view(),    name="admin_ban_user"),
    path("admin/users/<int:pk>/unban/", AdminUnbanUserView.as_view(),  name="admin_unban_user"),

    # ── User: reports (lost + found) ──────────────────────────────────────
    #   POST  ?  report_type=lost|found in body
    #   GET   ?  ?type=lost|found  &status=
    path("reports/",          UserReportListCreateView.as_view(), name="report_list_create"),
    path("reports/<int:pk>/", UserReportDetailView.as_view(),     name="report_detail"),

    # ── User: claims ──────────────────────────────────────────────────────
    path("reports/<int:pk>/claim/", UserClaimCreateView.as_view(), name="claim_create"),
    path("claims/",                 UserClaimListView.as_view(),   name="claim_list"),

    # ── User: notifications ───────────────────────────────────────────────
    path("notifications/",                  UserNotificationListView.as_view(), name="notification_list"),
    path("notifications/read-all/",         UserNotificationReadView.as_view(), name="notification_read_all"),
    path("notifications/<int:pk>/read/",    UserNotificationReadView.as_view(), name="notification_read"),

    # ── Admin: reports ────────────────────────────────────────────────────
    #   GET ?type=lost|found  &status=  &category=  &urgent=true  &search=
    path("admin/reports/",               AdminReportListView.as_view(),   name="admin_report_list"),
    path("admin/reports/stats/",         AdminReportStatsView.as_view(),  name="admin_report_stats"),
    path("admin/reports/<int:pk>/",      AdminReportDetailView.as_view(), name="admin_report_detail"),

    # ── Admin: claims ─────────────────────────────────────────────────────
    path("admin/claims/",            AdminClaimListView.as_view(),   name="admin_claim_list"),
    path("admin/claims/<int:pk>/",   AdminClaimDetailView.as_view(), name="admin_claim_detail"),

    # ── Admin: AI matching engine ─────────────────────────────────────────
    # ── Admin: AI matching engine ─────────────────────────────────────────
    path("admin/match/run/<int:pk>/",         AdminMatchRunView.as_view(),         name="admin_match_run"),
    path("admin/match/confirm/<int:pk>/",     AdminMatchConfirmView.as_view(),     name="admin_match_confirm"),
    path("admin/match/dismiss/<int:pk>/",     AdminMatchDismissView.as_view(),     name="admin_match_dismiss"),
    path("admin/match/suggestions/<int:pk>/", AdminMatchSuggestionsView.as_view(), name="admin_match_suggestions"),

    # ── Manual match ───────────────────────────────────────────────────────
    path("admin/match/manual/",  AdminManualMatchView.as_view(), name="admin_manual_match"),
    path("admin/match/unmatch/", AdminUnmatchView.as_view(),     name="admin_unmatch"),

    # ── Public: browse found items ─────────────────────────────────────────
    path("found-items/",          BrowseFoundItemsView.as_view(),       name="browse_found_items"),
    path("found-items/<int:pk>/", BrowseFoundItemDetailView.as_view(),  name="browse_found_item_detail"),

    path("admin/audit-logs/", AdminAuditLogView.as_view(), name="admin_audit_logs"),

    path("public/stats/", PublicStatsView.as_view(), name="public_stats"),

]