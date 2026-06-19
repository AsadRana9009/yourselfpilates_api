from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('subscriptions', '0016_pack_region'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CreditWallet',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('total_hours', models.DecimalField(decimal_places=2, max_digits=10)),
                ('used_hours', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('remaining_hours', models.DecimalField(decimal_places=2, max_digits=10)),
                ('purchase_date', models.DateTimeField(auto_now_add=True)),
                ('expiry_date', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(
                    choices=[
                        ('active', 'Active'),
                        ('expired', 'Expired'),
                        ('consumed', 'Consumed'),
                        ('cancelled', 'Cancelled'),
                    ],
                    default='active',
                    max_length=20,
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='credit_wallets',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('pack', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='wallet_entries',
                    to='subscriptions.pack',
                )),
                ('order', models.OneToOneField(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='wallet',
                    to='subscriptions.order',
                )),
                ('region', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='wallets',
                    to='subscriptions.region',
                )),
            ],
            options={
                'ordering': ['-purchase_date'],
            },
        ),
    ]
