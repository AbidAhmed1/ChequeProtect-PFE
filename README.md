# ChequeProtect-PFE — AI-Powered Check Processing System

## 🛍️ Overview
**ChèqueProtect** is an intelligent end-to-end system designed to modernize and secure Tunisian bank check processing using Web, Mobile, and Advanced AI techniques.

The platform was awarded **17.46/20 (Très Bien)** for the Graduation Project (PFE) at **ESEN Manouba** in partnership with **EXCELLIA Solutions**.

## 🚀 Features
- 🧬 **4-Phase AI Pipeline** — Fake check detection, BCT compliance verification, cascade OCR, and Siamese signature verification.
- 📱 **Mobile Tracking Application** — Real-time tracking and submission for users via Flutter.
- 💻 **Agent Web Portal** — Comprehensive Angular dashboard with Signals and real-time Chart.js analytics.
- 🤖 **AI Assistant Chatbot** — Integrated Groq LLAMA 3 model for automatic claim management.
- 🔐 **KYC Module** — MTCNN & FaceNet512 biometric ID verification.

## 🛠️ Technologies

- Java Spring Boot 3.5+ & FastAPI
- Angular 21+ & Flutter
- YOLOv8, XGBoost, TensorFlow, OpenCV
- Apache Kafka & PostgreSQL 16
- Docker Compose & Spring Cloud API Gateway

## 📂 Project Structure

```plaintext
ChequeProtect-PFE/
├── 📁 ai-tunicheque/                # Service IA (FastAPI, YOLO, OCR & Signature Verification)
│   ├── 📁 app/                      # Code source principal de l'application IA
│   ├── 📁 scripts/                  # Scripts d'initialisation (génération de données, spécimens BCT)
│   │   ├── create_specimens_table.sql
│   │   ├── enroll_specimen.py
│   │   ├── generate_cheques.py
│   │   ├── generate_users.py
│   │   └── seed_bank_bct.py
│   ├── 📁 training/                 # Scripts et notebooks d'entraînement des modèles ML/DL
│   │   ├── augmentYolo_dataset.py
│   │   ├── colab_train_benef.ipynb
│   │   ├── colab_train_datelieu.ipynb
│   │   ├── colab_train_tireur.ipynb
│   │   ├── train_phase1.py
│   │   ├── train_siamese.py
│   │   └── train_yolo.py
│   ├── crop_signature.py            # Extraction et prétraitement de signatures
│   └── requirements.txt             # Dépendances Python
│
├── 📁 Docker/                       # Configurations Docker & Orchestration
│   ├── docker-compose.yml           # Déploiement multi-services
│   ├── Dockerfile.ai                # Conteneurisation du service IA
│   ├── Dockerfile.frontend          # Conteneurisation du Frontend Web
│   ├── Dockerfile.spring            # Conteneurisation des microservices Spring
│   ├── init-db.sh                   # Script d'initialisation de la base de données
│   └── nginx.conf                   # Configuration Reverse Proxy Nginx
│
├── 📁 Frontend/                     # Interfaces Utilisateur
│   ├── 📁 mobile/                   # Application Mobile (Flutter)
│   │   ├── 📁 android/
│   │   ├── 📁 ios/
│   │   ├── 📁 lib/                  # Code source Flutter
│   │   ├── 📁 web/
│   │   └── pubspec.yaml             # Dépendances et configuration Flutter
│   └── 📁 web/                      # Application Web Administration (Angular)
│       ├── 📁 src/                  # Composants et services Angular
│       ├── angular.json             # Configuration du projet Angular
│       └── package.json             # Dépendances Node.js / Angular
│
├── 📁 tunicheque-microservices/     # Backend Microservices (Spring Boot)
│   ├── 📁 analytics/                # Service d'analyse et de reporting
│   ├── 📁 api-gateway/              # API Gateway (Routage centralisé)
│   ├── 📁 auth-service/             # Service d'Authentification & Sécurité (JWT)
│   ├── 📁 cheque-service/           # Service de gestion et traitement des chèques
│   ├── 📁 notification-service/     # Service de notifications
│   ├── 📁 scripts/                  # Scripts utilitaires du backend
│   ├── API_CONTRACT_MOBILE.md       # Spécification des APIs Mobile
│   └── API_CONTRACT_WEB.md          # Spécification des APIs Web
│
└── 📁 Apipostman/                   # Collections Postman pour le test des APIs

## 🎯 Project Objective
To automate manual banking verification processes, mitigate check fraud, and provide an enterprise-ready microservices architecture.
