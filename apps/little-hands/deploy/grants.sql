\set ON_ERROR_STOP on
BEGIN;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM littlehands_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO littlehands_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO littlehands_runtime;
REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON booking_auditevent, booking_operation FROM littlehands_runtime;
REVOKE ALL ON django_migrations FROM littlehands_runtime;
COMMIT;
