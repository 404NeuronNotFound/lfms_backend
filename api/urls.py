from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from .views import (
    ChangePasswordView,
    RegisterView,
    LoginView,
    AdminDashboard,
    UserDashboard,
    ProfileView,
    LogoutView,
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
]