from django.conf import settings
from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)

class UserManager(BaseUserManager):
    """Manager for users."""

    def create_user(self, email, password=None, **extra_fields):
        """Create and return a user with an email and password."""
        if not email:
            raise ValueError('User must have an email!')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        user.is_active = True
        return user


    def create_superuser(self, email, password):
        """Create, save and return a super user."""
        if not email:
            raise ValueError('User must have an email!')
        user = self.create_user(email, password)
        user.is_superuser = True
        user.role = "admin"
        user.is_active = True
        user.save(using=self._db)
        return user



class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(max_length=255, unique=True)
    bio = models.TextField(blank=True, null=True)
    date_joined = models.DateTimeField(auto_now_add=True)
    full_name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    # Admin and staff fields
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)

    contact_number = models.CharField(max_length=20, blank=True, null=True)
    role = models.CharField(max_length=20, default='professor')
    
    is_student = models.BooleanField(default=False)
    is_public = models.BooleanField(default=False, help_text="True for professors who self-registered; False for admin-created.")
    photo = models.ImageField(upload_to='profile_photos/', blank=True, null=True)

    street = models.CharField(max_length=200, null=True, blank=True)
    city = models.CharField(max_length=200, null=True, blank=True)
    country = models.CharField(max_length=200, null=True, blank=True)
    state = models.CharField(max_length=200, null=True, blank=True)
    zipcode = models.CharField(max_length=100, null=True, blank=True)


    # Subscription fields
    subscribed_pack = models.ForeignKey(
        'subscriptions.Pack',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subscribers',
        help_text="Currently subscribed pack"
    )
    used_hours = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Total hours used by the professor for bookings"
    )
    remaining_hours = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Remaining hours from subscription"
    )
    total_purchased_hours = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Total hours purchased by the user from all packs"
    )
    subscription_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date when user last subscribed"
    )

    objects = UserManager()

    USERNAME_FIELD = 'email'


class PasswordResetOTP(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='password_reset_otps')
    code = models.CharField(max_length=6)  # 4-6 digit OTP
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    def is_expired(self):
        from django.utils import timezone
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"OTP for {self.user.email}: {self.code} (expires {self.expires_at})"


class Student(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile', null=True, blank=True)
    full_name = models.CharField(max_length=255)
    email = models.EmailField()
    contact_number = models.CharField(max_length=20, blank=True, null=True)
    is_public = models.BooleanField(default=False, help_text='True when the student registered themselves')
    professor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'professor'},
        related_name='students',
        null=True,
        blank=True,
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name

