"""
tests/test_crop_zones.py
═════════════════════════════════════════════════════════════
Test les différentes zones de crop pour trouver la VRAIE
zone montant sur les chèques.

USAGE :
    python tests/test_crop_zones.py
"""

import os
import cv2
import base64
import requests
import re
from pathlib import Path

def extraire_montant(texte: str) -> str:
    """Extrait un nombre du texte OCR"""
    if not texte:
        return ""
    texte = str(texte).strip()
    m = re.search(r'#([\d,. ]+)#', texte)
    if m:
        texte = m.group(1).strip()
    m2 = re.search(r'(\d{1,6}[,.]?\d{0,3})', texte.replace(' ', ''))
    if m2:
        val = m2.group(1).replace(',', '.')
        try:
            return str(round(float(val), 3))
        except:
            pass
    return ""


def ocr_ocrspace(crop: bytes) -> str:
    """Appelle OCR.space sur un crop"""
    b64 = base64.b64encode(crop).decode('utf-8')
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
            return r.json()["ParsedResults"][0]["ParsedText"]
    except:
        pass
    return ""


def test_zones(image_path: str, montant_reel: float):
    """Test différentes zones de crop sur une image"""
    img = cv2.imread(image_path)
    if img is None:
        print(f"❌ Image non trouvée : {image_path}")
        return

    h, w = img.shape[:2]
    nom = Path(image_path).stem

    print(f"\n{'='*70}")
    print(f"  {nom:<25} — Montant réel: {montant_reel:<10} DT")
    print(f"{'='*70}")
    print(f"  Dimensions image: {w}x{h}")
    print()

    # Zones à tester
    zones = [
        ("Haut (0-55%)",       0.00, 0.55),
        ("Médian court (35-65%)", 0.35, 0.65),
        ("Médian long (30-70%)",  0.30, 0.70),
        ("Bas court (45-75%)",    0.45, 0.75),
        ("Bas long (40-80%)",     0.40, 0.80),
        ("Très bas (50-90%)",     0.50, 0.90),
        ("Zone entière",       0.00, 1.00),
    ]

    meilleur = None
    meilleur_err = float('inf')

    for nom_zone, y1_pct, y2_pct in zones:
        y1 = int(h * y1_pct)
        y2 = int(h * y2_pct)
        crop = img[y1:y2, :]

        # Sauvegarder le crop
        crop_jpg = cv2.imencode('.jpg', crop, [int(cv2.IMWRITE_JPEG_QUALITY), 95])[1]

        # OCR
        print(f"  ⏳ {nom_zone:<20}", end="", flush=True)
        texte = ocr_ocrspace(crop_jpg)
        montant = extraire_montant(texte)

        if montant:
            try:
                val = float(montant)
                if montant_reel > 0:
                    erreur = abs(val - montant_reel) / montant_reel * 100
                    icone = "✅" if erreur < 5.0 else ("⚠️ " if erreur < 50 else "❌")
                    print(f" {icone} {montant:<12} err={erreur:>8.1f}%  "
                          f"brut='{texte[:50]}'")

                    if erreur < meilleur_err:
                        meilleur_err = erreur
                        meilleur = (nom_zone, montant, erreur)
                else:
                    print(f"  {montant:<12} brut='{texte[:50]}'")
            except:
                print(f"  ❌ {montant:<12} (invalide)")
        else:
            print(f"  ❌ (non extrait)  brut='{texte[:50]}'")

    if meilleur and montant_reel > 0:
        zone, montant, err = meilleur
        print()
        print(f"  🏆 MEILLEUR : {zone:<20} → {montant:<12} (err={err:.1f}%)")


def main():
    print("\n╔════════════════════════════════════════════════════════════════╗")
    print("║  TEST ZONES DE CROP — IDENTIFICATION VRAIE ZONE MONTANT       ║")
    print("╚════════════════════════════════════════════════════════════════╝")

    tests = [
        ("Chequetest/chequeN.jpg", 958.500),
        ("Chequetest/chequeR.jpg", 200.000),
        ("Chequetest/recto.jpg", 1652.824),
        ("Chequetest/ChequeT.jpg", 700.000),
    ]

    for img_path, montant_reel in tests:
        if Path(img_path).exists():
            test_zones(img_path, montant_reel)
        else:
            print(f"\n⚠️  {img_path} non trouvé")

    print("\n" + "="*70)
    print("  RECOMMANDATION : Utiliser la zone MEILLEUR trouvée pour tous")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()