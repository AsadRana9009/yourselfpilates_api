from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

def send_booking_reminders():
    """
    Send reminders for bookings scheduled tomorrow.
    This will be triggered externally via a cron job.
    """
    from .models import Booking  

    tomorrow = timezone.now().date() + timedelta(days=1)
    upcoming_bookings = Booking.objects.filter(
        booking_date=tomorrow,
        status='confirmed'
    ).select_related('professor').prefetch_related('students')

    if not upcoming_bookings.exists():
        logger.info("No upcoming bookings found for tomorrow.")
        return

    for booking in upcoming_bookings:
        try:
            # Send to professor
            send_reminder_email(
                recipient_email=booking.professor.email,
                recipient_name=booking.professor.full_name,
                booking=booking
            )

            # Send to all students
            for student in booking.students.all():
                send_reminder_email(
                    recipient_email=student.email,
                    recipient_name=student.full_name,
                    booking=booking
                )

        except Exception as e:
            logger.error(f"Error sending reminder for booking {booking.id}: {e}")

    logger.info(f"Reminders sent for {upcoming_bookings.count()} booking(s) scheduled for {tomorrow}.")


def send_reminder_email(recipient_email, recipient_name, booking):
    """Send individual reminder email."""
    subject = f"Reminder: Upcoming Booking Scheduled for Tomorrow - {booking.booking_date}"

    message = (
        f"Dear {recipient_name},\n\n"
        f"This is a formal reminder that you have a booking scheduled for tomorrow. Please find the details below:\n\n"
        f"Date: {booking.booking_date}\n"
        f"Time: {booking.time_slot}\n"
        f"Professor: {booking.professor.full_name}\n"
        f"Title: {booking.title or 'N/A'}\n"
        f"Notes: {booking.notes or 'No additional notes'}\n\n"
        f"We kindly request that you attend your session on time. If you have any questions or need to reschedule, please contact us in advance.\n\n"
        f"Thank you for choosing Yourself Pilates.\n\n"
        f"Best regards,\nYourself Pilates Team"
    )

    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [recipient_email],
        fail_silently=False,
    )
    logger.info(f"Reminder email sent to {recipient_email} for booking {booking.id}.")
