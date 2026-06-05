from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from subscriptions.models import Order, Pack


class OrderVisibilityTests(APITestCase):
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
        self.student = User.objects.create_user(
            email='student@example.com',
            password='testpass123',
            full_name='Student User',
            role='student',
        )
        self.professor_pack = Pack.objects.create(
            title='Professor Pack',
            target_role='professor',
            price='99.00',
            total_hours=10,
        )
        self.student_pack = Pack.objects.create(
            title='Student Pack',
            target_role='student',
            price='49.00',
            total_hours=5,
        )
        self.professor_order = Order.objects.create(
            user=self.professor,
            pack=self.professor_pack,
            amount=self.professor_pack.price,
            payment_method='creditcard',
        )
        self.student_order = Order.objects.create(
            user=self.student,
            pack=self.student_pack,
            amount=self.student_pack.price,
            payment_method='creditcard',
        )

    def test_admin_can_filter_pro_orders(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get('/api/subscriptions/orders/?owner_role=pro')

        self.assertEqual(response.status_code, 200)
        order_ids = {order['id'] for order in response.data['results']}
        self.assertIn(self.professor_order.id, order_ids)
        self.assertNotIn(self.student_order.id, order_ids)

    def test_admin_can_filter_student_orders(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get('/api/subscriptions/orders/?owner_role=student')

        self.assertEqual(response.status_code, 200)
        order_ids = {order['id'] for order in response.data['results']}
        self.assertIn(self.student_order.id, order_ids)
        self.assertNotIn(self.professor_order.id, order_ids)

    def test_non_admin_stays_scoped_to_own_orders(self):
        self.client.force_authenticate(user=self.student)

        response = self.client.get('/api/subscriptions/orders/?owner_role=student')

        self.assertEqual(response.status_code, 200)
        order_ids = {order['id'] for order in response.data['results']}
        self.assertIn(self.student_order.id, order_ids)
        self.assertNotIn(self.professor_order.id, order_ids)
