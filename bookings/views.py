from rest_framework import viewsets, status, permissions
from rest_framework.response import Response
from rest_framework.decorators import action
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes


from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .models import Booking, TIME_SLOTS
from .serializers import BookingSerializer

from django.db.models import Case, When, Value, IntegerField
from .igloo_utils import delete_igloo_pin_for_booking
from django.utils import timezone
from decimal import Decimal

class BookingViewSet(viewsets.ModelViewSet):
    def perform_destroy(self, instance):
        # Also delete any cancelled bookings for the same slot/professor to fully free the slot
        Booking.objects.filter(
            professor=instance.professor,
            booking_date=instance.booking_date,
            time_slot=instance.time_slot,
            status='cancelled'
        ).delete()
        # Optionally, delete Igloo PIN if exists
        if instance.igloo_pin:
            from .igloo_utils import delete_igloo_pin_for_booking
            try:
                delete_igloo_pin_for_booking(instance)
            except Exception as e:
                print(f"Igloo PIN deletion failed (destroy): {e}")
        instance.delete()
        
    serializer_class = BookingSerializer
    filter_backends = (DjangoFilterBackend, SearchFilter, OrderingFilter)
    filterset_fields = {
        'booking_date': ['exact'],
        'booking_type': ['exact'],
    }
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        now = timezone.now().date()

        base_qs = Booking.objects.annotate(
            is_past=Case(
                When(booking_date__lt=now, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            )
        ).order_by('is_past', 'booking_date', 'time_slot', '-created_at')

        if user.role == 'admin':
            return base_qs
        if user.role in ['professor', 'teacher']:
            return base_qs.filter(professor=user)
        return Booking.objects.none()

    def create(self, request, *args, **kwargs):
        user = request.user

        # Professors/teachers must have at least 1 remaining hour to book
        if getattr(user, 'role', None) in ['professor', 'teacher'] and user.remaining_hours < 1:
            return Response(
                {"error": "Insufficient hours. Please subscribe to a pack before booking."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='date',
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description='Date to get available slots for (format: YYYY-MM-DD)',
            ),
        ],
        responses={
            200: OpenApiTypes.OBJECT,
            400: OpenApiTypes.OBJECT,
        },
    )
    @action(detail=False, methods=['get'])
    def available_slots(self, request):
        """Get all available slots for a specific date"""
        date = request.query_params.get('date')
        if not date:
            return Response(
                {"error": "Date parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        booked_slots = Booking.objects.filter(
            booking_date=date
        ).exclude(status='cancelled').values_list('time_slot', flat=True)

        available = [
            {'value': slot[0], 'display': slot[1]}
            for slot in TIME_SLOTS
            if slot[0] not in booked_slots
        ]

        return Response(available)

    def perform_create(self, serializer):
        if not self.request.user.role == 'admin':
            booking = serializer.save(professor=self.request.user)
            # Increment used_hours for the professor by 1
            professor = self.request.user
            professor.used_hours = (professor.used_hours or 0) + 1
            professor.save(update_fields=["used_hours"])
        else:
            serializer.save()
    
    @action(detail=True, methods=['GET'])
    def approve(self, request, pk=None):
        """Admin-only endpoint to approve a booking"""
        return self._change_booking_status(pk, 'confirmed', request)

    
    @action(detail=True, methods=['GET'])
    def reject(self, request, pk=None):
        """Admin-only endpoint to reject a booking"""
        return self._change_booking_status(pk, 'cancelled', request)

    
    def _change_booking_status(self, pk, new_status, request):

        booking = self.get_object()
    
        # Admin can cancel anything
        if request.user.role == 'admin':
            pass
        # Professor/Teacher can cancel only *their own* bookings
        elif request.user.role in ['professor', 'teacher']:
            if booking.professor != request.user:
                return Response(
                    {"detail": "You can only cancel your own bookings"},
                    status=status.HTTP_403_FORBIDDEN
                )
        else:
            return Response(
                {"detail": "You are not allowed to cancel bookings"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # If cancelling/rejecting, increment remaining_hours and decrement used_hours for professor
        if new_status == 'cancelled' and booking.professor and booking.professor.role in ['professor', 'teacher']:
            from decimal import Decimal
            booking.professor.remaining_hours = booking.professor.remaining_hours + Decimal('1')
            # Decrement used_hours, but not below zero
            if booking.professor.used_hours is not None:
                booking.professor.used_hours = max(booking.professor.used_hours - 1, 0)
            else:
                booking.professor.used_hours = 0
            booking.professor.save(update_fields=["remaining_hours", "used_hours"])
            
        # If cancelling, delete the Igloo PIN (if exists)
        if new_status == 'cancelled' and booking.igloo_pin:
            delete_igloo_pin_for_booking(booking)
    
        # Update status
        booking.status = new_status
        booking.save()
    
        serializer = self.get_serializer(booking)
        self._send_status_notification(booking, new_status)
    
        return Response(serializer.data, status=status.HTTP_200_OK)


    
    def _send_status_notification(self, booking, status):
        """Example notification method (implement with your email service)"""
        subject = f"Booking {status}"
        message = f"Your booking for {booking.booking_date} {booking.get_time_slot_display()} has been {status}"
        print(f"Notification sent: {subject} - {message}")

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='month',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Filter by month (format: "Month Year" e.g. "June 2025")',
            ),
            OpenApiParameter(
                name='week_start',
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description='Start date for week filter (format: YYYY-MM-DD)',
            ),
            OpenApiParameter(
                name='week_end',
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description='End date for week filter (format: YYYY-MM-DD)',
            ),
            OpenApiParameter(
                name='day',
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description='Filter by specific day (format: YYYY-MM-DD)',
            ),
            OpenApiParameter(
                name='status',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Filter by booking status',
                enum=['pending', 'confirmed', 'cancelled'],
            ),
        ],
    )
    @action(detail=False, methods=['get'])
    def filter_bookings(self, request):
        """
        Filter bookings by day, week, or month
        Parameters (all optional):
        - month: "June 2025" (format: "%B %Y")
        - week_start: "2025-06-01" (format: "%Y-%m-%d")
        - week_end: "2025-06-07" (format: "%Y-%m-%d")
        - day: "2025-06-15" (format: "%Y-%m-%d")
        """
        queryset = self.get_queryset()
        
        # Month filter
        month_str = request.query_params.get('month')
        if month_str:
            try:
                month_date = datetime.strptime(month_str, "%B %Y").date()
                start_date = month_date.replace(day=1)
                end_date = start_date + relativedelta(months=1) - timedelta(days=1)
                queryset = queryset.filter(
                    booking_date__gte=start_date,
                    booking_date__lte=end_date
                )
            except ValueError:
                return Response(
                    {"error": "Invalid month format. Use 'Month Year' (e.g. 'June 2025')"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Week filter
        week_start = request.query_params.get('week_start')
        week_end = request.query_params.get('week_end')
        if week_start and week_end:
            try:
                start_date = datetime.strptime(week_start, "%Y-%m-%d").date()
                end_date = datetime.strptime(week_end, "%Y-%m-%d").date()
                queryset = queryset.filter(
                    booking_date__gte=start_date,
                    booking_date__lte=end_date
                )
            except ValueError:
                return Response(
                    {"error": "Invalid date format. Use 'YYYY-MM-DD'"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        day_str = request.query_params.get('day')
        if day_str:
            try:
                day_date = datetime.strptime(day_str, "%Y-%m-%d").date()
                queryset = queryset.filter(booking_date=day_date)
            except ValueError:
                return Response(
                    {"error": "Invalid date format. Use 'YYYY-MM-DD'"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        status = request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status.lower())
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
