from django.contrib import admin
from .models import User, UserProfile, LostReport, ReportImage, MatchSuggestion, Notification

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
	pass

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    pass

@admin.register(LostReport)
class LostReportAdmin(admin.ModelAdmin):
    pass

@admin.register(ReportImage)
class ReportImageAdmin(admin.ModelAdmin):
    pass

@admin.register(MatchSuggestion)
class MatchSuggestionAdmin(admin.ModelAdmin):
    pass

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    pass