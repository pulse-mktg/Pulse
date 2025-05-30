# Generated by Django 5.1.6 on 2025-03-04 23:21

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('website', '0004_googleadscampaign_googleadsadgroup_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='ClientGroup',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('description', models.TextField(blank=True)),
                ('icon_class', models.CharField(default='bi-collection', help_text='Bootstrap icon class', max_length=50)),
                ('color', models.CharField(default='#6c757d', help_text='Group color (HEX code)', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('clients', models.ManyToManyField(blank=True, related_name='groups', to='website.client')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='client_groups', to='website.tenant')),
            ],
            options={
                'ordering': ['name'],
                'unique_together': {('tenant', 'name')},
            },
        ),
    ]
