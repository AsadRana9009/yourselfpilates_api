from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import generics, viewsets, status, permissions
from rest_framework.exceptions import NotFound
from rest_framework.authtoken.models import Token

from user.models import User, Student
from .permissions import IsAdmin
from user.serializers import UserSerializer, UserAdminSerializer, StudentSerializer, AuthTokenSerializer
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.conf import settings
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema
from .models import PasswordResetOTP
from .serializers import RequestPasswordResetOTPSerializer, VerifyPasswordResetOTPSerializer, ConfirmPasswordResetOTPSerializer, ResetPasswordWithOTPSerializer
from django.utils import timezone
import random

class LoginView(APIView):
    """Login endpoint that returns a Django auth token along with user details."""
    @extend_schema(request=AuthTokenSerializer)
    def post(self, request):
        serializer = AuthTokenSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        token, created = Token.objects.get_or_create(user=user)
        return Response({
            'token': token.key,
            'email': user.email,
            'full_name': user.full_name,
            'role': user.role,
            'user_id': str(user.pk),
        })


class CreateUserView(generics.CreateAPIView):
    serializer_class = UserSerializer


class ManageUserView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

    def delete(self, request, *args, **kwargs):
        user = self.get_object()
        user.delete()
        return Response({"detail": "Your account has been deleted."}, status=status.HTTP_204_NO_CONTENT)


class UserAdminViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserAdminSerializer
    permission_classes = [IsAdmin]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='role',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Filter users by role',
            ),
        ]
    )
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        role = request.query_params.get('role')
        if role:
            queryset = queryset.filter(role=role)
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        queryset = self.queryset
        role = self.request.query_params.get('role')
        if role:
            queryset = queryset.filter(role=role)
        is_public = self.request.query_params.get('is_public')
        if is_public is not None:
            queryset = queryset.filter(is_public=is_public.lower() == 'true')
        return queryset.order_by('-date_joined')

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='user_id',
                required=True,
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY
            )
        ],
        responses={status.HTTP_200_OK: UserAdminSerializer}
    )
    @action(detail=False, methods=['get'])
    def approve(self, request):
        user_id = request.query_params.get('user_id')
        user = User.objects.get(id=user_id)
        user.is_active = True
        user.save()
        return Response(self.get_serializer(user).data)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='user_id',
                required=True,
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY
            )
        ],
        responses={status.HTTP_200_OK: UserAdminSerializer}
    )
    @action(detail=False, methods=['get'])
    def cancel(self, request):
        user_id = request.query_params.get('user_id')
        user = User.objects.get(id=user_id)
        user.is_active = False
        user.save()
        return Response(self.get_serializer(user).data)

    @action(detail=True, methods=['post'], url_path='top_up_hours')
    def top_up_hours(self, request, pk=None):
        """Admin: manually add or set remaining_hours for a professor."""
        user = self.get_object()
        hours = request.data.get('hours')
        mode = request.data.get('mode', 'add')  # 'add' or 'set'

        if hours is None:
            return Response(
                {"error": "hours is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            hours = int(hours)
            if hours < 0:
                raise ValueError
        except (ValueError, TypeError):
            return Response(
                {"error": "hours must be a non-negative integer."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if mode == 'set':
            user.remaining_hours = hours
        else:
            user.remaining_hours = (user.remaining_hours or 0) + hours
            user.total_purchased_hours = (user.total_purchased_hours or 0) + hours

        user.save(update_fields=['remaining_hours', 'total_purchased_hours'])
        return Response(
            {
                "message": f"Hours updated successfully.",
                "remaining_hours": float(user.remaining_hours),
                "total_purchased_hours": float(user.total_purchased_hours),
            },
            status=status.HTTP_200_OK,
        )


class StudentViewSet(viewsets.ModelViewSet):
    def perform_destroy(self, instance):
        from dashboard.models import StudentVisit
        # Delete StudentVisit for this student user
        StudentVisit.objects.filter(student=instance.user).delete()
        super().perform_destroy(instance)

    def perform_create(self, serializer):
        from user.models import User
        from dashboard.models import StudentVisit
        email = serializer.validated_data.get('email')
        full_name = serializer.validated_data.get('full_name')
        contact_number = serializer.validated_data.get('contact_number')
        # Check if a user with this email and role=student exists
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'role': 'student',
                'full_name': full_name,
                'contact_number': contact_number,
                'is_active': True,
            }
        )
        # If user exists but is not a student, update role
        if user.role != 'student':
            user.role = 'student'
            user.save()
        # Save the Student and link to User
        serializer.save(user=user, is_public=False)
        
    queryset = Student.objects.all()
    serializer_class = StudentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'professor':
            queryset = Student.objects.filter(professor=user)
        elif user.role == 'admin':
            queryset = Student.objects.all()
        else:
            return Student.objects.none()

        is_public = self.request.query_params.get('is_public')
        if is_public is not None:
            queryset = queryset.filter(is_public=is_public.lower() == 'true')

        return queryset.order_by('-id')

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='professor_id',
                type=int,
                location=OpenApiParameter.QUERY,
                required=True,
                description='ID of the professor to fetch assigned students for'
            )
        ],
        responses=StudentSerializer(many=True),
        description="Get students assigned to a specific professor by ID"
    )
    @action(detail=False, methods=['get'], url_path='by-professor')
    def by_professor(self, request):
        professor_id = request.query_params.get('professor_id')

        if not professor_id:
            return Response({"detail": "professor_id is required."}, status=400)

        try:
            professor = User.objects.get(id=professor_id, role='professor')
        except User.DoesNotExist:
            raise NotFound("Professor not found.")

        students = Student.objects.filter(professor=professor)
        serializer = self.get_serializer(students, many=True)
        return Response(serializer.data)

@extend_schema(request=RequestPasswordResetOTPSerializer)
class RequestPasswordResetOTPView(APIView):
    def post(self, request):
        serializer = RequestPasswordResetOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'message': 'If the email exists, an OTP has been sent for verification.'})
        # Generate 4-digit OTP
        otp_code = f"{random.randint(1000, 9999)}"
        expires_at = timezone.now() + timezone.timedelta(minutes=10)
        PasswordResetOTP.objects.create(user=user, code=otp_code, expires_at=expires_at)
        from django.core.mail import send_mail
        send_mail(
            'Password Reset OTP',
            (
                f'Dear {user.full_name},\n\n'
                f'We have received a request to reset the password for your account associated with this email address.\n'
                f'\n'
                f'Please use the following One-Time Password (OTP) to proceed with resetting your password:\n'
                f'\n'
                f'OTP: {otp_code}\n'
                f'\n'
                f'This OTP is valid for 10 minutes. If you did not request a password reset, please ignore this email or contact support.\n\n'
                f'Best regards,\nYourself Pilates Team'
            ),
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        return Response({'message': 'OTP sent to your email for verification.'})

@extend_schema(request=VerifyPasswordResetOTPSerializer)
class VerifyPasswordResetOTPView(APIView):
    def post(self, request):
        serializer = VerifyPasswordResetOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        otp = serializer.validated_data['otp']
        new_password = serializer.validated_data['new_password']
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'error': 'Invalid email or OTP.'}, status=400)
        otp_obj = PasswordResetOTP.objects.filter(user=user, code=otp, is_used=False).order_by('-created_at').first()
        if not otp_obj or otp_obj.is_expired():
            return Response({'error': 'Invalid or expired OTP.'}, status=400)
        user.set_password(new_password)
        user.save()
        otp_obj.is_used = True
        otp_obj.save()
        return Response({'success': True})

@extend_schema(request=ConfirmPasswordResetOTPSerializer)
class ConfirmPasswordResetOTPView(APIView):
    def post(self, request):
        serializer = ConfirmPasswordResetOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        otp = serializer.validated_data['otp']
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'error': 'Invalid email or OTP.'}, status=400)
        otp_obj = PasswordResetOTP.objects.filter(user=user, code=otp, is_used=False).order_by('-created_at').first()
        if not otp_obj or otp_obj.is_expired():
            return Response({'error': 'Invalid or expired OTP.'}, status=400)
        # Mark OTP as confirmed (but not used)
        otp_obj.is_used = False
        otp_obj.save()
        return Response({'success': True})

@extend_schema(request=ResetPasswordWithOTPSerializer)
class ResetPasswordWithOTPView(APIView):
    def post(self, request):
        serializer = ResetPasswordWithOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        otp = serializer.validated_data['otp']
        new_password = serializer.validated_data['new_password']
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'error': 'Invalid email or OTP.'}, status=400)
        otp_obj = PasswordResetOTP.objects.filter(user=user, code=otp, is_used=False).order_by('-created_at').first()
        if not otp_obj or otp_obj.is_expired():
            return Response({'error': 'Invalid or expired OTP.'}, status=400)
        user.set_password(new_password)
        user.save()
        otp_obj.is_used = True
        otp_obj.save()
        return Response({'message': 'Your password has been successfully reset. You can login now.'})
