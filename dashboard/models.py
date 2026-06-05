# videos/models.py
from django.db import models
from django.conf import settings

from django.utils import timezone
from user.models import User


# Log professor/teacher signups
class TeacherVisit(models.Model):
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'role__in': ['professor', 'teacher']})
    visited_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.teacher.email} visited at {self.visited_at}"

# Log student signups
class StudentVisit(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'role': 'student'})
    visited_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.student.email} visited at {self.visited_at}"

class Video(models.Model):
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='videos'
    )
    video_file = models.FileField(upload_to='videos/')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
