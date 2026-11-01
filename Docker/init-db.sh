#!/bin/bash
# Crée les 3 bases de données TuniCheque au premier démarrage de PostgreSQL
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    SELECT 'CREATE DATABASE database_auth'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'database_auth')\gexec

    SELECT 'CREATE DATABASE database_cheques'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'database_cheques')\gexec

    SELECT 'CREATE DATABASE database_notifications'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'database_notifications')\gexec
EOSQL

echo "Databases created: database_auth, database_cheques, database_notifications"
