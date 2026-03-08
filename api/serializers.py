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
        return obj.reports.count()

    def get_claims(self, obj):
        return obj.claim_requests.count()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  REPORT SERIALIZERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from .models import LostReport, ReportImage, MatchSuggestion, ClaimRequest


class ReportImageSerializer(serializers.ModelSerializer):
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


class ReportSerializer(serializers.ModelSerializer):
    """
    Full serializer for both lost and found reports.

    Read-only: user_info, images, image_count, status, admin_notes,
               views, date_reported, date_updated, matched_report_id

    User-writable: report_type, item_name, category, location,
                   date_event, description, location_detail, time_event,
                   brand, color, distinguishing_features, reward,
                   contact_phone, is_urgent, found_stored_at
    """

    images      = ReportImageSerializer(many=True, read_only=True)
    image_count = serializers.IntegerField(read_only=True)
    user_info   = serializers.SerializerMethodField()

    class Meta:
        model  = LostReport
        fields = [
            'id',
            'user_info',
            'report_type',
            'item_name',
            'category',
            'location',
            'date_event',
            'description',
            'location_detail',
            'time_event',
            'brand',
            'color',
            'distinguishing_features',
            'reward',
            'contact_phone',
            'is_urgent',
            'found_stored_at',
            'matched_report',
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
            'matched_report',
            'status', 'admin_notes',
            'views', 'image_count', 'images',
            'date_reported', 'date_updated',
        ]

    def get_user_info(self, obj):
        u = obj.user
        return {
            'id':       u.id,
            'username': u.username,
            'name':     f"{u.first_name} {u.last_name}".strip() or u.username,
        }

    def validate_report_type(self, value):
        valid = [t[0] for t in LostReport.TYPE_CHOICES]
        if value not in valid:
            raise serializers.ValidationError(f"Must be one of: {', '.join(valid)}")
        return value

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

    def validate_date_event(self, value):
        from django.utils.timezone import now
        if value > now().date():
            raise serializers.ValidationError("Date cannot be in the future.")
        return value

    def validate_description(self, value):
        if not value.strip():
            raise serializers.ValidationError("Description cannot be blank.")
        if len(value.strip()) < 20:
            raise serializers.ValidationError(
                "Description must be at least 20 characters."
            )
        return value.strip()

    def create(self, validated_data):
        return LostReport.objects.create(**validated_data)


class ReportListSerializer(serializers.ModelSerializer):
    """Lightweight list serializer — no heavy fields."""
    main_image  = serializers.SerializerMethodField()
    user_info   = serializers.SerializerMethodField()
    image_count = serializers.IntegerField(read_only=True)

    class Meta:
        model  = LostReport
        fields = [
            'id',
            'user_info',
            'report_type',
            'item_name',
            'category',
            'location',
            'date_event',
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


class AdminReportSerializer(ReportSerializer):
    """
    Admin serializer — unlocks status, admin_notes, matched_report as writable.
    Also returns extended user_info (email, phone).
    """
    user_info = serializers.SerializerMethodField()

    class Meta(ReportSerializer.Meta):
        read_only_fields = [
            'id', 'user_info',
            'views', 'image_count', 'images',
            'date_reported', 'date_updated',
        ]

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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MATCH SUGGESTION SERIALIZERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class MatchSuggestionSerializer(serializers.ModelSerializer):
    lost_report_summary  = serializers.SerializerMethodField()
    found_report_summary = serializers.SerializerMethodField()

    class Meta:
        model  = MatchSuggestion
        fields = [
            'id',
            'lost_report', 'lost_report_summary',
            'found_report', 'found_report_summary',
            'score', 'score_breakdown', 'confidence',
            'status',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'lost_report_summary', 'found_report_summary',
            'score', 'score_breakdown', 'confidence',
            'created_at', 'updated_at',
        ]

    def get_lost_report_summary(self, obj):
        r = obj.lost_report
        return {
            'id': r.id, 'item_name': r.item_name,
            'category': r.category, 'location': r.location,
            'date_event': str(r.date_event), 'status': r.status,
        }

    def get_found_report_summary(self, obj):
        r = obj.found_report
        return {
            'id': r.id, 'item_name': r.item_name,
            'category': r.category, 'location': r.location,
            'date_event': str(r.date_event), 'status': r.status,
        }

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CLAIM REQUEST SERIALIZERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ClaimRequestSerializer(serializers.ModelSerializer):
    claimant_info = serializers.SerializerMethodField()
    report_summary = serializers.SerializerMethodField()

    class Meta:
        model  = ClaimRequest
        fields = [
            'id',
            'report', 'report_summary',
            'claimant', 'claimant_info',
            'proof_description',
            'status', 'admin_response',
            'date_submitted', 'date_updated',
        ]
        read_only_fields = [
            'id', 'report', 'claimant', 'claimant_info', 'report_summary',
            'status', 'admin_response',
            'date_submitted', 'date_updated',
        ]

    def get_claimant_info(self, obj):
        u = obj.claimant
        return {
            'id': u.id, 'username': u.username,
            'name': f"{u.first_name} {u.last_name}".strip() or u.username,
            'email': u.email,
        }

    def get_report_summary(self, obj):
        r = obj.report
        return {
            'id': r.id, 'item_name': r.item_name,
            'report_type': r.report_type, 'status': r.status,
        }

    def validate_proof_description(self, value):
        if not value.strip():
            raise serializers.ValidationError("Proof description cannot be blank.")
        if len(value.strip()) < 20:
            raise serializers.ValidationError(
                "Please provide at least 20 characters describing your proof of ownership."
            )
        return value.strip()



# Keep old names as aliases so existing imports don't break
LostReportSerializer     = ReportSerializer
LostReportListSerializer = ReportListSerializer
AdminLostReportSerializer = AdminReportSerializer