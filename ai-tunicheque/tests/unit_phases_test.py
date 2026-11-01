import os
import sys
import asyncio
import argparse

# Ajouter le dossier actuel au chemin de recherche Python
sys.path.append(os.getcwd())

# FORCE PURE-PYTHON PROTOBUF TO RESOLVE TF / PADDLE CONFLICT
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

# --- Import des Phases ---
from app.phases.phase1_identification import ChequeIdentificationPhase, ImageSource
from app.phases.phase2_compliance import TuniChequeCompliancePhase
from app.phases.ocr_extraction_v2 import OCRPhaseV2
from app.phases.signature_verification import SiameseSignaturePhase

async def test_phase_1(recto_path, verso_path, cheque_id="TEST_P1"):
    print("\n🧪 TEST PHASE 1 : IDENTIFICATION")
    p1 = ChequeIdentificationPhase()
    with open(recto_path, "rb") as f: r_bytes = f.read()
    with open(verso_path, "rb") as f: v_bytes = f.read()
    
    # Utilisation de .analyze() au lieu de .identify()
    res = await p1.analyze(r_bytes, v_bytes, cheque_id=cheque_id, source=ImageSource.MOBILE)
    print(f"   Score : {res.score}")
    print(f"   Passé : {res.passed}")
    print(f"   Détails : {res.details}")

async def test_phase_2(recto_as_image_bytes, cheque_id="TEST_P2"):
    print("\n🧪 TEST PHASE 2 : COMPLIANCE (QR)")
    p2 = TuniChequeCompliancePhase()
    
    # Étape 1 : Lecture brute du QR
    print("   🔍 Extraction du QR Code (Phase 2)...")
    qr_data = p2.read_qr(recto_as_image_bytes)
    if qr_data and qr_data.get("is_pecc"):
        print(f"   ✅ QR Détecté et Valide !")
        for k, v in qr_data.items():
            if v: print(f"      - {k:15} : {v}")
    else:
        print("   ❌ Aucun QR Code valide détecté (Phase 2).")

    # Étape 2 : Analyse complète (Compliance)
    print("\n   ⚖️ Analyse de conformité...")
    res = await p2.analyze(recto_as_image_bytes, cheque_id=cheque_id)
    print(f"   Passé   : {res.passed}")
    print(f"   Décision: {res.details.get('decision')}")

async def test_phase_3(recto_path):
    print("\n🧪 TEST PHASE 3 : OCR EXTRACTION")
    p3 = OCRPhaseV2()
    with open(recto_path, "rb") as f:
        r_bytes = f.read()
    
    res = await p3.extract(r_bytes)
    
    # Affichage QR spécifique Phase 3
    qr_data = res.details.get("qr_data")
    print("   🔍 Extraction du QR Code (Phase 3)...")
    if qr_data:
        print(f"   ✅ QR Détecté !")
        if "raw_qr" in qr_data:
            print(f"      - [TEXTE BRUT]  : {qr_data['raw_qr']}")
        for k, v in qr_data.items():
            if v and k != "raw_qr": print(f"      - {k:15} : {v}")
    else:
        print("   ❌ Aucun QR Code détecté (Phase 3).")

    print("\n   📝 Données OCR extraites :")
    ext = res.details.get('extracted', {})
    for k, v in ext.items():
        print(f"      - {k:15} : {v}")

async def test_phase_4(recto_bytes, cheque_id="TEST", rib=None, name=None):
    print("\n🧪 TEST PHASE 4 : SIGNATURE")
    p4 = SiameseSignaturePhase()
    res = await p4.verify(recto_bytes, cheque_id=cheque_id, rib=rib, name=name)
    print(f"   Score : {res.score}")
    print(f"   Passé : {res.passed}")
    print(f"   Détails : {res.details}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Unitaire des Phases AI")
    parser.add_argument("--phase", type=int, choices=[1, 2, 3, 4], required=True, help="Numéro de la phase à tester")
    parser.add_argument("--recto", required=True, help="Chemin image recto")
    parser.add_argument("--verso", help="Chemin image verso (requis pour Phase 1)")
    parser.add_argument("--rib", help="RIB (pour Phase 4)")
    parser.add_argument("--name", help="Nom (pour Phase 4)")

    args = parser.parse_args()

    # Lecture des bytes
    with open(args.recto, "rb") as f: r_bytes = f.read()

    if args.phase == 1:
        if not args.verso:
            print("❌ Erreur : Phase 1 nécessite --verso")
        else:
            asyncio.run(test_phase_1(args.recto, args.verso))
    
    elif args.phase == 2:
        asyncio.run(test_phase_2(r_bytes))
    
    elif args.phase == 3:
        asyncio.run(test_phase_3(args.recto))
    
    elif args.phase == 4:
        asyncio.run(test_phase_4(r_bytes, rib=args.rib, name=args.name))
