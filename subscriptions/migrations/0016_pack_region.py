from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('subscriptions', '0015_region_packregionprice_order_region'),
    ]

    operations = [
        migrations.AddField(
            model_name='pack',
            name='region',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='packs',
                help_text='Gym location this pack belongs to (optional)',
                to='subscriptions.region',
            ),
        ),
    ]
