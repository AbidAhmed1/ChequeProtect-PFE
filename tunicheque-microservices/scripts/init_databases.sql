-- =============================================================================
--  TuniCheque — Script d'initialisation de toutes les bases de données
--  PostgreSQL 14+
--  Exécuter avec : psql -U postgres -f init_databases.sql
--  Idempotent : peut être relancé sans erreur (IF NOT EXISTS partout)
-- =============================================================================


-- =============================================================================
--  CRÉATION DES BASES
-- =============================================================================

SELECT 'CREATE DATABASE database_auth'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'database_auth')\gexec

SELECT 'CREATE DATABASE database_cheque'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'database_cheque')\gexec

SELECT 'CREATE DATABASE database_notification'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'database_notification')\gexec


-- =============================================================================
--  DATABASE_AUTH
-- =============================================================================

\connect database_auth

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ENUM TYPES
DO $$ BEGIN
    CREATE TYPE role_enum AS ENUM ('ADMIN','AGENT','TIREUR','BENEFICIAIRE','CLIENT');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE user_type_enum AS ENUM ('INTERNAL','CLIENT');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE otp_status_enum AS ENUM ('PENDING','VERIFIED','EXPIRED','CANCELLED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- TABLE : users
CREATE TABLE IF NOT EXISTS users (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name       VARCHAR(200),
    email           VARCHAR(255)    UNIQUE,
    password_hash   VARCHAR(255)    NOT NULL,
    phone           VARCHAR(20)     UNIQUE,
    cin_number      VARCHAR(8)      UNIQUE,
    rib             VARCHAR(20),
    face_image_url  TEXT,
    role            role_enum       NOT NULL,
    user_type       user_type_enum  NOT NULL,
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    is_verified     BOOLEAN         NOT NULL DEFAULT FALSE,
    is_blocked      BOOLEAN         NOT NULL DEFAULT FALSE,
    block_reason    TEXT,
    blocked_at      TIMESTAMP,
    blocked_by      UUID,
    otp_code        VARCHAR(255),
    otp_expires_at  TIMESTAMP,
    created_at      TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email  ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_phone  ON users(phone);
CREATE INDEX IF NOT EXISTS idx_users_role   ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active);

-- TABLE : bank_accounts
CREATE TABLE IF NOT EXISTS bank_accounts (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    rib             VARCHAR(20)     NOT NULL UNIQUE,
    code_banque     VARCHAR(2),
    code_agence     VARCHAR(3),
    num_compte      VARCHAR(13),
    cle_rib         VARCHAR(2),
    telephone       VARCHAR(20)     NOT NULL,
    nom_titulaire   VARCHAR(200),
    role            role_enum,
    active          BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bank_accounts_rib       ON bank_accounts(rib);
CREATE INDEX IF NOT EXISTS idx_bank_accounts_telephone ON bank_accounts(telephone);

-- TABLE : otp_sessions
CREATE TABLE IF NOT EXISTS otp_sessions (
    id          UUID                PRIMARY KEY DEFAULT gen_random_uuid(),
    telephone   VARCHAR(20)         NOT NULL,
    otp_code    VARCHAR(100)        NOT NULL,
    expiration  TIMESTAMP           NOT NULL,
    status      otp_status_enum     NOT NULL DEFAULT 'PENDING',
    attempts    INTEGER             NOT NULL DEFAULT 0,
    created_at  TIMESTAMP           NOT NULL DEFAULT NOW(),
    verified_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_otp_sessions_telephone ON otp_sessions(telephone);
CREATE INDEX IF NOT EXISTS idx_otp_sessions_status    ON otp_sessions(status);

-- TABLE : user_documents
CREATE TABLE IF NOT EXISTS user_documents (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID,
    session_id      VARCHAR(255),
    cin_recto_path  VARCHAR(500),
    cin_verso_path  VARCHAR(500),
    selfie_enc_path VARCHAR(500),
    face_b64        TEXT,
    created_at      TIMESTAMP   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_documents_user_id ON user_documents(user_id);


-- =============================================================================
--  DATABASE_CHEQUE
-- =============================================================================

\connect database_cheque

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

DO $$ BEGIN
    CREATE TYPE cheque_status_enum AS ENUM ('EN_ATTENTE','EN_TRAITEMENT','VALIDE','REJETE','FRAUDE_DETECTEE');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE ai_phase_enum AS ENUM ('identification','compliance','ocr','signature');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- TABLE : cheques
CREATE TABLE IF NOT EXISTS cheques (
    id                  UUID                PRIMARY KEY DEFAULT gen_random_uuid(),
    numero_cheque       VARCHAR(50),
    image_recto_url     VARCHAR(500)        NOT NULL,
    image_verso_url     VARCHAR(500),
    montant_extrait     DECIMAL(15, 3),
    montant_lettres     TEXT,
    beneficiaire_nom    VARCHAR(200),
    date_emission       DATE,
    rib_emetteur        VARCHAR(30),
    qr_data             TEXT,
    status              cheque_status_enum  NOT NULL DEFAULT 'EN_ATTENTE',
    decision_finale     VARCHAR(50),
    source              VARCHAR(10)         NOT NULL DEFAULT 'MOBILE',
    beneficiaire_id     UUID,
    tireur_id           UUID,
    agent_id            UUID,
    bank_account_id     UUID,
    ai_score_global     DECIMAL(5, 4),
    fraude_detectee     BOOLEAN             NOT NULL DEFAULT FALSE,
    motif_rejet         TEXT,
    pipeline_ms         INTEGER,
    created_at          TIMESTAMP           NOT NULL DEFAULT NOW(),
    validated_at        TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cheques_status          ON cheques(status);
CREATE INDEX IF NOT EXISTS idx_cheques_beneficiaire_id ON cheques(beneficiaire_id);
CREATE INDEX IF NOT EXISTS idx_cheques_tireur_id       ON cheques(tireur_id);
CREATE INDEX IF NOT EXISTS idx_cheques_agent_id        ON cheques(agent_id);
CREATE INDEX IF NOT EXISTS idx_cheques_created_at      ON cheques(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cheques_fraude          ON cheques(fraude_detectee) WHERE fraude_detectee = TRUE;

-- TABLE : ai_results
CREATE TABLE IF NOT EXISTS ai_results (
    id          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    cheque_id   UUID            NOT NULL,
    phase       ai_phase_enum   NOT NULL,
    score       DECIMAL(5, 4),
    passed      BOOLEAN         NOT NULL DEFAULT FALSE,
    details     TEXT,
    decision    VARCHAR(50),
    duration_ms INTEGER,
    created_at  TIMESTAMP       NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_ai_results_cheque_phase UNIQUE (cheque_id, phase)
);

CREATE INDEX IF NOT EXISTS idx_ai_results_cheque_id ON ai_results(cheque_id);

-- TABLE : reclamations
CREATE TABLE IF NOT EXISTS reclamations (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID        NOT NULL,
    cheque_id       VARCHAR(255),
    objet           VARCHAR(200),
    description     TEXT,
    statut          VARCHAR(50) NOT NULL DEFAULT 'OUVERTE',
    reponse_agent   TEXT,
    created_at      TIMESTAMP   NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reclamations_user_id ON reclamations(user_id);
CREATE INDEX IF NOT EXISTS idx_reclamations_statut  ON reclamations(statut);


-- =============================================================================
--  DATABASE_NOTIFICATION
-- =============================================================================

\connect database_notification

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

DO $$ BEGIN
    CREATE TYPE notification_type_enum AS ENUM ('EMAIL','SMS','PUSH');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- TABLE : notifications
CREATE TABLE IF NOT EXISTS notifications (
    id              UUID                        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID                        NOT NULL,
    cheque_id       VARCHAR(255),
    user_role       VARCHAR(20),
    type            notification_type_enum      NOT NULL,
    sujet           VARCHAR(200),
    contenu         TEXT,
    statut          VARCHAR(50)                 NOT NULL DEFAULT 'ENVOYE',
    kafka_topic     VARCHAR(60),
    error_message   TEXT,
    is_read         BOOLEAN                     NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMP                   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notifications_user_id        ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user_id_unread ON notifications(user_id, is_read) WHERE is_read = FALSE;
CREATE INDEX IF NOT EXISTS idx_notifications_created_at     ON notifications(created_at DESC);


-- =============================================================================
--  VÉRIFICATION FINALE
-- =============================================================================

\connect database_auth
\echo '--- database_auth ---'
\dt

\connect database_cheque
\echo '--- database_cheque ---'
\dt

\connect database_notification
\echo '--- database_notification ---'
\dt
