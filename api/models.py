from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone


class User(AbstractUser):
    """
    Custom user model.

    status lifecycle
    ────────────────
    active   → default; can login and use the app normally
    inactive → self-deactivated; blocked from login
               (auto-reactivates when user logs back in)
    banned   → set by admin; permanently blocked from login; cannot self-reactivate
    """

    ROLE_CHOICES = (
        ('ADMIN', 'Admin'),
        ('USER',  'User'),
    )

    STATUS_CHOICES = (
        ('active',   'Active'),
        ('inactive', 'Inactive'),
        ('banned',   'Banned'),
    )

    role   = models.CharField(max_length=10, choices=ROLE_CHOICES,  default='USER')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active', db_index=True)

    def __str__(self):
        return f"{self.username} ({self.role}) [{self.status}]"

    @property
    def is_banned(self):
        return self.status == 'banned'

    @property
    def is_inactive_account(self):
        return self.status == 'inactive'

    @property
    def is_active_account(self):
        return self.status == 'active'


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')

    phone_number = models.CharField(max_length=20, blank=True, null=True)
    address      = models.TextField(blank=True, null=True)
    bio          = models.TextField(blank=True, null=True)
    avatar       = models.ImageField(upload_to="profiles/", blank=True, null=True)

    def __str__(self):
        return f"{self.user.username}'s Profile"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  REPORT  (Lost + Found in one table)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class LostReport(models.Model):
    """
    Unified report model for both LOST and FOUND items.

    report_type
    ───────────
    'lost'  → user lost an item and is looking for it
    'found' → user found an item and is looking for its owner

    Status lifecycle
    ────────────────
    lost flow:
      open → under_review → matched → claimed → closed
                          ↘ rejected

    found flow:
      open → under_review → matched → claimed → closed
                          ↘ rejected

    Field nullability guide
    ───────────────────────
    REQUIRED always:
      user, report_type, item_name, category, location,
      date_event (date lost OR date found), description

    OPTIONAL (nullable):
      location_detail, time_event, brand, color,
      distinguishing_features, reward, contact_phone,
      is_urgent, admin_notes

    Found-specific optional:
      found_location  — where the item is being kept now
    """

    # ── Report type ──────────────────────────────────────────────────────
    TYPE_LOST  = 'lost'
    TYPE_FOUND = 'found'

    TYPE_CHOICES = (
        (TYPE_LOST,  'Lost'),
        (TYPE_FOUND, 'Found'),
    )

    # ── Status choices ──────────────────────────────────────────────────
    STATUS_OPEN         = 'open'
    STATUS_UNDER_REVIEW = 'under_review'
    STATUS_MATCHED      = 'matched'
    STATUS_CLAIMED      = 'claimed'
    STATUS_CLOSED       = 'closed'
    STATUS_REJECTED     = 'rejected'

    STATUS_CHOICES = (
        (STATUS_OPEN,         'Open'),
        (STATUS_UNDER_REVIEW, 'Under Review'),
        (STATUS_MATCHED,      'Matched'),
        (STATUS_CLAIMED,      'Claimed'),
        (STATUS_CLOSED,       'Closed'),
        (STATUS_REJECTED,     'Rejected'),
    )

    # ── Category choices ────────────────────────────────────────────────
    CATEGORY_CHOICES = (
        ('Electronics',    'Electronics'),
        ('Wallets & Bags', 'Wallets & Bags'),
        ('Keys',           'Keys'),
        ('Clothing',       'Clothing'),
        ('Jewelry',        'Jewelry'),
        ('Documents',      'Documents'),
        ('Pets',           'Pets'),
        ('Sports',         'Sports'),
        ('Other',          'Other'),
    )

    # ── Relationships ────────────────────────────────────────────────────
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='reports',           # changed from 'lost_reports'
    )

    # ── REQUIRED fields ───────────────────────────────────────────────────
    report_type = models.CharField(
        max_length=10,
        choices=TYPE_CHOICES,
        default=TYPE_LOST,
        db_index=True,
        # NOT NULL — determines the entire workflow branch
    )

    item_name = models.CharField(
        max_length=150,
    )

    category = models.CharField(
        max_length=30,
        choices=CATEGORY_CHOICES,
        db_index=True,
    )

    location = models.CharField(
        max_length=255,
        # For lost: where it was lost
        # For found: where it was found
    )

    date_event = models.DateField(
        # Replaces date_lost — works for both lost and found reports
        # For lost: the date the item was lost
        # For found: the date the item was found
    )

    description = models.TextField()

    # ── OPTIONAL enrichment fields ────────────────────────────────────────
    location_detail = models.CharField(
        max_length=255,
        blank=True, null=True,
    )

    time_event = models.TimeField(
        blank=True, null=True,
        # Replaces time_lost — approximate time of loss or finding
    )

    brand = models.CharField(
        max_length=100,
        blank=True, null=True,
    )

    color = models.CharField(
        max_length=50,
        blank=True, null=True,
    )

    distinguishing_features = models.TextField(
        blank=True, null=True,
    )

    reward = models.CharField(
        max_length=100,
        blank=True, null=True,
        # Only relevant for lost reports, but kept on the model for simplicity
    )

    contact_phone = models.CharField(
        max_length=30,
        blank=True, null=True,
    )

    is_urgent = models.BooleanField(
        default=False,
    )

    # ── Found-specific optional field ─────────────────────────────────────
    found_stored_at = models.CharField(
        max_length=255,
        blank=True, null=True,
        # Where the found item is currently being kept
        # e.g. "With me at home", "Turned in to mall security office"
    )

    # ── AI Matching ───────────────────────────────────────────────────────
    matched_report = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        blank=True, null=True,
        related_name='matched_by',
        # Set when admin confirms a match between a lost and found report
    )

    # ── Admin-managed fields ──────────────────────────────────────────────
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_OPEN,
        db_index=True,
    )

    admin_notes = models.TextField(
        blank=True, null=True,
    )

    # ── Auto-managed tracking fields ──────────────────────────────────────
    views = models.PositiveIntegerField(
        default=0,
    )

    date_reported = models.DateTimeField(
        default=timezone.now,
    )

    date_updated = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering            = ['-date_reported']
        verbose_name        = 'Report'
        verbose_name_plural = 'Reports'

    def __str__(self):
        return f"[{self.report_type.upper()}][{self.status.upper()}] {self.item_name} — {self.user.username}"

    @property
    def is_lost(self):
        return self.report_type == self.TYPE_LOST

    @property
    def is_found(self):
        return self.report_type == self.TYPE_FOUND

    @property
    def is_open(self):
        return self.status == self.STATUS_OPEN

    @property
    def is_resolved(self):
        return self.status in (self.STATUS_CLAIMED, self.STATUS_CLOSED)

    @property
    def image_count(self):
        return self.images.count()

    @property
    def main_image(self):
        return self.images.filter(is_main=True).first() or self.images.first()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  REPORT IMAGE  (one report → many images)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ReportImage(models.Model):
    """
    Stores uploaded images for a Report (lost or found).
    """

    report = models.ForeignKey(
        LostReport,
        on_delete=models.CASCADE,
        related_name='images',
    )

    image = models.ImageField(
        upload_to='reports/%Y/%m/',
    )

    is_main = models.BooleanField(
        default=False,
    )

    order = models.PositiveSmallIntegerField(
        default=0,
    )

    uploaded_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ['order', 'uploaded_at']

    def __str__(self):
        flag = " [MAIN]" if self.is_main else ""
        return f"Image#{self.pk}{flag} → Report #{self.report_id}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MATCH SUGGESTION  (AI matching engine output)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class MatchSuggestion(models.Model):
    """
    Stores AI-generated match suggestions between a lost and found report.

    The engine scores pairs and an admin confirms or dismisses each suggestion.

    Status lifecycle:
      pending   → freshly generated, awaiting admin review
      confirmed → admin confirmed this match; both reports set to 'matched'
      dismissed → admin dismissed this suggestion (not a real match)
    """

    STATUS_PENDING   = 'pending'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_DISMISSED = 'dismissed'

    STATUS_CHOICES = (
        (STATUS_PENDING,   'Pending'),
        (STATUS_CONFIRMED, 'Confirmed'),
        (STATUS_DISMISSED, 'Dismissed'),
    )

    lost_report = models.ForeignKey(
        LostReport,
        on_delete=models.CASCADE,
        related_name='match_suggestions_as_lost',
        limit_choices_to={'report_type': 'lost'},
    )

    found_report = models.ForeignKey(
        LostReport,
        on_delete=models.CASCADE,
        related_name='match_suggestions_as_found',
        limit_choices_to={'report_type': 'found'},
    )

    score = models.FloatField(
        # 0.0 – 1.0; computed by matching.py
    )

    score_breakdown = models.JSONField(
        default=dict,
        # Stores per-component scores for transparency:
        # { "category": 0.35, "name": 0.28, "location": 0.15, "date": 0.10 }
    )

    confidence = models.CharField(
        max_length=10,
        default='low',
        # 'high' >= 0.75, 'medium' >= 0.50, 'low' < 0.50
    )

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-score']
        unique_together = [('lost_report', 'found_report')]
        verbose_name        = 'Match Suggestion'
        verbose_name_plural = 'Match Suggestions'

    def __str__(self):
        return f"Match #{self.pk}: Lost#{self.lost_report_id} ↔ Found#{self.found_report_id} [{self.score:.2f}] [{self.status}]"

    @property
    def confidence_label(self):
        if self.score >= 0.75:
            return 'high'
        if self.score >= 0.50:
            return 'medium'
        return 'low'


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CLAIM REQUEST
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ClaimRequest(models.Model):
    """
    Filed by a user to claim ownership of a found item.

    Only relevant when the related lost report has status 'matched'.
    Admin reviews the proof and either approves (→ 'claimed') or rejects.

    Status lifecycle:
      pending  → submitted, awaiting admin review
      approved → admin verified ownership; report status → 'claimed'
      rejected → admin rejected the claim; user may re-submit with better proof
    """

    STATUS_PENDING  = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'

    STATUS_CHOICES = (
        (STATUS_PENDING,  'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    )

    report = models.ForeignKey(
        LostReport,
        on_delete=models.CASCADE,
        related_name='claim_requests',
    )

    claimant = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='claim_requests',
    )

    proof_description = models.TextField(
        # User describes how they can prove ownership:
        # serial number, purchase receipt, unique features, photos, etc.
    )

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )

    admin_response = models.TextField(
        blank=True, null=True,
        # Admin's reason for approving or rejecting
    )

    date_submitted = models.DateTimeField(auto_now_add=True)
    date_updated   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date_submitted']
        verbose_name        = 'Claim Request'
        verbose_name_plural = 'Claim Requests'

    def __str__(self):
        return f"Claim #{self.pk} by {self.claimant.username} on Report #{self.report_id} [{self.status}]"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  NOTIFICATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class Notification(models.Model):
    """
    In-app notifications triggered by system events.

    type values and when they fire:
      report_received  → user submits a report
      under_review     → admin moves report to under_review
      matched          → admin confirms a match
      claim_received   → user submits a claim request
      claim_approved   → admin approves a claim
      claim_rejected   → admin rejects a claim
      report_closed    → report is closed
      report_rejected  → admin rejects a report
    """

    TYPE_CHOICES = (
        # ── user-facing ──
        ('report_received', 'Report Received'),
        ('under_review',    'Under Review'),
        ('matched',         'Matched'),
        ('claim_received',  'Claim Received'),
        ('claim_approved',  'Claim Approved'),
        ('claim_rejected',  'Claim Rejected'),
        ('report_closed',   'Report Closed'),
        ('report_rejected', 'Report Rejected'),
        # ── admin-facing ──
        ('new_report',      'New Report Submitted'),
        ('new_claim',       'New Claim Submitted'),
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notifications',
    )

    notif_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        db_index=True,
    )

    report = models.ForeignKey(
        LostReport,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='notifications',
    )

    claim = models.ForeignKey(
        ClaimRequest,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='notifications',
    )

    title   = models.CharField(max_length=150)
    message = models.TextField()
    is_read = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name        = 'Notification'
        verbose_name_plural = 'Notifications'

    def __str__(self):
        return f"Notif → {self.user.username}: [{self.notif_type}] {self.title}"


class AuditLog(models.Model):
    ACTION_CHOICES = [
        # Auth
        ('login',            'User Login'),
        ('logout',           'User Logout'),
        ('register',         'User Registered'),
        ('password_change',  'Password Changed'),
        # Reports
        ('report_created',   'Report Created'),
        ('report_updated',   'Report Updated'),
        ('report_deleted',   'Report Deleted'),
        ('report_closed',    'Report Closed'),
        # Claims
        ('claim_submitted',  'Claim Submitted'),
        ('claim_approved',   'Claim Approved'),
        ('claim_rejected',   'Claim Rejected'),
        # Matches
        ('match_confirmed',  'Match Confirmed'),
        ('match_dismissed',  'Match Dismissed'),
        ('match_run',        'AI Match Run'),
        # Users (admin)
        ('user_banned',      'User Banned'),
        ('user_unbanned',    'User Unbanned'),
        ('user_deleted',     'User Deleted'),
        ('role_changed',     'Role Changed'),
    ]

    ACTOR_CHOICES = [
        ('user',   'User'),
        ('admin',  'Admin'),
        ('system', 'System'),
    ]

    action     = models.CharField(max_length=40, choices=ACTION_CHOICES, db_index=True)
    actor_type = models.CharField(max_length=10, choices=ACTOR_CHOICES, default='user')
    actor      = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='audit_logs'
    )
    target_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='audit_logs_as_target'
    )
    report  = models.ForeignKey('LostReport',   on_delete=models.SET_NULL, null=True, blank=True)
    claim   = models.ForeignKey('ClaimRequest', on_delete=models.SET_NULL, null=True, blank=True)
    detail  = models.TextField(blank=True, default='')
    ip      = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name        = 'Audit Log'
        verbose_name_plural = 'Audit Logs'

    def __str__(self):
        actor = self.actor.username if self.actor else 'System'
        return f"[{self.action}] by {actor} at {self.created_at:%Y-%m-%d %H:%M}"