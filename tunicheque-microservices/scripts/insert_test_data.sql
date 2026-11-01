-- =============================================================================
--  TuniCheque — Données réelles de test (chèques du dossier Chequetest)
--  Exécuter sur : database_auth
--  Usage : psql -U postgres -d database_auth -f insert_test_data.sql
--
--  Chèques couverts :
--    chequeR.jpg — BTK Ariana — GUIZANI RYM         — RIB 20003030001148336517
--    ChequeT.jpg — BIAT Ariana — CHERCOUHI HICHEM   — RIB 08010011042001092378
--    recto.jpg   — BT Bekalta  — DOGGUI MOKHTAR     — RIB 05207000077307812272
--
--  PIN mobile par défaut : 112233
-- =============================================================================

\connect database_auth

-- =============================================================================
--  BANK ACCOUNTS
--  Nécessaires pour que l'inscription mobile via RIB fonctionne :
--    POST /api/auth/register/rib/initiate  →  cherche dans bank_accounts
-- =============================================================================

INSERT INTO bank_accounts (
    rib, code_banque, code_agence, num_compte, cle_rib,
    telephone, nom_titulaire, role, active
)
VALUES
    -- chequeR : GUIZANI RYM — BTK Bank, Ariana (76 Av H. Bourguiba)
    -- RIB = 20 | 003 | 0300011483365 | 17
    ('20003030001148336517', '20', '003', '0300011483365', '17',
     '+21629000101', 'GUIZANI RYM', 'TIREUR', true),

    -- ChequeT : CHERCOUHI HICHEM — BIAT, Ariana (RIB lu depuis CMC7)
    -- RIB = 08 | 010 | 0110420010923 | 78
    ('08010011042001092378', '08', '010', '0110420010923', '78',
     '+21629000102', 'CHERCOUHI HICHEM', 'TIREUR', true),

    -- recto.jpg : DOGGUI MOKHTAR — Banque de Tunisie, Bekalta
    -- RIB = 05 | 207 | 0000773078122 | 72  (visible sur chèque : 05 207 000 077 307812 2 72)
    ('05207000077307812272', '05', '207', '0000773078122', '72',
     '+21629000103', 'DOGGUI MOKHTAR', 'TIREUR', true)

ON CONFLICT (rib) DO UPDATE SET
    nom_titulaire = EXCLUDED.nom_titulaire,
    telephone     = EXCLUDED.telephone,
    active        = true;


-- =============================================================================
--  USERS TIREURS
--  findUserIdByRib(rib) → userRepository.findByRib(rib)
--  Ces comptes reçoivent les notifications après validation du chèque.
--  Login mobile : téléphone + PIN 112233
-- =============================================================================

INSERT INTO users (
    full_name, email, password_hash, phone, cin_number,
    rib, role, user_type, is_active, is_verified
)
VALUES
    -- ── GUIZANI RYM (chequeR — BTK Ariana) ───────────────────────────────
    (
        'GUIZANI RYM',
        'guizani.rym@test.tn',
        crypt('112233', gen_salt('bf')),
        '+21629000101',
        '12345601',
        '20003030001148336517',
        'TIREUR', 'CLIENT',
        true, true
    ),

    -- ── CHERCOUHI HICHEM (ChequeT — BIAT Ariana) ─────────────────────────
    (
        'CHERCOUHI HICHEM',
        'chercouhi.hichem@test.tn',
        crypt('112233', gen_salt('bf')),
        '+21629000102',
        '23456702',
        '08010011042001092378',
        'TIREUR', 'CLIENT',
        true, true
    ),

    -- ── DOGGUI MOKHTAR (recto — BT Bekalta) ──────────────────────────────
    (
        'DOGGUI MOKHTAR',
        'doggui.mokhtar@test.tn',
        crypt('112233', gen_salt('bf')),
        '+21629000103',
        '34567803',
        '05207000077307812272',
        'TIREUR', 'CLIENT',
        true, true
    )

ON CONFLICT (email) DO UPDATE SET
    rib          = EXCLUDED.rib,
    full_name    = EXCLUDED.full_name,
    phone        = EXCLUDED.phone,
    is_active    = true,
    is_verified  = true;


-- =============================================================================
--  USERS BÉNÉFICIAIRES
--  Comptes mobiles qui vont déposer les chèques via l'app.
--  Login mobile : téléphone + PIN 112233
-- =============================================================================

INSERT INTO users (
    full_name, email, password_hash, phone, cin_number,
    role, user_type, is_active, is_verified
)
VALUES
    -- Bénéficiaire de chequeR (R. Voyages reçoit 200 DT de GUIZANI RYM)
    (
        'R VOYAGES',
        'r.voyages@test.tn',
        crypt('112233', gen_salt('bf')),
        '+21629000201',
        '45678904',
        'BENEFICIAIRE', 'CLIENT',
        true, true
    ),

    -- Bénéficiaire de ChequeT (Ryan Guizani reçoit 700 DT de CHERCOUHI HICHEM)
    (
        'RYAN GUIZANI',
        'ryan.guizani@test.tn',
        crypt('112233', gen_salt('bf')),
        '+21629000202',
        '56789005',
        'BENEFICIAIRE', 'CLIENT',
        true, true
    ),

    -- Bénéficiaire du chèque recto (BEKALTA)
    (
        'BEKALTA TEST',
        'bekalta.test@test.tn',
        crypt('112233', gen_salt('bf')),
        '+21629000203',
        '67890106',
        'BENEFICIAIRE', 'CLIENT',
        true, true
    )

ON CONFLICT (email) DO UPDATE SET
    full_name   = EXCLUDED.full_name,
    phone       = EXCLUDED.phone,
    is_active   = true,
    is_verified = true;


-- =============================================================================
--  VÉRIFICATION
-- =============================================================================

\echo ''
\echo '════════════════════════════════════════════════════'
\echo ' TIREURS insérés (findUserIdByRib doit les trouver)'
\echo '════════════════════════════════════════════════════'
SELECT
    u.id,
    u.full_name,
    u.phone,
    u.rib,
    u.role,
    ba.nom_titulaire AS ba_nom,
    ba.rib           AS ba_rib
FROM users u
LEFT JOIN bank_accounts ba ON ba.rib = u.rib
WHERE u.rib IN (
    '20003030001148336517',
    '08010011042001092378',
    '05207000077307812272'
)
ORDER BY u.full_name;

\echo ''
\echo '════════════════════════════════════════════════════'
\echo ' BÉNÉFICIAIRES insérés'
\echo '════════════════════════════════════════════════════'
SELECT id, full_name, phone, role
FROM users
WHERE email IN (
    'r.voyages@test.tn',
    'ryan.guizani@test.tn',
    'bekalta.test@test.tn'
)
ORDER BY full_name;

\echo ''
\echo '════════════════════════════════════════════════════'
\echo ' BANK ACCOUNTS insérés'
\echo '════════════════════════════════════════════════════'
SELECT rib, code_banque, code_agence, num_compte, cle_rib, telephone, nom_titulaire
FROM bank_accounts
WHERE rib IN (
    '20003030001148336517',
    '08010011042001092378',
    '05207000077307812272'
)
ORDER BY nom_titulaire;
