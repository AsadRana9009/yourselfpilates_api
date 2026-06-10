from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('subscriptions', '0014_pack_add_is_public'),
    ]

    operations = [
        migrations.CreateModel(
            name='Region',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('slug', models.SlugField(unique=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='PackRegionPrice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('pack', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='region_prices', to='subscriptions.pack')),
                ('region', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pack_prices', to='subscriptions.region')),
            ],
            options={
                'unique_together': {('pack', 'region')},
            },
        ),
        migrations.AddField(
            model_name='order',
            name='region',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='orders',
                to='subscriptions.region',
                help_text='Gym location selected by the user at purchase time',
            ),
        ),
    ]
