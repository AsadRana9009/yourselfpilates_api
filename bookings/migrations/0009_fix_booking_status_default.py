from django.db import migrations, models


def approve_to_confirmed(apps, schema_editor):
    """
    'approve' was the field's default but was never one of its STATUS_CHOICES,
    so every booking saved without an explicit status ended up holding a value
    the model itself rejects. Nothing ever queried for it — the codebase only
    asks for 'confirmed' or excludes 'cancelled' — so these rows are simply
    confirmed bookings wearing the wrong label.
    """
    Booking = apps.get_model('bookings', 'Booking')
    Booking.objects.filter(status='approve').update(status='confirmed')


def confirmed_to_approve(apps, schema_editor):
    # Deliberately a no-op: 'confirmed' and the old 'approve' rows are
    # indistinguishable after the forward pass, and restoring an invalid value
    # would only reintroduce the bug.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0008_booking_created_by'),
    ]

    operations = [
        migrations.AlterField(
            model_name='booking',
            name='status',
            field=models.CharField(
                choices=[('confirmed', 'Confirmed'), ('cancelled', 'Cancelled')],
                default='confirmed',
                max_length=20,
            ),
        ),
        migrations.RunPython(approve_to_confirmed, confirmed_to_approve),
    ]
