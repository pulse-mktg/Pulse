# Generated by Django 5.1.6 on 2025-03-05 16:35

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('website', '0006_client_business_model_types_client_company_size_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='clientgroup',
            name='category_type',
            field=models.CharField(blank=True, help_text='Category type this group is based on (company_size, revenue_range, etc.)', max_length=50, null=True),
        ),
        migrations.AddField(
            model_name='clientgroup',
            name='category_value',
            field=models.CharField(blank=True, help_text='Value of the category this group matches', max_length=50, null=True),
        ),
        migrations.AddField(
            model_name='clientgroup',
            name='is_auto_generated',
            field=models.BooleanField(default=False, help_text='Whether this group was automatically generated from client categories'),
        ),
    ]
