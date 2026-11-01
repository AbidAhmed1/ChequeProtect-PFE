"""
scripts/generate_cheques.py
============================
Generateur de cheques synthetiques avec resultats IA simules.

Genere 200 cheques avec distribution realiste :
  60% APPROVED
  15% REJECTED
  15% PENDING_REVIEW
  10% PENDING

Execution :
  cd D:\\projet-pfe\\ai-tunicheque
  python scripts/generate_cheques.py
"""

import os
import sys
import uuid
import random
import json
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from faker import Faker
import psycopg2
from dotenv import load_dotenv

load_dotenv()

fake = Faker("fr_FR")
Faker.seed(123)

conn = psycopg2.connect(os.getenv(
    "DATABASE_URL",
    "postgresql://cheque_admin:ChequeAdmin2025!@localhost/cheque_db"
))
cur = conn.cursor()

with open("scripts/ids_generated.json") as f:
    ids = json.load(f)

CODES_BANQUE = ["10","08","03","07","11","14","21","25","32","40"]

STATUTS = [
    ("APPROVED",                          60),
    ("REJECTED_FAKE_DOCUMENT",             5),
    ("REJECTED_SIGNATURE",                 5),
    ("REJECTED_CHEQUE_PERIME",             3),
    ("REJECTED_RIB_INVALIDE",              2),
    ("REJECTED_COMPLIANCE",                2),
    ("PENDING_REVIEW_IDENTIFICATION",      5),
    ("PENDING_REVIEW_INCOHERENCE_MONTANT", 5),
    ("PENDING_REVIEW_AGENT",               3),
    ("PENDING",                           10),
]
STATUT_LABELS = [s[0] for s in STATUTS]
STATUT_POIDS  = [s[1] for s in STATUTS]


def generer_qr_data(rib, montant, code_banque, date_em, num_cheque):
    return {
        "n":  num_cheque,
        "m":  montant,
        "r":  rib,
        "b":  code_banque,
        "de": date_em.strftime("%Y%m%d"),
        "dc": (date_em + timedelta(days=365)).strftime("%Y%m%d"),
    }


def generer_scores_ia(statut):
    if statut == "APPROVED":
        return {
            "p1_score": round(random.uniform(0.76, 0.98), 4),
            "p1_decision": "VALID_CHEQUE",
            "p2_score": round(random.uniform(0.80, 1.00), 4),
            "p2_passed": True,
            "sig_score": round(random.uniform(0.61, 0.95), 4),
            "sig_match": True,
        }
    elif "REJECTED_FAKE" in statut:
        return {
            "p1_score": round(random.uniform(0.05, 0.44), 4),
            "p1_decision": "REJECTED_FAKE",
            "p2_score": None, "p2_passed": None,
            "sig_score": None, "sig_match": None,
        }
    elif "REJECTED_SIGNATURE" in statut:
        return {
            "p1_score": round(random.uniform(0.76, 0.98), 4),
            "p1_decision": "VALID_CHEQUE",
            "p2_score": round(random.uniform(0.80, 1.00), 4),
            "p2_passed": True,
            "sig_score": round(random.uniform(0.10, 0.59), 4),
            "sig_match": False,
        }
    elif any(x in statut for x in ["PERIME","RIB","COMPLIANCE"]):
        return {
            "p1_score": round(random.uniform(0.76, 0.98), 4),
            "p1_decision": "VALID_CHEQUE",
            "p2_score": round(random.uniform(0.20, 0.65), 4),
            "p2_passed": False,
            "sig_score": None, "sig_match": None,
        }
    else:
        return {
            "p1_score": round(random.uniform(0.46, 0.74), 4),
            "p1_decision": "PENDING_REVIEW",
            "p2_score": round(random.uniform(0.60, 1.00), 4),
            "p2_passed": True,
            "sig_score": round(random.uniform(0.50, 0.75), 4),
            "sig_match": None,
        }


print("Generation de 200 cheques...")
cheque_ids = []

for i in range(200):
    cheque_id   = str(uuid.uuid4())
    tireur_id   = random.choice(ids["tireur_ids"])
    benef_id    = random.choice(ids["benef_ids"])
    agent_id    = random.choice(ids["agent_ids"])
    code_banque = random.choice(CODES_BANQUE)
    statut      = random.choices(STATUT_LABELS, weights=STATUT_POIDS, k=1)[0]

    montant     = round(random.uniform(50, 50000), 3)
    days_ago    = random.randint(0, 300)
    date_em     = date.today() - timedelta(days=days_ago)
    num_cheque  = "CHQ{}".format(random.randint(100000, 999999))

    cur.execute("SELECT rib, code_banque FROM users WHERE id=%s", (tireur_id,))
    row_tireur = cur.fetchone()
    rib        = row_tireur[0] if row_tireur else None
    cb_tireur  = row_tireur[1] if row_tireur else code_banque

    qr_data = generer_qr_data(rib, montant, cb_tireur or code_banque,
                              date_em, num_cheque)
    scores  = generer_scores_ia(statut)

    cur.execute("""
                INSERT INTO cheques (
                    id, tireur_id, beneficiaire_id, agent_id, code_banque, statut,
                    image_recto_path, image_verso_path,
                    qr_raw_data, qr_parsed, montant_chiffres, montant_lettres,
                    beneficiaire_nom, date_emission, numero_cheque,
                    phase1_score, phase1_decision, phase1_at,
                    phase2_score, phase2_passed,
                    signature_score, signature_match, final_decision, decision_at
                ) VALUES (
                             %s,%s,%s,%s,%s,%s,
                             %s,%s,
                             %s,%s::jsonb,%s,%s,
                             %s,%s,%s,
                             %s,%s,NOW()-%s*INTERVAL'1 hour',
                             %s,%s,
                             %s,%s,%s,NOW()-%s*INTERVAL'30 minutes'
                         )
                """, (
                    cheque_id, tireur_id, benef_id, agent_id, code_banque, statut,
                    "uploads/recto_{}.jpg".format(cheque_id),
                    "uploads/verso_{}.jpg".format(cheque_id),
                    json.dumps(qr_data), json.dumps(qr_data), montant,
                    "{} dinars".format(int(montant)),
                    fake.name(), date_em, num_cheque,
                    scores["p1_score"], scores["p1_decision"], random.randint(1, 72),
                    scores["p2_score"], scores["p2_passed"],
                    scores["sig_score"], scores["sig_match"], statut, random.randint(1, 48),
                ))

    # ai_results pour chaque phase executee
    phases = []
    if scores["p1_score"] is not None:
        phases.append((
            "identification", scores["p1_score"],
            scores["p1_decision"] != "REJECTED_FAKE",
            json.dumps({"decision": scores["p1_decision"],
                        "confidence_real": scores["p1_score"],
                        "confidence_fake": round(1-scores["p1_score"], 4)}),
            random.randint(200, 500), "EfficientNetV2S-v1.0"
        ))
    if scores["p2_score"] is not None:
        phases.append((
            "compliance", scores["p2_score"], scores["p2_passed"],
            json.dumps({"qr_present": True,
                        "checks": {"rib_valide": True, "date_valide": True,
                                   "montant_valide": True},
                        "violations": []}),
            random.randint(80, 250), "pyzbar-0.1.10"
        ))
    if scores["sig_score"] is not None:
        phases.append((
            "signature", scores["sig_score"], scores["sig_match"],
            json.dumps({"best_score": scores["sig_score"],
                        "result": "MATCH" if scores["sig_match"] else "NO_MATCH",
                        "specimens_count": random.randint(2, 5)}),
            random.randint(50, 200), "Siamese-SigNet-v1.0"
        ))

    for phase_data in phases:
        cur.execute("""
                    INSERT INTO ai_results
                        (cheque_id,phase,score,passed,details,duration_ms,model_version)
                    VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s)
                        ON CONFLICT (cheque_id, phase) DO NOTHING
                    """, (cheque_id,) + phase_data)

    cheque_ids.append(cheque_id)
    if (i+1) % 50 == 0:
        print("  {}/200 cheques generes...".format(i+1))

conn.commit()

with open("scripts/ids_generated.json") as f:
    all_ids = json.load(f)
all_ids["cheque_ids"] = cheque_ids
with open("scripts/ids_generated.json", "w") as f:
    json.dump(all_ids, f, indent=2)

cur.close()
conn.close()
print("Termine ! 200 cheques avec ai_results inseres.")