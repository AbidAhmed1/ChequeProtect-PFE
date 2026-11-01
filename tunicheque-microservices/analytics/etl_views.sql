-- =============================================================================
-- TuniCheque — Couche Sémantique Analytique (ETL Views)
-- Base cible   : database_cheques
-- Connexion PBI: Power BI Desktop > Obtenir données > PostgreSQL
--                Host: localhost:5432  DB: database_cheques  Schema: analytics
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS analytics;

-- -----------------------------------------------------------------------------
-- 1. FAIT PRINCIPAL — grain : 1 ligne par chèque traité
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.fait_cheques AS
SELECT
    c.id::text                                                      AS cheque_id,
    c.created_at::date                                              AS date_depot,
    DATE_TRUNC('week',  c.created_at)::date                         AS debut_semaine,
    DATE_TRUNC('month', c.created_at)::date                         AS debut_mois,
    EXTRACT(YEAR  FROM c.created_at)::int                           AS annee,
    EXTRACT(MONTH FROM c.created_at)::int                           AS mois_num,
    TO_CHAR(c.created_at, 'TMMonth')                                AS mois_label,
    EXTRACT(DOW   FROM c.created_at)::int                           AS jour_semaine_num,
    TO_CHAR(c.created_at, 'TMDay')                                  AS jour_semaine_label,
    -- Statuts
    c.status                                                        AS statut,
    CASE WHEN c.status = 'VALIDE' THEN 1 ELSE 0 END                 AS est_valide,
    CASE WHEN c.status IN ('REJETE','FRAUDE_DETECTEE') THEN 1
         ELSE 0 END                                                 AS est_rejete,
    CASE WHEN c.fraude_detectee THEN 1 ELSE 0 END                   AS est_fraude,
    CASE WHEN c.status IN ('EN_ATTENTE','EN_TRAITEMENT') THEN 1
         ELSE 0 END                                                 AS est_en_cours,
    -- Métriques
    COALESCE(c.montant_extrait, 0)                                  AS montant_tnd,
    COALESCE(c.ai_score_global, 0)                                  AS score_ia_global,
    COALESCE(c.pipeline_ms, 0)                                      AS duree_pipeline_ms,
    ROUND(COALESCE(c.pipeline_ms, 0) / 1000.0, 2)                   AS duree_pipeline_sec,
    -- Niveau de confiance IA (catégorie)
    CASE
        WHEN COALESCE(c.ai_score_global, 0) >= 0.90 THEN 'Haute confiance'
        WHEN COALESCE(c.ai_score_global, 0) >= 0.75 THEN 'Confiance moyenne'
        ELSE 'Faible confiance'
    END                                                             AS niveau_confiance,
    -- Dimensions
    c.source                                                        AS canal,
    c.agent_id::text                                                AS agent_id,
    c.beneficiaire_id::text                                         AS beneficiaire_id,
    c.tireur_id::text                                               AS tireur_id,
    c.emetteur_nom                                                  AS nom_emetteur,
    -- Délai de traitement (dépôt → décision)
    CASE
        WHEN c.validated_at IS NOT NULL
        THEN EXTRACT(EPOCH FROM (c.validated_at - c.created_at)) / 3600.0
        ELSE NULL
    END                                                             AS delai_traitement_h
FROM cheques c;


-- -----------------------------------------------------------------------------
-- 2. KPI JOURNALIERS — agrégat par date
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.kpi_daily AS
SELECT
    created_at::date                                                    AS date,
    COUNT(*)                                                            AS total,
    COUNT(*) FILTER (WHERE status = 'VALIDE')                           AS valides,
    COUNT(*) FILTER (WHERE status IN ('REJETE','FRAUDE_DETECTEE'))      AS rejetes,
    COUNT(*) FILTER (WHERE fraude_detectee = TRUE)                      AS fraudes,
    COUNT(*) FILTER (WHERE status IN ('EN_ATTENTE','EN_TRAITEMENT'))    AS en_attente,
    ROUND(AVG(ai_score_global)::numeric * 100, 1)                       AS score_ia_moy_pct,
    ROUND(AVG(pipeline_ms)::numeric / 1000.0, 2)                        AS duree_moy_sec,
    COALESCE(SUM(montant_extrait), 0)                                   AS montant_total_tnd,
    ROUND(
        COUNT(*) FILTER (WHERE status = 'VALIDE') * 100.0
        / NULLIF(COUNT(*) FILTER (WHERE status NOT IN ('EN_ATTENTE','EN_TRAITEMENT')), 0)
    , 2)                                                                AS taux_validation_pct
FROM cheques
GROUP BY 1
ORDER BY 1 DESC;


-- -----------------------------------------------------------------------------
-- 3. PERFORMANCE PAR AGENT
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.agent_performance AS
SELECT
    c.agent_id::text                                                    AS agent_id,
    COUNT(c.id)                                                         AS total_traites,
    COUNT(c.id) FILTER (WHERE c.status = 'VALIDE')                      AS valides,
    COUNT(c.id) FILTER (WHERE c.status IN ('REJETE','FRAUDE_DETECTEE')) AS rejetes,
    COUNT(c.id) FILTER (WHERE c.fraude_detectee = TRUE)                 AS fraudes_detectees,
    ROUND(AVG(c.ai_score_global)::numeric * 100, 1)                     AS score_moyen_pct,
    ROUND(AVG(c.pipeline_ms)::numeric / 1000.0, 1)                      AS duree_moy_sec,
    ROUND(
        COUNT(c.id) FILTER (WHERE c.status = 'VALIDE') * 100.0
        / NULLIF(COUNT(c.id) FILTER (WHERE c.status NOT IN ('EN_ATTENTE','EN_TRAITEMENT')), 0)
    , 2)                                                                AS taux_validation_pct,
    MIN(c.created_at)::date                                             AS premier_traitement,
    MAX(c.created_at)::date                                             AS dernier_traitement
FROM cheques c
WHERE c.agent_id IS NOT NULL
GROUP BY c.agent_id;


-- -----------------------------------------------------------------------------
-- 4. DISTRIBUTION DES SCORES IA — pour histogramme Power BI
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.score_distribution AS
SELECT
    CASE
        WHEN ai_score_global < 0.50 THEN '1_< 0.50'
        WHEN ai_score_global < 0.60 THEN '2_0.50–0.59'
        WHEN ai_score_global < 0.70 THEN '3_0.60–0.69'
        WHEN ai_score_global < 0.80 THEN '4_0.70–0.79'
        WHEN ai_score_global < 0.85 THEN '5_0.80–0.84'
        WHEN ai_score_global < 0.90 THEN '6_0.85–0.89'
        WHEN ai_score_global < 0.95 THEN '7_0.90–0.94'
        ELSE                             '8_≥ 0.95'
    END                                                     AS tranche,
    COUNT(*)                                                AS nb_cheques,
    COUNT(*) FILTER (WHERE fraude_detectee = TRUE)          AS nb_fraudes,
    ROUND(AVG(montant_extrait)::numeric, 3)                 AS montant_moyen,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2)       AS pct_total
FROM cheques
WHERE ai_score_global IS NOT NULL
GROUP BY 1
ORDER BY 1;


-- -----------------------------------------------------------------------------
-- 5. RÉSULTATS IA PAR PHASE — pour analyse pipeline
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.ai_phases AS
SELECT
    ar.cheque_id::text,
    ar.phase,
    ar.score,
    ar.passed::int          AS passe,
    ar.decision,
    ar.duration_ms          AS duree_ms,
    c.created_at::date      AS date_traitement,
    c.status                AS statut_final,
    c.fraude_detectee::int  AS est_fraude
FROM ai_results ar
JOIN cheques c ON c.id = ar.cheque_id
ORDER BY ar.created_at DESC;


-- -----------------------------------------------------------------------------
-- 6. RÉCLAMATIONS ANALYTIQUES
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.reclamations_analytics AS
SELECT
    r.id::text                                                          AS reclamation_id,
    r.created_at::date                                                  AS date_reclamation,
    DATE_TRUNC('month', r.created_at)::date                             AS mois_reclamation,
    r.statut,
    r.numero_cheque,
    r.cheque_id::text                                                   AS cheque_id,
    EXTRACT(EPOCH FROM (COALESCE(r.updated_at, NOW()) - r.created_at))
        / 3600.0                                                        AS delai_traitement_h,
    CASE
        WHEN r.statut = 'TRANSMISE' THEN 'Traitée'
        WHEN r.statut = 'OUVERTE'   THEN 'En attente'
        ELSE r.statut
    END                                                                 AS statut_label
FROM reclamations r;


-- -----------------------------------------------------------------------------
-- 7. VUE CONSOLIDÉE PRINCIPALE (rapport Power BI central)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.rapport_principal AS
SELECT
    c.id::text                                                          AS cheque_id,
    c.created_at::date                                                  AS date_depot,
    DATE_TRUNC('month', c.created_at)::date                             AS mois,
    c.status                                                            AS statut,
    CASE WHEN c.status = 'VALIDE' THEN 1 ELSE 0 END                     AS est_valide,
    CASE WHEN c.fraude_detectee THEN 1 ELSE 0 END                       AS est_fraude,
    COALESCE(c.montant_extrait, 0)                                      AS montant_tnd,
    COALESCE(c.ai_score_global, 0)                                      AS score_ia,
    COALESCE(c.pipeline_ms, 0) / 1000.0                                 AS duree_sec,
    c.source                                                            AS canal,
    c.emetteur_nom,
    CASE
        WHEN c.ai_score_global >= 0.90 THEN 'Haute'
        WHEN c.ai_score_global >= 0.75 THEN 'Moyenne'
        ELSE 'Faible'
    END                                                                 AS confiance,
    -- Phases IA
    MAX(CASE WHEN ar.phase = 'PHASE_1' THEN ar.score END)               AS score_identification,
    MAX(CASE WHEN ar.phase = 'PHASE_2' THEN ar.score END)               AS score_ocr,
    MAX(CASE WHEN ar.phase = 'PHASE_3' THEN ar.score END)               AS score_signature,
    MAX(CASE WHEN ar.phase = 'PHASE_4' THEN ar.score END)               AS score_kyc,
    -- Réclamations associées
    COUNT(DISTINCT r.id)                                                AS nb_reclamations
FROM cheques c
LEFT JOIN ai_results ar ON ar.cheque_id = c.id
LEFT JOIN reclamations r ON r.cheque_id = c.id
GROUP BY c.id, c.created_at, c.status, c.fraude_detectee,
         c.montant_extrait, c.ai_score_global, c.pipeline_ms,
         c.source, c.emetteur_nom;


-- =============================================================================
-- GUIDE DE CONNEXION POWER BI DESKTOP
-- =============================================================================
-- 1. Ouvrir Power BI Desktop
-- 2. Accueil > Obtenir les données > Base de données PostgreSQL
-- 3. Serveur : localhost   Base de données : database_cheques
-- 4. Mode de connectivité : DirectQuery (temps réel) ou Import (performance)
-- 5. Navigateur : sélectionner le schéma "analytics" > cocher les 7 vues
-- 6. Créer les relations :
--    rapport_principal.date_depot  ↔  kpi_daily.date
--    agent_performance.agent_id    ↔  rapport_principal.agent_id
--    ai_phases.cheque_id           ↔  rapport_principal.cheque_id
-- 7. Publier sur Power BI Service (app.powerbi.com)
-- 8. Fichier > Incorporer le rapport > Publier sur le web
-- 9. Copier l'URL iframe et la coller dans l'interface admin TuniCheque
-- =============================================================================
