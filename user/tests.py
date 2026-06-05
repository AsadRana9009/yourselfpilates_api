from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from user.models import Student


class StudentVisibilityTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(
            email='admin@example.com',
            password='testpass123',
            full_name='Admin User',
            role='admin',
        )
        self.professor = User.objects.create_user(
            email='professor@example.com',
            password='testpass123',
            full_name='Professor User',
            role='professor',
        )

        self.private_student = Student.objects.create(
            full_name='Private Student',
            email='private@example.com',
            professor=self.professor,
            is_public=False,
        )
        self.public_student = Student.objects.create(
            full_name='Public Student',
            email='public@example.com',
            is_public=True,
        )

    def test_admin_can_filter_private_students(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get('/api/user/students/?is_public=false')

        self.assertEqual(response.status_code, 200)
        emails = {student['email'] for student in response.data['results']}
        self.assertIn(self.private_student.email, emails)
        self.assertNotIn(self.public_student.email, emails)

    def test_admin_can_filter_public_students(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get('/api/user/students/?is_public=true')

        self.assertEqual(response.status_code, 200)
        emails = {student['email'] for student in response.data['results']}
        self.assertIn(self.public_student.email, emails)
        self.assertNotIn(self.private_student.email, emails)

    def test_professor_filter_stays_scoped_to_own_students(self):
        self.client.force_authenticate(user=self.professor)

        response = self.client.get('/api/user/students/?is_public=false')

        self.assertEqual(response.status_code, 200)
        emails = {student['email'] for student in response.data['results']}
        self.assertIn(self.private_student.email, emails)
        self.assertNotIn(self.public_student.email, emails)
