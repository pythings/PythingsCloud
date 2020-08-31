CREATE DATABASE pythings;
CREATE USER pythings_master WITH PASSWORD '7sanq235';
ALTER USER pythings_master CREATEDB;
GRANT ALL PRIVILEGES ON DATABASE pythings to pythings_master;
\c pythings
GRANT CREATE ON SCHEMA PUBLIC TO pythings_master;
