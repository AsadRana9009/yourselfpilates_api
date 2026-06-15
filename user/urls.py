from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CreateUserView,
    ManageUserView,
    LoginView,
    UserAdminViewSet,
    StudentViewSet,
    RequestPasswordResetOTPView,
    VerifyPasswordResetOTPView,
    ConfirmPasswordResetOTPView,
    ResetPasswordWithOTPView,
    StudentRegistrationView,
    StudentLoginView,
    VerifyGmailEmailView,
    ResendVerificationOTPView,
    ProfessorsListView,
)
from rest_framework_simplejwt.views import TokenRefreshView

app_name = 'user'

# Create the router and register viewsets
router = DefaultRouter()
router.register(r'users', UserAdminViewSet, basename='admin-users')
router.register(r'students', StudentViewSet)

# Define URL patterns explicitly
urlpatterns = [
    # Regular user endpoints
    path('register/', CreateUserView.as_view(), name='register'),
    path('me/', ManageUserView.as_view(), name='user-profile'),
    path('login/', LoginView.as_view(), name='login'),

    # Student-specific endpoints with JWT - NOW DEFINED BEFORE ROUTER
    path('student/register/', StudentRegistrationView.as_view(), name='student-register'),
    path('student/login/', StudentLoginView.as_view(), name='student-login'),
    path('student/token/refresh/', TokenRefreshView.as_view(), name='student-token-refresh'),

    # Student email verification endpoints
    path('student/verify-email/', VerifyGmailEmailView.as_view(), name='student-verify-email'),
    path('student/resend-otp/', ResendVerificationOTPView.as_view(), name='student-resend-otp'),

    # Password reset endpoints
    path('request-reset-otp/', RequestPasswordResetOTPView.as_view(), name='request-reset-otp'),
    path('verify-reset-otp/', VerifyPasswordResetOTPView.as_view(), name='verify-reset-otp'),
    path('confirm-reset-otp/', ConfirmPasswordResetOTPView.as_view(), name='confirm-reset-otp'),
    path('reset-password-with-otp/', ResetPasswordWithOTPView.as_view(), name='reset-password-with-otp'),

    # Public professors list (for booking)
    path('professors/', ProfessorsListView.as_view(), name='professors-list'),

    # Router URLs at the end
    path('', include(router.urls)),
]