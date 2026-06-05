from django.core.management.base import BaseCommand
from bookings.models import Booking
from bookings.tasks import delete_igloo_pin
from django.utils import timezone

class Command(BaseCommand):
    help = 'Expires Igloo PINs for bookings whose end time has passed.'

    def handle(self, *args, **options):
        now = timezone.now()
        expired_bookings = Booking.objects.filter(
            igloo_pin__isnull=False,
            booking_date__lt=now.date()
        )
        for booking in expired_bookings:
            delete_igloo_pin(booking)
        # Also check for bookings ending today but with end time passed
        today_bookings = Booking.objects.filter(
            igloo_pin__isnull=False,
            booking_date=now.date()
        )
        from datetime import datetime
        for booking in today_bookings:
            try:
                _, end_time = booking.time_slot.split(' - ')
                end_dt = datetime.combine(booking.booking_date, datetime.strptime(end_time, '%H:%M').time())
                if timezone.now() > timezone.make_aware(end_dt):
                    delete_igloo_pin(booking)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error parsing end time for booking {booking.id}: {e}"))
        self.stdout.write(self.style.SUCCESS('Igloo PIN expiration check complete.'))
