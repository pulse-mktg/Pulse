# Generated by Django 5.1.6 on 2025-03-26 22:19

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('website', '0009_budget_budgetalert_budgetallocation_spendsnapshot_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Competitor',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('website', models.URLField(blank=True, max_length=255, null=True)),
                ('description', models.TextField(blank=True)),
                ('strength', models.CharField(choices=[('low', 'Low threat'), ('medium', 'Medium threat'), ('high', 'High threat'), ('direct', 'Direct competitor'), ('indirect', 'Indirect competitor')], default='medium', max_length=20)),
                ('advantages', models.TextField(blank=True, help_text='Key advantages of this competitor')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.AddField(
            model_name='client',
            name='industry',
            field=models.CharField(blank=True, choices=[('retail', 'Retail'), ('healthcare', 'Healthcare'), ('technology', 'Technology'), ('finance', 'Finance & Banking'), ('education', 'Education'), ('manufacturing', 'Manufacturing'), ('food_beverage', 'Food & Beverage'), ('real_estate', 'Real Estate'), ('hospitality', 'Hospitality & Tourism'), ('entertainment', 'Entertainment & Media'), ('automotive', 'Automotive'), ('ecommerce', 'E-Commerce'), ('agriculture', 'Agriculture'), ('construction', 'Construction'), ('professional_services', 'Professional Services'), ('nonprofit', 'Non-profit & NGO'), ('energy', 'Energy & Utilities'), ('logistics', 'Logistics & Transportation'), ('telecom', 'Telecommunications'), ('government', 'Government'), ('other', 'Other')], max_length=30, null=True),
        ),
        migrations.AddField(
            model_name='client',
            name='website',
            field=models.URLField(blank=True, max_length=255, null=True),
        ),
        migrations.AddIndex(
            model_name='client',
            index=models.Index(fields=['industry'], name='website_cli_industr_a2eaa3_idx'),
        ),
        migrations.AddIndex(
            model_name='client',
            index=models.Index(fields=['website', 'tenant', 'is_active'], name='website_cli_website_0d9c04_idx'),
        ),
        migrations.AddField(
            model_name='competitor',
            name='client',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='competitors', to='website.client'),
        ),
        migrations.AddIndex(
            model_name='competitor',
            index=models.Index(fields=['client', 'is_active'], name='website_com_client__fc03ab_idx'),
        ),
        migrations.AddIndex(
            model_name='competitor',
            index=models.Index(fields=['strength'], name='website_com_strengt_b0e045_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='competitor',
            unique_together={('client', 'name')},
        ),
    ]
