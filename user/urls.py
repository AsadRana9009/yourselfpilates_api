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
    ResetPasswordWithOTPView
    )
app_name = 'user'

# Create the router and register viewsets if needed
router = DefaultRouter()
router.register(r'users', UserAdminViewSet, basename='admin-users')
router.register(r'students', StudentViewSet)


urlpatterns = [
    path('register/', CreateUserView.as_view(), name='register'),
    path('me/', ManageUserView.as_view(), name='user-profile'),
    path('login/', LoginView.as_view(), name='login'),

    path('request-reset-otp/', RequestPasswordResetOTPView.as_view(), name='request-reset-otp'),
    path('verify-reset-otp/', VerifyPasswordResetOTPView.as_view(), name='verify-reset-otp'),
    path('confirm-reset-otp/', ConfirmPasswordResetOTPView.as_view(), name='confirm-reset-otp'),
    path('reset-password-with-otp/', ResetPasswordWithOTPView.as_view(), name='reset-password-with-otp'),

    path('', include(router.urls)),
]