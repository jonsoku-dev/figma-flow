import re

from django.conf import settings
from django.db import migrations, models


def trigger(name, timing, table, body):
    return (
        f'CREATE TRIGGER IF NOT EXISTS {name} {timing} ON {table} FOR EACH ROW {body}',
        f'DROP TRIGGER IF EXISTS {name}',
    )


# Keep locking reads off the table that invokes the trigger.
reserve_interval = """
    INSERT INTO booking_roomschedulelock (room_id) VALUES (NEW.room_id)
    ON DUPLICATE KEY UPDATE room_id = NEW.room_id;

    SELECT session_id INTO conflicting_session
    FROM booking_roomscheduleentry
    WHERE room_id = NEW.room_id
      AND starts_at < NEW.ends_at AND ends_at > NEW.starts_at
    LIMIT 1 FOR UPDATE;

    IF conflicting_session IS NOT NULL THEN
        SIGNAL SQLSTATE '23000' SET MYSQL_ERRNO = 1062,
            MESSAGE_TEXT = 'scheduled_room_no_overlap';
    END IF;

    INSERT INTO booking_roomscheduleentry (session_id, room_id, starts_at, ends_at)
    VALUES (NEW.id, NEW.room_id, NEW.starts_at, NEW.ends_at);
"""

schedule_insert = f"""
BEGIN
    DECLARE conflicting_session BIGINT DEFAULT NULL;
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET conflicting_session = NULL;
    IF NEW.status = 'scheduled' THEN
        {reserve_interval}
    END IF;
END
"""

schedule_update = f"""
BEGIN
    DECLARE conflicting_session BIGINT DEFAULT NULL;
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET conflicting_session = NULL;
    IF OLD.status <> NEW.status OR OLD.room_id <> NEW.room_id
        OR OLD.starts_at <> NEW.starts_at OR OLD.ends_at <> NEW.ends_at THEN
        DELETE FROM booking_roomscheduleentry WHERE session_id = OLD.id;
        IF NEW.status = 'scheduled' THEN
            {reserve_interval}
        END IF;
    END IF;
END
"""

TRIGGERS = [
    trigger(f'{name}_immutable_{event.lower()}', f'BEFORE {event}', table,
            "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'audit and operation records are immutable'")
    for name, table in (('audit_event', 'booking_auditevent'), ('operation', 'booking_operation'))
    for event in ('UPDATE', 'DELETE')
] + [
    trigger('room_capacity_immutable', 'BEFORE UPDATE', 'booking_room', """
        BEGIN
            IF NEW.capacity <> OLD.capacity THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'room capacity is immutable';
            END IF;
        END
    """),
    trigger('room_schedule_insert', 'AFTER INSERT', 'booking_classsession', schedule_insert),
    trigger('room_schedule_update', 'AFTER UPDATE', 'booking_classsession', schedule_update),
    trigger('room_schedule_delete', 'AFTER DELETE', 'booking_classsession',
            'DELETE FROM booking_roomscheduleentry WHERE session_id = OLD.id'),
]


def install_triggers(apps, schema_editor):
    prefix = 'CREATE TRIGGER'
    if settings.INSTALL_TRIGGERS_AS_SCHEMA_OWNER:
        owner = settings.DATABASE_DEFAULTS['owner']
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,31}', owner):
            raise ValueError('Invalid MySQL schema owner')
        prefix = f"CREATE DEFINER = '{owner}'@'%' TRIGGER"
    for forward, _ in TRIGGERS:
        schema_editor.execute(forward.replace('CREATE TRIGGER', prefix, 1), params=None)


def remove_triggers(apps, schema_editor):
    for _, reverse in reversed(TRIGGERS):
        schema_editor.execute(reverse, params=None)


class Migration(migrations.Migration):
    dependencies = [('booking', '0001_initial')]
    operations = [
        migrations.CreateModel(
            name='OperationLock',
            fields=[('actor_id', models.BigIntegerField(primary_key=True, serialize=False))],
        ),
        migrations.CreateModel(
            name='RoomScheduleLock',
            fields=[('room_id', models.BigIntegerField(primary_key=True, serialize=False))],
        ),
        migrations.CreateModel(
            name='RoomScheduleEntry',
            fields=[
                ('session_id', models.BigIntegerField(primary_key=True, serialize=False)),
                ('room_id', models.BigIntegerField()),
                ('starts_at', models.DateTimeField()),
                ('ends_at', models.DateTimeField()),
            ],
            options={'indexes': [models.Index(fields=['room_id', 'starts_at'], name='room_schedule_search')]},
        ),
            migrations.RunPython(install_triggers, reverse_code=remove_triggers, atomic=False),
    ]
