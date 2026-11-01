# API Contract — Interface Web TuniCheque (Admin & Agent)

**Gateway** : `http://localhost:8080`  
**Version** : 1.0

---

## Authentification

### Login web (Email + Mot de passe)

```
POST /api/auth/login
Content-Type: application/json
```

**Body :**
```json
{
  "email": "agent@tunicheque.tn",
  "password": "MonMotDePasse1!"
}
```

**Réponse 200 :**
```json
{
  "token": "eyJ...",
  "role": "AGENT",
  "userType": "INTERNAL",
  "expiresIn": 3600
}
```

**Rôles web :**
- `ADMIN` — gestion complète
- `AGENT` — traitement des chèques

**Header à inclure dans toutes les requêtes suivantes :**
```
Authorization: Bearer <token>
```

---

## ADMINISTRATION — Gestion des utilisateurs

> Toutes ces routes nécessitent le rôle `ADMIN`.

### Lister tous les utilisateurs

```
GET /api/auth/admin/users
Authorization: Bearer <token>
```

**Query params (optionnels) :**
- `role` : `ADMIN` | `AGENT` | `TIREUR` | `BENEFICIAIRE`

**Réponse 200 :**
```json
[
  {
    "id": "uuid",
    "fullName": "Ahmed Ben Salah",
    "email": "agent@tunicheque.tn",
    "phone": "+21620123456",
    "cinNumber": "12345678",
    "role": "AGENT",
    "userType": "INTERNAL",
    "isActive": true,
    "isVerified": true
  }
]
```

---

### Créer un compte AGENT ou ADMIN

```
POST /api/auth/admin/users
Authorization: Bearer <token>
Content-Type: application/json
```

**Body :**
```json
{
  "fullName": "Sonia Mansouri",
  "email": "sonia.mansouri@tunicheque.tn",
  "password": "SecurePass2025!",
  "role": "AGENT",
  "phone": "+21625000001"
}
```

> Un email de bienvenue avec les identifiants est automatiquement envoyé à l'agent.

**Réponse 201 :**
```json
{
  "id": "uuid",
  "fullName": "Sonia Mansouri",
  "email": "sonia.mansouri@tunicheque.tn",
  "role": "AGENT"
}
```

---

### Activer / Désactiver un utilisateur

```
PATCH /api/auth/admin/users/{id}/toggle-active
Authorization: Bearer <token>
```

**Réponse 200 :**
```json
{ "message": "Compte désactivé.", "isActive": false }
```

---

### Supprimer un utilisateur

```
DELETE /api/auth/admin/users/{id}
Authorization: Bearer <token>
```

**Réponse 204** (No Content)

---

## AGENT — Traitement des chèques

> Rôle requis : `AGENT` ou `ADMIN`.

### Liste des chèques en attente

```
GET /api/cheques/en-attente
Authorization: Bearer <token>
```

**Réponse 200 :** liste de chèques avec `status = EN_ATTENTE`

---

### Tous les chèques

```
GET /api/cheques/all
Authorization: Bearer <token>
```

**Réponse 200 :** liste complète (toutes décisions)

---

### Détail d'un chèque + résultats IA

```
GET /api/cheques/{id}
Authorization: Bearer <token>
```

**Réponse 200 :**
```json
{
  "id": "uuid",
  "numeroCheque": "0012345",
  "montantExtrait": 1500.000,
  "montantLettres": "mille cinq cents dinars",
  "beneficiaireNom": "GUIZANI RYM",
  "dateEmission": "2025-03-15",
  "ribEmetteur": "10001000000000000197",
  "status": "EN_ATTENTE",
  "decisionFinale": "PENDING_REVIEW",
  "source": "MOBILE",
  "beneficiaireId": "uuid",
  "tireurId": "uuid",
  "agentId": null,
  "aiScoreGlobal": 0.6250,
  "fraudeDetectee": false,
  "motifRejet": null,
  "pipelineMs": 4200,
  "createdAt": "2025-03-15T14:30:00",
  "validatedAt": null
}
```

---

### Résultats IA par phase

```
GET /api/cheques/{id}/ai-results
Authorization: Bearer <token>
```

**Réponse 200 :**
```json
[
  {
    "phase": "identification",
    "passed": true,
    "score": 0.8500,
    "durationMs": 1200,
    "decision": null
  },
  {
    "phase": "compliance",
    "passed": true,
    "score": 0.9000,
    "durationMs": 800,
    "decision": "COMPLIANCE_OK"
  },
  {
    "phase": "ocr",
    "passed": true,
    "score": 0.7500,
    "durationMs": 1500,
    "decision": null
  },
  {
    "phase": "signature",
    "passed": false,
    "score": 0.4000,
    "durationMs": 700,
    "decision": "REVIEW"
  }
]
```

---

### Valider ou Rejeter un chèque

```
POST /api/cheques/{id}/valider
Authorization: Bearer <token>
Content-Type: application/json
```

**Body (validation) :**
```json
{
  "decision": "VALIDE"
}
```

**Body (rejet) :**
```json
{
  "decision": "REJETE",
  "motif": "Signature non conforme — date illisible"
}
```

**Réponse 200 :** objet chèque mis à jour

> Après validation : les notifications Kafka sont envoyées automatiquement au TIREUR et au BENEFICIAIRE.

---

## ADMINISTRATION — Statistiques

> Rôle requis : `ADMIN`.

### Statistiques globales

```
GET /api/cheques/all
Authorization: Bearer <token>
```

> Calculer les stats côté frontend à partir de la liste complète, ou utiliser les endpoints de statistiques ci-dessous.

### Statistiques dashboard admin

Les endpoints de stats utilisent les données des chèques :

| Indicateur | Calcul |
|-----------|--------|
| Total chèques | `GET /api/cheques/all` → `length` |
| Taux de validation | `VALIDE / total * 100` |
| Taux de fraude | `FRAUDE_DETECTEE / total * 100` |
| Temps moyen pipeline | moyenne de `pipelineMs` |

---

## KYC (Vérification d'identité visiteur)

> Ces endpoints sont appelés automatiquement lors de l'inscription mobile. L'agent peut consulter les résultats.

### Lancer la vérification KYC

```
POST /api/auth/kyc/initiate
Authorization: Bearer <tokenInscription>
Content-Type: multipart/form-data
```

**Paramètres :**
- `visageFront` : photo du visage de l'utilisateur
- `cinRecto` : photo recto de la CIN
- `cinVerso` : photo verso de la CIN (optionnel)

**Réponse 200 :**
```json
{
  "verified": true,
  "similarity": 0.85,
  "message": "Identité vérifiée avec succès."
}
```

---

## RÉCLAMATIONS (Chatbot)

### Créer une réclamation

```
POST /api/reclamations
Authorization: Bearer <token>
Content-Type: application/json
```

**Body :**
```json
{
  "objet": "Chèque rejeté à tort",
  "description": "Mon chèque de 1500 DT a été rejeté sans raison valable.",
  "chequeId": "uuid"
}
```

**Réponse 201 :**
```json
{
  "reclamationId": "uuid",
  "statut": "EN_COURS",
  "message": "Réclamation enregistrée. Vous recevrez une réponse par email."
}
```

---

## BANQUE DE TEST — Comptes disponibles

Pour les tests en développement :

| Email | Rôle | Mot de passe |
|-------|------|-------------|
| `admin@tunicheque.tn` | ADMIN | (défini au démarrage) |
| `agent@tunicheque.tn` | AGENT | (défini au démarrage) |

> Les comptes ADMIN et AGENT sont créés au démarrage via `DataInitializer.java`.

---

## Codes erreur

| Code | Signification |
|------|---------------|
| `400` | Données invalides |
| `401` | Token absent ou expiré → rediriger vers login |
| `403` | Accès interdit (rôle insuffisant) |
| `404` | Ressource introuvable |
| `409` | Conflit (email déjà utilisé) |
| `500` | Erreur serveur |
