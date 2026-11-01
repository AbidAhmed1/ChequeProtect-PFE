import os
import sys
import glob
import cv2
import numpy as np
import structlog
from pathlib import Path

# Setup paths
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from app.phase3.holistic_ocr import ChequeHandwritingReader

logger = structlog.get_logger()

DATASET_DIR = os.path.join(ROOT, "training_data", "svm_words")
SAVE_PATH = os.path.join(ROOT, "app", "phase3", "svm_montants.joblib")

def main():
    print(f"====== TRAINING FINAL HOLISTIC SVM ======")
    reader = ChequeHandwritingReader()
    
    if not os.path.exists(DATASET_DIR):
        print(f"Error: Dataset not found {DATASET_DIR}")
        print("Please run scripts/generate_svm_data.py first.")
        sys.exit(1)
        
    words = os.listdir(DATASET_DIR)
    
    X = []
    y = []
    
    count = 0
    print("Extracting features from synthetic images...")
    for word in words:
        word_dir = os.path.join(DATASET_DIR, word)
        if not os.path.isdir(word_dir):
            continue
            
        imgs = glob.glob(os.path.join(word_dir, "*.jpg"))
        for img_path in imgs:
            img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
                
            # Normalization and padding using the reader's method
            norm_img = reader._normalize_with_padding(img, reader.target_size)
            
            # Extract Hybrid features (Density + HOG)
            features = reader.extract_features(norm_img)
            X.append(features)
            y.append(word)  # Add label
            
            count += 1
            if count % 1000 == 0:
                print(f"Processed {count} images...")
                
    if not X:
        print("No valid images found for training.")
        sys.exit(1)
        
    X = np.array(X, dtype=np.float32)
    
    print(f"Dataset ready: {len(X)} samples, {len(set(y))} unique classes.")
    
    print("Training SVM model... (this may take a few minutes for complex HOG features)")
    reader.train(X, y, save_path=SAVE_PATH)
    
    print(f"Model saved completely at {SAVE_PATH}!")

if __name__ == "__main__":
    main()
