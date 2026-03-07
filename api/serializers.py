from rest_framework import serializers
from django.contrib.auth import get_user_model, authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from .models import UserProfile

User = get_user_model()

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


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        user = authenticate(username=data["username"], password=data["password"])

        if not user:
            raise serializers.ValidationError({"non_field_errors": ["Invalid username or password."]})

        if user.status == "banned":
            raise serializers.ValidationError({
                "non_field_errors": [
                    "Your account has been banned. Please contact support."
                ]
            })

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



class UserListSerializer(serializers.ModelSerializer):
    """
    Serializer for GET /admin/users/
    Returns a nested `profile` object so the frontend ApiUser type is satisfied:
      { phone_number, address, bio, avatar }
    """
    profile = serializers.SerializerMethodField()
    reports = serializers.SerializerMethodField()   
    claims  = serializers.SerializerMethodField()   

    class Meta:
        model  = User
        fields = [
            "id", "username", "first_name", "last_name",
            "email", "role", "status", "date_joined", "last_login",
            "profile", "reports", "claims",
        ]

    def get_profile(self, obj):
        request = self.context.get("request")
        try:
            p = obj.profile
        except Exception:
            return {"phone_number": None, "address": None, "bio": None, "avatar": None}

        avatar_url = None
        if p.avatar:
            try:
                url = p.avatar.url
                avatar_url = request.build_absolute_uri(url) if request else url
            except Exception:
                pass

        return {
            "phone_number": p.phone_number,
            "address":      p.address,
            "bio":          p.bio,
            "avatar":       avatar_url,
        }

    def get_reports(self, obj):
    
        return 0

    def get_claims(self, obj):

        return 0
    

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  LOST REPORT SERIALIZERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from .models import LostReport, ReportImage


class ReportImageSerializer(serializers.ModelSerializer):
    """
    Serializes a single image row.
    Returns the absolute URL of the image file.
    """
    image_url = serializers.SerializerMethodField()

    class Meta:
        model  = ReportImage
        fields = ['id', 'image_url', 'is_main', 'order', 'uploaded_at']

    def get_image_url(self, obj):
        request = self.context.get('request')
        try:
            url = obj.image.url
            return request.build_absolute_uri(url) if request else url
        except Exception:
            return None


class LostReportSerializer(serializers.ModelSerializer):
    """
    Full serializer used for:
      • GET  /api/reports/          (list — read)
      • GET  /api/reports/<id>/     (detail — read)
      • POST /api/reports/          (create — write)
      • PATCH /api/reports/<id>/    (partial update — write)

    Read fields (populated automatically, not accepted in POST/PATCH):
      user_info, images, image_count, status, admin_notes,
      views, date_reported, date_updated

    Write fields (accepted in POST body):
      item_name, category, location, date_lost, description,
      location_detail, time_lost, brand, color,
      distinguishing_features, reward, contact_phone, is_urgent
    """

    # ── Read-only computed / related fields ───────────────────────────────
    images      = ReportImageSerializer(many=True, read_only=True)
    image_count = serializers.IntegerField(source='image_count', read_only=True)
    user_info   = serializers.SerializerMethodField()

    class Meta:
        model  = LostReport
        fields = [
            # identity
            'id',
            # reporter (read-only, set from request.user in view)
            'user_info',
            # REQUIRED by user
            'item_name',
            'category',
            'location',
            'date_lost',
            'description',
            # OPTIONAL by user
            'location_detail',
            'time_lost',
            'brand',
            'color',
            'distinguishing_features',
            'reward',
            'contact_phone',
            'is_urgent',
            # admin-only / auto fields
            'status',
            'admin_notes',
            'views',
            'image_count',
            'images',
            'date_reported',
            'date_updated',
        ]
        read_only_fields = [
            'id', 'user_info',
            'status', 'admin_notes',
            'views', 'image_count', 'images',
            'date_reported', 'date_updated',
        ]

    def get_user_info(self, obj):
        """Minimal reporter snapshot — avoids exposing sensitive user data."""
        u = obj.user
        return {
            'id':       u.id,
            'username': u.username,
            'name':     f"{u.first_name} {u.last_name}".strip() or u.username,
        }

    # ── Validation ────────────────────────────────────────────────────────
    def validate_item_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Item name cannot be blank.")
        if len(value.strip()) < 3:
            raise serializers.ValidationError("Item name must be at least 3 characters.")
        return value.strip()

    def validate_category(self, value):
        valid = [c[0] for c in LostReport.CATEGORY_CHOICES]
        if value not in valid:
            raise serializers.ValidationError(
                f"Invalid category. Choose from: {', '.join(valid)}"
            )
        return value

    def validate_location(self, value):
        if not value.strip():
            raise serializers.ValidationError("Location cannot be blank.")
        return value.strip()

    def validate_date_lost(self, value):
        from django.utils.timezone import now
        if value > now().date():
            raise serializers.ValidationError("Date lost cannot be in the future.")
        return value

    def validate_description(self, value):
        if not value.strip():
            raise serializers.ValidationError("Description cannot be blank.")
        if len(value.strip()) < 20:
            raise serializers.ValidationError(
                "Description must be at least 20 characters so finders have enough context."
            )
        return value.strip()

    # ── Create ────────────────────────────────────────────────────────────
    def create(self, validated_data):
        # user is injected by the view via serializer.save(user=request.user)
        return LostReport.objects.create(**validated_data)


class LostReportListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for list views — excludes heavy fields
    (full images list, admin_notes, distinguishing_features)
    to keep paginated responses fast.
    """
    main_image  = serializers.SerializerMethodField()
    user_info   = serializers.SerializerMethodField()
    image_count = serializers.IntegerField(source='image_count', read_only=True)

    class Meta:
        model  = LostReport
        fields = [
            'id',
            'user_info',
            'item_name',
            'category',
            'location',
            'date_lost',
            'date_reported',
            'status',
            'is_urgent',
            'reward',
            'views',
            'image_count',
            'main_image',
        ]

    def get_user_info(self, obj):
        u = obj.user
        return {
            'id':       u.id,
            'username': u.username,
            'name':     f"{u.first_name} {u.last_name}".strip() or u.username,
        }

    def get_main_image(self, obj):
        img = obj.main_image
        if not img:
            return None
        request = self.context.get('request')
        try:
            url = img.image.url
            return request.build_absolute_uri(url) if request else url
        except Exception:
            return None


class AdminLostReportSerializer(LostReportSerializer):
    """
    Extends the base serializer for admin endpoints.
    Unlocks admin_notes as a writable field and exposes full user details.
    """
    user_info = serializers.SerializerMethodField()

    class Meta(LostReportSerializer.Meta):
        read_only_fields = [
            'id', 'user_info',
            'views', 'image_count', 'images',
            'date_reported', 'date_updated',
        ]
        # admin can write: status, admin_notes + all user-writable fields

    def get_user_info(self, obj):
        u = obj.user
        try:
            phone = u.profile.phone_number
        except Exception:
            phone = None
        return {
            'id':       u.id,
            'username': u.username,
            'name':     f"{u.first_name} {u.last_name}".strip() or u.username,
            'email':    u.email,
            'phone':    phone,
        }