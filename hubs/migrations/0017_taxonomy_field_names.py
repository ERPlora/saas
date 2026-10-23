"""HUBS-F36: the fields of a sector and a business type get names the admin shows in the staff's language («Código»,
«Activo», «Orden»…), where it showed «Code» and «By is active». Only Django's state changes: no SQL, both ways.
"""

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hubs', '0016_hub_suspension_clock'),
    ]

    operations = [
        migrations.AlterField(
            model_name='businesstype',
            name='code',
            field=models.SlugField(help_text='Stable code used by the API. Never change it.', max_length=80, unique=True, verbose_name='code'),
        ),
        migrations.AlterField(
            model_name='businesstype',
            name='color',
            field=models.CharField(blank=True, help_text='Hex colour, e.g. #ff6b35.', max_length=20, verbose_name='colour'),
        ),
        migrations.AlterField(
            model_name='businesstype',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, verbose_name='created at'),
        ),
        migrations.AlterField(
            model_name='businesstype',
            name='display_order',
            field=models.IntegerField(default=0, verbose_name='order'),
        ),
        migrations.AlterField(
            model_name='businesstype',
            name='icon',
            field=models.CharField(blank=True, max_length=100, verbose_name='icon'),
        ),
        migrations.AlterField(
            model_name='businesstype',
            name='is_active',
            field=models.BooleanField(default=True, verbose_name='active'),
        ),
        migrations.AlterField(
            model_name='businesstype',
            name='sector',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='business_types', to='hubs.sector', verbose_name='sector'),
        ),
        migrations.AlterField(
            model_name='businesstype',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, verbose_name='updated at'),
        ),
        migrations.AlterField(
            model_name='businesstype',
            name='vertical',
            field=models.CharField(blank=True, default='', help_text='Template a new hub of this type starts from (hair_salon, restaurant…); blank for none.', max_length=40, validators=[django.core.validators.RegexValidator('^[a-z][a-z0-9_]*$', 'Enter a vertical made of lowercase letters, digits and underscores, starting with a letter.')], verbose_name='vertical'),
        ),
        migrations.AlterField(
            model_name='sector',
            name='code',
            field=models.SlugField(help_text='Stable code used by the API. Never change it.', unique=True, verbose_name='code'),
        ),
        migrations.AlterField(
            model_name='sector',
            name='color',
            field=models.CharField(blank=True, help_text='Hex colour, e.g. #ff6b35.', max_length=20, verbose_name='colour'),
        ),
        migrations.AlterField(
            model_name='sector',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, verbose_name='created at'),
        ),
        migrations.AlterField(
            model_name='sector',
            name='display_order',
            field=models.IntegerField(default=0, verbose_name='order'),
        ),
        migrations.AlterField(
            model_name='sector',
            name='icon',
            field=models.CharField(blank=True, max_length=100, verbose_name='icon'),
        ),
        migrations.AlterField(
            model_name='sector',
            name='is_active',
            field=models.BooleanField(default=True, verbose_name='active'),
        ),
        migrations.AlterField(
            model_name='sector',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, verbose_name='updated at'),
        ),
    ]
