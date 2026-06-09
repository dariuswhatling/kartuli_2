import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('lessons', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Conversation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(default='New session', max_length=200)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='conversations', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-updated_at'],
            },
        ),
        migrations.CreateModel(
            name='Message',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('user', 'User'), ('assistant', 'Assistant')], max_length=12)),
                ('content', models.TextField()),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('conversation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='chat.conversation')),
            ],
            options={
                'ordering': ['created_at'],
            },
        ),
        migrations.CreateModel(
            name='Skill',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('topic', models.CharField(max_length=120)),
                ('label', models.CharField(blank=True, max_length=200)),
                ('score', models.FloatField(default=0.5)),
                ('attempts', models.PositiveIntegerField(default=0)),
                ('correct_count', models.FloatField(default=0.0)),
                ('last_seen', models.DateTimeField(auto_now=True)),
                ('lesson', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='skills', to='lessons.lesson')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='skills', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['score', '-last_seen'],
                'unique_together': {('user', 'lesson', 'topic')},
            },
        ),
        migrations.CreateModel(
            name='Attempt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('question', models.TextField(blank=True)),
                ('answer', models.TextField(blank=True)),
                ('correctness', models.FloatField(default=0.0)),
                ('note', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attempts', to=settings.AUTH_USER_MODEL)),
                ('skill', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attempt_log', to='chat.skill')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
