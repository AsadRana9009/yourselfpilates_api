from django.contrib import admin
from django.utils import timezone
from .models import Pack, SubscriptionHistory, Order, CreditWallet, Region, PackRegionPrice


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'slug', 'location', 'email', 'phone', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name', 'slug', 'location', 'email', 'phone']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['created_at']


@admin.register(PackRegionPrice)
class PackRegionPriceAdmin(admin.ModelAdmin):
    list_display = ['pack', 'region', 'price']
    list_filter = ['region']
    search_fields = ['pack__title', 'region__name']


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

    def delete_model(self, request, obj):
        """Subtract hours from user when a paid order is deleted from admin."""
        if obj.payment_status == 'Pago':
            user = obj.user
            user.remaining_hours = max(0, (user.remaining_hours or 0) - obj.pack.total_hours)
            user.total_purchased_hours = max(0, (user.total_purchased_hours or 0) - obj.pack.total_hours)
            user.save(update_fields=['remaining_hours', 'total_purchased_hours'])
        obj.delete()

    def delete_queryset(self, request, queryset):
        """Subtract hours from users when bulk-deleting paid orders from admin."""
        for order in queryset.filter(payment_status='Pago').select_related('user', 'pack'):
            user = order.user
            user.remaining_hours = max(0, (user.remaining_hours or 0) - order.pack.total_hours)
            user.total_purchased_hours = max(0, (user.total_purchased_hours or 0) - order.pack.total_hours)
            user.save(update_fields=['remaining_hours', 'total_purchased_hours'])
        queryset.delete()


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

    def delete_model(self, request, obj):
        """Subtract hours from user when a single SubscriptionHistory is deleted."""
        user = obj.user
        user.remaining_hours = max(0, (user.remaining_hours or 0) - obj.hours_added)
        user.total_purchased_hours = max(0, (user.total_purchased_hours or 0) - obj.hours_added)
        user.save(update_fields=['remaining_hours', 'total_purchased_hours'])
        obj.delete()

    def delete_queryset(self, request, queryset):
        """Subtract hours from users when bulk-deleting SubscriptionHistory records."""
        from django.db.models import Sum
        from django.contrib.auth import get_user_model
        User = get_user_model()

        # Group hours to deduct per user
        for entry in queryset.select_related('user'):
            user = entry.user
            user.remaining_hours = max(0, (user.remaining_hours or 0) - entry.hours_added)
            user.total_purchased_hours = max(0, (user.total_purchased_hours or 0) - entry.hours_added)
            user.save(update_fields=['remaining_hours', 'total_purchased_hours'])
        queryset.delete()


@admin.register(CreditWallet)
class CreditWalletAdmin(admin.ModelAdmin):
    list_display = ['user', 'pack', 'region', 'total_hours', 'used_hours', 'remaining_hours', 'status', 'purchase_date', 'expiry_date']
    list_filter = ['status', 'purchase_date', 'region']
    search_fields = ['user__email', 'user__full_name', 'pack__title']
    readonly_fields = ['purchase_date', 'remaining_hours']
