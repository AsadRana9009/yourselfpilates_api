from rest_framework import serializers
from .models import Booking, TIME_SLOTS
from django.utils import timezone
from user.models import User, Student
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from decimal import Decimal
import threading
import logging

logger = logging.getLogger(__name__)


WEEKDAYS_PT = {
    0: 'Segunda-Feira', 1: 'Terça-Feira', 2: 'Quarta-Feira',
    3: 'Quinta-Feira', 4: 'Sexta-Feira', 5: 'Sábado', 6: 'Domingo'
}

ROLE_LABEL_MAP = {
    'professor': 'Professor/Instrutor',
    'teacher': 'Professor/Instrutor',
    'student': 'Aluno (Público)',
    'admin': 'Administrador',
}


def send_booking_notifications_async(booking, action='created', created_by_role='professor'):
    """Fire-and-forget wrapper — runs email delivery in a background thread."""
    thread = threading.Thread(
        target=_send_booking_notifications_safe,
        args=(booking, action, created_by_role),
        daemon=True,
    )
    thread.start()


def _send_booking_notifications_safe(booking, action, created_by_role):
    try:
        send_booking_notifications(booking, action, created_by_role)
    except Exception as exc:
        logger.error("send_booking_notifications failed: %s", exc, exc_info=True)


def send_booking_notifications(booking, action='created', created_by_role='professor'):
    """Send email notifications to professor, each student, and all admin users."""
    formatted_date = booking.booking_date.strftime('%d/%m/%Y')
    booking_weekday = WEEKDAYS_PT.get(booking.booking_date.weekday(), '')
    student_names = ', '.join([s.full_name for s in booking.students.all()]) or 'N/A'
    region_name = booking.region.name if booking.region else 'N/A'
    booking_type_display = 'Pro' if booking.booking_type == 'pro' else 'Público'
    created_by_label = ROLE_LABEL_MAP.get(created_by_role, created_by_role.capitalize())
    action_label = 'criado' if action == 'created' else 'atualizado'
    pin = booking.igloo_pin or 'N/A'
    professor_name = booking.professor.full_name if booking.professor else 'N/A'
    professor_email = booking.professor.email if booking.professor else 'N/A'

    # ── 1. Professor email ──────────────────────────────────────────────────
    if booking.professor:
        context = {
            'instructor_name': professor_name,
            'student_names': student_names,
            'booking_date': formatted_date,
            'booking_weekday': booking_weekday,
            'time_slot': booking.time_slot,
            'pin': pin,
            'notes': booking.notes or '',
            'booking_type': booking_type_display,
            'region_name': region_name,
            'booking_id': booking.id,
            'title': booking.title or '',
        }
        html_content = render_to_string('emails/booking_confirmed.html', context)
        plain_message = (
            f"Olá, {professor_name}!\n\n"
            f"O agendamento da aula foi confirmado com sucesso.\n\n"
            f"Data: {formatted_date}\n"
            f"Horário: {booking.time_slot}\n"
            f"Aluno(a): {student_names}\n"
            f"Tipo: {booking_type_display}\n"
            f"PIN de acesso: {pin}\n"
            f"Notas: {booking.notes or 'N/A'}\n\n"
            f"Com os melhores cumprimentos,\nYourself Pilates"
        )
        send_mail(
            "Agendamento Confirmado - Yourself Pilates",
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            [booking.professor.email],
            fail_silently=True,
            html_message=html_content,
        )

    # ── 2. Student emails ───────────────────────────────────────────────────
    for student in booking.students.all():
        student_context = {
            'student_name': student.full_name,
            'booking_date': formatted_date,
            'booking_weekday': booking_weekday,
            'time_slot': booking.time_slot,
            'professor_name': professor_name,
            'booking_type': booking_type_display,
            'region_name': region_name,
            'notes': booking.notes or '',
        }
        student_html = render_to_string('emails/booking_student.html', student_context)
        plain_message = (
            f"Olá, {student.full_name}!\n\n"
            f"A sua aula foi agendada na Yourself Pilates!\n\n"
            f"Data: {booking_weekday} | {formatted_date}\n"
            f"Horário: {booking.time_slot}\n"
            f"Instrutor: {professor_name}\n"
            f"Tipo: {booking_type_display}\n\n"
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

    # ── 3. Admin emails (all active admins) ─────────────────────────────────
    admin_emails = list(
        User.objects.filter(role='admin', is_active=True).values_list('email', flat=True)
    )
    if admin_emails:
        student_details = [
            {'name': s.full_name, 'email': s.email or 'N/A'}
            for s in booking.students.all()
        ]
        admin_context = {
            'action': action_label,
            'booking_id': booking.id,
            'title': booking.title or 'N/A',
            'booking_type': booking_type_display,
            'professor_name': professor_name,
            'professor_email': professor_email,
            'student_details': student_details,
            'student_names': student_names,
            'booking_date': formatted_date,
            'booking_weekday': booking_weekday,
            'time_slot': booking.time_slot,
            'notes': booking.notes or 'N/A',
            'region_name': region_name,
            'status': booking.get_status_display() if hasattr(booking, 'get_status_display') else booking.status,
            'pin': pin,
            'created_by': created_by_label,
            'total_students': booking.total_students,
        }
        admin_html = render_to_string('emails/booking_admin.html', admin_context)
        plain_message = (
            f"[ADMIN] Agendamento #{booking.id} {action_label}\n\n"
            f"Criado por: {created_by_label}\n"
            f"Tipo: {booking_type_display}\n"
            f"Professor: {professor_name} ({professor_email})\n"
            f"Aluno(a): {student_names}\n"
            f"Data: {booking_weekday} | {formatted_date}\n"
            f"Horário: {booking.time_slot}\n"
            f"Região: {region_name}\n"
            f"Status: {admin_context['status']}\n"
            f"PIN: {pin}\n"
        )
        send_mail(
            f"[Admin] Agendamento #{booking.id} {action_label} - Yourself Pilates",
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            admin_emails,
            fail_silently=True,
            html_message=admin_html,
        )


class UserDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'full_name', 'email']


class StudentDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = Student
        fields = ['id', 'full_name', 'email']


class BookingSerializer(serializers.ModelSerializer):
    total_students = serializers.IntegerField(read_only=True)

    professor = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role__in=['professor', 'teacher']),
        write_only=True,
        required=False,
        allow_null=True,
    )
    students = serializers.PrimaryKeyRelatedField(
        queryset=Student.objects.all(),
        many=True,
        write_only=True,
        required=False,
    )

    professor_details = UserDataSerializer(source='professor', read_only=True)
    student_details = StudentDataSerializer(source='students', many=True, read_only=True)
    region_name = serializers.CharField(source='region.name', read_only=True, allow_null=True)

    class Meta:
        model = Booking
        fields = [
            'id', 'title', 'booking_type', 'professor', 'booking_date', 'time_slot', 'approve',
            'status', 'total_students', 'notes', 'students', 'created_at', 'updated_at',
            'professor_details', 'student_details', 'region', 'region_name'
        ]
        validators = []  # UniqueTogetherValidator is replaced by the manual check in validate()
        extra_kwargs = {
            'status': {'required': False},
            'created_at': {'read_only': True},
            'updated_at': {'read_only': True},
            'total_students': {'read_only': True},
            'approve': {'required': False},
            'region': {'required': False, 'allow_null': True},
        }

    def validate(self, data):
        requesting_user = self.context['request'].user

        # Pro professor bookings have no region
        if data.get('booking_type') == 'pro':
            data['region'] = None

        # Pro professors can only attach their own assigned students.
        # Public professors can attach any public student from their region.
        if not self.instance and getattr(requesting_user, 'role', None) in ['professor', 'teacher']:
            if not getattr(requesting_user, 'is_public', False):
                # Pro professor: students must be assigned to them
                bad = [s for s in data.get('students', []) if s.professor_id != requesting_user.id]
                if bad:
                    names = ', '.join(s.full_name for s in bad)
                    raise serializers.ValidationError(
                        f"Students not assigned to you: {names}"
                    )
            else:
                # Public professor: students must be public and in the same region
                professor_region = requesting_user.region
                bad = [
                    s for s in data.get('students', [])
                    if not s.is_public or (professor_region and s.region_id != professor_region.id)
                ]
                if bad:
                    names = ', '.join(s.full_name for s in bad)
                    raise serializers.ValidationError(
                        f"Students not from your region: {names}"
                    )

        if 'booking_date' in data and data['booking_date'] < timezone.now().date():
            raise serializers.ValidationError("Booking date must be in the future")

        if 'booking_date' in data and 'time_slot' in data:
            existing = Booking.objects.filter(
                booking_date=data['booking_date'],
                time_slot=data['time_slot']
            ).exclude(status='cancelled')
            if self.instance:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise serializers.ValidationError("This time slot is already booked")

        # Only check remaining_hours for new bookings (not updates)
        # Admin can always create bookings regardless of professor's hours
        if not self.instance:
            professor = data.get('professor') or (requesting_user if requesting_user.role in ['professor', 'teacher'] else None)
            if (
                professor
                and professor.role in ['professor', 'teacher']
                and getattr(requesting_user, 'role', None) != 'admin'
            ):
                if professor.remaining_hours < 1:
                    raise serializers.ValidationError(
                        "Insufficient hours. Please subscribe to a pack to book classes."
                    )

        return data

    def validate_status(self, value):
        if 'status' in self.initial_data and self.context['request'].user.role != 'admin':
            raise serializers.ValidationError("Only admin can change booking status")
        return value

    def create(self, validated_data):
        student_ids = validated_data.pop('students', [])
        booking = Booking.objects.create(**validated_data)
        booking.students.set(student_ids)
        # persist accurate total_students after m2m set
        booking.total_students = booking.students.count()
        booking.save()

        # Deduct 1 hour from professor's remaining_hours — skip for admin-created bookings
        requesting_user = self.context['request'].user
        if (
            booking.professor.role in ['professor', 'teacher']
            and getattr(requesting_user, 'role', None) != 'admin'
        ):
            booking.professor.remaining_hours = booking.professor.remaining_hours - Decimal('1')
            booking.professor.save()

        created_by_role = self.context['request'].user.role
        send_booking_notifications(booking, 'created', created_by_role)
        return booking

    def update(self, instance, validated_data):
        for attr in ['title', 'booking_type', 'professor', 'booking_date', 'time_slot', 'approve', 'status', 'notes', 'region']:
            if attr in validated_data:
                setattr(instance, attr, validated_data[attr])
        instance.save()

        if 'students' in validated_data:
            instance.students.set(validated_data['students'])
            instance.total_students = instance.students.count()
            instance.save()
        created_by_role = self.context['request'].user.role
        send_booking_notifications(instance, 'updated', created_by_role)
        return instance
