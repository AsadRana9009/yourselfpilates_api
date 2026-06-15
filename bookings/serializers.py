from rest_framework import serializers
from .models import Booking, TIME_SLOTS
from django.utils import timezone
from user.models import User, Student
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from decimal import Decimal


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
        queryset=User.objects.filter(role='professor'),
        write_only=True
    )
    students = serializers.PrimaryKeyRelatedField(
        queryset=Student.objects.all(),
        many=True,
        write_only=True
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
        extra_kwargs = {
            'status': {'required': False},
            'created_at': {'read_only': True},
            'updated_at': {'read_only': True},
            'total_students': {'read_only': True},
            'approve': {'required': False},
            'region': {'required': False, 'allow_null': True},
        }

    def validate(self, data):
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
            professor = data.get('professor')
            requesting_user = self.context['request'].user
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

        self.send_booking_email(booking, 'created')
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
        self.send_booking_email(instance, 'updated')
        return instance
    
    def send_booking_email(self, booking, action):
        """Send formal, descriptive email notification to student and professor."""
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
                'pin': booking.igloo_pin or 'N/A',
            }
            html_content = render_to_string('emails/booking_confirmed.html', context)
            plain_message = (
                f"Olá, {booking.professor.full_name}!\n\n"
                f"O agendamento da aula com o(a) aluno(a) {student_names} foi confirmado com sucesso.\n\n"
                f"Data: {formatted_date}\n"
                f"Horário: {booking.time_slot}\n"
                f"PIN de acesso: {booking.igloo_pin or 'N/A'}\n\n"
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
