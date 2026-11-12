from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('booking', '0001_initial')]
    operations = [migrations.RunSQL(
        sql='''
        CREATE FUNCTION booking_reject_record_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit and operation records are immutable';
        END; $$;
        CREATE TRIGGER audit_event_immutable BEFORE UPDATE OR DELETE ON booking_auditevent
        FOR EACH ROW EXECUTE FUNCTION booking_reject_record_mutation();
        CREATE TRIGGER operation_immutable BEFORE UPDATE OR DELETE ON booking_operation
        FOR EACH ROW EXECUTE FUNCTION booking_reject_record_mutation();
        CREATE FUNCTION booking_protect_room_capacity() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.capacity IS DISTINCT FROM OLD.capacity THEN
                RAISE EXCEPTION 'room capacity is immutable';
            END IF;
            RETURN NEW;
        END; $$;
        CREATE TRIGGER room_capacity_immutable BEFORE UPDATE ON booking_room
        FOR EACH ROW EXECUTE FUNCTION booking_protect_room_capacity();
        ''',
        reverse_sql='''
        DROP TRIGGER room_capacity_immutable ON booking_room;
        DROP FUNCTION booking_protect_room_capacity();
        DROP TRIGGER operation_immutable ON booking_operation;
        DROP TRIGGER audit_event_immutable ON booking_auditevent;
        DROP FUNCTION booking_reject_record_mutation();
        ''',
    )]
