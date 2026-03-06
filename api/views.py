from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from .models import UserProfile
from .serializers import RegisterSerializer, LoginSerializer, UserProfileSerializer, UserSerializer
from django.contrib.auth import get_user_model
from .permissions import IsAdminUserRole, IsNormalUserRole
from rest_framework.permissions import IsAuthenticated


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
        # Ensure user has a profile
        profile, _ = UserProfile.objects.get_or_create(user=request.user)

        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    def patch(self, request):
        # Ensure user has a profile
        profile, _ = UserProfile.objects.get_or_create(user=request.user)

        serializer = UserSerializer(
            request.user,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=400)