"""app URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static
from django.conf import settings
from django.http import JsonResponse

from user import views as core_views

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)

# Define a simple home response
def home(request):
    return JsonResponse({
        "message": "Welcome to Yourself Backend API!"
    })

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/schema/', SpectacularAPIView.as_view(), name='api-schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(
        url_name='api-schema'
        ), name='api-docs'),
    path('api/user/', include('user.urls')),
    path('api/booking/', include('bookings.urls')),
    path('api/dashboard/', include('dashboard.urls')),
    path('api/subscriptions/', include('subscriptions.urls')),
    path('api/tv/', include('tv.urls')),

    path('', home, name='home'),
]

# Always serve media files (DEBUG and non-DEBUG local dev)
urlpatterns += static(
    settings.MEDIA_URL, document_root=settings.MEDIA_ROOT,
)