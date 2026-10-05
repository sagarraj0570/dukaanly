-- Dukaanly — Database Initialization Script
-- This file runs automatically on first container start (empty volume).
-- It enables PostGIS and postgis_topology extensions in the application database.
-- NOTE: This only runs once when postgres_data volume is first created.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
