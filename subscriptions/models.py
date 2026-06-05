from django.db import models
from django.conf import settings
import uuid


class Pack(models.Model):
    ROLE_CHOICES = [
        ('student', 'Student'),
        ('professor', 'Professor'),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="packs/", blank=True, null=True)
    active = models.BooleanField(default=True)
    is_public = models.BooleanField(default=False, help_text="If True, visible to all users. If False, Pro members only.")
    target_role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='professor')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    total_hours = models.PositiveIntegerField(default=0, help_text="Total hours included in this pack")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class Order(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ('multibanco', 'MultiBanco'),
        ('mbway', 'MB WAY'),
        ('creditcard', 'Credit Card'),
    ]
    
    PAYMENT_STATUS_CHOICES = [
        ('Pendente', 'Pendente'),
        ('Pago', 'Pago'),
        ('Cancelado', 'Cancelado'),
    ]
    
    # Basic order info
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='orders'
    )
    pack = models.ForeignKey(
        Pack,
        on_delete=models.CASCADE,
        related_name='orders'
    )
    order_id = models.CharField(max_length=25, unique=True, editable=False)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Payment details
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='Pendente')
    
    # MultiBanco specific fields
    mb_key = models.CharField(max_length=50, blank=True, null=True, help_text="MB Key used (e.g., CWR-828507)")
    mb_entity = models.CharField(max_length=10, blank=True, null=True, help_text="MultiBanco Entity")
    mb_reference = models.CharField(max_length=20, blank=True, null=True, help_text="MultiBanco Reference")
    expiry_date = models.DateTimeField(blank=True, null=True, help_text="Payment expiry date")
    
    # MB WAY specific fields
    mbway_phone = models.CharField(max_length=20, blank=True, null=True, help_text="Phone number for MB WAY (format: 351#912345678)")
    
    # Credit Card specific fields
    ccard_payment_url = models.TextField(blank=True, null=True, help_text="IfThenPay payment page URL")
    ccard_signature_key = models.CharField(max_length=100, blank=True, null=True, help_text="Signature key (sk) for verification")
    
    # IfThenPay tracking
    request_id = models.CharField(max_length=100, blank=True, null=True, help_text="IfThenPay RequestId")
    
    # Payment method change tracking
    payment_method_updated_at = models.DateTimeField(blank=True, null=True, help_text="Last time payment method was changed")
    previous_payment_method = models.CharField(max_length=20, blank=True, null=True, help_text="Previous payment method before change")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    payment_datetime = models.DateTimeField(blank=True, null=True, help_text="Datetime reported by IfThenPay when payment was made")
    
    class Meta:
        ordering = ['-created_at']
    
    def save(self, *args, **kwargs):
        if not self.order_id:
            # Generate unique order_id (max 25 chars)
            self.order_id = f"ORD{uuid.uuid4().hex[:20].upper()}"
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"Order {self.order_id} - {self.user.email} - {self.payment_status}"


class SubscriptionHistory(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subscription_history'
    )
    pack = models.ForeignKey(
        Pack,
        on_delete=models.CASCADE,
        related_name='subscriptions'
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subscription_records',
        help_text="Associated order for this subscription"
    )
    hours_added = models.PositiveIntegerField(help_text="Hours added from this subscription")
    subscribed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-subscribed_at']
        verbose_name_plural = "Subscription Histories"

    def __str__(self):
        return f"{self.user.email} - {self.pack.title} ({self.subscribed_at.date()})"
