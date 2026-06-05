from django.contrib import admin
from django.utils import timezone
from .models import Pack, SubscriptionHistory, Order


@admin.register(Pack)
class PackAdmin(admin.ModelAdmin):
    list_display = ['title', 'target_role', 'price', 'total_hours', 'active', 'created_at']
    list_filter = ['active', 'target_role']
    search_fields = ['title', 'description']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['order_id', 'user', 'pack', 'amount', 'payment_method', 'payment_status', 'created_at', 'paid_at']
    list_filter = ['payment_status', 'payment_method', 'created_at']
    search_fields = ['order_id', 'user__email', 'user__full_name', 'mb_reference', 'request_id']
    readonly_fields = ['order_id', 'created_at', 'request_id']
    fieldsets = (
        ('Order Info', {
            'fields': ('order_id', 'user', 'pack', 'amount', 'payment_method', 'payment_status')
        }),
        ('MultiBanco Details', {
            'fields': ('mb_key', 'mb_entity', 'mb_reference', 'expiry_date')
        }),
        ('IfThenPay Tracking', {
            'fields': ('request_id',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'paid_at')
        }),
    )

    def save_model(self, request, obj, form, change):
        """When order is saved as Pago from admin, credit hours to the user."""
        is_new_pay = (
            not change and obj.payment_status == 'Pago'
        ) or (
            change
            and 'payment_status' in form.changed_data
            and obj.payment_status == 'Pago'
        )
        super().save_model(request, obj, form, change)
        if is_new_pay:
            user = obj.user
            user.remaining_hours = (user.remaining_hours or 0) + obj.pack.total_hours
            user.total_purchased_hours = (user.total_purchased_hours or 0) + obj.pack.total_hours
            user.subscribed_pack = obj.pack
            user.subscription_date = timezone.now()
            user.save()
            SubscriptionHistory.objects.get_or_create(
                user=user,
                pack=obj.pack,
                order=obj,
                defaults={'hours_added': obj.pack.total_hours},
            )


@admin.register(SubscriptionHistory)
class SubscriptionHistoryAdmin(admin.ModelAdmin):
    list_display = ['user', 'pack', 'hours_added', 'order', 'subscribed_at']
    list_filter = ['subscribed_at', 'pack']
    search_fields = ['user__email', 'user__full_name', 'pack__title']
    readonly_fields = ['subscribed_at']

    def save_model(self, request, obj, form, change):
        """Sync remaining_hours on the user whenever a SubscriptionHistory is added/edited."""
        is_new = not change
        super().save_model(request, obj, form, change)
        if is_new:
            user = obj.user
            user.remaining_hours = (user.remaining_hours or 0) + obj.hours_added
            user.total_purchased_hours = (user.total_purchased_hours or 0) + obj.hours_added
            if obj.pack:
                user.subscribed_pack = obj.pack
            user.subscription_date = timezone.now()
            user.save()
