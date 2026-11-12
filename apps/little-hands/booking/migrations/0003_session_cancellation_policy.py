from django.db import migrations, models


def pin_existing_policies(apps, schema_editor):
    ClassSession = apps.get_model('booking', 'ClassSession')
    Course = apps.get_model('booking', 'Course')
    database = schema_editor.connection.alias
    for course in Course.objects.using(database).all().iterator():
        ClassSession.objects.using(database).filter(course_id=course.pk).update(
            cancellation_cutoff_minutes=course.cancellation_cutoff_minutes,
        )


class Migration(migrations.Migration):
    dependencies = [('booking', '0002_immutable_records')]
    operations = [
        migrations.AddField(
            model_name='classsession',
            name='cancellation_cutoff_minutes',
            field=models.PositiveIntegerField(default=120, verbose_name='취소 마감(분 전)'),
            preserve_default=False,
        ),
        migrations.RunPython(pin_existing_policies, migrations.RunPython.noop),
    ]
