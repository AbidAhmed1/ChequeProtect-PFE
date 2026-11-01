"""
tests/full_pipeline_test.py — Client de test du pipeline TuniCheque

Utilise le même formatter que main.py (app/utils/report_formatter.py)
→ Affichage identique dans le serveur et dans les tests.

Usage :
    python tests/full_pipeline_test.py \
        --recto Chequetest/recto.jpg \
        --verso Chequetest/verso_biat.jpg \
        --id    CHEQUE_BCT_001
"""
import argparse
import json
import sys
import requests
from pathlib import Path

# Ajouter la racine du projet au path pour importer app.utils
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.utils.report_formatter import format_rapport


def main():
    ap = argparse.ArgumentParser(description="Test pipeline IA TuniCheque")
    ap.add_argument("--recto",  required=True)
    ap.add_argument("--verso",  required=True)
    ap.add_argument("--id",     required=True)
    ap.add_argument("--source", default="mobile", choices=["mobile", "scanner"])
    ap.add_argument("--url",    default="http://localhost:8083/api/ai/pipeline")
    args = ap.parse_args()

    recto, verso = Path(args.recto), Path(args.verso)
    if not recto.exists():
        print(f"❌ Fichier recto introuvable : {recto}")
        return 1
    if not verso.exists():
        print(f"❌ Fichier verso introuvable : {verso}")
        return 1

    print(f"📤 Envoi vers {args.url}")
    print(f"   recto : {recto.name} ({recto.stat().st_size // 1024} KB)")
    print(f"   verso : {verso.name} ({verso.stat().st_size // 1024} KB)")
    print(f"⚙️  Analyse du chèque {args.id} en cours...")

    try:
        with open(recto, "rb") as fr, open(verso, "rb") as fv:
            files = {
                "recto": (recto.name, fr, "image/jpeg"),
                "verso": (verso.name, fv, "image/jpeg"),
            }
            data = {"cheque_id": args.id, "source": args.source}
            resp = requests.post(args.url, files=files, data=data, timeout=180)
    except requests.ConnectionError:
        print(f"❌ Serveur injoignable sur {args.url}")
        return 2
    except Exception as e:
        print(f"❌ Erreur : {e}")
        return 2

    if resp.status_code != 200:
        print(f"❌ HTTP {resp.status_code} : {resp.text[:300]}")
        return 3

    try:
        result = resp.json()
    except json.JSONDecodeError:
        print(f"❌ Réponse non-JSON : {resp.text[:300]}")
        return 3

    # Utilise le formatter partagé (même sortie que le serveur)
    print(format_rapport(result))

    # Sauvegarde JSON pour inspection
    sortie = Path(f"rapport_{args.id}.json")
    try:
        sortie.write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"💾 JSON complet : {sortie}")
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())