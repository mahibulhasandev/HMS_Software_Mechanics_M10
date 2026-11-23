--
-- PostgreSQL database cluster dump
--

\restrict WkIXpckFbgyPefQFW7pGNWDfxfr9KYY7kscVU9GxwW7dROpN4jhMhoHvJj3z7dZ

SET default_transaction_read_only = off;

SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;

--
-- Roles
--

CREATE ROLE admin;
ALTER ROLE admin WITH SUPERUSER INHERIT CREATEROLE CREATEDB LOGIN REPLICATION BYPASSRLS PASSWORD 'SCRAM-SHA-256$4096:7rpTehB3/eY3mnGbp1Z1hA==$+S8eedLlDfl2emSJYzvWI+oYYXD9K1WeVwqubdJOZIs=:lURF89fdvwS7WQz+WxPvoZHJSQVfpK55hK2rJCdNvb4=';
CREATE ROLE hms_app;
ALTER ROLE hms_app WITH NOSUPERUSER INHERIT NOCREATEROLE NOCREATEDB NOLOGIN NOREPLICATION NOBYPASSRLS;

--
-- User Configurations
--








\unrestrict WkIXpckFbgyPefQFW7pGNWDfxfr9KYY7kscVU9GxwW7dROpN4jhMhoHvJj3z7dZ

--
-- PostgreSQL database cluster dump complete
--

