from rest_framework import serializers
from django.conf import settings
from .models import Pack, SubscriptionHistory, Order, Region, PackRegionPrice


class RegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Region
        fields = ['id', 'name', 'slug', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']


class PackRegionPriceSerializer(serializers.ModelSerializer):
    region_name = serializers.CharField(source='region.name', read_only=True)
    region_slug = serializers.CharField(source='region.slug', read_only=True)

    class Meta:
        model = PackRegionPrice
        fields = ['id', 'region', 'region_name', 'region_slug', 'price']


class PackSerializer(serializers.ModelSerializer):
    region_prices = PackRegionPriceSerializer(many=True, read_only=True)
    region_name = serializers.CharField(source='region.name', read_only=True, default=None)

    class Meta:
        model = Pack
        fields = ["id", "title", "description", "image", "active", "is_public", "target_role", "price", "total_hours", "region", "region_name", "region_prices", "created_at", "updated_at"]
        read_only_fields = ["id", "region_name", "created_at", "updated_at"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        image_path = data.get("image")
        if image_path:
            request = self.context.get("request")
            if request:
                # build_absolute_uri handles both relative paths and already-absolute URLs
                data["image"] = request.build_absolute_uri(image_path)
            else:
                base = getattr(settings, "BACKEND_URL", "http://localhost:8000")
                data["image"] = f"{base.rstrip('/')}{image_path}"
        return data


class SubscriptionHistorySerializer(serializers.ModelSerializer):
    pack_title = serializers.CharField(source='pack.title', read_only=True)
    
    class Meta:
        model = SubscriptionHistory
        fields = ["id", "pack", "pack_title", "hours_added", "subscribed_at"]
        read_only_fields = ["id", "subscribed_at"]


class OrderSerializer(serializers.ModelSerializer):
    pack_details = PackSerializer(source='pack', read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    region_name = serializers.CharField(source='region.name', read_only=True, default=None)

    class Meta:
        model = Order
        fields = [
            'id', 'user', 'user_email', 'user_name', 'pack', 'pack_details',
            'amount', 'payment_method', 'payment_status', 'mb_key', 'mb_entity',
            'mb_reference', 'order_id', 'request_id', 'expiry_date', 'mbway_phone',
            'ccard_payment_url', 'created_at', 'paid_at', 'payment_method_updated_at',
            'previous_payment_method', 'region', 'region_name',
        ]
        read_only_fields = [
            'id', 'user', 'pack', 'amount', 'mb_key', 'mb_entity', 'mb_reference',
            'order_id', 'request_id', 'expiry_date', 'created_at', 'paid_at',
            'payment_status', 'ccard_payment_url', 'payment_method_updated_at',
            'previous_payment_method', 'region_name',
        ]
    
    def validate_payment_method(self, value):
        """Validate payment method is one of the allowed values"""
        if value not in ['multibanco', 'mbway', 'creditcard']:
            raise serializers.ValidationError(
                "Invalid payment method. Choose 'multibanco', 'mbway', or 'creditcard'."
            )
        return value
    
    def validate(self, data):
        """Validate mbway_phone is provided when payment_method is mbway"""
        payment_method = data.get('payment_method')
        mbway_phone = data.get('mbway_phone')
        
        # If updating to mbway, phone is required
        if payment_method == 'mbway' and not mbway_phone:
            # Check if instance already has mbway_phone
            if not (self.instance and self.instance.mbway_phone):
                raise serializers.ValidationError({
                    'mbway_phone': 'Phone number is required for MB WAY payments. Format: 351#912345678'
                })
        
        return data
