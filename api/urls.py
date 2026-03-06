from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from .views import (
    RegisterView,
    LoginView,
    AdminDashboard,
    UserDashboard,
    ProfileView,
    LogoutView,
)

urlpatterns = [
    # ── Auth ──────────────────────────────────────────────────────────────
    path("register/",       RegisterView.as_view(),    name="register"),
    path("login/",          LoginView.as_view(),        name="login"),
    path("logout/",         LogoutView.as_view(),       name="logout"),

    # ── JWT token management ──────────────────────────────────────────────
    # POST { "refresh": "<token>" } → { "access": "<new_token>" }
    path("token/refresh/",  TokenRefreshView.as_view(), name="token_refresh"),
    # POST { "token": "<token>" }   → 200 if valid, 401 if not
    path("token/verify/",   TokenVerifyView.as_view(),  name="token_verify"),

    # ── Dashboards ────────────────────────────────────────────────────────
    path("admin-dashboard/", AdminDashboard.as_view(), name="admin_dashboard"),
    path("user-dashboard/",  UserDashboard.as_view(),  name="user_dashboard"),

    # ── Profile ───────────────────────────────────────────────────────────
    path("profile/",        ProfileView.as_view(),     name="profile"),
]