from rest_framework.permissions import IsAuthenticated, AllowAny


def get_display_role(user):
    """Return a human-readable role label: Pro/Public Professor/Student."""
    role = getattr(user, 'role', '')
    is_public = getattr(user, 'is_public', False)
    if role in ('professor', 'teacher'):
        return 'Public Professor' if is_public else 'Pro Professor'
    if role == 'student':
        return 'Public Student' if is_public else 'Pro Student'
    return role.capitalize() if role else 'Unknown'
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import generics, viewsets, status, permissions
from rest_framework.exceptions import NotFound
from rest_framework.authtoken.models import Token

from user.models import User, Student, EmailVerificationOTP
from .permissions import IsAdmin
from user.serializers import (
    UserSerializer, UserAdminSerializer, StudentSerializer, AuthTokenSerializer,
    StudentRegistrationSerializer, StudentLoginSerializer, VerifyEmailSerializer, ResendVerificationOTPSerializer
)
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth import get_user_model
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
import threading


class StudentRegistrationView(APIView):
    """
    Student registration endpoint with JWT authentication.
    POST /api/user/student/register/
    No email verification required — account is created and verified immediately.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        request=StudentRegistrationSerializer,
        responses={201: StudentRegistrationSerializer},
        description="Register a new student. Account is created and verified immediately — no email OTP step required."
    )
    def post(self, request):
        serializer = StudentRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            validated_data = serializer.validated_data
            email = validated_data.get('email').lower()

            try:
                from django.db import transaction
                from subscriptions.models import Region as RegionModel

                region_id = request.data.get('region')
                region_obj = None
                if region_id:
                    try:
                        region_obj = RegionModel.objects.get(id=region_id)
                    except RegionModel.DoesNotExist:
                        pass

                with transaction.atomic():
                    user = get_user_model().objects.create_user(
                        email=email,
                        password=validated_data.get('password'),
                        full_name=validated_data.get('full_name'),
                        contact_number=validated_data.get('contact_number'),
                        role='student',
                        is_student=True,
                        is_public=True,
                        is_active=True,
                        region=region_obj,
                    )

                    student_record, created = Student.objects.get_or_create(
                        user=user,
                        defaults={
                            'full_name': user.full_name,
                            'email': user.email,
                            'contact_number': user.contact_number,
                            'is_public': True,
                            'is_verified': True,
                            'region': region_obj,
                        }
                    )
                    if not created:
                        # post_save signal may have auto-created the Student without region; patch now
                        update_fields = []
                        if region_obj and student_record.region_id != region_obj.id:
                            student_record.region = region_obj
                            update_fields.append('region')
                        if not student_record.is_verified:
                            student_record.is_verified = True
                            update_fields.append('is_verified')
                        if update_fields:
                            student_record.save(update_fields=update_fields)

                    _full_name = user.full_name
                    _email = user.email
                    def _send_welcome():
                        try:
                            send_mail(
                                'Your Account Has Been Created',
                                (
                                    f'Dear {_full_name},\n\n'
                                    f'We are pleased to inform you that your account has been successfully created on Yourself Pilates.\n'
                                    f'\n'
                                    f'You may now log in using the following credentials:\n'
                                    f'Email: {_email}\n'
                                    f'\n'
                                    f'If you have any questions or require assistance, please contact our support team.\n\n'
                                    f'Best regards,\nYourself Pilates Team'
                                ),
                                settings.DEFAULT_FROM_EMAIL,
                                [_email],
                                fail_silently=True,
                            )
                        except Exception:
                            pass
                    threading.Thread(target=_send_welcome, daemon=True).start()

                    from rest_framework_simplejwt.tokens import RefreshToken
                    refresh = RefreshToken.for_user(user)

                    return Response({
                        "message": "Student registered successfully.",
                        "user": {
                            "id": user.id,
                            "email": user.email,
                            "full_name": user.full_name,
                            "role": user.role,
                            "display_role": get_display_role(user),
                            "is_public": user.is_public,
                            "is_verified": True,
                            "region_id": user.region_id,
                        },
                        "tokens": {
                            "refresh": str(refresh),
                            "access": str(refresh.access_token),
                        },
                        "token_type": "Bearer"
                    }, status=status.HTTP_201_CREATED)

            except Exception as e:
                return Response({
                    "error": "Registration failed. Please try again later.",
                    "details": str(e)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class StudentLoginView(APIView):
    """
    Student login endpoint with JWT authentication.
    POST /api/user/student/login/
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        request=StudentLoginSerializer,
        responses={200: StudentLoginSerializer},
        description="Login for students with JWT tokens"
    )
    def post(self, request):
        serializer = StudentLoginSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = serializer.validated_data['user']

            # Get student record to include is_verified
            from .models import Student
            try:
                student_record = user.student_profile
                is_verified = student_record.is_verified
            except Student.DoesNotExist:
                is_verified = None

            # Generate JWT tokens
            from rest_framework_simplejwt.tokens import RefreshToken

            refresh = RefreshToken.for_user(user)

            return Response({
                "message": "Login successful",
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "full_name": user.full_name,
                    "role": user.role,
                    "display_role": get_display_role(user),
                    "is_public": user.is_public,
                    "contact_number": user.contact_number,
                    "is_verified": is_verified,
                    "region_id": user.region_id,
                },
                "tokens": {
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                },
                "token_type": "Bearer"
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_401_UNAUTHORIZED)

class LoginView(APIView):
    """Login endpoint that returns a Django auth token along with user details."""
    permission_classes = [AllowAny]
    authentication_classes = []

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
            'display_role': get_display_role(user),
            'is_public': user.is_public,
            'user_id': str(user.pk),
            'region_id': user.region_id,
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
        region = self.request.query_params.get('region')
        if region is not None:
            queryset = queryset.filter(region=region)
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
        if not user_id:
            return Response({
                'error': 'user_id parameter is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({
                'error': f'User with id {user_id} not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'error': 'An error occurred while fetching user',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        try:
            user.is_active = True
            user.save()
            return Response(self.get_serializer(user).data)
        except Exception as e:
            return Response({
                'error': 'An error occurred while updating user',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
        if not user_id:
            return Response({
                'error': 'user_id parameter is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({
                'error': f'User with id {user_id} not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'error': 'An error occurred while fetching user',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        try:
            user.is_active = False
            user.save()
            return Response(self.get_serializer(user).data)
        except Exception as e:
            return Response({
                'error': 'An error occurred while updating user',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'], url_path='top_up_hours')
    def top_up_hours(self, request, pk=None):
        """Admin: manually add or set remaining_hours for a professor."""
        try:
            user = self.get_object()
        except Exception as e:
            return Response(
                {"error": "User not found.", "details": str(e)},
                status=status.HTTP_404_NOT_FOUND
            )

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
                raise ValueError("Hours cannot be negative")
        except (ValueError, TypeError) as e:
            return Response(
                {"error": "hours must be a non-negative integer.", "details": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        if mode not in ['add', 'set']:
            return Response(
                {"error": "mode must be either 'add' or 'set'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
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

        except Exception as e:
            return Response(
                {"error": "Failed to update hours. Please try again.", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class StudentViewSet(viewsets.ModelViewSet):
    def perform_destroy(self, instance):
        from dashboard.models import StudentVisit
        # Delete StudentVisit for this student user
        StudentVisit.objects.filter(student=instance.user).delete()
        super().perform_destroy(instance)

    def perform_create(self, serializer):
        from user.models import User, Student
        email = serializer.validated_data.get('email')
        full_name = serializer.validated_data.get('full_name')
        contact_number = serializer.validated_data.get('contact_number')
        region = serializer.validated_data.get('region')
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'role': 'student',
                'full_name': full_name,
                'contact_number': contact_number,
                'is_active': True,
                'region': region,
            }
        )
        if user.role != 'student':
            user.role = 'student'
            user.save()
        # Keep User.region in sync with Student.region
        if region and user.region != region:
            user.region = region
            user.save(update_fields=['region'])
        # If a Student record was auto-created by the post_save signal, update it
        # instead of inserting a duplicate (which would violate the unique user_id key).
        existing = Student.objects.filter(user=user).first()
        if existing:
            serializer.instance = existing
        # Auto-assign the requesting professor as the student's owner
        professor = self.request.user if self.request.user.role in ['professor', 'teacher'] else None
        serializer.save(user=user, is_public=False, professor=professor)
        
    queryset = Student.objects.all()
    serializer_class = StudentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role in ['professor', 'teacher']:
            if user.is_public:
                # Public professors can see public students in their region
                queryset = Student.objects.filter(is_public=True, region=user.region)
            else:
                # Pro professors see only their assigned students
                queryset = Student.objects.filter(professor=user)
        elif user.role == 'admin':
            queryset = Student.objects.all()
        else:
            return Student.objects.none()

        is_public = self.request.query_params.get('is_public')
        if is_public is not None:
            queryset = queryset.filter(is_public=is_public.lower() == 'true')

        region = self.request.query_params.get('region')
        if region is not None:
            queryset = queryset.filter(region=region)

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
            return Response({
                "error": "professor_id is required."
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            professor_id = int(professor_id)
        except (ValueError, TypeError):
            return Response({
                "error": "professor_id must be a valid integer."
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            professor = User.objects.get(id=professor_id, role='professor')
        except User.DoesNotExist:
            raise NotFound("Professor not found.")

        try:
            students = Student.objects.filter(professor=professor)
            serializer = self.get_serializer(students, many=True)
            return Response(serializer.data)
        except Exception as e:
            return Response({
                "error": "Failed to fetch students.",
                "details": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@extend_schema(request=RequestPasswordResetOTPSerializer)
class RequestPasswordResetOTPView(APIView):
    def post(self, request):
        serializer = RequestPasswordResetOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Return success message anyway to prevent email enumeration
            return Response({'message': 'If the email exists, an OTP has been sent for verification.'})

        try:
            # Clean up any existing OTPs for this user
            PasswordResetOTP.objects.filter(user=user, is_used=False).delete()

            # Generate 4-digit OTP
            otp_code = f"{random.randint(1000, 9999)}"
            expires_at = timezone.now() + timezone.timedelta(minutes=10)
            PasswordResetOTP.objects.create(user=user, code=otp_code, expires_at=expires_at)

            _user_email = user.email
            _user_name = user.full_name
            def _send_reset():
                try:
                    send_mail(
                        'Password Reset OTP',
                        (
                            f'Dear {_user_name},\n\n'
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
                        [_user_email],
                        fail_silently=True,
                    )
                except Exception:
                    pass
            threading.Thread(target=_send_reset, daemon=True).start()
            return Response({'message': 'OTP sent to your email for verification.'})

        except Exception as e:
            return Response({
                'error': 'Failed to send OTP email. Please try again later.',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
            return Response({
                'error': 'Invalid email or OTP.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get the latest unused OTP for this user
        otp_obj = PasswordResetOTP.objects.filter(
            user=user,
            code=otp,
            is_used=False
        ).order_by('-created_at').first()

        if not otp_obj:
            return Response({
                'error': 'Invalid OTP.'
            }, status=status.HTTP_400_BAD_REQUEST)

        if otp_obj.is_expired():
            return Response({
                'error': 'OTP has expired. Please request a new one.'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Use transaction to ensure atomicity
            from django.db import transaction
            with transaction.atomic():
                user.set_password(new_password)
                user.save()
                otp_obj.is_used = True
                otp_obj.save()

            return Response({'success': True, 'message': 'Password reset successfully.'})

        except Exception as e:
            return Response({
                'error': 'Failed to reset password. Please try again.',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
            return Response({
                'error': 'Invalid email or OTP.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get the latest unused OTP for this user
        otp_obj = PasswordResetOTP.objects.filter(
            user=user,
            code=otp,
            is_used=False
        ).order_by('-created_at').first()

        if not otp_obj:
            return Response({
                'error': 'Invalid OTP.'
            }, status=status.HTTP_400_BAD_REQUEST)

        if otp_obj.is_expired():
            return Response({
                'error': 'OTP has expired. Please request a new one.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # OTP is valid - confirm it (but don't mark as used yet)
        try:
            otp_obj.save()  # Update timestamp to show it was confirmed
            return Response({
                'success': True,
                'message': 'OTP confirmed. You can now reset your password.'
            })
        except Exception as e:
            return Response({
                'error': 'Failed to confirm OTP. Please try again.',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
            return Response({
                'error': 'Invalid email or OTP.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get the latest unused OTP for this user
        otp_obj = PasswordResetOTP.objects.filter(
            user=user,
            code=otp,
            is_used=False
        ).order_by('-created_at').first()

        if not otp_obj:
            return Response({
                'error': 'Invalid OTP.'
            }, status=status.HTTP_400_BAD_REQUEST)

        if otp_obj.is_expired():
            return Response({
                'error': 'OTP has expired. Please request a new one.'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Use transaction to ensure atomicity
            from django.db import transaction
            with transaction.atomic():
                user.set_password(new_password)
                user.save()
                otp_obj.is_used = True
                otp_obj.save()

            return Response({
                'message': 'Your password has been successfully reset. You can login now.'
            })

        except Exception as e:
            return Response({
                'error': 'Failed to reset password. Please try again.',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VerifyGmailEmailView(APIView):
    """
    Verify student Gmail address with OTP.
    POST /api/user/student/verify-email/
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        request=VerifyEmailSerializer,
        responses={200: None},
        description="Verify student Gmail address using OTP code sent during registration"
    )
    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            otp = serializer.validated_data['otp']

            # Get the latest unused OTP for this email
            otp_obj = EmailVerificationOTP.objects.filter(
                email=email,
                is_used=False
            ).order_by('-created_at').first()

            if not otp_obj:
                return Response({
                    'error': 'No verification OTP found for this email. Please request a new one.'
                }, status=status.HTTP_400_BAD_REQUEST)

            if otp_obj.is_expired():
                return Response({
                    'error': 'OTP has expired. Please request a new verification code.'
                }, status=status.HTTP_400_BAD_REQUEST)

            if otp_obj.code != otp:
                return Response({
                    'error': 'Invalid OTP code. Please check and try again.'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Use transaction to handle race conditions and ensure atomicity
            from django.db import transaction
            try:
                with transaction.atomic():
                    # Double-check if user already exists (prevent race condition)
                    if User.objects.filter(email=email).exists():
                        return Response({
                            'error': 'An account with this email already exists. Please login instead.'
                        }, status=status.HTTP_400_BAD_REQUEST)

                    # OTP is valid - create the user now
                    registration_data = otp_obj.registration_data

                    # Resolve region before creating user so it's set on both User and Student
                    from subscriptions.models import Region as RegionModel
                    region_id = registration_data.get('region_id')
                    region_obj = None
                    if region_id:
                        try:
                            region_obj = RegionModel.objects.get(id=region_id)
                        except RegionModel.DoesNotExist:
                            pass

                    # Create user with hashed password (region set here too)
                    user = get_user_model().objects.create_user(
                        email=registration_data['email'],
                        password=registration_data['password'],
                        full_name=registration_data['full_name'],
                        contact_number=registration_data['contact_number'],
                        role=registration_data['role'],
                        is_student=registration_data['is_student'],
                        is_public=registration_data['is_public'],
                        is_active=registration_data['is_active'],
                        region=region_obj,
                    )

                    # Mark OTP as used and link to user
                    otp_obj.is_used = True
                    otp_obj.user = user
                    otp_obj.save()

                    # Create or update student record with verified status
                    from .models import Student
                    student_record, created = Student.objects.get_or_create(
                        user=user,
                        defaults={
                            'full_name': user.full_name,
                            'email': user.email,
                            'contact_number': user.contact_number,
                            'is_public': True,
                            'is_verified': True,
                            'region': region_obj,
                        }
                    )
                    if not created:
                        # Update existing student record
                        student_record.is_verified = True
                        student_record.full_name = user.full_name
                        student_record.email = user.email
                        student_record.contact_number = user.contact_number
                        student_record.is_public = True
                        if region_obj:
                            student_record.region = region_obj
                        student_record.save()

                    # Generate JWT tokens for the verified student
                    from rest_framework_simplejwt.tokens import RefreshToken
                    refresh = RefreshToken.for_user(user)

                    return Response({
                        "message": "Email verified successfully! Your account has been created.",
                        "user": {
                            "id": user.id,
                            "email": user.email,
                            "full_name": user.full_name,
                            "role": user.role,
                            "display_role": get_display_role(user),
                            "is_verified": True,
                        },
                        "tokens": {
                            "refresh": str(refresh),
                            "access": str(refresh.access_token),
                        },
                        "token_type": "Bearer"
                    }, status=status.HTTP_200_OK)

            except Exception as e:
                return Response({
                    'error': 'Failed to create account. Please try again.',
                    'details': str(e)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ResendVerificationOTPView(APIView):
    """
    Resend verification OTP for student registration.
    POST /api/user/student/resend-otp/
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        request=ResendVerificationOTPSerializer,
        responses={200: None},
        description="Resend verification OTP to student email address"
    )
    def post(self, request):
        serializer = ResendVerificationOTPSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']

            try:
                # Check if user exists and is already verified
                user = User.objects.filter(email=email, role='student').first()
                if user:
                    from .models import Student
                    try:
                        student_record = user.student_profile
                        if student_record.is_verified:
                            return Response({
                                'message': 'This email is already verified. You can log in to your account.'
                            }, status=status.HTTP_200_OK)
                    except Student.DoesNotExist:
                        pass  # Continue with sending OTP

                # Get existing OTP registration data if user doesn't exist
                registration_data = None
                if not user:
                    existing_otp = EmailVerificationOTP.objects.filter(
                        email=email,
                        is_used=False
                    ).order_by('-created_at').first()
                    if existing_otp:
                        registration_data = existing_otp.registration_data

                # Generate new OTP
                otp_code = f"{random.randint(100000, 999999)}"
                expires_at = timezone.now() + timezone.timedelta(minutes=30)

                # Mark previous OTPs as used
                EmailVerificationOTP.objects.filter(
                    email=email,
                    is_used=False
                ).update(is_used=True)

                # Create new OTP record
                EmailVerificationOTP.objects.create(
                    user=user,
                    code=otp_code,
                    email=email,
                    expires_at=expires_at,
                    registration_data=registration_data or {}
                )

                # Send verification email in background so response is instant
                full_name = user.full_name if user else (registration_data.get('full_name') if registration_data else 'Student')
                _resend_email = email
                _resend_name = full_name
                _resend_code = otp_code
                def _send_resend():
                    try:
                        send_mail(
                            'Verify Your Email Address - Yourself Pilates',
                            (
                                f'Dear {_resend_name},\n\n'
                                f'Here is your new verification code for your student account:\n'
                                f'\n'
                                f'OTP: {_resend_code}\n'
                                f'\n'
                                f'This OTP is valid for 30 minutes.\n'
                                f'\n'
                                f'If you did not request this code, please ignore this email or contact support.\n\n'
                                f'Best regards,\nYourself Pilates Team'
                            ),
                            settings.DEFAULT_FROM_EMAIL,
                            [_resend_email],
                            fail_silently=True,
                        )
                    except Exception:
                        pass
                threading.Thread(target=_send_resend, daemon=True).start()

                return Response({
                    "message": "New verification code sent to your email address.",
                    "email": email
                }, status=status.HTTP_200_OK)

            except Exception as e:
                return Response({
                    'error': 'Failed to send verification email. Please try again later.',
                    'details': str(e)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProfessorsListView(APIView):
    """Return a list of active professors/teachers for booking selection."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = User.objects.filter(role__in=['professor', 'teacher'], is_active=True)
        region = request.query_params.get('region')
        if region:
            qs = qs.filter(region=region)
        is_public = request.query_params.get('is_public')
        if is_public is not None:
            qs = qs.filter(is_public=is_public.lower() == 'true')
        professors = qs.values('id', 'full_name', 'email').order_by('full_name')
        return Response(list(professors))

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
