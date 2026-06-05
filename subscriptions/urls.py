from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    PackViewSet, 
    OrderViewSet, 
    ifthenpay_callback,
    creditcard_success_callback,
    creditcard_error_callback,
    creditcard_cancel_callback
)

router = DefaultRouter()
router.register(r"packs", PackViewSet, basename="packs")
router.register(r"orders", OrderViewSet, basename="orders")

urlpatterns = [
    path('callback/ifthenpay/', ifthenpay_callback, name='ifthenpay-callback'),
    path('callback/creditcard/success/', creditcard_success_callback, name='creditcard-success'),
    path('callback/creditcard/error/', creditcard_error_callback, name='creditcard-error'),
    path('callback/creditcard/cancel/', creditcard_cancel_callback, name='creditcard-cancel'),
] + router.urls
