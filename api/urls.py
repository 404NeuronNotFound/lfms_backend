from django.urls import path
from .views import RegisterView, LoginView, AdminDashboard, UserDashboard

urlpatterns = [
    path('register/', RegisterView.as_view()),
    path('login/', LoginView.as_view()),
    path('admin-dashboard/', AdminDashboard.as_view()),
    path('user-dashboard/', UserDashboard.as_view()),
]