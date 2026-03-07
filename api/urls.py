from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from .views import (
    AdminReportListView,
    ChangePasswordView,
    DeactivateAccountView,
    ReactivateAccountView,
    RegisterView,
    LoginView,
    AdminDashboard,
    UserDashboard,
    ProfileView,
    LogoutView,
    AdminUserListView,
    AdminUserStatsView,
    AdminUserDetailView,
    AdminBanUserView,
    AdminUnbanUserView,
    UserReportListCreateView,
    UserReportDetailView,
    AdminReportStatsView,
    AdminReportDetailView,
    
)

urlpatterns = [

    path("register/",       RegisterView.as_view(),    name="register"),
    path("login/",          LoginView.as_view(),        name="login"),
    path("logout/",         LogoutView.as_view(),       name="logout"),


    path("token/refresh/",  TokenRefreshView.as_view(), name="token_refresh"),

    path("token/verify/",   TokenVerifyView.as_view(),  name="token_verify"),


    path("admin-dashboard/", AdminDashboard.as_view(), name="admin_dashboard"),
    path("user-dashboard/",  UserDashboard.as_view(),  name="user_dashboard"),

    path("profile/",        ProfileView.as_view(),     name="profile"),

    path("change-password/", ChangePasswordView.as_view(), name="change_password"),

    path("account/deactivate/",  DeactivateAccountView.as_view(),  name="account_deactivate"),
    path("account/reactivate/",  ReactivateAccountView.as_view(),  name="account_reactivate"),

    path("admin/users/",              AdminUserListView.as_view(),   name="admin_user_list"),
    path("admin/users/stats/",        AdminUserStatsView.as_view(),  name="admin_user_stats"),
    path("admin/users/<int:pk>/",     AdminUserDetailView.as_view(), name="admin_user_detail"),
    path("admin/users/<int:pk>/ban/", AdminBanUserView.as_view(),    name="admin_ban_user"),
    path("admin/users/<int:pk>/unban/",AdminUnbanUserView.as_view(), name="admin_unban_user"),
    
     # ── User: lost reports ────────────────────────────────────────────────
    path("reports/",          UserReportListCreateView.as_view(), name="report_list_create"),
    path("reports/<int:pk>/", UserReportDetailView.as_view(),     name="report_detail"),

    # ── Admin: lost reports ───────────────────────────────────────────────
    path("admin/reports/",               AdminReportListView.as_view(),   name="admin_report_list"),
    path("admin/reports/stats/",         AdminReportStatsView.as_view(),  name="admin_report_stats"),
    path("admin/reports/<int:pk>/",      AdminReportDetailView.as_view(), name="admin_report_detail"),
]