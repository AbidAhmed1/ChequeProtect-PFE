"""
tests/diagnostic_yolo_llm.py
═════════════════════════════════════════════════════════════
Script de diagnostic :
  1. Vérifie que YOLO Phase 3 existe
  2. Affiche les classes YOLO
  3. Vérifie les clés LLM Vision
  4. Teste une détection YOLO
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def check_yolo():
    """Vérifie YOLO Phase 3"""
    print("\n╔════════════════════════════════════════════════════╗")
    print("║  1️⃣  DIAGNOSTIC YOLO PHASE 3                       ║")
    print("╚════════════════════════════════════════════════════╝")

    yolo_path = os.environ.get("YOLO_PHASE3_PATH", "saved_models/yolo_ocr/best_v24.pt")
    print(f"\n  Chemin YOLO : {yolo_path}")

    if Path(yolo_path).exists():
        print(f"  ✅ Fichier existe ({Path(yolo_path).stat().st_size / 1e6:.1f} MB)")
    else:
        print(f"  ❌ Fichier NON trouvé")
        return False

    # Charger le modèle
    try:
        from ultralytics import YOLO
        print("\n  ⏳ Chargement du modèle...")
        model = YOLO(yolo_path)
        print(f"  ✅ Modèle chargé")

        # Afficher les classes
        print(f"\n  Classes détectées par YOLO Phase 3 :")
        print("  " + "─" * 46)
        for class_id, class_name in model.names.items():
            print(f"    {class_id:2d} → {class_name}")
        print("  " + "─" * 46)

        # Chercher montant
        has_montant = any("montant" in name.lower() for name in model.names.values())
        if has_montant:
            print(f"  ✅ Classe 'montant' trouvée")
            return True
        else:
            print(f"  ⚠️  Pas de classe 'montant' trouvée")
            print(f"     Adapter le script pour utiliser une classe existante")
            return True  # Modèle OK, juste besoin d'adapter les classes

    except ImportError:
        print(f"  ❌ pip install ultralytics")
        return False
    except Exception as e:
        print(f"  ❌ Erreur : {e}")
        return False


def check_llm_keys():
    """Vérifie les clés LLM Vision"""
    print("\n╔════════════════════════════════════════════════════╗")
    print("║  2️⃣  DIAGNOSTIC CLÉS LLM VISION                   ║")
    print("╚════════════════════════════════════════════════════╝")

    keys = {
        "GEMINI_API_KEY": "Google Gemini (GRATUIT 1500/jour)",
        "ANTHROPIC_API_KEY": "Claude (payant, $5 gratuit)",
        "OPENROUTER_API_KEY": "OpenRouter (gratuit)",
    }

    found_keys = 0
    for env_var, description in keys.items():
        key = os.environ.get(env_var)
        if key:
            masked = key[:10] + "..." + key[-10:]
            print(f"  ✅ {env_var:<25} → {masked}")
            found_keys += 1
        else:
            print(f"  ❌ {env_var:<25} → manquante")
            print(f"     Description : {description}")

    if found_keys == 0:
        print("\n  🚨 Aucune clé LLM trouvée !")
        print("     Ajouter au moins l'une de ces clés dans .env")
        return False

    print(f"\n  ✅ {found_keys} clé(s) trouvée(s)")
    return found_keys > 0


def test_yolo_detection():
    """Teste une détection YOLO sur une image"""
    print("\n╔════════════════════════════════════════════════════╗")
    print("║  3️⃣  TEST DÉTECTION YOLO                           ║")
    print("╚════════════════════════════════════════════════════╝")

    # Chercher une image test
    test_images = [
        "Chequetest/chequeN.jpg",
        "Chequetest/chequeR.jpg",
        "Chequetest/recto.jpg",
    ]

    test_image = None
    for img in test_images:
        if Path(img).exists():
            test_image = img
            break

    if not test_image:
        print(f"\n  ❌ Aucune image test trouvée")
        print(f"     Cherché : {', '.join(test_images)}")
        return False

    print(f"\n  Image test : {test_image}")

    try:
        from ultralytics import YOLO
        yolo_path = os.environ.get("YOLO_PHASE3_PATH", "saved_models/yolo_ocr/best_v24.pt")
        model = YOLO(yolo_path)

        print(f"  ⏳ Détection en cours...")
        results = model(test_image, conf=0.15, verbose=False)

        if not results or len(results) == 0:
            print(f"  ❌ Aucune détection")
            return False

        detections = results[0]
        if not hasattr(detections, 'boxes') or len(detections.boxes) == 0:
            print(f"  ❌ Aucune boîte détectée")
            return False

        print(f"  ✅ {len(detections.boxes)} boîte(s) détectée(s)")
        print(f"\n  Détections :")
        for i, box in enumerate(detections.boxes):
            cls = int(box.cls[0])
            conf = float(box.conf[0])
            class_name = model.names.get(cls, f"class_{cls}")
            print(f"    {i+1}. {class_name:<20} conf={conf:.2f}")

        return True

    except Exception as e:
        print(f"  ❌ Erreur : {e}")
        return False


def main():
    print("\n" + "="*60)
    print("  DIAGNOSTIC COMPLET — YOLO + LLM VISION")
    print("="*60)

    yolo_ok = check_yolo()
    llm_ok = check_llm_keys()
    test_ok = False

    if yolo_ok:
        test_ok = test_yolo_detection()

    # Résumé final
    print("\n" + "="*60)
    print("  RÉSUMÉ")
    print("="*60)
    print(f"  ✅ YOLO Phase 3           : {'OK' if yolo_ok else 'MANQUANT'}")
    print(f"  ✅ Clés LLM Vision        : {'OK' if llm_ok else 'MANQUANT'}")
    print(f"  ✅ Détection YOLO         : {'OK' if test_ok else 'ERREUR'}")
    print()

    if yolo_ok and llm_ok:
        print("  ✅ PRÊT ! Lance :")
        print("     python tests/yolo_llm_montant_extraction.py --image Chequetest/chequeN.jpg")
    else:
        print("  ❌ Configuration incomplète")
        if not yolo_ok:
            print("     → Vérifier YOLO Phase 3 dans saved_models/")
        if not llm_ok:
            print("     → Ajouter une clé LLM dans .env")

    print("="*60 + "\n")


if __name__ == "__main__":
    main()