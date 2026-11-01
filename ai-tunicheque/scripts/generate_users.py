"""
scripts/generate_users.py
==========================
Generateur d utilisateurs synthetiques pour TuniCheque.

Genere :
  - 3 ADMIN
  - 10 AGENT (un par banque)
  - 50 TIREUR (clients qui emettent des cheques)
  - 20 BENEFICIAIRE (clients qui recoivent des cheques)

Execution :
  cd D:\\projet-pfe\\ai-tunicheque
  python scripts/generate_users.py
"""

import os
import sys
import hashlib
import uuid
import random
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from faker import Faker
import psycopg2
from dotenv import load_dotenv

load_dotenv()

fake = Faker("fr_FR")
Faker.seed(42)

conn = psycopg2.connect(os.getenv(
    "DATABASE_URL",
    "postgresql://cheque_admin:ChequeAdmin2025!@localhost/cheque_db"
))
cur = conn.cursor()

CODES_BANQUE = ["10","08","03","07","11","14","21","25","32","40"]


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def generer_rib(code_banque: str) -> str:
    agence  = str(random.randint(1, 999)).zfill(3)
    compte  = str(random.randint(1, 9999999999999)).zfill(13)
    base_18 = code_banque + agence + compte
    cle     = 97 - (int(base_18) % 97)
    if cle == 0:
        cle = 97
    return base_18 + str(cle).zfill(2)


def generer_cin() -> str:
    lettre   = random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    chiffres = str(random.randint(1000000, 9999999))
    return lettre + chiffres


def inserer_user(role: str, code_banque: str = None) -> str:
    user_id  = str(uuid.uuid4())
    prenom   = fake.first_name()
    nom      = fake.last_name()
    suffix   = str(random.randint(100, 999))
    username = (prenom + "." + nom + suffix).lower().replace(" ", "_")[:90]
    email    = username + ("@tunicheque.tn" if role in ("AGENT","ADMIN")
                           else "@mail.tn")
    rib      = generer_rib(code_banque) if code_banque else None

    cur.execute("""
                INSERT INTO users
                (id, username, email, password_hash, role,
                 full_name, cin, rib, code_banque, is_active)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE)
                    ON CONFLICT (username) DO NOTHING
                """, (
                    user_id, username, email,
                    hash_password("Password@2025"),
                    role,
                    "{} {}".format(prenom, nom),
                    generer_cin(),
                    rib,
                    code_banque,
                ))
    return user_id


print("Generation des utilisateurs...")

admin_ids = [inserer_user("ADMIN") for _ in range(3)]
print("  {} admins crees".format(len(admin_ids)))

agent_ids = [inserer_user("AGENT", code) for code in CODES_BANQUE]
print("  {} agents crees".format(len(agent_ids)))

tireur_ids = [inserer_user("TIREUR", random.choice(CODES_BANQUE))
              for _ in range(50)]
print("  {} tireurs crees".format(len(tireur_ids)))

benef_ids = [inserer_user("BENEFICIAIRE", random.choice(CODES_BANQUE))
             for _ in range(20)]
print("  {} beneficiaires crees".format(len(benef_ids)))

conn.commit()

os.makedirs("scripts", exist_ok=True)
with open("scripts/ids_generated.json", "w") as f:
    json.dump({
        "admin_ids":  admin_ids,
        "agent_ids":  agent_ids,
        "tireur_ids": tireur_ids,
        "benef_ids":  benef_ids,
    }, f, indent=2)

cur.close()
conn.close()
print("Termine ! IDs sauvegardes dans scripts/ids_generated.json")