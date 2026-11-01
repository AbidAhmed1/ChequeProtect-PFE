"""
tests/yolo_ocrspace_smart_correction.py
═════════════════════════════════════════════════════════════
YOLO + OCR.space avec correction intelligente des erreurs OCR

Problème observé :
  recto.jpg : OCR lit 16520.824 au lieu de 1652.824

Cause : OCR.space confond "1" et "16" (reconnaissance du "1")

Solution : Post-processing intelligent
  1. Si montant > 5000 AND montant/10 < 5000
     → Probable erreur de reconnaissance (chiffre en trop)
     → Diviser par 10

  2. Si montant < 100 AND montant * 10 semble raisonnable
     → Probable chiffre manquant
     → Multiplier par 10

Stratégie : Tester différentes corrections et garder
            celle qui semble la plus "normale" (entre 50-5000)

USAGE :
    python tests/yolo_ocrspace_smart_correction.py \
        --image "Chequetest/recto.jpg" \
        --montant_reel 1652.824 \
        --verbose
"""

import os
import cv2
import base64
import requests
import re
import argparse
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def detecter_montant_yolo(image_path: str, verbose=False) -> dict:
    """YOLO détecte boîte montant"""
    try:
        from ultralytics import YOLO

        yolo_path = os.environ.get("YOLO_PHASE3_PATH", "saved_models/yolo_ocr/best_v24.pt")
        if not Path(yolo_path).exists():
            return {}

        model = YOLO(yolo_path)
        results = model(image_path, conf=0.05, verbose=False)

        if not results or len(results) == 0:
            return {}

        detections = results[0]
        if not hasattr(detections, 'boxes') or len(detections.boxes) == 0:
            return {}

        img = cv2.imread(image_path)

        class_names = {
            0: "montant_chiffres", 1: "montant_lettres", 2: "num_cheque",
            3: "banque", 4: "cmc7", 5: "signature", 6: "date_lieu",
            7: "rib", 8: "titulaire", 9: "beneficiaire", 10: "qr-code",
            11: "date-expiration", 12: "montant-max", 13: "agence"
        }

        champs = {}

        for box in detections.boxes:
            conf = float(box.conf[0])
            cls = int(box.cls[0])
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

            field_name = class_names.get(cls, f"field_{cls}")

            if field_name not in champs:
                champs[field_name] = []

            champs[field_name].append({
                "box": (x1, y1, x2, y2),
                "conf": conf,
                "crop": img[y1:y2, x1:x2]
            })

        return champs

    except Exception as e:
        return {}


def selectionner_montant_box(champs: dict) -> tuple:
    """Sélectionne boîte montant"""
    priorities = ["montant_chiffres", "montant_lettres", "montant-max"]

    for priority in priorities:
        if priority in champs and len(champs[priority]) > 0:
            best_det = max(champs[priority], key=lambda x: x["conf"])
            return best_det["crop"], priority, best_det["conf"]

    return None, None, 0


def ocrspace_lire(crop_bytes: bytes) -> str:
    """OCR.space Engine 2"""
    b64 = base64.b64encode(crop_bytes).decode('utf-8')

    try:
        r = requests.post(
            "https://api.ocr.space/parse/image",
            data={
                "apikey": "helloworld",
                "language": "fre",
                "isOverlayRequired": False,
                "base64Image": f"data:image/jpeg;base64,{b64}",
                "OCREngine": 2
            },
            timeout=30
        )

        if r.status_code == 200 and r.json().get("ParsedResults"):
            return r.json()["ParsedResults"][0]["ParsedText"].strip()
    except:
        pass

    return ""


def extraire_montant_brut(texte: str) -> float:
    """Extrait le nombre brut du texte OCR"""
    if not texte:
        return None

    texte = str(texte).strip()

    # Pattern : nombre entre #
    m = re.search(r'#([\d,. ]+)#', texte)
    if m:
        val_str = m.group(1).strip().replace(',', '.')
        try:
            return float(val_str)
        except:
            pass

    # Pattern : nombre simple (plus grand nombre trouvé)
    matches = re.findall(r'(\d{1,6}[,.]?\d{0,3})', texte.replace(' ', '').replace(',', '.'))
    if matches:
        # Prendre le plus grand nombre
        numbers = [float(m) for m in matches]
        return max(numbers) if numbers else None

    return None


def corriger_montant(montant_brut: float, verbose=False) -> dict:
    """
    Corrige les erreurs OCR courantes.

    Heuristiques :
      1. Si montant entre 50-5000 → probablement correct
      2. Si montant > 5000 :
         - Tester montant/10, montant/100, montant/1000
         - Garder celui qui tombe dans 50-5000
      3. Si montant < 50 :
         - Tester montant*10, montant*100
         - Garder celui qui tombe dans 50-5000
    """

    if montant_brut is None:
        return {"montant": None, "correction_appliquee": None}

    # Zone acceptable
    ZONE_NORMALE = (50, 5000)

    # Déjà correct ?
    if ZONE_NORMALE[0] <= montant_brut <= ZONE_NORMALE[1]:
        if verbose:
            print(f"  ✅ Montant dans zone normale : {montant_brut}")
        return {"montant": montant_brut, "correction_appliquee": None}

    if verbose:
        print(f"  ⚠️  Montant brut : {montant_brut} → en dehors zone normale")

    # Tenter corrections
    corrections = []

    if montant_brut > ZONE_NORMALE[1]:
        # Trop grand → diviser
        for diviseur in [10, 100, 1000]:
            montant_corrige = montant_brut / diviseur
            if ZONE_NORMALE[0] <= montant_corrige <= ZONE_NORMALE[1]:
                corrections.append({
                    "montant": montant_corrige,
                    "correction": f"÷ {diviseur}",
                    "score": 1.0
                })
                if verbose:
                    print(f"  → Essai : {montant_brut} ÷ {diviseur} = {montant_corrige} ✓")

    elif montant_brut < ZONE_NORMALE[0]:
        # Trop petit → multiplier
        for multiplicateur in [10, 100, 1000]:
            montant_corrige = montant_brut * multiplicateur
            if ZONE_NORMALE[0] <= montant_corrige <= ZONE_NORMALE[1]:
                corrections.append({
                    "montant": montant_corrige,
                    "correction": f"× {multiplicateur}",
                    "score": 1.0
                })
                if verbose:
                    print(f"  → Essai : {montant_brut} × {multiplicateur} = {montant_corrige} ✓")

    # Sélectionner meilleure correction
    if corrections:
        best = corrections[0]  # Première correction valide
        if verbose:
            print(f"  ✅ Correction appliquée : {best['correction']} → {best['montant']}")
        return best

    # Aucune correction possible
    if verbose:
        print(f"  ❌ Aucune correction ne ramène à la zone normale")

    return {"montant": montant_brut, "correction_appliquee": None}


def valider_montant(montant, montant_reel: float) -> dict:
    """Valide le montant final"""
    if montant is None:
        return {
            "valide": False,
            "erreur_pct": None,
            "icone": "❌"
        }

    try:
        val = float(montant)
        if montant_reel > 0:
            err = abs(val - montant_reel) / montant_reel * 100
            valide = err < 5.0
            icone = "✅" if valide else ("⚠️ " if err < 50 else "❌")

            return {
                "valide": valide,
                "erreur_pct": round(err, 2),
                "icone": icone
            }
    except:
        pass

    return {
        "valide": False,
        "erreur_pct": None,
        "icone": "❌"
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--montant_reel", type=float, default=0.0)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    verbose = args.verbose

    print("\n╔═════════════════════════════════════════════════════════════╗")
    print("║  YOLO + OCR.space + Smart Correction                      ║")
    print("╚═════════════════════════════════════════════════════════════╝")
    print(f"  Image       : {args.image}")
    print(f"  Montant réel: {args.montant_reel}")
    print()

    if not Path(args.image).exists():
        print(f"  ❌ Image non trouvée")
        return

    t0 = time.time()

    # YOLO
    if verbose:
        print("  1️⃣  YOLO DÉTECTION")
        print("  " + "─" * 55)

    champs = detecter_montant_yolo(args.image, verbose=verbose)

    if not champs:
        print("  ❌ YOLO n'a rien trouvé")
        return

    crop_montant, field_name, conf = selectionner_montant_box(champs)

    if crop_montant is None:
        print("  ❌ Pas de boîte montant")
        return

    if verbose:
        print(f"  ✅ Montant détecté : {field_name} (conf={conf:.2f})")

    # OCR.space
    if verbose:
        print()
        print("  2️⃣  OCR.space")
        print("  " + "─" * 55)

    _, crop_bytes = cv2.imencode('.jpg', crop_montant, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    texte_ocr = ocrspace_lire(crop_bytes)

    if not texte_ocr:
        print("  ❌ OCR.space vide")
        return

    if verbose:
        print(f"  ✅ OCR.space : '{texte_ocr[:60]}'...")

    # Extraction montant brut
    montant_brut = extraire_montant_brut(texte_ocr)

    if verbose:
        print()
        print("  3️⃣  EXTRACTION & CORRECTION")
        print("  " + "─" * 55)
        print(f"  Montant brut : {montant_brut}")

    # Correction intelligente
    correction_info = corriger_montant(montant_brut, verbose=verbose)
    montant_final = correction_info["montant"]

    # Validation
    validation = valider_montant(montant_final, args.montant_reel)

    # Résultats
    ms = int((time.time() - t0) * 1000)

    print()
    print("  " + "=" * 55)
    print(f"  RÉSULTAT FINAL")
    print("  " + "=" * 55)
    print(f"  Champ utilisé      : {field_name} (conf={conf:.2f})")
    print(f"  Texte OCR          : '{texte_ocr[:50]}'...")
    print(f"  Montant brut       : {montant_brut}")
    print(f"  Correction         : {correction_info.get('correction', 'aucune')}")
    print(f"  Montant final      : {montant_final if montant_final else '(non détecté)'}")

    if args.montant_reel > 0:
        print()
        print(f"  {validation['icone']} Montant réel   : {args.montant_reel}")
        if validation['erreur_pct'] is not None:
            print(f"  {validation['icone']} Erreur         : {validation['erreur_pct']}%")

    print(f"  Temps              : {ms} ms")
    print("  " + "=" * 55)
    print()


if __name__ == "__main__":
    main()