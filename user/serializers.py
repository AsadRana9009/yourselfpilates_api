"""
Serializers for the user API view.
"""
from .models import User, EmailVerificationOTP
from bookings.models import Booking
from bookings.serializers import BookingSerializer
from django.contrib.auth import (
    get_user_model,
    authenticate,
)
from rest_framework import serializers
from .models import Student
import re


class StudentRegistrationSerializer(serializers.ModelSerializer):
    """Serializer for student registration with JWT authentication"""
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'},
        min_length=8
    )
    confirm_password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )

    class Meta:
        model = get_user_model()
        fields = [
            'email',
            'password',
            'confirm_password',
            'full_name',
            'contact_number',
            'region',
        ]
        extra_kwargs = {
            'email': {'required': True},
            'full_name': {'required': True},
            'contact_number': {'required': True},
            'region': {'required': False, 'allow_null': True},
        }

    def validate_email(self, value):
        """Validate email format and check if already exists"""
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', value):
            raise serializers.ValidationError("Invalid email format.")

        # Normalize email to lowercase
        email = value.lower()

        # Check if verified user already exists
        existing_user = get_user_model().objects.filter(email=email).first()
        if existing_user:
            # Check if user has verified their email
            from .models import Student
            try:
                student_profile = existing_user.student_profile
                if student_profile.is_verified:
                    raise serializers.ValidationError("A verified user with this email already exists.")
                else:
                    # Delete unverified user to allow re-registration
                    existing_user.delete()
            except Student.DoesNotExist:
                # User exists but no student profile - delete and allow re-registration
                existing_user.delete()

        return email

    def validate_contact_number(self, value):
        """Validate contact number format"""
        if not value:
            raise serializers.ValidationError("Contact number is required.")

        # Remove any spaces or special characters for validation (keep +)
        clean_number = re.sub(r'[^\d+]', '', value)

        # Basic validation for international phone number (starts with + and has 8-15 digits)
        if not re.match(r'^\+\d{8,15}$', clean_number):
            raise serializers.ValidationError(
                "Invalid phone number format. Use international format: +[country_code][number] (e.g., +351912345678)"
            )

        return value

    def validate(self, attrs):
        """Validate password match and strength"""
        if attrs['password'] != attrs['confirm_password']:
            raise serializers.ValidationError({
                "password": "Passwords do not match."
            })

        # Validate password strength with comprehensive requirements
        password = attrs.get('password')

        # Check minimum length
        if len(password) < 8:
            raise serializers.ValidationError({
                "password": "Password must be at least 8 characters long."
            })

        # Check for uppercase letter
        if not re.search(r'[A-Z]', password):
            raise serializers.ValidationError({
                "password": "Password must contain at least one uppercase letter (A-Z)."
            })

        # Check for lowercase letter
        if not re.search(r'[a-z]', password):
            raise serializers.ValidationError({
                "password": "Password must contain at least one lowercase letter (a-z)."
            })

        # Check for digit
        if not re.search(r'\d', password):
            raise serializers.ValidationError({
                "password": "Password must contain at least one digit (0-9)."
            })

        # Check for special character (optional but recommended)
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            raise serializers.ValidationError({
                "password": "Password must contain at least one special character (!@#$%^&*(),.?\":{}|<>)."
            })

        # Check for common passwords (basic list)
        common_passwords = ['password123', 'admin123', '12345678', 'abcd1234', 'password', '123456789']
        if password.lower() in common_passwords:
            raise serializers.ValidationError({
                "password": "This password is too common. Please choose a stronger password."
            })

        return attrs

    def create(self, validated_data):
        """Create and return a new student user"""
        # Remove confirm_password from validated_data
        validated_data.pop('confirm_password', None)

        # Set default values for student
        validated_data['role'] = 'student'
        validated_data['is_active'] = True
        validated_data['is_student'] = True
        validated_data['is_public'] = True  # Self-registered student

        # Create user with hashed password
        user = get_user_model().objects.create_user(**validated_data)

        return user


class StudentSerializer(serializers.ModelSerializer):
    region_name = serializers.CharField(source='region.name', read_only=True, allow_null=True)
    purchased_hours = serializers.SerializerMethodField()
    remaining_hours = serializers.SerializerMethodField()
    used_hours = serializers.SerializerMethodField()

    def get_purchased_hours(self, obj):
        return float(obj.user.total_purchased_hours) if obj.user else 0

    def get_remaining_hours(self, obj):
        return float(obj.user.remaining_hours) if obj.user else 0

    def get_used_hours(self, obj):
        return float(obj.user.used_hours) if obj.user else 0

    class Meta:
        model = Student
        fields = ['id', 'full_name', 'email', 'contact_number', 'is_public', 'is_verified', 'joined_at', 'professor', 'region', 'region_name', 'purchased_hours', 'remaining_hours', 'used_hours']
        read_only_fields = ['id', 'is_public', 'joined_at', 'region_name', 'purchased_hours', 'remaining_hours', 'used_hours']
        extra_kwargs = {
            'professor': {'required': False, 'allow_null': True},
            'region': {'required': False, 'allow_null': True},
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
    region_name = serializers.SerializerMethodField()
    display_role = serializers.SerializerMethodField()
    confirm_password = serializers.CharField(
        write_only=True,
        required=False,
        style={'input_type': 'password'}
    )

    def get_display_role(self, obj):
        role = getattr(obj, 'role', '')
        is_public = getattr(obj, 'is_public', False)
        if role in ('professor', 'teacher'):
            return 'Public Professor' if is_public else 'Pro Professor'
        if role == 'student':
            return 'Public Student' if is_public else 'Pro Student'
        return role.capitalize() if role else 'Unknown'

    def get_region_name(self, obj):
        if obj.region_id:
            return obj.region.name
        # For students, region may be set on the linked Student record
        if obj.role == 'student':
            student = Student.objects.filter(user=obj).select_related('region').first()
            if student and student.region_id:
                return student.region.name
        return None

    class Meta:
        model = get_user_model()
        fields = [
            'email', 'password', 'full_name', 'role', 'display_role', 'is_public', 'bio',
            'contact_number', 'photo', 'city', 'remaining_hours', 'used_hours',
            'total_purchased_hours', 'confirm_password', 'region', 'region_name',
            'subscribed_pack_details', 'booking_details', 'is_verified'
        ]
        extra_kwargs = {
            'password': {'write_only': True, 'min_length': 8},
            'remaining_hours': {'read_only': True},
            'used_hours': {'read_only': True},
            'is_public': {'read_only': True},
            'region': {'required': False, 'allow_null': True},
        }

    def validate_email(self, value):
        """Validate email format"""
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', value):
            raise serializers.ValidationError("Invalid email format.")
        return value.lower()

    def validate_contact_number(self, value):
        """Validate contact number format"""
        if not value:
            return value  # Contact number is optional in UserSerializer

        # Remove any spaces or special characters for validation (keep +)
        clean_number = re.sub(r'[^\d+]', '', value)

        # Basic validation for international phone number (starts with + and has 8-15 digits)
        if not re.match(r'^\+\d{8,15}$', clean_number):
            raise serializers.ValidationError(
                "Invalid phone number format. Use international format: +[country_code][number] (e.g., +351912345678)"
            )

        return value

    def validate(self, attrs):
        """Validate password confirmation if provided"""
        if 'confirm_password' in attrs:
            if attrs.get('password') != attrs.get('confirm_password'):
                raise serializers.ValidationError({
                    "password": "Passwords do not match."
                })
            # Remove confirm_password before saving
            attrs.pop('confirm_password', None)

        # Validate password strength if provided
        password = attrs.get('password')
        if password:
            if len(password) < 8:
                raise serializers.ValidationError({
                    "password": "Password must be at least 8 characters long."
                })
            if not re.search(r'[A-Z]', password):
                raise serializers.ValidationError({
                    "password": "Password must contain at least one uppercase letter (A-Z)."
                })
            if not re.search(r'[a-z]', password):
                raise serializers.ValidationError({
                    "password": "Password must contain at least one lowercase letter (a-z)."
                })
            if not re.search(r'\d', password):
                raise serializers.ValidationError({
                    "password": "Password must contain at least one digit (0-9)."
                })
            if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
                raise serializers.ValidationError({
                    "password": "Password must contain at least one special character (!@#$%^&*(),.?\":{}|<>)."
                })

        return attrs

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
        # Pro professor: self-registered, so is_public=False
        user.is_public = False
        # Set default is_verified if not provided
        if not hasattr(user, 'is_verified') or user.is_verified is None:
            user.is_verified = False
        user.save(update_fields=['is_public', 'is_verified'])
        return user

    def to_representation(self, instance):
        """Enhanced response to include JWT tokens for students"""
        data = super().to_representation(instance)

        # Add JWT tokens for student users
        if instance.role == 'student':
            from rest_framework_simplejwt.tokens import RefreshToken
            refresh = RefreshToken.for_user(instance)
            data['tokens'] = {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
            data['token_type'] = 'Bearer'
            data['message'] = 'Student registered successfully'

        return data

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
    region_name = serializers.CharField(source='region.name', read_only=True, allow_null=True)


    class Meta:
        model = User
        fields = [
            'id', 'email', 'password', 'full_name', 'role', 'bio', 'date_joined',
            'contact_number', 'photo', 'is_active', 'is_public', 'is_verified', 'street', 'city', 'state', 'country',
            'zipcode', 'students', 'student_ids', 'remaining_hours', 'used_hours',
            'total_purchased_hours', 'region', 'region_name',
            'subscribed_pack_details', 'booking_details'
        ]
        read_only_fields = ['id', 'date_joined', 'bio', 'used_hours', 'is_public', 'is_verified', 'region_name']
        extra_kwargs = {
            'password': {'write_only': True, 'min_length': 8},
            'is_active': {'read_only': True},
            'region': {'required': False, 'allow_null': True},
        }

    def validate_email(self, value):
        """Validate email format"""
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', value):
            raise serializers.ValidationError("Invalid email format.")
        return value.lower()

    def validate_contact_number(self, value):
        """Validate contact number format"""
        if not value:
            return value  # Contact number is optional

        # Remove any spaces or special characters for validation (keep +)
        clean_number = re.sub(r'[^\d+]', '', value)

        # Basic validation for international phone number (starts with + and has 8-15 digits)
        if not re.match(r'^\+\d{8,15}$', clean_number):
            raise serializers.ValidationError(
                "Invalid phone number format. Use international format: +[country_code][number] (e.g., +351912345678)"
            )

        return value

    def validate_password(self, value):
        """Validate password strength"""
        if value and len(value) < 8:
            raise serializers.ValidationError("Password must be at least 8 characters long.")
        return value

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
                try:
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
                        fail_silently=True,
                    )
                except Exception:
                    pass
            user.set_password(password)
        # Public professor: added by admin, so is_public=True
        if user.role == 'professor':
            user.is_public = True
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


class StudentLoginSerializer(serializers.Serializer):
    """Serializer for student login with JWT"""
    email = serializers.EmailField(required=True)
    password = serializers.CharField(
        required=True,
        write_only=True,
        style={'input_type': 'password'}
    )

    def validate_email(self, value):
        """Normalize email to lowercase"""
        return value.lower()

    def validate(self, attrs):
        """Validate credentials and return user"""
        email = attrs.get('email')
        password = attrs.get('password')

        if email and password:
            user = authenticate(
                request=self.context.get('request'),
                username=email,
                password=password
            )

            if not user:
                raise serializers.ValidationError(
                    "Invalid email or password.",
                    code='authorization'
                )

            if not user.is_active:
                raise serializers.ValidationError(
                    "This user account has been disabled.",
                    code='authorization'
                )

            if user.role != 'student':
                raise serializers.ValidationError(
                    "This endpoint is for students only.",
                    code='authorization'
                )

            attrs['user'] = user
            return attrs

        raise serializers.ValidationError(
            "Both email and password are required.",
            code='required'
        )


class VerifyEmailSerializer(serializers.Serializer):
    """Serializer for email verification with OTP"""
    email = serializers.EmailField(required=True)
    otp = serializers.CharField(required=True, max_length=6, min_length=6)

    def validate_email(self, value):
        """Normalize email to lowercase"""
        return value.lower()


class ResendVerificationOTPSerializer(serializers.Serializer):
    """Serializer for resending verification OTP"""
    email = serializers.EmailField(required=True)

    def validate_email(self, value):
        """Normalize email to lowercase and check if registration exists"""
        email = value.lower()
        # Check if there's a pending registration or existing user
        if not EmailVerificationOTP.objects.filter(email=email).exists() and not get_user_model().objects.filter(email=email, role='student').exists():
            raise serializers.ValidationError("No registration found with this email address.")
        return email
