"""
enroll_specimen.py — Enrôlement de spécimen de signature en base de données.

Usage :
    # Enrôler un spécimen pour le RIB de démonstration
    python scripts/enroll_specimen.py --rib 25048000002908196556 --image path/to/signature.jpg

    # Enrôler avec nom du titulaire
    python scripts/enroll_specimen.py \
        --rib 25048000002908196556 \
        --image Chequetest/verso_biat.jpg \
        --name "EXCELLIA SOLUTIONS"

    # Enrôler depuis un dossier (plusieurs spécimens)
    python scripts/enroll_specimen.py --rib 25048000002908196556 --folder path/to/signatures/

    # Lister tous les spécimens enrôlés
    python scripts/enroll_specimen.py --list

    # Tester Phase 4 avec un RIB spécifique
    python scripts/enroll_specimen.py --test-rib 25048000002908196556
"""

import argparse
import os
import shutil
import sys
from pathlib import Path
from datetime import datetime

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/cheque_db")
SPECIMENS_DIR = _ROOT / "specimens"
DB_SIGNATURES_DIR = _ROOT / "database_signatures"


def get_engine():
    return create_engine(DATABASE_URL)


def ensure_dirs():
    SPECIMENS_DIR.mkdir(parents=True, exist_ok=True)
    DB_SIGNATURES_DIR.mkdir(parents=True, exist_ok=True)


def enroll_single(engine, rib: str, image_path: str, name: str = None,
                  user_id: str = None, enrolled_by: str = "MANUAL") -> bool:
    rib_clean = "".join(c for c in rib if c.isdigit())
    if len(rib_clean) != 20:
        print(f"  ⚠️  RIB invalide : {rib} (doit contenir 20 chiffres, trouvé {len(rib_clean)})")
        return False

    src = Path(image_path)
    if not src.exists():
        print(f"  ❌ Image introuvable : {image_path}")
        return False

    # Copier dans database_signatures/ (nom = RIB.ext)
    dest_db = DB_SIGNATURES_DIR / f"{rib_clean}{src.suffix.lower()}"
    shutil.copy2(src, dest_db)

    # Copier dans specimens/{rib}/ pour l'endpoint enroll
    spec_dir = SPECIMENS_DIR / rib_clean
    spec_dir.mkdir(parents=True, exist_ok=True)
    ts = int(datetime.now().timestamp())
    dest_spec = spec_dir / f"spec_{ts}{src.suffix.lower()}"
    shutil.copy2(src, dest_spec)

    # Insérer en base
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO specimens_signatures (rib, user_id, full_name, image_path, enrolled_by)
                VALUES (:rib, :user_id, :name, :path, :by)
            """), {
                "rib":     rib_clean,
                "user_id": user_id,
                "name":    name or "",
                "path":    str(dest_db.resolve()),
                "by":      enrolled_by,
            })
            conn.commit()
        print(f"  ✅ Spécimen enrôlé")
        print(f"     RIB      : {rib_clean}")
        print(f"     Titulaire: {name or '(non renseigné)'}")
        print(f"     Fichier  : {dest_db.name}")
        print(f"     DB path  : {dest_db.resolve()}")
        return True
    except Exception as e:
        print(f"  ❌ Erreur DB : {e}")
        print(f"  ℹ️  Fichier copié quand même dans database_signatures/ — Phase 4 le trouvera via recherche locale.")
        return False


def enroll_folder(engine, rib: str, folder: str, name: str = None) -> int:
    folder_path = Path(folder)
    if not folder_path.exists():
        print(f"  ❌ Dossier introuvable : {folder}")
        return 0
    images = [f for f in folder_path.iterdir()
              if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg", ".png")]
    if not images:
        print(f"  ⚠️  Aucune image trouvée dans {folder}")
        return 0
    count = 0
    for img in images:
        print(f"  Enrôlement de {img.name}...")
        if enroll_single(engine, rib, str(img), name):
            count += 1
    return count


def list_specimens(engine):
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
            print("  Aucun spécimen enrôlé en base.")
            return
        print(f"\n  {'RIB':<22} {'Titulaire':<30} {'Nb':<5} {'Dernier'}")
        print("  " + "-"*75)
        for r in rows:
            print(f"  {r[0]:<22} {(r[1] or '—'):<30} {r[2]:<5} {str(r[3])[:19]}")
    except Exception as e:
        print(f"  ❌ Erreur : {e}")
        print("  ℹ️  La table specimens_signatures n'existe peut-être pas encore.")
        print("  → Exécutez d'abord : psql -U postgres -d cheque_db -f scripts/create_specimens_table.sql")


def test_phase4(rib: str):
    """Vérifie que Phase 4 trouve bien les spécimens pour ce RIB."""
    import importlib.util
    rib_clean = "".join(c for c in rib if c.isdigit())

    print(f"\n  Test de récupération spécimens pour RIB : {rib_clean}")

    # Vérification locale
    db_sigs = list(DB_SIGNATURES_DIR.glob(f"{rib_clean}*"))
    if db_sigs:
        print(f"  ✅ database_signatures/ : {[f.name for f in db_sigs]}")
    else:
        print(f"  ❌ database_signatures/ : aucun fichier trouvé")

    # Vérification specimens/
    spec_dir = SPECIMENS_DIR / rib_clean
    if spec_dir.exists():
        specs = list(spec_dir.glob("*.jp*g")) + list(spec_dir.glob("*.png"))
        print(f"  ✅ specimens/{rib_clean}/ : {len(specs)} fichier(s)")
    else:
        print(f"  ❌ specimens/{rib_clean}/ : dossier absent")

    # Vérification DB
    try:
        engine = get_engine()
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT image_path FROM specimens_signatures WHERE rib=:r AND is_active=TRUE"
            ), {"r": rib_clean}).fetchall()
        if rows:
            print(f"  ✅ DB specimens_signatures : {len(rows)} enregistrement(s)")
            for r in rows:
                ok = "✅" if Path(r[0]).exists() else "❌ fichier manquant"
                print(f"     {ok} {r[0]}")
        else:
            print(f"  ❌ DB specimens_signatures : aucun enregistrement pour ce RIB")
    except Exception as e:
        print(f"  ❌ DB : {e}")


def main():
    parser = argparse.ArgumentParser(description="Enrôlement de spécimens de signature")
    parser.add_argument("--rib",     help="RIB du titulaire (20 chiffres)")
    parser.add_argument("--image",   help="Image de signature à enrôler")
    parser.add_argument("--folder",  help="Dossier contenant plusieurs signatures")
    parser.add_argument("--name",    help="Nom du titulaire", default=None)
    parser.add_argument("--user-id", help="UUID du titulaire (optionnel)", default=None)
    parser.add_argument("--list",    action="store_true", help="Lister les spécimens enrôlés")
    parser.add_argument("--test-rib",help="Tester la récupération pour un RIB")
    args = parser.parse_args()

    print("\n" + "═"*60)
    print("  TuniCheque — Gestionnaire de spécimens de signature")
    print("═"*60)

    ensure_dirs()
    print(f"  DB             : {DATABASE_URL.split('@')[-1]}")
    print(f"  database_sigs/ : {DB_SIGNATURES_DIR}")
    print(f"  specimens/     : {SPECIMENS_DIR}")

    if args.list:
        engine = get_engine()
        list_specimens(engine)

    elif args.test_rib:
        test_phase4(args.test_rib)

    elif args.rib and args.folder:
        engine = get_engine()
        count = enroll_folder(engine, args.rib, args.folder, args.name)
        print(f"\n  {count} spécimen(s) enrôlé(s).")

    elif args.rib and args.image:
        engine = get_engine()
        enroll_single(engine, args.rib, args.image, args.name, args.user_id)

    else:
        print("\n  Usage :")
        print("    python scripts/enroll_specimen.py --rib 25048000002908196556 --image sig.jpg")
        print("    python scripts/enroll_specimen.py --list")
        print("    python scripts/enroll_specimen.py --test-rib 25048000002908196556")
        parser.print_help()

    print()


if __name__ == "__main__":
    main()