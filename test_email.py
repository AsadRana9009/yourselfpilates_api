#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'yourselfpilot.settings')
django.setup()

from django.core.mail import send_mail
from django.conf import settings

print(f"Email Backend: {settings.EMAIL_BACKEND}")
print(f"SMTP Host: {settings.EMAIL_HOST}")
print(f"SMTP Port: {settings.EMAIL_PORT}")
print(f"From Email: {settings.DEFAULT_FROM_EMAIL}")
print(f"SMTP User: {settings.EMAIL_HOST_USER}")

try:
    result = send_mail(
        'Test Email from Yourself Pilates',
        'This is a test email to verify SMTP is working.',
        settings.DEFAULT_FROM_EMAIL,
        ['sanamobin074@gmail.com'],
        fail_silently=False,
    )
    print(f"Email sent successfully! Result: {result}")
except Exception as e:
    print(f"Email sending failed: {str(e)}")
    import traceback
    traceback.print_exc()