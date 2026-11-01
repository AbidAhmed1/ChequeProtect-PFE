"""
tests/test_phase3.py
═══════════════════════════════════════════════════════════════════════
Test Phase 3 : Cascade OCR (YOLO + OCR.Space + PaddleOCR + VLMs)

COMMANDE :
  cd D:\projet-pfe\ai-tunicheque
  .venv\Scripts\Activate.ps1
  python tests/test_phase3.py
"""

import os, sys

# ── DOIT ÊTRE EN TOUT PREMIER ────────────────────────────────────
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"
os.environ["FLAGS_use_mkldnn"]                        = "0"
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"]   = "True"
os.environ["GLOG_minloglevel"]                        = "3"
os.environ["TF_CPP_MIN_LOG_LEVEL"]                    = "3"

import asyncio
import time
from pathlib import Path

# Ajouter le root au path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv()


# ═══════════════════════════════════════════════════════════════
# CAS DE TEST
# ═══════════════════════════════════════════════════════════════

TEST_CASES = [
    ("Chequetest/chequeN.jpg",  958.5),
    ("Chequetest/chequeR.jpg",  200.0),
    ("Chequetest/recto.jpg",    1652.824),
    ("Chequetest/ChequeT.jpg",  700.0),
]


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def print_sep(char="═", n=62):
    print("  " + char * n)

def status_icon(erreur):
    if erreur is None:       return "❌"
    if erreur < 2.0:         return "✅"
    if erreur < 10.0:        return "⚠️ "
    return "❌"


# ═══════════════════════════════════════════════════════════════
# VÉRIFICATION PRÉLIMINAIRE
# ═══════════════════════════════════════════════════════════════

def check_prerequisites():
    """Vérifier que tout est en place avant de tester"""

    print("\n  📋 VÉRIFICATION PRÉLIMINAIRE")
    print_sep("─")

    ok = True

    # Clés API
    apis = {
        "OCRSPACE_API_KEY":   ("OCR.Space",    True),
        "YOLO_MONTANT_PATH":  ("YOLO Montant", True),
        "MISTRAL_API_KEY":    ("Mistral",       False),
        "OPENROUTER_API_KEY": ("Qwen (gratuit)",False),
        "GEMINI_API_KEY":     ("Gemini (gratuit)",False),
        "ANTHROPIC_API_KEY":  ("Claude",        False),
    }

    print("  Variables .env :")
    for env_key, (nom, required) in apis.items():
        val = os.getenv(env_key, "")
        if val:
            print(f"    ✅ {nom:<25} : {val[:12]}...")
        elif required:
            print(f"    ❌ {nom:<25} : MANQUANTE (requise)")
            ok = False
        else:
            print(f"    ⚠️  {nom:<25} : absente (optionnelle)")

    # Modèle YOLO
    yolo_path = os.getenv("YOLO_MONTANT_PATH",
                          "saved_models/yolo_montant/yolo_montant_best.pt")
    print(f"\n  Modèle YOLO :")
    if Path(yolo_path).exists():
        size_mb = Path(yolo_path).stat().st_size / 1024 / 1024
        print(f"    ✅ {yolo_path} ({size_mb:.1f} MB)")
    else:
        print(f"    ⚠️  {yolo_path} non trouvé (Pipeline utilisera image complète)")

    # Images de test
    print(f"\n  Images de test :")
    found = 0
    for img_path, _ in TEST_CASES:
        if Path(img_path).exists():
            print(f"    ✅ {img_path}")
            found += 1
        else:
            print(f"    ❌ {img_path} MANQUANTE")
    if found == 0:
        print(f"    ❌ Aucune image de test trouvée !")
        ok = False

    print_sep("─")
    print(f"  {'✅ Prêt à tester' if ok else '⚠️  Vérifier les éléments manquants'}")
    print()

    return ok, found


# ═══════════════════════════════════════════════════════════════
# TEST PRINCIPAL
# ═══════════════════════════════════════════════════════════════

async def run_tests():
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  TEST PHASE 3 — CASCADE OCR (YOLO + OCR.Space + VLMs)      ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    ok, n_images = check_prerequisites()

    # Charger Phase 3
    print("  🔧 CHARGEMENT PHASE 3")
    print_sep("─")

    try:
        from app.phases.Phase3_ocr_extraction_v2 import OCRPhaseV2
    except ImportError as e:
        print(f"\n  ❌ Import impossible : {e}")
        print("     Vérifier que Phase3_ocr_extraction_v2.py est dans app/phases/")
        return

    t_init = time.time()
    phase3 = OCRPhaseV2()
    t_init_ms = (time.time() - t_init) * 1000
    print(f"\n  ✅ Phase 3 chargée en {t_init_ms:.0f}ms")

    print_sep()
    print()

    # ── Tests ────────────────────────────────────────────────────
    results = []
    total_ms = 0

    for img_path, expected in TEST_CASES:
        p = Path(img_path)
        if not p.exists():
            print(f"\n  ⚠️  Image manquante : {img_path}\n")
            continue

        print(f"\n  {'━'*62}")
        print(f"  📋 {p.name}  |  Attendu : {expected} DT")
        print(f"  {'━'*62}")

        # Lire image
        with open(img_path, "rb") as f:
            img_bytes = f.read()

        t0 = time.time()
        result = await phase3.extract(img_bytes)
        elapsed_ms = (time.time() - t0) * 1000
        total_ms += elapsed_ms

        # Extraire résultats
        ext      = result.details.get("extracted", {})
        yolo     = result.details.get("yolo", {})
        couches  = result.details.get("couches", {})
        montant  = ext.get("montant_chiffres")
        human_rv = result.details.get("human_review_required", True)

        # Calculer erreur
        if montant is not None:
            erreur = abs(montant - expected) / expected * 100
        else:
            erreur = None

        icon = status_icon(erreur)

        # Afficher résultats détaillés
        print(f"\n  YOLO zone   : {'✅ ' + str(yolo.get('confiance','0')):.0%} détectée" if yolo.get('zone_detectee') else "  YOLO zone   : ⚠️  image complète utilisée")

        print(f"\n  Couches OCR :")
        for layer_name, data in couches.items():
            l_icon = "✅" if data["montant"] is not None else "❌"
            print(f"    {l_icon} {layer_name:<22} → {str(data['montant']):<10} (score: {data['score']:.0%})")

        print(f"\n  Résultat final :")
        print(f"    {icon} Montant détecté : {montant} DT")
        print(f"       Attendu        : {expected} DT")
        if erreur is not None:
            print(f"       Erreur         : {erreur:.2f}%")
        print(f"       Score          : {result.score:.0%}")
        print(f"       Temps          : {elapsed_ms:.0f}ms")
        print(f"       Révision humaine : {'⚠️  OUI' if human_rv else '✅ NON'}")

        results.append({
            "file":     p.name,
            "expected": expected,
            "detected": montant,
            "erreur":   erreur,
            "score":    result.score,
            "ms":       elapsed_ms,
            "yolo_ok":  yolo.get("zone_detectee", False),
            "couches":  couches,
        })

    # ── Résumé final ─────────────────────────────────────────────
    print(f"\n\n  {'═'*62}")
    print(f"  📊 RÉSUMÉ FINAL")
    print(f"  {'═'*62}\n")

    exact  = sum(1 for r in results if r["erreur"] is not None and r["erreur"] < 2)
    proche = sum(1 for r in results if r["erreur"] is not None and 2 <= r["erreur"] < 10)
    echec  = len(results) - exact - proche
    total  = len(results)

    print(f"  ✅ Exact   (erreur < 2%)   : {exact}/{total}")
    print(f"  ⚠️  Proche (erreur < 10%)  : {proche}/{total}")
    print(f"  ❌ Échec   (erreur > 10%)  : {echec}/{total}")
    print(f"  ⏱️  Temps moyen            : {total_ms/max(total,1):.0f}ms")
    print()

    # Tableau résumé
    print(f"  {'Fichier':<22} {'Attendu':>10} {'Détecté':>12} {'Erreur':>8} {'Score':>7} {'YOLO':>5}")
    print(f"  {'─'*65}")

    for r in results:
        err_str = f"{r['erreur']:.1f}%" if r["erreur"] is not None else "N/A"
        det_str = str(r["detected"]) if r["detected"] is not None else "None"
        yolo_str = "✅" if r["yolo_ok"] else "⚠️"
        icon = status_icon(r["erreur"])

        print(f"  {icon} {r['file']:<20} {r['expected']:>10} {det_str:>12} "
              f"{err_str:>8} {r['score']:>6.0%} {yolo_str:>5}")

    print()

    # Couches utilisées
    print(f"  Couches OCR utilisées :")
    all_layers = set()
    for r in results:
        for l in r["couches"].keys():
            all_layers.add(l)
    for l in sorted(all_layers):
        successes = sum(1 for r in results if r["couches"].get(l, {}).get("montant") is not None)
        print(f"    - {l:<25} : {successes}/{total} succès")

    print()

    # Verdict global
    if exact == total:
        print(f"  🏆 PARFAIT ! La Phase 3 lit tous les montants correctement")
    elif exact + proche == total:
        print(f"  ✅ BON RÉSULTAT — quelques ajustements post-processing possibles")
    elif exact + proche >= total // 2:
        print(f"  ⚠️  RÉSULTAT PARTIEL — améliorer pré-traitement ou ajouter couches")
    else:
        print(f"  ❌ INSUFFISANT — vérifier YOLO + qualité images + clés API")

    print()
    print(f"  API Keys actives :")
    print(f"    OCR.Space   : ✅ {os.getenv('OCRSPACE_API_KEY','')[:10]}...")
    print(f"    Mistral     : {'✅' if os.getenv('MISTRAL_API_KEY') else '❌'}")
    print(f"    OpenRouter  : {'✅' if os.getenv('OPENROUTER_API_KEY') else '❌'}")
    print(f"    Gemini      : {'✅' if os.getenv('GEMINI_API_KEY') else '❌'}")
    print(f"    Claude      : {'✅' if os.getenv('ANTHROPIC_API_KEY') else '❌'}")
    print()


# ═══════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    asyncio.run(run_tests())