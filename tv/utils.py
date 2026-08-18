from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone


#: How far ahead the rail looks for the class to announce as "A seguir".
NEXT_BOOKING_LOOKAHEAD_DAYS = 7


def display_timezone():
    """
    Bookings are stored as a naive date + an "HH:MM - HH:MM" label, i.e. as
    wall-clock time at the gym. The project runs on TIME_ZONE='UTC', so the
    screen must resolve "now" against the gym's local timezone instead.
    """
    return ZoneInfo(getattr(settings, 'TV_DISPLAY_TIMEZONE', 'Europe/Lisbon'))


def local_now():
    return timezone.now().astimezone(display_timezone())


def parse_time_slot(time_slot):
    """'15:00 - 16:00' -> (time(15, 0), time(16, 0), is_midnight_end)."""
    try:
        raw_start, raw_end = [part.strip() for part in time_slot.split('-')]
        start_h, start_m = [int(x) for x in raw_start.split(':')]
        end_h, end_m = [int(x) for x in raw_end.split(':')]
    except (ValueError, AttributeError):
        return None

    # The last slot is labelled '23:00 - 24:00', which time() cannot represent.
    ends_next_day = end_h >= 24
    if ends_next_day:
        end_h -= 24

    return time(start_h, start_m), time(end_h, end_m), ends_next_day


def slot_bounds(booking_date, time_slot, tzinfo=None):
    """Aware start/end datetimes for a booking's slot, or None if unparseable."""
    parsed = parse_time_slot(time_slot)
    if not parsed:
        return None

    tzinfo = tzinfo or display_timezone()
    start_time, end_time, ends_next_day = parsed
    start = datetime.combine(booking_date, start_time, tzinfo=tzinfo)
    end = datetime.combine(booking_date, end_time, tzinfo=tzinfo)
    if ends_next_day or end <= start:
        end += timedelta(days=1)
    return start, end


def get_current_booking(region, now=None):
    """The confirmed booking running right now at `region`, or None."""
    from bookings.models import Booking

    now = now or local_now()
    today = now.date()
    candidates = (
        Booking.objects
        .filter(region=region, booking_date__in=[today - timedelta(days=1), today])
        .exclude(status='cancelled')
        .select_related('professor')
        .prefetch_related('students')
    )

    for booking in candidates:
        bounds = slot_bounds(booking.booking_date, booking.time_slot)
        if bounds and bounds[0] <= now < bounds[1]:
            return booking, bounds
    return None


def get_next_booking(region, now=None):
    """The next confirmed booking due to start at `region` after `now`, or None.

    Once a slot is over the rail must move on to whoever comes next, so the
    screen is never blank between classes. The week-long window means a quiet
    day — or a class moved a few days out — still leaves something to show.
    """
    from bookings.models import Booking

    now = now or local_now()
    today = now.date()
    candidates = (
        Booking.objects
        .filter(
            region=region,
            booking_date__gte=today,
            booking_date__lte=today + timedelta(days=NEXT_BOOKING_LOOKAHEAD_DAYS),
        )
        .exclude(status='cancelled')
        .select_related('professor')
        .prefetch_related('students')
    )

    upcoming = []
    for booking in candidates:
        bounds = slot_bounds(booking.booking_date, booking.time_slot)
        if bounds and bounds[0] > now:
            upcoming.append((bounds[0], booking, bounds))

    if not upcoming:
        return None
    upcoming.sort(key=lambda item: item[0])
    _, booking, bounds = upcoming[0]
    return booking, bounds


def student_names(booking):
    return [s.full_name for s in booking.students.all() if s.full_name]


def student_label(students):
    if len(students) > 1:
        return ', '.join(students[:-1]) + ' e ' + students[-1]
    return students[0] if students else ''


def build_next_payload(screen, now=None):
    """Who the room belongs to next, for the rail's 'A seguir' block."""
    now = now or local_now()
    upcoming = get_next_booking(screen.region, now=now)
    if not upcoming:
        return None

    booking, (start, end) = upcoming
    students = student_names(booking)
    teacher = getattr(booking.professor, 'full_name', '') or ''
    return {
        'students': students,
        'student_label': student_label(students),
        'teacher': teacher if screen.show_teacher_name else '',
        'time_slot': booking.time_slot,
        'starts_at': start.isoformat(),
        'ends_at': end.isoformat(),
        'seconds_until': max(0, int((start - now).total_seconds())),
    }


def build_welcome_payload(screen, now=None):
    """Serialisable description of the booking to greet on screen (or an idle payload)."""
    now = now or local_now()
    current = get_current_booking(screen.region, now=now)
    if not current:
        return {
            'active': False,
            'message': '',
            'teacher': '',
            'students': [],
            'time_slot': '',
            'started_at': None,
            'ends_at': None,
            'seconds_remaining': 0,
            'up_next': build_next_payload(screen, now=now),
        }

    booking, (start, end) = current
    students = student_names(booking)
    teacher = getattr(booking.professor, 'full_name', '') or ''

    template = screen.welcome_message_template or 'Bem-vindo(a) {student}, desejamos-te um excelente treino!'

    try:
        message = template.format(
            student=student_label(students),
            teacher=teacher,
            region=screen.region.name,
        )
    except (KeyError, IndexError):
        message = template

    return {
        'active': True,
        'message': message,
        'teacher': teacher if screen.show_teacher_name else '',
        'students': students,
        'time_slot': booking.time_slot,
        'started_at': start.isoformat(),
        'ends_at': end.isoformat(),
        'seconds_remaining': max(0, int((end - now).total_seconds())),
        'up_next': build_next_payload(screen, now=now),
    }
