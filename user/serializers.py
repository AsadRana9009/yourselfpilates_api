"""
Serializers for the user API view.
"""
from .models import User
from bookings.models import Booking
from bookings.serializers import BookingSerializer
from django.contrib.auth import (
    get_user_model,
    authenticate,
)
from rest_framework import serializers
from .models import Student


class StudentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Student
        fields = ['id', 'full_name', 'email', 'contact_number', 'is_public', 'joined_at', 'professor']
        read_only_fields = ['id', 'is_public', 'joined_at']
        extra_kwargs = {
            'professor': {'required': False, 'allow_null': True}
        }


class BookingSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = [
            'id', 'title', 'booking_date', 'time_slot', 'status', 'approve', 'total_students', 'created_at', 'updated_at'
        ]

class UserSerializer(serializers.ModelSerializer):
    subscribed_pack_details = serializers.SerializerMethodField()
    booking_details = serializers.SerializerMethodField()


    class Meta:
        model = get_user_model()
        fields = [
            'email', 'password', 'full_name', 'role', 'bio',
            'contact_number', 'photo', 'city', 'remaining_hours', 'used_hours',
            'total_purchased_hours',
            'subscribed_pack_details', 'booking_details'
        ]
        extra_kwargs = {
            'password': {'write_only': True, 'min_length': 5},
            'remaining_hours': {'read_only': True},
            'used_hours': {'read_only': True},
        }

    def get_subscribed_pack_details(self, obj):
        # Get all subscription history for this user
        from subscriptions.models import SubscriptionHistory
        subscriptions = SubscriptionHistory.objects.filter(user=obj).order_by('-subscribed_at')
        if subscriptions.exists():
            return [
                {
                    'id': sub.pack.id,
                    'title': sub.pack.title,
                    'total_hours': sub.hours_added,
                    'subscription_date': sub.subscribed_at,
                }
                for sub in subscriptions
            ]
        return []

    def get_booking_details(self, obj):
        # Return bookings where user is professor
        bookings = Booking.objects.filter(professor=obj).order_by('-booking_date', '-created_at')
        return BookingSummarySerializer(bookings, many=True).data

    def create(self, validated_data):
        user = get_user_model().objects.create_user(**validated_data)
        # Mark as public (self-registered) so the admin can distinguish them
        user.is_public = True
        user.save(update_fields=['is_public'])
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        user = super().update(instance, validated_data)

        if password:
            user.set_password(password)
            user.save()

        return user


class AuthTokenSerializer(serializers.Serializer):
    """Serializer for the user auth token."""
    email = serializers.EmailField()
    password = serializers.CharField(
        style={'input_type': 'password'},
        trim_whitespace=False,
    )

    def validate(self, attrs):
        """Validate and authenticate the user."""
        email = attrs.get('email')
        password = attrs.get('password')
        user = authenticate(
            request=self.context.get('request'),
            username=email,
            password=password,
        )
        if not user:
            msg = 'Unable to authenticate with provided credentials.'
            raise serializers.ValidationError(msg, code='authorization')

        attrs['user'] = user
        return attrs


class FlexiblePKRelatedField(serializers.PrimaryKeyRelatedField):
    def to_internal_value(self, data):
        try:
            data = int(data)
        except (ValueError, TypeError):
            self.fail('incorrect_type', data_type=type(data).__name__)
        return super().to_internal_value(data)



class UserAdminSerializer(serializers.ModelSerializer):
    # Read students as nested data
    students = StudentSerializer(many=True, read_only=True)
    student_ids = FlexiblePKRelatedField(
        queryset=Student.objects.all(),
        many=True,
        write_only=True,
        required=False
    )
    subscribed_pack_details = serializers.SerializerMethodField()
    booking_details = serializers.SerializerMethodField()


    class Meta:
        model = User
        fields = [
            'id', 'email', 'password', 'full_name', 'role', 'bio', 'date_joined',
            'contact_number', 'photo', 'is_active', 'is_public', 'street', 'city', 'state', 'country',
            'zipcode', 'students', 'student_ids', 'remaining_hours', 'used_hours',
            'total_purchased_hours',
            'subscribed_pack_details', 'booking_details'
        ]
        read_only_fields = ['id', 'date_joined', 'bio', 'used_hours', 'is_public']
        extra_kwargs = {
            'password': {'write_only': True, 'min_length': 5},
            'is_active': {'read_only': True},
        }

    def get_subscribed_pack_details(self, obj):
        # Get all subscription history for this user
        from subscriptions.models import SubscriptionHistory
        subscriptions = SubscriptionHistory.objects.filter(user=obj).order_by('-subscribed_at')
        if subscriptions.exists():
            return [
                {
                    'id': sub.pack.id,
                    'title': sub.pack.title,
                    'total_hours': sub.hours_added,
                    'subscription_date': sub.subscribed_at,
                }
                for sub in subscriptions
            ]
        return []

    def get_booking_details(self, obj):
        bookings = Booking.objects.filter(professor=obj).order_by('-booking_date', '-created_at')
        return BookingSummarySerializer(bookings, many=True).data

    def create(self, validated_data):
        student_ids = validated_data.pop('student_ids', [])
        password = validated_data.get('password')
        user = get_user_model()(**{k: v for k, v in validated_data.items() if k != 'password'})
        if password:
            # Send email before hashing
            if user.role == 'professor':
                from django.core.mail import send_mail
                from django.conf import settings
                send_mail(
                    'Your Account Has Been Created',
                    (
                        f'Dear {user.full_name},\n\n'
                        f'We are pleased to inform you that your account has been successfully created on Yourself Pilates.\n'
                        f'\n'
                        f'You may now log in using the following credentials:\n'
                        f'Email: {user.email}\n'
                        f'Password: {password}\n'
                        f'\n'
                        f'For security reasons, we recommend changing your password after your first login. If you have any questions or require assistance, please contact our support team.\n\n'
                        f'Best regards,\nYourself Pilates Team'
                    ),
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                    fail_silently=False,
                )
            user.set_password(password)
        user.save()
        if user.role == 'professor':
            for student in student_ids:
                student.professor = user
                student.save()
        return user

    def update(self, instance, validated_data):
        student_ids = validated_data.pop('student_ids', None)
        password = validated_data.pop('password', None)
        user = super().update(instance, validated_data)

        if password:
            user.set_password(password)
            user.save()

        if student_ids is not None and user.role == 'professor':
            user.students.update(professor=None)
            for student in student_ids:
                student.professor = user
                student.save()

        return user


class RequestPasswordResetOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()

class VerifyPasswordResetOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)
    new_password = serializers.CharField(min_length=8)

class ConfirmPasswordResetOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)

class ResetPasswordWithOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)
    new_password = serializers.CharField(min_length=8)
