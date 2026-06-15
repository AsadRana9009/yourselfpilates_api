import logging

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string

from user.models import User, Student as StudentModel
from dashboard.models import TeacherVisit, StudentVisit

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def create_teacher_student_visit(sender, instance, created, **kwargs):
    # Ensure is_student flag reflects the role field
    expected_is_student = getattr(instance, 'role', '') == 'student'
    if instance.is_student != expected_is_student:
        # Use update to avoid re-triggering signals
        User.objects.filter(pk=instance.pk).update(is_student=expected_is_student)
        # reflect change on current instance to avoid stale attribute
        instance.is_student = expected_is_student

    # Ensure admin users always have is_staff=True for Django admin access
    if instance.role == 'admin' and not instance.is_staff:
        User.objects.filter(pk=instance.pk).update(is_staff=True)
        instance.is_staff = True
    if created:
        if hasattr(instance, 'role') and instance.role in ['professor', 'teacher']:
            if not TeacherVisit.objects.filter(teacher=instance).exists():
                TeacherVisit.objects.create(teacher=instance)
            # Send email to admins when a new professor registers
            if instance.role == 'professor':
                admin_emails = list(User.objects.filter(role='admin').values_list('email', flat=True))
                if admin_emails:
                    subject = 'New Professor Registration'
                    message = (
                        f'Dear Admin,\n\n'
                        f'This is to inform you that a new professor has registered on Yourself Pilates.\n\n'
                        f'Full Name: {instance.full_name}\n'
                        f'Email: {instance.email}\n\n'
                        f'Please review their registration and take any necessary actions.\n\n'
                        f'Best regards,\nYourself Pilates System'
                    )
                    send_mail(
                        subject,
                        message,
                        settings.DEFAULT_FROM_EMAIL,
                        admin_emails,
                        fail_silently=True,
                    )

                # Send branded HTML welcome email to the professor
                try:
                    html_message = render_to_string(
                        'emails/welcome_professor.html',
                        {
                            'full_name': instance.full_name,
                            'frontend_url': settings.FRONTEND_URL,
                        },
                    )
                    send_mail(
                        'Bem-vindo(a) à Yourself Pilates!',
                        '',  # plain-text fallback (empty; HTML is the primary content)
                        settings.DEFAULT_FROM_EMAIL,
                        [instance.email],
                        html_message=html_message,
                        fail_silently=False,
                    )
                except Exception as e:
                    logger.error(
                        'Failed to send welcome email to professor %s: %s',
                        instance.email,
                        e,
                    )

        if hasattr(instance, 'role') and instance.role == 'student':
            if not StudentVisit.objects.filter(student=instance).exists():
                StudentVisit.objects.create(student=instance)
            # Ensure a Student record exists linked to this User
            try:
                if not StudentModel.objects.filter(user=instance).exists():
                    StudentModel.objects.create(
                        user=instance,
                        full_name=getattr(instance, 'full_name', '') or instance.email,
                        email=getattr(instance, 'email', ''),
                        contact_number=getattr(instance, 'contact_number', None),
                        is_public=True,
                    )
            except Exception as e:
                logger.error('Failed creating Student model for user %s: %s', instance.email, e)


# When a Student record is created/updated, ensure the linked User is marked as student
@receiver(post_save, sender=StudentModel)
def mark_user_as_student_on_student_create(sender, instance, created, **kwargs):
    user_pk = instance.user_id
    if not user_pk:
        return
    try:
        user = User.objects.get(pk=user_pk)
    except User.DoesNotExist:
        return
    # set role to student if not already
    changed = False
    if user.role != 'student':
        user.role = 'student'
        changed = True
    if not user.is_student:
        # use update to avoid recursive signals
        User.objects.filter(pk=user.pk).update(is_student=True, role='student')
    elif changed:
        user.save(update_fields=['role'])


# When a Student is deleted, clear the flag on the linked User
@receiver(post_delete, sender=StudentModel)
def unmark_user_as_student_on_student_delete(sender, instance, **kwargs):
    # Use user_id (raw FK column) to avoid a DB lookup that would raise
    # User.DoesNotExist when the Student was cascade-deleted alongside its User.
    user_pk = instance.user_id
    if user_pk:
        User.objects.filter(pk=user_pk).update(is_student=False)
