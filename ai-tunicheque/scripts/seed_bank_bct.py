"""
seed_bank_bct.py — Simulateur de base de données BCT (Banque Centrale de Tunisie)

Ce script joue le rôle d'une "boîte noire" : il simule les données bancaires
réelles que fournirait le système BCT (confidentiel) et peuple la table
bank_accounts de database_auth avec des comptes tunisiens réalistes.

Usage :
    python scripts/seed_bank_bct.py

Prérequis :
    pip install psycopg2-binary
"""

import psycopg2
import random
import uuid
from datetime import datetime

# ── Connexion PostgreSQL ──────────────────────────────────────────────────────
DB_CONFIG = {
    "host":     "localhost",
    "port":     5432,
    "dbname":   "database_auth",
    "user":     "postgres",
    "password": "kmss-a5kK",
}

# ── Banques tunisiennes (code BCT réel) ───────────────────────────────────────
BANQUES = [
    ("10", "STB"),   # Société Tunisienne de Banque
    ("11", "BNA"),   # Banque Nationale Agricole
    ("14", "BH"),    # Banque de l'Habitat
    ("20", "UIB"),   # Union Internationale de Banques
    ("25", "ATB"),   # Arab Tunisian Bank
    ("32", "Attijari"),
    ("45", "BIAT"),  # Banque Internationale Arabe de Tunisie
    ("50", "Zitouna"),
    ("60", "BTE"),   # Banque de Tunisie et des Emirats
]

# ── Données réalistes ─────────────────────────────────────────────────────────
PRENOMS = ["Mohamed", "Ahmed", "Fatma", "Sonia", "Khaled", "Imen",
           "Yassine", "Amira", "Bilel", "Rania", "Nabil", "Sarra",
           "Maher", "Leila", "Karim", "Wafa", "Tarek", "Olfa"]

NOMS    = ["Ben Ali", "Trabelsi", "Gharbi", "Mansouri", "Jebali",
           "Khelifi", "Bouzid", "Hamdi", "Sassi", "Ferjani",
           "Maaroufi", "Belhadj", "Zaied", "Oueslati", "Chebbi"]

AGENCES_PAR_BANQUE = {
    "10": ["001", "002", "015", "023", "044"],
    "11": ["001", "003", "010", "021", "033"],
    "14": ["001", "004", "012", "022", "041"],
    "20": ["001", "002", "009", "018", "030"],
    "25": ["001", "005", "011", "020", "038"],
    "32": ["001", "003", "008", "017", "029"],
    "45": ["001", "002", "007", "016", "027"],
    "50": ["001", "004", "013", "024", "042"],
    "60": ["001", "006", "014", "025", "043"],
}

ROLES   = ["TIREUR", "TIREUR", "TIREUR", "BENEFICIAIRE"]  # 75% tireurs


# ── Algorithme clé RIB BCT (Luhn mod97) ─────────────────────────────────────

def calculer_cle_rib(code_banque: str, code_agence: str, num_compte: str) -> str:
    """Calcule la clé RIB (2 derniers chiffres) selon la norme BCT."""
    base = code_banque + code_agence + num_compte
    if len(base) != 18:
        raise ValueError(f"Base RIB invalide : {len(base)} chiffres (attendu 18)")
    reste = int(base) * 100 % 97
    cle   = 97 - reste
    return str(cle).zfill(2)


def generer_rib(code_banque: str, code_agence: str) -> tuple[str, str, str, str]:
    """Génère un RIB tunisien valide (20 chiffres) avec clé correcte."""
    num_compte = str(random.randint(1000000000000, 9999999999999))  # 13 chiffres
    cle = calculer_cle_rib(code_banque, code_agence, num_compte)
    rib = code_banque + code_agence + num_compte + cle
    return rib, code_banque, code_agence, num_compte, cle


def generer_telephone() -> str:
    """Génère un numéro tunisien mobile réaliste (+216 2X/5X/9X XXXXXXX)."""
    prefixes = ["20", "21", "22", "23", "24", "25", "26", "27", "28", "29",
                "50", "51", "52", "53", "54", "55", "56", "57", "58", "59",
                "90", "91", "92", "93", "94", "95", "96", "97", "98", "99"]
    prefix = random.choice(prefixes)
    suffix = str(random.randint(100000, 999999))
    return "+216" + prefix + suffix


# ── Insertion ────────────────────────────────────────────────────────────────

def seed(nb_comptes: int = 30):
    conn = psycopg2.connect(**DB_CONFIG)
    cur  = conn.cursor()

    # Vérifier si la table est déjà remplie
    cur.execute("SELECT COUNT(*) FROM bank_accounts")
    (count,) = cur.fetchone()
    if count > 0:
        print(f"[BCT] Table bank_accounts déjà remplie ({count} comptes). Rien à faire.")
        cur.close()
        conn.close()
        return

    inseres = 0
    telephones_utilises = set()
    ribs_utilises       = set()

    for _ in range(nb_comptes):
        # Choisir une banque et une agence
        code_banque, nom_banque = random.choice(BANQUES)
        code_agence = random.choice(AGENCES_PAR_BANQUE[code_banque])

        # Générer RIB unique
        for _ in range(10):  # 10 tentatives max pour éviter les doublons
            rib, cb, ca, nc, cle = generer_rib(code_banque, code_agence)
            if rib not in ribs_utilises:
                ribs_utilises.add(rib)
                break
        else:
            continue

        # Téléphone unique
        for _ in range(10):
            tel = generer_telephone()
            if tel not in telephones_utilises:
                telephones_utilises.add(tel)
                break
        else:
            continue

        # Identité
        prenom      = random.choice(PRENOMS)
        nom         = random.choice(NOMS)
        nom_complet = f"{prenom} {nom}"
        role        = random.choice(ROLES)

        # Insertion
        cur.execute("""
            INSERT INTO bank_accounts
                (id, rib, code_banque, code_agence, num_compte, cle_rib,
                 telephone, nom_titulaire, role, active, created_at)
            VALUES
                (%s, %s, %s, %s, %s, %s,
                 %s, %s, %s, %s, %s)
            ON CONFLICT (rib) DO NOTHING
        """, (
            str(uuid.uuid4()),
            rib, cb, ca, nc, cle,
            tel, nom_complet, role,
            True, datetime.now()
        ))
        inseres += 1
        print(f"  [{nom_banque}] RIB={rib}  TEL={tel}  NOM={nom_complet}  ROLE={role}")

    conn.commit()
    cur.close()
    conn.close()
    print(f"\n[BCT] {inseres} comptes bancaires insérés dans database_auth.bank_accounts")


# ── Quelques comptes fixes pour les tests ────────────────────────────────────

def seed_comptes_test():
    """
    Insère des comptes avec des téléphones connus pour faciliter les tests.
    Ces numéros peuvent être utilisés directement dans l'appli mobile.
    """
    conn = psycopg2.connect(**DB_CONFIG)
    cur  = conn.cursor()

    comptes_test = [
        # (telephone, nom, role, banque, agence)
        ("+21620000001", "Ahmed Ben Salem",   "TIREUR",       "10", "001"),
        ("+21620000002", "Fatma Gharbi",      "BENEFICIAIRE", "45", "002"),
        ("+21620000003", "Mohamed Trabelsi",  "TIREUR",       "11", "003"),
        ("+21620000004", "Sonia Mansouri",    "BENEFICIAIRE", "25", "001"),
        ("+21620000005", "Khaled Jebali",     "TIREUR",       "32", "001"),
    ]

    for tel, nom, role, cb, ca in comptes_test:
        # Vérifier si le téléphone est déjà en base
        cur.execute("SELECT id FROM bank_accounts WHERE telephone = %s", (tel,))
        if cur.fetchone():
            print(f"  [TEST] {tel} déjà présent — ignoré")
            continue

        rib, cb2, ca2, nc, cle = generer_rib(cb, ca)

        cur.execute("""
            INSERT INTO bank_accounts
                (id, rib, code_banque, code_agence, num_compte, cle_rib,
                 telephone, nom_titulaire, role, active, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (rib) DO NOTHING
        """, (
            str(uuid.uuid4()),
            rib, cb2, ca2, nc, cle,
            tel, nom, role, True, datetime.now()
        ))
        print(f"  [TEST] RIB={rib}  TEL={tel}  NOM={nom}  ROLE={role}")

    conn.commit()
    cur.close()
    conn.close()
    print("\n[BCT] Comptes de test insérés.")


if __name__ == "__main__":
    print("=" * 60)
    print("  BCT — Simulateur Base de Données Bancaire Tunisienne")
    print("=" * 60)
    print()
    print("[1/2] Génération de 30 comptes aléatoires...")
    seed(nb_comptes=30)
    print()
    print("[2/2] Insertion des comptes de test (téléphones fixes)...")
    seed_comptes_test()
    print()
    print("Terminé. Vous pouvez maintenant tester l'inscription via RIB.")
    print()
    print("Téléphones de test :")
    print("  +21620000001  → Ahmed Ben Salem    (TIREUR)")
    print("  +21620000002  → Fatma Gharbi       (BENEFICIAIRE)")
    print("  +21620000003  → Mohamed Trabelsi   (TIREUR)")
    print("  +21620000004  → Sonia Mansouri     (BENEFICIAIRE)")
    print("  +21620000005  → Khaled Jebali      (TIREUR)")
