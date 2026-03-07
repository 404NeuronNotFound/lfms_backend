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
#  LOST REPORT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class LostReport(models.Model):
    """
    A report filed by a user when they have lost an item.

    Field nullability guide
    ───────────────────────
    REQUIRED (cannot be null/blank — validation will reject missing values):
      user            — must always belong to a real authenticated user
      item_name       — the core identifier of the report
      category        — needed for search and filtering
      location        — where it was lost; critical for matching
      date_lost       — when it was lost; critical for matching
      description     — minimum useful context for finders

    OPTIONAL (null/blank=True — these fields are genuinely not always known):
      location_detail — more specific spot (e.g. "near escalator"); best-effort
      time_lost       — many users don't know the exact time
      brand           — not all items have a brand (handmade, generic items)
      color           — may be multicolored, patterned, or irrelevant
      distinguishing  — unique marks; not every item has them
      reward          — entirely the user's choice; most won't offer one
      contact_phone   — user may prefer in-app messaging only
      is_urgent       — defaults False; user opts in to urgent flagging
      admin_notes     — filled by admins during review; not always needed
      status          — defaults 'open'; managed by admin workflow
      views           — auto-tracked counter; defaults 0
      date_reported   — auto-set on creation (server-side)
      date_updated    — auto-set on every save (server-side)
    """

    STATUS_OPEN          = 'open'
    STATUS_UNDER_REVIEW  = 'under_review'
    STATUS_MATCHED       = 'matched'
    STATUS_CLAIMED       = 'claimed'
    STATUS_CLOSED        = 'closed'
    STATUS_REJECTED      = 'rejected'

    STATUS_CHOICES = (
        (STATUS_OPEN,         'Open'),
        (STATUS_UNDER_REVIEW, 'Under Review'),
        (STATUS_MATCHED,      'Matched'),
        (STATUS_CLAIMED,      'Claimed'),
        (STATUS_CLOSED,       'Closed'),
        (STATUS_REJECTED,     'Rejected'),
    )

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

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='lost_reports',
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
    )

    date_lost = models.DateField(
    )

    description = models.TextField(
    )
    location_detail = models.CharField(
        max_length=255,
        blank=True, null=True,
    )

    time_lost = models.TimeField(
        blank=True, null=True,
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
    )

    contact_phone = models.CharField(
        max_length=30,
        blank=True, null=True,
    )

    is_urgent = models.BooleanField(
        default=False,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_OPEN,
        db_index=True,
    )

    admin_notes = models.TextField(
        blank=True, null=True,
    )

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
        ordering            = ['-date_reported']   # newest first
        verbose_name        = 'Lost Report'
        verbose_name_plural = 'Lost Reports'

    def __str__(self):
        return f"[{self.status.upper()}] {self.item_name} — {self.user.username}"

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
    Stores uploaded images for a LostReport.

    Kept in a separate table so multiple images can attach to one report
    without resorting to ArrayField or comma-separated values.

    Nullability:
      report      — NOT NULL: image must belong to a report
      image       — NOT NULL: the file itself is the entire purpose of this row
      is_main     — NOT NULL (default False): first/primary image flag
      order       — NOT NULL (default 0): display sort order (lower = earlier)
      uploaded_at — NOT NULL (auto): server-side upload timestamp
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