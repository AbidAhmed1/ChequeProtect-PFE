"""
setup_phase4.py — Initialisation complète de Phase 4.

Ce script :
  1. Crée les dossiers nécessaires
  2. Crée la table specimens_signatures en base
  3. Insère les seuils de configuration
  4. Affiche un rapport de diagnostic

Usage :
    python scripts/setup_phase4.py
    python scripts/setup_phase4.py --diagnostic-only
"""

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text, inspect

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/cheque_db")


def create_dirs():
    dirs = [
        _ROOT / "database_signatures",
        _ROOT / "specimens",
        _ROOT / "scripts",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        print(f"  ✅ {d.relative_to(_ROOT)}/")


def run_migration(engine):
    sql = """
    CREATE TABLE IF NOT EXISTS specimens_signatures (
        id          SERIAL PRIMARY KEY,
        rib         VARCHAR(20),
        user_id     VARCHAR(100),
        full_name   VARCHAR(200),
        image_path  TEXT         NOT NULL,
        is_active   BOOLEAN      DEFAULT TRUE,
        enrolled_by VARCHAR(100) DEFAULT 'MANUAL',
        created_at  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
        updated_at  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_specimens_rib     ON specimens_signatures (rib);
    CREATE INDEX IF NOT EXISTS idx_specimens_uid     ON specimens_signatures (user_id);
    CREATE INDEX IF NOT EXISTS idx_specimens_active  ON specimens_signatures (is_active);

    CREATE TABLE IF NOT EXISTS configurations (
        cle         VARCHAR(100) PRIMARY KEY,
        valeur      TEXT         NOT NULL,
        type_valeur VARCHAR(20)  DEFAULT 'STRING',
        description TEXT,
        updated_at  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
    );
    """
    config_inserts = [
        ("phase4.threshold_match",  "0.80", "FLOAT",   "Score minimum pour MATCH automatique"),
        ("phase4.threshold_review", "0.50", "FLOAT",   "Score minimum pour REVIEW (expert)"),
        ("phase4.strict_mode",      "false","BOOLEAN",  "Mode strict : seuils +0.10/+0.05"),
        ("phase4.enabled",          "true", "BOOLEAN",  "Activer Phase 4"),
    ]
    try:
        with engine.connect() as conn:
            conn.execute(text(sql))
            for cle, val, typ, desc in config_inserts:
                conn.execute(text("""
                    INSERT INTO configurations (cle, valeur, type_valeur, description)
                    VALUES (:k, :v, :t, :d)
                    ON CONFLICT (cle) DO NOTHING
                """), {"k": cle, "v": val, "t": typ, "d": desc})
            conn.commit()
        print("  ✅ Table specimens_signatures créée")
        print("  ✅ Table configurations créée + seuils insérés")
        return True
    except Exception as e:
        print(f"  ❌ Migration échouée : {e}")
        return False


def diagnostic(engine):
    print("\n" + "─"*60)
    print("  DIAGNOSTIC PHASE 4")
    print("─"*60)

    # Dossiers
    for name, path in [
        ("database_signatures/", _ROOT / "database_signatures"),
        ("specimens/",           _ROOT / "specimens"),
        ("saved_models/",        _ROOT / "saved_models"),
    ]:
        exists = path.exists()
        count  = len(list(path.glob("*"))) if exists else 0
        icon   = "✅" if exists else "❌"
        print(f"  {icon} {name:<25} {count} fichier(s)")

    # Modèles
    for name, path in [
        ("signature_encoder.keras", _ROOT / "saved_models" / "signature_encoder.keras"),
        ("best.pt (YOLO sig.)",     _ROOT / "saved_models" / "best.pt"),
    ]:
        icon = "✅" if path.exists() else "❌"
        size = f"{path.stat().st_size // 1024} KB" if path.exists() else "absent"
        print(f"  {icon} {name:<28} {size}")

    # Base de données
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"  ✅ {'Connexion DB':<28} {DATABASE_URL.split('@')[-1]}")

        insp = inspect(engine)
        tables = insp.get_table_names()

        for t in ["specimens_signatures", "configurations"]:
            icon = "✅" if t in tables else "❌"
            count = 0
            if t in tables:
                with engine.connect() as conn:
                    count = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            print(f"  {icon} Table {t:<20} {count} ligne(s)")

    except Exception as e:
        print(f"  ❌ Connexion DB : {e}")
        print(f"     URL utilisée  : {DATABASE_URL}")

    # Résumé
    print("\n─"*60)
    sig_dir = _ROOT / "database_signatures"
    sigs = list(sig_dir.glob("*.jpg")) + list(sig_dir.glob("*.png")) if sig_dir.exists() else []
    if sigs:
        print(f"  Spécimens locaux trouvés ({len(sigs)}) :")
        for s in sigs[:5]:
            print(f"    • {s.name}")
    else:
        print("  ⚠️  Aucun spécimen local dans database_signatures/")
        print("  → Enrôler un spécimen avec :")
        print("    python scripts/enroll_specimen.py --rib <RIB_20_CHIFFRES> --image <signature.jpg>")


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--diagnostic-only", action="store_true")
    args = p.parse_args()

    print("\n" + "═"*60)
    print("  TuniCheque — Setup Phase 4 : Vérification Signature")
    print("═"*60)

    engine = create_engine(DATABASE_URL)

    if not args.diagnostic_only:
        print("\n  [1/2] Création des dossiers")
        create_dirs()

        print("\n  [2/2] Migration base de données")
        run_migration(engine)

    diagnostic(engine)
    print()


if __name__ == "__main__":
    main()