# API Contract — Application Mobile TuniCheque
> Version 2.0 — Terminologie mise à jour : TIREUR (ex-TITULAIRE)

**Gateway** : `http://localhost:8080`  
**Auth Service** : port 8081 (via Gateway)  
**Cheque Service** : port 8082 (via Gateway)  
**Notification Service** : port 8083 (via Gateway)

---

## Authentification JWT

Toutes les requêtes après login incluent :
```
Authorization: Bearer <token>
```
La Gateway injecte automatiquement dans chaque requête downstream :
- `X-User-Id` : UUID de l'utilisateur
- `X-User-Role` : `TIREUR` | `BENEFICIAIRE`
- `X-User-Type` : `CLIENT`

---

## Rôles mobiles

| Rôle | Description |
|------|-------------|
| `TIREUR` | Émet des chèques |
| `BENEFICIAIRE` | Reçoit et dépose des chèques |

---

## PARCOURS A — Inscription via RIB bancaire

### Étape 1 — Initier avec le RIB

```
POST /api/auth/rib/initiate
Content-Type: application/json
```

**Body :**
```json
{ "rib": "10001000000000000197" }
```

**Réponse 200 :**
```json
{
  "sessionId": "uuid-session",
  "telephoneMasque": "+216 ** ****01",
  "message": "Est-ce votre numéro ? +216 ** ****01",
  "expiresInSeconds": 600
}
```

**Erreurs :**
- `400` RIB invalide (format ou clé Luhn BCT)
- `404` RIB non trouvé en base
- `409` Compte déjà existant pour ce numéro

---

### Étape 2 — Confirmer le numéro + envoyer OTP SMS

```
POST /api/auth/rib/send-otp
Content-Type: application/json
```

**Body :**
```json
{ "sessionId": "uuid-session" }
```

**Réponse 200 :**
```json
{ "message": "Code OTP envoyé par SMS." }
```

---

### Étape 3 — Vérifier le code OTP

```
POST /api/auth/rib/verify-otp
Content-Type: application/json
```

**Body :**
```json
{
  "sessionId": "uuid-session",
  "otp": "123456"
}
```

**Réponse 200 :**
```json
{
  "tokenInscription": "eyJ...",
  "sessionId": "uuid-session"
}
```

**Erreurs :**
- `400` Code incorrect (N tentatives restantes)
- `410` OTP expiré (2 minutes)
- `429` Trop de tentatives — session annulée (max 3)

---

### Étape 4 — Créer le compte avec PIN

```
POST /api/auth/rib/create-account
Authorization: Bearer <tokenInscription>
Content-Type: application/json
```

**Body :**
```json
{
  "sessionId": "uuid-session",
  "pin": "142536",
  "pinConfirm": "142536"
}
```

**Réponse 200 :**
```json
{
  "token": "eyJ...",
  "role": "TIREUR",
  "userType": "CLIENT",
  "expiresIn": 3600
}
```

---

## PARCOURS B — Inscription visiteur (KYC)

### Étape A — Initier avec le téléphone

```
POST /api/auth/otp/initiate
Content-Type: application/json
```

**Body :**
```json
{ "telephone": "+21620123456" }
```

**Réponse 200 :**
```json
{
  "sessionId": "uuid-session",
  "expiresInSeconds": 120
}
```

---

### Étape B — Vérifier l'OTP SMS

```
POST /api/auth/otp/verify
Content-Type: application/json
```

**Body :**
```json
{
  "sessionId": "uuid-session",
  "otp": "123456"
}
```

**Réponse 200 :**
```json
{
  "tokenInscription": "eyJ...",
  "sessionId": "uuid-session"
}
```

---

### Étape C — Compléter l'inscription

```
POST /api/auth/otp/complete
Authorization: Bearer <tokenInscription>
Content-Type: application/json
```

**Body :**
```json
{
  "nom": "Ben Salem",
  "prenom": "Ahmed",
  "cin": "12345678",
  "email": "ahmed@example.com",
  "pin": "142536",
  "pinConfirm": "142536",
  "role": "TIREUR",
  "rib": "10001000000000000197"
}
```
> `role` : `TIREUR` ou `BENEFICIAIRE`  
> `rib` : optionnel (20 chiffres si fourni)

**Réponse 200 :**
```json
{
  "token": "eyJ...",
  "role": "TIREUR",
  "userType": "CLIENT",
  "expiresIn": 3600
}
```

---

## CONNEXION MOBILE

```
POST /api/auth/login/mobile
Content-Type: application/json
```

**Body :**
```json
{
  "telephone": "+21620123456",
  "pin": "142536"
}
```

**Réponse 200 :**
```json
{
  "token": "eyJ...",
  "role": "TIREUR",
  "userType": "CLIENT",
  "expiresIn": 86400
}
```

---

## PROFIL UTILISATEUR

### Récupérer le profil

```
GET /api/auth/profile/me
Authorization: Bearer <token>
```

**Réponse 200 :**
```json
{
  "id": "uuid",
  "fullName": "Ahmed Ben Salem",
  "phone": "+21620123456",
  "email": "ahmed@example.com",
  "cinNumber": "12345678",
  "rib": "10001000000000000197",
  "role": "TIREUR",
  "userType": "CLIENT",
  "isActive": true,
  "isVerified": true
}
```

### Modifier le profil

```
PUT /api/auth/profile/me
Authorization: Bearer <token>
Content-Type: application/json
```

**Body :**
```json
{
  "fullName": "Ahmed Ben Salem",
  "email": "ahmed@example.com"
}
```

### Changer le PIN

```
PUT /api/auth/profile/change-password
Authorization: Bearer <token>
Content-Type: application/json
```

**Body :**
```json
{
  "ancienMotDePasse": "142536",
  "nouveauMotDePasse": "654321",
  "confirmationMotDePasse": "654321"
}
```

---

## CHÈQUES

### Déposer un chèque (BENEFICIAIRE)

```
POST /api/cheques/upload
Authorization: Bearer <token>
Content-Type: multipart/form-data
```

**Paramètres :**
- `recto` : image recto (obligatoire)
- `verso` : image verso (optionnel)

**Réponse 200 :** objet `Cheque` complet

---

### Mes chèques (paginés)

```
GET /api/cheques/mes-cheques?page=0&size=10&statut=VALIDE
Authorization: Bearer <token>
```

**Query params :**
- `page` : numéro de page (défaut: 0)
- `size` : taille de page (défaut: 10)
- `statut` : filtre optionnel

**Réponse 200 :**
```json
{
  "content": [ { "id": "uuid", "montantExtrait": 1500.000, "status": "VALIDE", "..." : "..." } ],
  "totalElements": 42,
  "totalPages": 5,
  "number": 0,
  "size": 10
}
```

---

### Détail d'un chèque

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
  "status": "VALIDE",
  "decisionFinale": "VALIDE",
  "source": "MOBILE",
  "beneficiaireId": "uuid",
  "tireurId": "uuid",
  "aiScoreGlobal": 0.8750,
  "fraudeDetectee": false,
  "createdAt": "2025-03-15T14:30:00",
  "validatedAt": "2025-03-15T15:00:00"
}
```

---

### Statistiques dashboard mobile

```
GET /api/cheques/mobile/stats
Authorization: Bearer <token>
```

**Réponse BENEFICIAIRE :**
```json
{
  "totalCheques": 12,
  "enTraitement": 2,
  "valides": 8,
  "rejetes": 1,
  "enAttente": 1,
  "montantValide": 15750.000,
  "totalEmissions": 0,
  "emissionsEnAttente": 0,
  "emissionsValidees": 0,
  "montantEnCours": 0
}
```

**Réponse TIREUR :**
```json
{
  "totalCheques": 0,
  "enTraitement": 0,
  "valides": 0,
  "rejetes": 0,
  "enAttente": 0,
  "montantValide": 0,
  "totalEmissions": 7,
  "emissionsEnAttente": 2,
  "emissionsValidees": 5,
  "montantEnCours": 3200.000
}
```

---

## NOTIFICATIONS

### Toutes les notifications

```
GET /api/notifications/user/{userId}
Authorization: Bearer <token>
```

### Notifications non lues

```
GET /api/notifications/user/{userId}/unread
Authorization: Bearer <token>
```

### Compteur non lues

```
GET /api/notifications/user/{userId}/unread-count
Authorization: Bearer <token>
```

**Réponse :**
```json
{ "unreadCount": 3 }
```

### Marquer une notification comme lue

```
PATCH /api/notifications/{id}/read
Authorization: Bearer <token>
```

### Tout marquer comme lu

```
PATCH /api/notifications/user/{userId}/read-all
Authorization: Bearer <token>
```

---

## Statuts des chèques

| Statut | Description |
|--------|-------------|
| `EN_ATTENTE` | En attente de traitement agent |
| `EN_TRAITEMENT` | Pipeline IA en cours |
| `VALIDE` | Validé par l'agent |
| `REJETE` | Rejeté |
| `FRAUDE_DETECTEE` | Fraude détectée par l'IA |

---

## Codes erreur

| Code | Signification |
|------|---------------|
| `400` | Données invalides (PIN faible, CIN incorrect…) |
| `401` | Token absent ou expiré |
| `403` | Accès interdit |
| `404` | Ressource introuvable |
| `409` | Conflit (email/CIN/téléphone déjà utilisé) |
| `410` | OTP expiré |
| `429` | Trop de tentatives OTP |
| `500` | Erreur serveur |
