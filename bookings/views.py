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
from .serializers import BookingSerializer, send_booking_notifications, send_booking_notifications_async

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
        'region': ['exact'],
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

    @action(detail=False, methods=['post'])
    def pro_student_book(self, request):
        """Allow authenticated pro students to book a professor, deducting from the professor's hours."""
        from user.models import User as UserModel
        user = request.user

        if getattr(user, 'role', None) != 'student' or getattr(user, 'is_public', True):
            return Response(
                {"error": "Only pro students can use this endpoint."},
                status=status.HTTP_403_FORBIDDEN,
            )

        professor_id = request.data.get('professor')
        booking_date = request.data.get('booking_date')
        time_slot = request.data.get('time_slot')
        notes = request.data.get('notes', '')
        title = request.data.get('title', '')

        if not all([professor_id, booking_date, time_slot]):
            return Response(
                {"error": "professor, booking_date, and time_slot are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            professor = UserModel.objects.get(
                id=professor_id,
                role__in=['professor', 'teacher'],
                is_active=True,
            )
        except UserModel.DoesNotExist:
            return Response(
                {"error": "Professor not found or is no longer active."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check student's own remaining hours (pro students buy packs and spend their own credits)
        if (user.remaining_hours or Decimal('0')) < 1:
            return Response(
                {"error": "Insufficient hours. Please purchase a pack before booking."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            bd = datetime.strptime(booking_date, '%Y-%m-%d').date()
        except ValueError:
            return Response({"error": "Invalid date format. Use YYYY-MM-DD"}, status=status.HTTP_400_BAD_REQUEST)

        if bd < timezone.now().date():
            return Response({"error": "Booking date must be in the future"}, status=status.HTTP_400_BAD_REQUEST)

        if Booking.objects.filter(booking_date=bd, time_slot=time_slot, professor=professor).exclude(status='cancelled').exists():
            return Response({"error": "This time slot is already booked for this professor"}, status=status.HTTP_400_BAD_REQUEST)

        booking = Booking.objects.create(
            professor=professor,
            booking_date=bd,
            time_slot=time_slot,
            notes=notes,
            title=title or f"Booking by {user.full_name}",
            booking_type='pro',
        )

        try:
            student_profile = user.student_profile
            booking.students.add(student_profile)
            booking.total_students = booking.students.count()
            booking.save(update_fields=['total_students'])
        except Exception:
            pass

        # Deduct 1 hour from the student's own credits
        user.used_hours = (user.used_hours or Decimal('0')) + Decimal('1')
        user.remaining_hours = max(Decimal('0'), (user.remaining_hours or Decimal('0')) - Decimal('1'))
        user.save(update_fields=["used_hours", "remaining_hours"])

        send_booking_notifications_async(booking, 'created', created_by_role='pro_student')

        serializer = self.get_serializer(booking)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'])
    def student_book(self, request):
        """Allow authenticated public students to book a public professor in a specific region."""
        from user.models import User as UserModel, Student
        from subscriptions.models import Region, Order, CreditWallet
        from django.db.models import Sum
        user = request.user

        # Only public students (self-registered) may independently book
        if getattr(user, 'role', None) == 'student' and not getattr(user, 'is_public', False):
            return Response(
                {"error": "Pro Professor Students cannot independently book classes. Contact your professor."},
                status=status.HTTP_403_FORBIDDEN,
            )

        professor_id = request.data.get('professor')
        booking_date = request.data.get('booking_date')
        time_slot = request.data.get('time_slot')
        region_id = request.data.get('region')
        notes = request.data.get('notes', '')
        title = request.data.get('title', '')

        if not all([professor_id, booking_date, time_slot, region_id]):
            return Response(
                {"error": "professor, booking_date, time_slot, and region are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Only active public professors can be booked via this endpoint
        try:
            professor = UserModel.objects.get(
                id=professor_id,
                role__in=['professor', 'teacher'],
                is_public=True,
                is_active=True,
            )
        except UserModel.DoesNotExist:
            return Response(
                {"error": "Public professor not found or is no longer active."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Resolve region — must exist and be active
        try:
            region = Region.objects.get(id=region_id, is_active=True)
        except Region.DoesNotExist:
            return Response({"error": "Region not found or inactive"}, status=status.HTTP_404_NOT_FOUND)

        # Professor must belong to the same region as the booking
        if professor.region_id != region.id:
            return Response(
                {"error": f"This professor is not available in the selected region."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            bd = datetime.strptime(booking_date, '%Y-%m-%d').date()
        except ValueError:
            return Response({"error": "Invalid date format. Use YYYY-MM-DD"}, status=status.HTTP_400_BAD_REQUEST)

        if bd < timezone.now().date():
            return Response({"error": "Booking date must be in the future"}, status=status.HTTP_400_BAD_REQUEST)

        if Booking.objects.filter(booking_date=bd, time_slot=time_slot).exclude(status='cancelled').exists():
            return Response({"error": "This time slot is already booked"}, status=status.HTTP_400_BAD_REQUEST)

        # Check student's available credits for this region via CreditWallet
        # (covers both real purchases and free credits added by admins)
        wallet_remaining = CreditWallet.objects.filter(
            user=user,
            region=region,
            status='active',
        ).aggregate(total=Sum('remaining_hours'))['total'] or 0

        try:
            student_profile = user.student_profile
        except Exception:
            student_profile = None

        if wallet_remaining < 1:
            return Response(
                {
                    "error": (
                        f"No credits available for region '{region.name}'. "
                        "Please purchase a pack for this region to book a class."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        booking = Booking.objects.create(
            professor=professor,
            booking_date=bd,          # use the parsed date object, not the raw string
            time_slot=time_slot,
            notes=notes,
            title=title or f"Booking by {user.full_name}",
            booking_type='public',
            region=region,
        )

        if student_profile:
            booking.students.add(student_profile)
            booking.total_students = booking.students.count()
            booking.save(update_fields=['total_students'])

        # Deduct 1 hour from the student's oldest active CreditWallet entry for this region
        wallet = CreditWallet.objects.filter(
            user=user,
            region=region,
            status='active',
        ).order_by('purchase_date').first()
        if wallet:
            wallet.used_hours += 1
            wallet.save()
        # Mirror deduction on the User record so the dashboard reflects it
        user.used_hours = (user.used_hours or 0) + 1
        user.remaining_hours = max(0, (user.remaining_hours or 0) - 1)
        user.save(update_fields=['used_hours', 'remaining_hours'])

        send_booking_notifications_async(booking, 'created', created_by_role='student')

        serializer = self.get_serializer(booking)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def perform_create(self, serializer):
        if not self.request.user.role == 'admin':
            booking = serializer.save(professor=self.request.user)
            professor = self.request.user
            professor.used_hours = (professor.used_hours or 0) + 1
            professor.remaining_hours = max(0, (professor.remaining_hours or 0) - 1)
            professor.save(update_fields=["used_hours", "remaining_hours"])
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
        
        if new_status == 'cancelled':
            if booking.booking_type == 'pro':
                from decimal import Decimal
                student_profile = booking.students.first()
                student_user = student_profile.user if student_profile else None
                # If booked by a pro student (student has their own remaining_hours), restore student credits
                if student_user and student_user.role == 'student' and not student_user.is_public:
                    student_user.remaining_hours = (student_user.remaining_hours or Decimal('0')) + Decimal('1')
                    student_user.used_hours = max(Decimal('0'), (student_user.used_hours or Decimal('0')) - Decimal('1'))
                    student_user.save(update_fields=["remaining_hours", "used_hours"])
                # If booked by a professor (old flow), restore professor's credit
                elif booking.professor and booking.professor.role in ['professor', 'teacher']:
                    booking.professor.remaining_hours = booking.professor.remaining_hours + Decimal('1')
                    booking.professor.used_hours = max(Decimal('0'), (booking.professor.used_hours or Decimal('0')) - Decimal('1'))
                    booking.professor.save(update_fields=["remaining_hours", "used_hours"])

            # Public bookings: restore the student's CreditWallet credit
            if booking.booking_type == 'public' and booking.region:
                from subscriptions.models import CreditWallet
                student_profile = booking.students.first()
                if student_profile and student_profile.user:
                    student_user = student_profile.user
                    # Find the wallet entry most recently debited (highest used_hours first)
                    wallet = CreditWallet.objects.filter(
                        user=student_user,
                        region=booking.region,
                    ).exclude(status='cancelled').order_by('-used_hours', 'purchase_date').first()
                    if wallet and wallet.used_hours > 0:
                        wallet.used_hours = max(0, wallet.used_hours - 1)
                        wallet.save()
                    # Mirror restoration on the User record
                    student_user.used_hours = max(0, (student_user.used_hours or 0) - 1)
                    student_user.remaining_hours = (student_user.remaining_hours or 0) + 1
                    student_user.save(update_fields=['used_hours', 'remaining_hours'])

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
