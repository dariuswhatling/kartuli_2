import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Lesson',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=300)),
                ('original_filename', models.CharField(blank=True, max_length=300)),
                ('file', models.FileField(blank=True, null=True, upload_to='lessons/')),
                ('raw_text', models.TextField(blank=True)),
                ('summary', models.TextField(blank=True)),
                ('topics', models.JSONField(blank=True, default=list)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('processing', 'Processing'), ('ready', 'Ready'), ('failed', 'Failed')], default='pending', max_length=20)),
                ('error', models.TextField(blank=True)),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lessons', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-uploaded_at'],
            },
        ),
        migrations.CreateModel(
            name='Chunk',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.PositiveIntegerField(default=0)),
                ('text', models.TextField()),
                ('topics', models.JSONField(blank=True, default=list)),
                ('section', models.CharField(blank=True, max_length=200)),
                ('grammar_points', models.JSONField(blank=True, default=list)),
                ('vocab', models.JSONField(blank=True, default=list)),
                ('embedding', models.JSONField(blank=True, default=list)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chunks', to=settings.AUTH_USER_MODEL)),
                ('lesson', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chunks', to='lessons.lesson')),
            ],
            options={
                'ordering': ['lesson_id', 'order'],
            },
        ),
    ]
