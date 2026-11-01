-- ================================================================
-- TuniCheque — Migration : Table des spécimens de signature
-- Base cible : cheque_db  (AI service)
-- Exécuter : psql -U postgres -d cheque_db -f create_specimens_table.sql
-- ================================================================

-- Table principale des spécimens
CREATE TABLE IF NOT EXISTS specimens_signatures (
    id          SERIAL PRIMARY KEY,
    rib         VARCHAR(20)  NOT NULL,          -- RIB 20 chiffres (clé de lookup)
    user_id     VARCHAR(100),                   -- UUID du titulaire (optionnel)
    full_name   VARCHAR(200),                   -- Nom du titulaire (pour debug)
    image_path  TEXT         NOT NULL,          -- Chemin absolu vers l'image
    is_active   BOOLEAN      DEFAULT TRUE,
    enrolled_by VARCHAR(100),                   -- 'KYC_FLOW' | 'ADMIN_MANUAL' | 'IMPORT'
    created_at  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

-- Index pour la recherche par RIB (chemin critique dans Phase 4)
CREATE INDEX IF NOT EXISTS idx_specimens_rib      ON specimens_signatures (rib);
CREATE INDEX IF NOT EXISTS idx_specimens_user_id  ON specimens_signatures (user_id);
CREATE INDEX IF NOT EXISTS idx_specimens_active   ON specimens_signatures (is_active);

-- Table de configuration (seuils, flags — lus par database.py:get_config())
CREATE TABLE IF NOT EXISTS configurations (
    cle         VARCHAR(100) PRIMARY KEY,
    valeur      TEXT         NOT NULL,
    type_valeur VARCHAR(20)  DEFAULT 'STRING',  -- STRING | FLOAT | INTEGER | BOOLEAN
    description TEXT,
    updated_at  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

-- Valeurs par défaut des seuils Phase 4
INSERT INTO configurations (cle, valeur, type_valeur, description)
VALUES
    ('phase4.threshold_match',  '0.80', 'FLOAT',   'Score minimum pour validation automatique'),
    ('phase4.threshold_review', '0.50', 'FLOAT',   'Score minimum pour renvoi expert'),
    ('phase4.strict_mode',      'false','BOOLEAN',  'Mode strict : seuils +0.10/+0.05'),
    ('phase4.enabled',          'true', 'BOOLEAN',  'Activer/désactiver Phase 4')
ON CONFLICT (cle) DO NOTHING;

-- Vue utilitaire pour l'admin
CREATE OR REPLACE VIEW v_specimens_stats AS
SELECT
    rib,
    full_name,
    COUNT(*)                    AS nb_specimens,
    MAX(created_at)             AS dernier_enrolement,
    BOOL_OR(is_active)          AS a_specimen_actif
FROM specimens_signatures
GROUP BY rib, full_name
ORDER BY dernier_enrolement DESC;