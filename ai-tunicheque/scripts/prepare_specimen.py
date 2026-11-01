"""
prepare_specimen.py — Préparation complète d'un spécimen de signature.

Ce script fait TOUT en une seule commande :
  1. Lit le QR du chèque → extrait le RIB automatiquement
  2. Détecte et découpe la zone signature (YOLO → fallback zone fixe)
  3. Crée la table specimens_signatures si elle n'existe pas
  4. Enrôle le spécimen (fichier local + base de données)

Usage :
    python scripts/prepare_specimen.py --recto Chequetest/chequeR.jpg

    # Avec verso pour un meilleur QR
    python scripts/prepare_specimen.py --recto Chequetest/chequeR.jpg --verso Chequetest/verso_biat.jpg

    # Forcer un RIB manuellement si le QR échoue
    python scripts/prepare_specimen.py --recto Chequetest/chequeR.jpg --rib 25048000002908196556

    # Voir les spécimens enrôlés
    python scripts/prepare_specimen.py --list
"""

import argparse
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

os.environ["TF_CPP_MIN_LOG_LEVEL"]  = "3"
os.environ["GLOG_minloglevel"]       = "3"
os.environ["FLAGS_call_stack_level"] = "0"

from dotenv import load_dotenv
load_dotenv()

import cv2
import numpy as np
from sqlalchemy import create_engine, text, inspect

DATABASE_URL      = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/cheque_db")
DB_SIGNATURES_DIR = _ROOT / "database_signatures"
SPECIMENS_DIR     = _ROOT / "specimens"
SAVED_MODELS_DIR  = _ROOT / "saved_models"


# ═══════════════════════════════════════════════════════════════
#  ÉTAPE 1 — Créer la table si elle n'existe pas
# ═══════════════════════════════════════════════════════════════

def setup_database(engine) -> bool:
    print("\n  [1/4] Vérification base de données...")
    try:
        insp   = inspect(engine)
        tables = insp.get_table_names()





        if "specimens_signatures" not in tables:
            with engine.connect() as conn:
                conn.execute(text("""
                    CREATE TABLE specimens_signatures (
                        id          SERIAL PRIMARY KEY,
                        rib         VARCHAR(20),
                        user_id     VARCHAR(100),
                        full_name   VARCHAR(200),
                        image_path  TEXT        NOT NULL,
                        is_active   BOOLEAN     DEFAULT TRUE,
                        enrolled_by VARCHAR(100) DEFAULT 'SCRIPT',
                        created_at  TIMESTAMP   DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                conn.execute(text(
                    "CREATE INDEX idx_spec_rib ON specimens_signatures (rib)"
                ))
                conn.commit()
            print("  ✅ Table specimens_signatures créée")
        else:
            with engine.connect() as conn:
                nb = conn.execute(
                    text("SELECT COUNT(*) FROM specimens_signatures")
                ).scalar()
            print(f"  ✅ Table specimens_signatures existe ({nb} spécimen(s) déjà enrôlé(s))")

        # Table configurations (seuils Phase 4)
        if "configurations" not in tables:
            with engine.connect() as conn:
                conn.execute(text("""
                    CREATE TABLE configurations (
                        cle         VARCHAR(100) PRIMARY KEY,
                        valeur      TEXT         NOT NULL,
                        type_valeur VARCHAR(20)  DEFAULT 'STRING'
                    )
                """))
                for row in [
                    ("phase4.threshold_match",  "0.80", "FLOAT"),
                    ("phase4.threshold_review", "0.50", "FLOAT"),
                ]:
                    conn.execute(text(
                        "INSERT INTO configurations (cle,valeur,type_valeur) VALUES (:k,:v,:t)"
                    ), {"k": row[0], "v": row[1], "t": row[2]})
                conn.commit()
            print("  ✅ Table configurations créée")

        return True

    except Exception as e:
        print(f"  ❌ Erreur DB : {e}")
        print(f"     → Vérifiez que la base '{DATABASE_URL.split('/')[-1]}' existe.")
        print(f"     → Créez-la avec : psql -U postgres -c \"CREATE DATABASE cheque_db;\"")
        return False


# ═══════════════════════════════════════════════════════════════
#  ÉTAPE 2 — Lire le RIB depuis le QR du chèque
# ═══════════════════════════════════════════════════════════════

def extract_rib_from_qr(recto_path: str, verso_path: str = None) -> tuple[str, str]:
    """
    Retourne (rib, nom_tireur) depuis le QR pecc.tn du chèque.
    Essaie recto puis verso si fourni.
    """
    print("\n  [2/4] Lecture QR pour extraire le RIB...")

    def try_decode_qr(image_path: str) -> tuple[str, str]:
        img = cv2.imread(image_path)
        if img is None:
            return "", ""
        detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(img)
        if not data:
            # Essai avec image agrandie (meilleure détection)
            big = cv2.resize(img, (img.shape[1]*2, img.shape[0]*2),
                             interpolation=cv2.INTER_CUBIC)
            data, _, _ = detector.detectAndDecode(big)
        return data or "", ""

    for path, label in [(recto_path, "recto"), (verso_path, "verso")]:
        if not path:
            continue
        raw, _ = try_decode_qr(path)
        if not raw:
            continue

        # Parser le QR pecc.tn — format : RIB|NUM|TITULAIRE|PLAFOND|VALIDITE|...
        rib, nom = "", ""
        parts = [p.strip() for p in raw.replace(";", "|").split("|")]
        for p in parts:
            clean = p.replace(" ", "").replace("-", "")
            if len(clean) == 20 and clean.isdigit():
                rib = clean
            elif len(p) > 5 and p.replace(" ", "").isalpha() and not rib:
                nom = p

        # Fallback : chercher un champ RIB= explicite
        import re
        m = re.search(r'RIB[=:]\s*([0-9]{20})', raw, re.IGNORECASE)
        if m:
            rib = m.group(1)
        m2 = re.search(r'(?:TITULAIRE|BENEFICIAIRE|NOM)[=:]\s*([A-Z\s]+)', raw, re.IGNORECASE)
        if m2:
            nom = m2.group(1).strip()

        if rib:
            print(f"  ✅ QR lu ({label}) → RIB : {rib}")
            if nom:
                print(f"     Tireur : {nom}")
            return rib, nom

    print("  ⚠️  QR non détecté automatiquement.")
    return "", ""


# ═══════════════════════════════════════════════════════════════
#  ÉTAPE 3 — Extraire la zone signature
# ═══════════════════════════════════════════════════════════════

def extract_signature_zone(recto_path: str, output_path: Path) -> bool:
    """
    Extrait la zone signature via YOLO (best.pt) ou zone fixe bas-droite.
    Sauvegarde dans output_path.
    """
    print("\n  [3/4] Extraction de la zone signature...")

    img = cv2.imread(recto_path)
    if img is None:
        print(f"  ❌ Image illisible : {recto_path}")
        return False

    h, w = img.shape[:2]
    region = None

    # Tentative YOLO
    yolo_path = SAVED_MODELS_DIR / "best.pt"
    if yolo_path.exists():
        try:
            from ultralytics import YOLO
            model = YOLO(str(yolo_path))
            results = model.predict(img, conf=0.20, verbose=False)
            for r in results:
                for box in r.boxes:
                    if int(box.cls[0]) == 5:  # classe 5 = signature
                        x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
                        pad_h = int((y2 - y1) * 0.05)
                        pad_w = int((x2 - x1) * 0.05)
                        region = img[
                            max(0, y1 - pad_h) : min(h, y2 + pad_h),
                            max(0, x1 - pad_w) : min(w, x2 + pad_w)
                        ]
                        print(f"  ✅ YOLO : signature détectée "
                              f"[{x1},{y1} → {x2},{y2}]")
                        break
        except Exception as e:
            print(f"  ⚠️  YOLO indisponible ({str(e)[:50]}), zone fixe utilisée")

    # Fallback : zone fixe bas-droite (standard chèques tunisiens)
    if region is None or region.size == 0:
        y1f, y2f = int(0.60 * h), int(0.85 * h)
        x1f, x2f = int(0.55 * w), int(0.98 * w)
        region = img[y1f:y2f, x1f:x2f]
        print(f"  ℹ️  Zone fixe bas-droite utilisée "
              f"[{x1f},{y1f} → {x2f},{y2f}]")

    if region is None or region.size == 0:
        print("  ❌ Impossible d'extraire la zone signature")
        return False

    # Sauvegarder en couleur (le preprocessing est fait par Phase 4 au moment de la comparaison)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), region)
    print(f"  ✅ Signature extraite → {output_path.name} "
          f"({region.shape[1]}×{region.shape[0]} px)")
    return True


# ═══════════════════════════════════════════════════════════════
#  ÉTAPE 4 — Enrôler le spécimen
# ═══════════════════════════════════════════════════════════════

def enroll(engine, rib: str, image_path: Path, nom: str = "") -> bool:
    print("\n  [4/4] Enrôlement du spécimen...")

    if not image_path.exists():
        print(f"  ❌ Fichier spécimen introuvable : {image_path}")
        return False

    # Copier dans database_signatures/{rib}.jpg (lookup local Phase 4)
    DB_SIGNATURES_DIR.mkdir(parents=True, exist_ok=True)
    dest_local = DB_SIGNATURES_DIR / f"{rib}.jpg"
    import shutil
    shutil.copy2(image_path, dest_local)
    print(f"  ✅ Copié dans database_signatures/{rib}.jpg")

    # Copier dans specimens/{rib}/ (endpoint enroll)
    spec_dir = SPECIMENS_DIR / rib
    spec_dir.mkdir(parents=True, exist_ok=True)
    import time as _t
    dest_spec = spec_dir / f"spec_{int(_t.time())}.jpg"
    shutil.copy2(image_path, dest_spec)

    # Insérer en base
    try:
        with engine.connect() as conn:
            # Désactiver les anciens spécimens pour ce RIB
            conn.execute(text(
                "UPDATE specimens_signatures SET is_active=FALSE WHERE rib=:r"
            ), {"r": rib})
            # Insérer le nouveau
            conn.execute(text("""
                INSERT INTO specimens_signatures (rib, full_name, image_path, enrolled_by)
                VALUES (:rib, :nom, :path, 'SCRIPT')
            """), {"rib": rib, "nom": nom, "path": str(dest_local.resolve())})
            conn.commit()
        print(f"  ✅ Enrôlé en base")
        print(f"     RIB      : {rib}")
        print(f"     Tireur   : {nom or '(non renseigné)'}")
        print(f"     Fichier  : {dest_local}")
        return True
    except Exception as e:
        print(f"  ⚠️  DB non accessible ({str(e)[:60]})")
        print(f"     → Fichier local OK — Phase 4 le trouvera quand même via database_signatures/")
        return False


# ═══════════════════════════════════════════════════════════════
#  Lister les spécimens enrôlés
# ═══════════════════════════════════════════════════════════════

def list_specimens(engine):
    print("\n  Spécimens enrôlés en base :")
    print("  " + "─"*60)
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT rib, full_name, COUNT(*) as nb, MAX(created_at) as last
                FROM specimens_signatures
                WHERE is_active = TRUE
                GROUP BY rib, full_name
                ORDER BY last DESC
            """)).fetchall()
        if not rows:
            print("  Aucun spécimen enrôlé.")
        else:
            for r in rows:
                print(f"  • RIB {r[0]}  |  {r[1] or '—':<30}  |  {str(r[3])[:19]}")
    except Exception as e:
        print(f"  ❌ {e}")

    print("\n  Fichiers dans database_signatures/ :")
    if DB_SIGNATURES_DIR.exists():
        files = list(DB_SIGNATURES_DIR.glob("*.jp*g")) + list(DB_SIGNATURES_DIR.glob("*.png"))
        if files:
            for f in files:
                print(f"  • {f.name}")
        else:
            print("  (vide)")
    else:
        print("  (dossier absent)")


# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Prépare et enrôle un spécimen de signature pour Phase 4"
    )
    parser.add_argument("--recto", help="Image recto du chèque")
    parser.add_argument("--verso", help="Image verso (optionnel, aide le QR)")
    parser.add_argument("--rib",   help="RIB forcé si QR illisible (20 chiffres)")
    parser.add_argument("--nom",   help="Nom du tireur (optionnel)")
    parser.add_argument("--list",  action="store_true", help="Lister les spécimens")
    args = parser.parse_args()

    print("\n" + "═"*60)
    print("  TuniCheque — Préparation spécimen de signature")
    print("═"*60)
    print(f"  DB  : {DATABASE_URL.split('@')[-1]}")

    engine = create_engine(DATABASE_URL)

    if args.list:
        list_specimens(engine)
        print()
        return

    if not args.recto:
        print("\n  ⚠️  Usage : python scripts/prepare_specimen.py --recto <image.jpg>")
        parser.print_help()
        return

    if not Path(args.recto).exists():
        print(f"\n  ❌ Image introuvable : {args.recto}")
        return

    # Étape 1 — DB
    db_ok = setup_database(engine)

    # Étape 2 — RIB
    rib, nom = "", args.nom or ""
    if args.rib:
        rib = "".join(c for c in args.rib if c.isdigit())
        print(f"\n  [2/4] RIB fourni manuellement : {rib}")
    else:
        rib, nom_qr = extract_rib_from_qr(args.recto, args.verso)
        if not nom:
            nom = nom_qr

    if not rib:
        print("\n  ❌ RIB introuvable — relancez avec --rib <20_chiffres>")
        print("  Astuce : récupérez le RIB dans le rapport Phase 2 (champ qr_data.rib)")
        return

    if len(rib) != 20:
        print(f"\n  ❌ RIB invalide : {rib} ({len(rib)} chiffres — attendu 20)")
        return

    # Étape 3 — Extraction signature
    specimen_path = _ROOT / "specimens" / "extracted" / f"specimen_{rib}.jpg"
    extracted = extract_signature_zone(args.recto, specimen_path)
    if not extracted:
        return

    # Étape 4 — Enrôlement
    enroll(engine, rib, specimen_path, nom)

    # Résumé final
    print("\n" + "═"*60)
    print("  ✅ Spécimen prêt. Lancez maintenant le test :")
    print(f"     python tests/full_pipeline_test.py \\")
    print(f"       --recto {args.recto} \\")
    print(f"       --verso {args.verso or 'Chequetest/verso_biat.jpg'} \\")
    print(f"       --id TEST_PHASE4")
    print("═"*60 + "\n")


if __name__ == "__main__":
    main()