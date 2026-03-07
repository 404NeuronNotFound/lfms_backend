from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken

from .models import UserProfile
from .serializers import (
    RegisterSerializer, LoginSerializer,
    UserProfileSerializer, UserSerializer,
)
from .permissions import IsAdminUserRole, IsNormalUserRole
from django.contrib.auth import get_user_model

User = get_user_model()


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "User registered successfully"}, status=201)
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
            return Response(
                {"detail": "Refresh token is required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            token = RefreshToken(refresh_token)
            token.blacklist() 
            return Response({"message": "Logged out successfully."}, status=status.HTTP_205_RESET_CONTENT)
        except (TokenError, InvalidToken) as e:
         
            return Response({"message": "Logged out."}, status=status.HTTP_205_RESET_CONTENT)


class AdminDashboard(APIView):
    permission_classes = [IsAdminUserRole]

    def get(self, request):
        return Response({"message": "Welcome Admin!"})


class UserDashboard(APIView):
    permission_classes = [IsNormalUserRole]

    def get(self, request):
        return Response({"message": "Welcome User!"})


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

        bracket_avatar = "profile[avatar]"
        dot_avatar     = "profile.avatar"
        if bracket_avatar in request.FILES:
            profile_fields["avatar"] = request.FILES[bracket_avatar]
        elif dot_avatar in request.FILES:
            profile_fields["avatar"] = request.FILES[dot_avatar]
        elif "avatar" in request.FILES:
            profile_fields["avatar"] = request.FILES["avatar"]

        if profile_fields:
            data["profile"] = profile_fields

        serializer = UserSerializer(
            request.user,
            data=data,
            partial=True,
            context={"request": request},
        )

        if serializer.is_valid():
            serializer.save()
            return Response({
                "message": "Profile updated successfully",
                "user": serializer.data,
            })

        return Response(serializer.errors, status=400)
    

class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        current_password     = request.data.get("current_password")
        new_password         = request.data.get("new_password")
        confirm_new_password = request.data.get("confirm_new_password")

 
        if not current_password:
            return Response({"current_password": ["Current password is required."]}, status=400)
        if not new_password:
            return Response({"new_password": ["New password is required."]}, status=400)
        if len(new_password) < 6:
            return Response({"new_password": ["Password must be at least 6 characters."]}, status=400)
        if new_password != confirm_new_password:
            return Response({"confirm_new_password": ["Passwords do not match."]}, status=400)

   
        if not request.user.check_password(current_password):
            return Response({"current_password": ["Current password is incorrect."]}, status=400)

  
        request.user.set_password(new_password)
        request.user.save()

        return Response({"message": "Password changed successfully."}, status=200)