from django.db import models
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from user.models import Student

User = get_user_model()

TIME_SLOTS = [
    ('00:00 - 01:00', '00:00 - 01:00'), ('01:00 - 02:00', '01:00 - 02:00'),
    ('02:00 - 03:00', '02:00 - 03:00'), ('03:00 - 04:00', '03:00 - 04:00'),
    ('04:00 - 05:00', '04:00 - 05:00'), ('05:00 - 06:00', '05:00 - 06:00'),
    ('06:00 - 07:00', '06:00 - 07:00'), ('07:00 - 08:00', '07:00 - 08:00'),
    ('08:00 - 09:00', '08:00 - 09:00'), ('09:00 - 10:00', '09:00 - 10:00'),
    ('10:00 - 11:00', '10:00 - 11:00'), ('11:00 - 12:00', '11:00 - 12:00'),
    ('12:00 - 13:00', '12:00 - 13:00'), ('13:00 - 14:00', '13:00 - 14:00'),
    ('14:00 - 15:00', '14:00 - 15:00'), ('15:00 - 16:00', '15:00 - 16:00'),
    ('16:00 - 17:00', '16:00 - 17:00'), ('17:00 - 18:00', '17:00 - 18:00'),
    ('18:00 - 19:00', '18:00 - 19:00'), ('19:00 - 20:00', '19:00 - 20:00'),
    ('20:00 - 21:00', '20:00 - 21:00'), ('21:00 - 22:00', '21:00 - 22:00'),
    ('22:00 - 23:00', '22:00 - 23:00'), ('23:00 - 24:00', '23:00 - 24:00')
]

class Booking(models.Model):
    PIN_TYPE_CHOICES = [
        ('onetime', 'One-Time'),
        ('hourly', 'Hourly'),
        ('permanent', 'Permanent'),
    ]

    STATUS_CHOICES = [
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
    ]

    BOOKING_TYPE_CHOICES = [
        ('pro', 'Pro'),
        ('public', 'Public'),
    ]

    title = models.CharField(max_length=100, blank=True, null=True, unique=False)
    booking_type = models.CharField(
        max_length=10,
        choices=BOOKING_TYPE_CHOICES,
        default='pro'
    )
    professor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        limit_choices_to={'role__in': ['professor', 'teacher']},
        related_name='professor_bookings'
    )
    students = models.ManyToManyField(
        Student,
        related_name='student_bookings'
    )
    booking_date = models.DateField()
    time_slot = models.CharField(
        max_length=20,
        choices=TIME_SLOTS
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='approve'
    )
    approve = models.BooleanField(default=False)

    total_students = models.PositiveIntegerField(default=10)
    notes = models.TextField(blank=True, null=True)
    igloo_pin = models.CharField(max_length=10, blank=True, null=True, help_text='Igloo PIN code for this booking')
    igloo_job_id = models.CharField(max_length=100, blank=True, null=True, help_text='Igloo Job ID for this booking')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('booking_date', 'time_slot', 'professor')
        ordering = ['booking_date', 'time_slot']

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)  # Save the instance first
        self.total_students = self.students.count() 

    def clean(self):
        if Booking.objects.filter(
            booking_date=self.booking_date,
            time_slot=self.time_slot
        ).exclude(status='cancelled').exclude(pk=self.pk).exists():
            raise ValidationError("This time slot is already booked")

    def __str__(self):
        return f"{self.booking_date} {self.get_time_slot_display()} - {self.professor.get_full_name()}"
