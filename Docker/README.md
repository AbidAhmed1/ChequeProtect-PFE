# TuniCheque — Déploiement Docker

## Pré-requis
- Docker Desktop ≥ 4.x (avec Docker Compose v2)
- 8 Go RAM minimum (modèles ML lourds)
- 20 Go disque libre

## Structure des fichiers créés

```
Docker/
├── docker-compose.yml     ← orchestration complète
├── Dockerfile.spring      ← build Maven → JRE (auth, cheque, notification, gateway)
├── Dockerfile.ai          ← FastAPI Python 3.11
├── Dockerfile.frontend    ← Angular build → Nginx
├── nginx.conf             ← config Nginx + proxy /api/ vers gateway
├── init-db.sh             ← création des 3 bases PostgreSQL
├── .env                   ← clés API et mots de passe
└── README.md              ← ce fichier
```

## Démarrage rapide

```powershell
# 1. Se placer dans le dossier Docker
cd D:\projet-pfe\Docker

# 2. Construire et démarrer tous les services
docker compose up --build -d

# 3. Vérifier que tout est UP
docker compose ps

# 4. Suivre les logs en temps réel
docker compose logs -f
```

## Ordre de démarrage (géré automatiquement)

```
postgres → zookeeper → kafka
         ↓
      ai-service
         ↓
   auth-service ──────┐
   cheque-service ────┼→ api-gateway → frontend
   notification-service
```

## Ports exposés

| Service            | Port local | URL                            |
|--------------------|-----------|--------------------------------|
| Frontend Angular   | 4200      | http://localhost:4200          |
| API Gateway        | 8080      | http://localhost:8080          |
| Auth Service       | 8081      | http://localhost:8081/swagger-ui.html |
| Cheque Service     | 8082      | http://localhost:8082/swagger-ui.html |
| AI Service         | 8083      | http://localhost:8083/health   |
| Notification Svc   | 8085      | http://localhost:8085/swagger-ui.html |
| PostgreSQL         | 5432      | localhost:5432                 |
| Kafka              | 9092      | localhost:9092                 |

## Commandes utiles

```powershell
# Arrêter tous les services
docker compose down

# Arrêter et supprimer les données (reset complet)
docker compose down -v

# Rebuild un seul service
docker compose up --build -d cheque-service

# Voir les logs d'un service
docker compose logs -f auth-service

# Accéder à la base de données
docker exec -it tunicheque-postgres psql -U postgres -d database_auth
```

## Dépannage

**Le service AI met du temps à démarrer** — normal, le chargement des modèles ML prend 1-2 minutes. Le healthcheck attend 60s avant de commencer.

**Erreur "port already in use"** — arrêter les services locaux (Spring Boot, PostgreSQL local) avant de lancer Docker.

**Out of memory** — augmenter la RAM allouée à Docker Desktop (Settings → Resources → Memory).
