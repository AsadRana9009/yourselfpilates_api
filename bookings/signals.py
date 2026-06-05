from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from .models import Booking
from .igloo_utils import create_igloo_pin_for_booking
from django.core.mail import send_mail
from django.template.loader import render_to_string

def send_pin_email(booking, pin):
    subject = f"Agendamento Confirmado - Yourself Pilates"

    # Collect student names
    student_names = ', '.join(
        [s.full_name for s in booking.students.all()]
    ) or 'N/A'

    # Format date as dd/mm/yyyy
    formatted_date = booking.booking_date.strftime('%d/%m/%Y')

    # Email to professor using HTML template
    if booking.professor:
        context = {
            'instructor_name': booking.professor.full_name,
            'student_names': student_names,
            'booking_date': formatted_date,
            'time_slot': booking.time_slot,
            'pin': pin,
        }
        html_content = render_to_string('emails/booking_confirmed.html', context)
        plain_message = (
            f"Olá, {booking.professor.full_name}!\n\n"
            f"O agendamento da aula com o(a) aluno(a) {student_names} foi confirmado com sucesso.\n\n"
            f"Data: {formatted_date}\n"
            f"Horário: {booking.time_slot}\n"
            f"PIN de acesso: {pin}\n\n"
            f"Com os melhores cumprimentos,\nYourself Pilates"
        )
        send_mail(
            subject,
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            [booking.professor.email],
            fail_silently=True,
            html_message=html_content,
        )

    # Portuguese weekday names
    WEEKDAYS_PT = {
        0: 'Segunda-Feira', 1: 'Terça-Feira', 2: 'Quarta-Feira',
        3: 'Quinta-Feira', 4: 'Sexta-Feira', 5: 'Sábado', 6: 'Domingo'
    }
    booking_weekday = WEEKDAYS_PT.get(booking.booking_date.weekday(), '')

    # Email to each student using HTML template
    for student in booking.students.all():
        student_context = {
            'student_name': student.full_name,
            'booking_date': formatted_date,
            'booking_weekday': booking_weekday,
            'time_slot': booking.time_slot,
        }
        student_html = render_to_string('emails/booking_student.html', student_context)
        plain_message = (
            f"Olá, {student.full_name}!\n\n"
            f"A sua aula foi agendada na Yourself Pilates!\n\n"
            f"Data: {booking_weekday} | {formatted_date}\n"
            f"Horário: {booking.time_slot}\n\n"
            f"Bom treino!\nEquipa Yourself Pilates"
        )
        send_mail(
            'Aula Agendada - Yourself Pilates',
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            [student.email],
            fail_silently=True,
            html_message=student_html,
        )

@receiver(post_save, sender=Booking)
def create_igloo_pin_signal(sender, instance, created, **kwargs):
    device_id = getattr(settings, 'IGLOO_DEVICE_ID', None)
    bridge_id = getattr(settings, 'IGLOO_BRIDGE_ID', None)
    if created and device_id and bridge_id and not instance.igloo_pin:
        try:
            pin, job_id = create_igloo_pin_for_booking(instance, device_id, bridge_id)
            instance.igloo_pin = pin
            instance.igloo_job_id = job_id
            instance.save(update_fields=["igloo_pin", "igloo_job_id"])
            send_pin_email(instance, pin)
        except Exception as e:
            print(f"Igloo PIN creation failed (signal): {e}")
