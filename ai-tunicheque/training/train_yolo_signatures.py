import os
from ultralytics import YOLO

import os
from ultralytics import YOLO

def train_yolo():
    # --- CONFIGURATION ---
    # Chemin vers le dernier checkpoint (le run qui a crashé à l'étape 15)
    last_checkpoint = r"C:\Users\raeda\runs\detect\yolo_signatures_tuned_v24\weights\last.pt"
    
    # Chemin vers le fichier YAML de données (adapté à la nouvelle structure)
    data_yaml = os.path.join(os.path.dirname(__file__), "..", "cheques_dataset.yaml")
    
    if os.path.exists(last_checkpoint):
        print(f"🔄 Reprise de l'entraînement détectée : {last_checkpoint}")
        model = YOLO(last_checkpoint)
        resume = True
    else:
        print(f"⚠️ Aucun checkpoint trouvé à {last_checkpoint}")
        print("Démarrage d'un nouveau Fine-Tuning sur le modèle de base.")
        base_model = os.path.join(os.path.dirname(__file__), "..", "models", "best.pt")
        model = YOLO(base_model if os.path.exists(base_model) else "yolov8n.pt")
        resume = False
    
    # --- LANCEMENT ---
    print(f"🚀 Cible : {data_yaml}")
    
    results = model.train(
        data=data_yaml,
        epochs=30,      # Votre cible initiale
        imgsz=640,
        batch=8,
        device='cpu',   # Utilisez '0' si vous avez un GPU fonctionnel
        name='yolo_signatures_tuned_v24', # Pour garder le même dossier de log
        resume=resume
    )
    
    print("✅ Session d'entraînement terminée !")

if __name__ == "__main__":
    train_yolo()
