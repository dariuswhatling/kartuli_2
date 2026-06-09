from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("chat", "0001_initial"),
    ]

    operations = [
        migrations.DeleteModel(name="Attempt"),
        migrations.DeleteModel(name="Skill"),
    ]
