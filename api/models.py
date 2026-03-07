from django.db import models
from django.contrib.auth.models import AbstractUser


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