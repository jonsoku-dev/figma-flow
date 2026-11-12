\set ON_ERROR_STOP on
\set owner_password `cat /run/secrets/owner_password`
\set runtime_password `cat /run/secrets/runtime_password`
CREATE ROLE littlehands_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD :'owner_password';
CREATE ROLE littlehands_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD :'runtime_password';
REVOKE ALL ON DATABASE littlehands FROM PUBLIC;
GRANT CONNECT ON DATABASE littlehands TO littlehands_owner, littlehands_runtime;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO littlehands_owner;
GRANT USAGE ON SCHEMA public TO littlehands_runtime;
CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public;
