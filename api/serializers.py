from rest_framework import serializers
from django.contrib.auth import get_user_model, authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from .models import UserProfile

User = get_user_model()


# ── Registration ───────────────────────────────────────────────────────────
class RegisterSerializer(serializers.ModelSerializer):
    password         = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    class Meta:
        model  = User
        fields = [
            "username", "first_name", "last_name",
            "email", "password", "confirm_password", "role",
        ]
        extra_kwargs = {"password": {"write_only": True}}

    def validate(self, data):
        if data["password"] != data["confirm_password"]:
            raise serializers.ValidationError({"password": "Passwords do not match."})
        return data

    def create(self, validated_data):
        validated_data.pop("confirm_password")
        return User.objects.create_user(
            username=validated_data["username"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
            email=validated_data.get("email", ""),
            password=validated_data["password"],
            role=validated_data.get("role", "USER"),
            status="active",
        )


# ── Login ─────────────────────────────────────────────────────────────────
class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        user = authenticate(username=data["username"], password=data["password"])

        if not user:
            raise serializers.ValidationError({"non_field_errors": ["Invalid username or password."]})

        # Hard block: banned accounts can never login
        if user.status == "banned":
            raise serializers.ValidationError({
                "non_field_errors": [
                    "Your account has been banned. Please contact support."
                ]
            })

        # Soft block: inactive accounts are re-activated on login
        if user.status == "inactive":
            user.status = "active"
            user.save(update_fields=["status"])

        refresh = RefreshToken.for_user(user)
        return {
            "refresh":  str(refresh),
            "access":   str(refresh.access_token),
            "role":     user.role,
            "username": user.username,
            "status":   user.status,
        }


# ── Profile ────────────────────────────────────────────────────────────────
class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model        = UserProfile
        fields       = ["phone_number", "address", "bio", "avatar"]
        extra_kwargs = {"avatar": {"required": False, "allow_null": True}}

    def to_representation(self, instance):
        ret     = super().to_representation(instance)
        request = self.context.get("request")
        avatar  = instance.avatar
        if avatar:
            try:
                url          = avatar.url
                ret["avatar"] = request.build_absolute_uri(url) if request else url
            except Exception:
                ret["avatar"] = None
        else:
            ret["avatar"] = None
        return ret

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


# ── User (full) ────────────────────────────────────────────────────────────
class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(required=False)

    class Meta:
        model  = User
        fields = [
            "id", "username", "first_name", "last_name",
            "email", "role", "status", "date_joined",
            "last_login", "profile",
        ]

    def to_representation(self, instance):
        # Propagate request context down into nested profile serializer
        self.fields["profile"].context.update(self.context)
        return super().to_representation(instance)

    def update(self, instance, validated_data):
        profile_data = validated_data.pop("profile", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if profile_data is not None:
            profile, _ = UserProfile.objects.get_or_create(user=instance)
            for attr, value in profile_data.items():
                setattr(profile, attr, value)
            profile.save()

        return instance


# ── Admin: lightweight user list ───────────────────────────────────────────
class UserListSerializer(serializers.ModelSerializer):
    """Slim serializer used for the admin All-Users list endpoint."""
    avatar = serializers.SerializerMethodField()
    reports = serializers.SerializerMethodField()   # placeholder — wire to real model later
    claims  = serializers.SerializerMethodField()

    class Meta:
        model  = User
        fields = [
            "id", "username", "first_name", "last_name",
            "email", "role", "status", "date_joined", "last_login",
            "avatar", "reports", "claims",
        ]

    def get_avatar(self, obj):
        request = self.context.get("request")
        try:
            avatar = obj.profile.avatar
            if avatar:
                url = avatar.url
                return request.build_absolute_uri(url) if request else url
        except Exception:
            pass
        return None

    def get_reports(self, obj):
        # Replace with obj.reports.count() once the Report model exists
        return 0

    def get_claims(self, obj):
        # Replace with obj.claims.count() once the Claim model exists
        return 0