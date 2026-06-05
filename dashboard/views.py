import collections

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import viewsets, permissions
from rest_framework.decorators import action

from bookings.permissions import IsAdminUser
from django.utils import timezone
from datetime import timedelta
from bookings.models import Booking
from user.models import User, Student
from .models import Video
from .serializers import VideoSerializer
from .models import TeacherVisit, StudentVisit
        

class AnalyticsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        now = timezone.now()
        today = now.date()
        start_of_week = today - timedelta(days=today.weekday())
        start_of_month = today.replace(day=1)

        # Bookings
        total_bookings = Booking.objects.count()
        bookings_this_month = Booking.objects.filter(booking_date__gte=start_of_month).count()
        bookings_this_week = Booking.objects.filter(booking_date__gte=start_of_week).count()
        confirmed_bookings = Booking.objects.filter(status='confirmed').count()
        cancelled_bookings = Booking.objects.filter(status='cancelled').count()

        # Confirmed bookings (time-based)
        last_7_days = now - timedelta(days=7)
        last_30_days = now - timedelta(days=30)
        last_3_months = now - timedelta(days=90)
        confirmed_last_7_days = Booking.objects.filter(status='confirmed', created_at__gte=last_7_days).count()
        confirmed_last_30_days = Booking.objects.filter(status='confirmed', created_at__gte=last_30_days).count()
        confirmed_last_3_months = Booking.objects.filter(status='confirmed', created_at__gte=last_3_months).count()

        # Teachers
        total_teachers = User.objects.filter(role__in=['professor', 'teacher'], is_active=True).count()
        active_teachers = User.objects.filter(role__in=['professor', 'teacher'], is_active=True).count()
        registered_teachers = total_teachers  # Assuming all with role are registered

        # Students
        total_students = Student.objects.count()
        active_students = Student.objects.count()  # Adjust if you have an 'active' field
        registered_students = total_students  # Assuming all are registered

        # Teacher Visitors (chart data)

        def get_daily_counts(model, start_date, end_date):
            visits = model.objects.filter(visited_at__date__gte=start_date, visited_at__date__lte=end_date)
            counts = collections.Counter([v.visited_at.date() for v in visits])
            days = [(start_date + timedelta(days=i)) for i in range((end_date - start_date).days + 1)]
            return [{"date": d.isoformat(), "count": counts.get(d, 0)} for d in days]

        end_date = today
        teacher_visitors_last_7_days = get_daily_counts(TeacherVisit, end_date - timedelta(days=6), end_date)
        teacher_visitors_last_30_days = get_daily_counts(TeacherVisit, end_date - timedelta(days=29), end_date)
        teacher_visitors_last_3_months = get_daily_counts(TeacherVisit, end_date - timedelta(days=89), end_date)
        student_visitors_last_7_days = get_daily_counts(StudentVisit, end_date - timedelta(days=6), end_date)
        student_visitors_last_30_days = get_daily_counts(StudentVisit, end_date - timedelta(days=29), end_date)
        student_visitors_last_3_months = get_daily_counts(StudentVisit, end_date - timedelta(days=89), end_date)

        return Response({
            # Bookings
            "total_bookings": total_bookings,
            "bookings_this_month": bookings_this_month,
            "bookings_this_week": bookings_this_week,
            "confirmed_bookings": confirmed_bookings,
            "cancelled_bookings": cancelled_bookings,

            # Confirmed bookings (time-based)
            "confirmed_last_7_days": confirmed_last_7_days,
            "confirmed_last_30_days": confirmed_last_30_days,
            "confirmed_last_3_months": confirmed_last_3_months,

            # Teachers
            "total_teachers": total_teachers,
            "active_teachers": active_teachers,
            "registered_teachers": registered_teachers,

            # Students
            "total_students": total_students,
            "active_students": active_students,
            "registered_students": registered_students,

            # Teacher & Student Visitors (chart data)
            "teacher_visitors": {
                "last_7_days": teacher_visitors_last_7_days,
                "last_30_days": teacher_visitors_last_30_days,
                "last_3_months": teacher_visitors_last_3_months,
            },
            "student_visitors": {
                "last_7_days": student_visitors_last_7_days,
                "last_30_days": student_visitors_last_30_days,
                "last_3_months": student_visitors_last_3_months,
            }
        })


class VideoViewSet(viewsets.ModelViewSet):
    queryset = Video.objects.all().order_by('-id')
    serializer_class = VideoSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=True, methods=['get'], url_path='stream')
    def stream(self, request, *args, **kwargs):
        """
        Stream the video file with HTTP Range support for iOS compatibility.
        iOS (AVPlayer) requires Accept-Ranges and 206 Partial Content responses.
        Without Range support, iOS silently fails to play video.

        Usage: GET /api/dashboard/videos/<id>/stream/
        """
        import os
        from django.http import FileResponse, Http404

        instance = self.get_object()
        file_path = instance.video_file.path

        if not os.path.exists(file_path):
            raise Http404('Video not found')

        file_size = os.path.getsize(file_path)

        # Determine content type
        content_type = 'video/mp4'
        if file_path.endswith('.mov'):
            content_type = 'video/quicktime'
        elif file_path.endswith('.webm'):
            content_type = 'video/webm'

        range_header = request.META.get('HTTP_RANGE')

        if range_header:
            range_value = range_header.strip().replace('bytes=', '')
            parts = range_value.split('-')
            try:
                start = int(parts[0]) if parts[0] else 0
            except ValueError:
                start = 0
            try:
                end = int(parts[1]) if len(parts) > 1 and parts[1] else file_size - 1
            except ValueError:
                end = file_size - 1
            end = min(end, file_size - 1)
            length = end - start + 1

            f = open(file_path, 'rb')
            f.seek(start)
            data = f.read(length)
            f.close()

            response = FileResponse(
                iter([data]),
                content_type=content_type,
                status=206,
            )
            response['Content-Range'] = f'bytes {start}-{end}/{file_size}'
            response['Content-Length'] = str(length)
            response['Accept-Ranges'] = 'bytes'
            return response
        else:
            response = FileResponse(open(file_path, 'rb'), content_type=content_type)
            response['Content-Length'] = str(file_size)
            response['Accept-Ranges'] = 'bytes'
            return response

    def perform_create(self, serializer):
        if self.request.user.role == 'admin':
            serializer.save(uploaded_by=self.request.user)
