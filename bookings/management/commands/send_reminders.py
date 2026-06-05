from django.core.management.base import BaseCommand
from bookings.scheduler import send_booking_reminders

class Command(BaseCommand):
    help = 'Send reminder emails for tomorrow’s bookings.'

    def handle(self, *args, **kwargs):
        send_booking_reminders()
        self.stdout.write(self.style.SUCCESS("Booking reminders sent successfully."))
