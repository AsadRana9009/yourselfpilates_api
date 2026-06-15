from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, Student, PasswordResetOTP


@admin.register(User)
class UserAdmin(BaseUserAdmin):
	ordering = ['-date_joined']
	list_display = [
		'id',
		'email',
		'full_name',
		'role',
		'is_student',
		'is_active',
		'is_staff',
		'is_superuser',
		'date_joined',
	]
	list_filter = ['role', 'is_student', 'is_active', 'is_staff', 'is_superuser']
	search_fields = ['email', 'full_name', 'contact_number']
	readonly_fields = ['last_login', 'date_joined']

	fieldsets = (
		(None, {'fields': ('email', 'password')}),
		('Personal info', {'fields': ('full_name', 'bio', 'contact_number', 'photo', 'region')}),
		('Address', {'fields': ('street', 'city', 'state', 'country', 'zipcode')}),
		('Subscription', {'fields': ('subscribed_pack', 'used_hours', 'remaining_hours', 'total_purchased_hours', 'subscription_date')}),
		('Permissions', {'fields': ('role', 'is_student', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
		('Important dates', {'fields': ('last_login', 'date_joined')}),
	)

	add_fieldsets = (
		(
			None,
			{
				'classes': ('wide',),
				'fields': ('email', 'full_name', 'password1', 'password2', 'role', 'is_student', 'is_active', 'is_staff', 'is_superuser'),
			},
		),
	)

	def has_delete_permission(self, request, obj=None):
		# Prevent deleting your own account — Django would raise DoesNotExist
		# when it tries to reload request.user on the very next request.
		if obj is not None and obj.pk == request.user.pk:
			return False
		return super().has_delete_permission(request, obj)

	def delete_queryset(self, request, queryset):
		# Guard the "Delete selected" bulk action the same way.
		queryset.exclude(pk=request.user.pk).delete()


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
	list_display = ['id', 'full_name', 'email', 'contact_number', 'is_public', 'region', 'professor', 'joined_at']
	list_filter = ['joined_at', 'region']
	search_fields = ['full_name', 'email', 'contact_number']
	autocomplete_fields = ['professor', 'user']


@admin.register(PasswordResetOTP)
class PasswordResetOTPAdmin(admin.ModelAdmin):
	list_display = ['id', 'user', 'code', 'is_used', 'created_at', 'expires_at']
	list_filter = ['is_used', 'created_at', 'expires_at']
	search_fields = ['user__email', 'code']
	autocomplete_fields = ['user']
