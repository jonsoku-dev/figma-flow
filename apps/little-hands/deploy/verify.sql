\set ON_ERROR_STOP on
SELECT count(*) AS bookings FROM booking_booking;
SELECT count(*) AS audit_events FROM booking_auditevent;
DO $$
BEGIN
    IF has_table_privilege('littlehands_runtime', 'booking_auditevent', 'UPDATE')
       OR has_table_privilege('littlehands_runtime', 'booking_auditevent', 'DELETE')
       OR has_table_privilege('littlehands_runtime', 'booking_auditevent', 'TRUNCATE')
       OR has_table_privilege('littlehands_runtime', 'booking_operation', 'UPDATE')
       OR has_table_privilege('littlehands_runtime', 'booking_operation', 'DELETE')
       OR has_table_privilege('littlehands_runtime', 'booking_operation', 'TRUNCATE')
       OR has_schema_privilege('littlehands_runtime', 'public', 'CREATE') THEN
        RAISE EXCEPTION 'runtime role is overprivileged';
    END IF;
    IF (SELECT count(*) FROM pg_trigger WHERE tgname IN ('audit_event_immutable', 'operation_immutable') AND tgenabled = 'O') <> 2 THEN
        RAISE EXCEPTION 'immutable journal triggers missing';
    END IF;
    IF EXISTS (
        SELECT 1 FROM booking_classsession s
        LEFT JOIN booking_booking b ON b.session_id = s.id AND b.status = 'confirmed'
        GROUP BY s.id, s.capacity HAVING COALESCE(sum(b.quantity), 0) > s.capacity
    ) THEN
        RAISE EXCEPTION 'confirmed bookings exceed capacity';
    END IF;
END $$;
