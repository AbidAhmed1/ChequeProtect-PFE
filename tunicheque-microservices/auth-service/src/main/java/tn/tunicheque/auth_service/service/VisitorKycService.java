package tn.tunicheque.auth_service.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.*;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestTemplate;
import tn.tunicheque.auth_service.dto.request.VisitorCompleteRequest;
import tn.tunicheque.auth_service.dto.response.AuthResponse;
import tn.tunicheque.auth_service.entity.User;
import tn.tunicheque.auth_service.entity.UserDocument;
import tn.tunicheque.auth_service.entity.enums.Role;
import tn.tunicheque.auth_service.entity.enums.UserType;
import tn.tunicheque.auth_service.exception.EmailAlreadyExistsException;
import tn.tunicheque.auth_service.repository.UserDocumentRepository;
import tn.tunicheque.auth_service.repository.UserRepository;
import tn.tunicheque.auth_service.security.JwtService;

import jakarta.annotation.PostConstruct;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * VisitorKycService v2 — Biometrie pure (pas d'OCR).
 *
 * Flux :
 *   Etape 1 : Upload CIN recto → FastAPI extrait le visage (MTCNN)
 *             → face_base64 retourne et stocke en session
 *   Etape 2 : Upload selfie → FastAPI compare visage CIN vs selfie (FaceNet512)
 *             → score cosine, seuil 0.40
 *   Etape 3 : Creer compte BENEFICIAIRE si score valide
 *
 * CHANGEMENTS v2 vs v1 :
 *   - Endpoint OCR supprime → remplace par /api/ai/face-extract-cin
 *   - Suppression extraction nom/prenom/cin depuis CIN (pas fiable)
 *   - Selfie chiffre AES-256 avant stockage
 *   - Photos CIN supprimees apres creation du compte
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class VisitorKycService {

    private final UserRepository         userRepository;
    private final UserDocumentRepository documentRepository;
    private final PasswordEncoder        passwordEncoder;
    private final JwtService             jwtService;
    private final RestTemplate           restTemplate;
    private final FileStorageService     fileStorage;
    private final EncryptionService      encryptionService;

    @Value("${ai.service.url:http://localhost:8083}")
    private String aiUrl;

    // Session KYC en memoire : sessionId → { face_base64, cin_recto_path, cin_verso_path }
    private final Map<String, Map<String, Object>> sessions = new ConcurrentHashMap<>();

    @PostConstruct
    public void init() {
        try {
            fileStorage.init();
            log.info("KYC FileStorage initialise → dossier uploads/kyc cree");
        } catch (Exception e) {
            log.error("Erreur init FileStorage : {}", e.getMessage());
        }
    }

    // ══ ETAPE 1 — Upload CIN + Extraction visage (MTCNN) ══════════

    /**
     * Reçoit la CIN recto + verso.
     * Appelle FastAPI /api/ai/face-extract-cin (MTCNN).
     * Sauvegarde CIN sur disque + face_base64 en session.
     *
     * Retourne : { sessionId, faceDetecte, message }
     */
    public Map<String, Object> processCin(byte[] recto, byte[] verso) throws Exception {

        // 1. Appeler FastAPI d'abord avec les bytes en clair (MTCNN a besoin de l'image lisible)
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);
        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        body.add("cin_recto", new ByteArrayResource(recto) {
            @Override public String getFilename() { return "cin_recto.jpg"; }
        });
        body.add("cin_verso", new ByteArrayResource(verso) {
            @Override public String getFilename() { return "cin_verso.jpg"; }
        });

        @SuppressWarnings("unchecked")
        Map<String, Object> faceResult = restTemplate.postForEntity(
                aiUrl + "/api/ai/face-extract-cin",
                new HttpEntity<>(body, headers),
                Map.class
        ).getBody();

        if (faceResult == null)
            throw new RuntimeException("FastAPI face-extract-cin indisponible. Verifiez le service IA.");

        String faceBase64 = (String) faceResult.getOrDefault("face_base64", "");
        boolean faceDetected = !faceBase64.isBlank();

        if (!faceDetected)
            throw new RuntimeException(
                    "Aucun visage detecte sur la CIN. Fournissez une photo CIN nette et bien eclairee.");

        // 2. Chiffrer AES-256 avant stockage sur disque (fichiers .enc illisibles sans la cle)
        String rectoPath = fileStorage.save(encryptionService.encrypt(recto), "cin_recto", "enc");
        String versoPath = fileStorage.save(encryptionService.encrypt(verso), "cin_verso", "enc");

        // 3. Generer sessionId + sauvegarder en base
        String sessionId = UUID.randomUUID().toString();

        UserDocument doc = UserDocument.builder()
                .sessionId(sessionId)
                .cinRectoPath(rectoPath)
                .cinVersoPath(versoPath)
                .faceBase64(faceBase64)
                .build();
        documentRepository.save(doc);

        // 4. Stocker en memoire
        Map<String, Object> sessionData = new HashMap<>();
        sessionData.put("face_base64",     faceBase64);
        sessionData.put("cin_recto_path",  rectoPath);
        sessionData.put("cin_verso_path",  versoPath);
        sessionData.put("face_verified",   false);
        sessions.put(sessionId, sessionData);

        log.info("CIN traitee et chiffree AES-256 : visage extrait → sessionId={}", sessionId);

        Map<String, Object> response = new HashMap<>();
        response.put("sessionId",    sessionId);
        response.put("faceDetecte",  true);
        response.put("message",      "Visage extrait de la CIN. Passez a l'etape de verification selfie.");
        return response;
    }

    // ══ ETAPE 2 — Selfie + Comparaison biometrique (FaceNet512) ═══

    /**
     * Reçoit le selfie.
     * Chiffre AES-256 et sauvegarde sur disque.
     * Appelle FastAPI /api/ai/face-compare (FaceNet512 + cosine).
     * Valide si distance < 0.40.
     *
     * Retourne : { verified, similarity_score, message, sessionId }
     */
    public Map<String, Object> verifyFace(byte[] selfie, String sessionId) throws Exception {

        Map<String, Object> session = sessions.get(sessionId);
        if (session == null) {
            // Spring Boot a redemarré → session perdue en mémoire, on recharge depuis la DB
            UserDocument doc = documentRepository.findBySessionId(sessionId)
                    .orElseThrow(() -> new RuntimeException(
                            "Session KYC introuvable. Recommencez depuis l'étape 1 (photo CIN)."));
            if (doc.getFaceBase64() == null || doc.getFaceBase64().isBlank())
                throw new RuntimeException("Photo CIN non disponible. Recommencez depuis l'étape 1.");
            session = new HashMap<>();
            session.put("face_base64",    doc.getFaceBase64());
            session.put("cin_recto_path", doc.getCinRectoPath());
            session.put("cin_verso_path", doc.getCinVersoPath());
            session.put("face_verified",  false);
            sessions.put(sessionId, session);
            log.info("Session KYC restauree depuis DB : sessionId={}", sessionId);
        }

        String faceBase64 = (String) session.getOrDefault("face_base64", "");
        if (faceBase64.isBlank())
            throw new RuntimeException("Photo CIN non disponible. Recommencez depuis l'étape 1.");

        // 1. Chiffrer le selfie AES-256 et sauvegarder (.enc illisible sans la cle)
        byte[] selfieChiffre = encryptionService.encrypt(selfie);
        String selfieEncPath = fileStorage.save(selfieChiffre, "selfie", "enc");

        // 2. Mettre a jour UserDocument
        documentRepository.findBySessionId(sessionId).ifPresent(doc -> {
            doc.setSelfieEncPath(selfieEncPath);
            documentRepository.save(doc);
        });

        // 3. Appeler FastAPI face-compare (FaceNet512 + MTCNN + cosine)
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);
        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        body.add("selfie", new ByteArrayResource(selfie) {
            @Override public String getFilename() { return "selfie.jpg"; }
        });
        body.add("face_base64", faceBase64);

        @SuppressWarnings("unchecked")
        Map<String, Object> compareResult = restTemplate.postForEntity(
                aiUrl + "/api/ai/face-compare",
                new HttpEntity<>(body, headers),
                Map.class
        ).getBody();

        if (compareResult == null)
            throw new RuntimeException("FastAPI face-compare indisponible.");

        double score    = ((Number) compareResult.getOrDefault("similarity_score", 0.0)).doubleValue();
        double distance = ((Number) compareResult.getOrDefault("distance", 1.0)).doubleValue();
        boolean ok      = (boolean) compareResult.getOrDefault("verified", false);

        log.info("Face compare : distance={} score={} verified={} sessionId={}",
                distance, score, ok, sessionId);

        // 4. Valider le score (seuil distance < 0.40 = FaceNet512 cosine)
        if (!ok) {
            throw new RuntimeException(
                    compareResult.getOrDefault("message",
                            "Identite non confirmee (score=" + String.format("%.0f", score*100) + "%). "
                                    + "Assurez-vous d'un bon eclairage et regardez directement la camera.").toString()
            );
        }

        // 5. Marquer la session comme verifiee (mémoire + DB)
        session.put("face_verified",   true);
        session.put("similarity_score", score);
        session.put("selfie_enc_path",  selfieEncPath);
        documentRepository.findBySessionId(sessionId).ifPresent(doc -> {
            doc.setFaceVerified(true);
            documentRepository.save(doc);
        });

        Map<String, Object> response = new HashMap<>();
        response.put("verified",         true);
        response.put("similarity_score", score);
        response.put("distance",         distance);
        response.put("sessionId",        sessionId);
        response.put("message",          compareResult.getOrDefault("message",
                "Identite confirmee — " + String.format("%.0f", score*100) + "% de correspondance."));
        return response;
    }

    // ══ ETAPE 3 — Creation du compte BENEFICIAIRE ═════════════════

    @Transactional
    public AuthResponse createVisitorAccount(VisitorCompleteRequest req) {

        Map<String, Object> session = sessions.get(req.getSessionId());

        if (session == null) {
            // Spring Boot a redemarré → restaurer depuis la DB
            UserDocument doc = documentRepository.findBySessionId(req.getSessionId())
                    .orElseThrow(() -> new RuntimeException(
                            "Session KYC introuvable. Recommencez depuis l'étape 1 (photo CIN)."));
            if (!doc.isFaceVerified())
                throw new RuntimeException("La vérification faciale n'a pas été complétée. Reprenez le selfie.");
            session = new HashMap<>();
            session.put("face_base64",    doc.getFaceBase64());
            session.put("cin_recto_path", doc.getCinRectoPath());
            session.put("face_verified",  true);
            sessions.put(req.getSessionId(), session);
            log.info("Session KYC restauree pour creation compte : sessionId={}", req.getSessionId());
        }

        if (!Boolean.TRUE.equals(session.get("face_verified")))
            throw new RuntimeException("La vérification faciale n'a pas été complétée. Reprenez le selfie.");
        if (!req.getPin().equals(req.getPinConfirm()))
            throw new IllegalArgumentException("Les codes PIN ne correspondent pas.");
        if (isWeakPin(req.getPin()))
            throw new IllegalArgumentException("Ce PIN est trop simple (ex: 123456, 000000).");
        if (userRepository.existsByEmail(req.getEmail()))
            throw new EmailAlreadyExistsException("Cet email est deja utilise.");

        // Creer le compte BENEFICIAIRE
        String emailVal = (req.getEmail() != null && !req.getEmail().isBlank())
                ? req.getEmail() : null;

        User user = User.builder()
                .phone(req.getPhone())
                .email(emailVal)
                .fullName(req.getFullName())
                .cinNumber(req.getCinNumber())
                .rib(req.getRib())
                .faceImageUrl((String) session.getOrDefault("cin_recto_path", null))
                .passwordHash(passwordEncoder.encode(req.getPin()))
                .role(Role.CLIENT)
                .userType(UserType.CLIENT)
                .isActive(true)
                .isVerified(true)
                .build();

        final User saved = userRepository.save(user);

        // Lier le document KYC a l'utilisateur
        documentRepository.findBySessionId(req.getSessionId()).ifPresent(doc -> {
            doc.setUserId(saved.getId());
            documentRepository.save(doc);
        });

        // CIN chiffrees AES-256 conservees sur disque comme preuve KYC
        // Selfie .enc aussi conserve — tous les fichiers sont illisibles sans la cle AES

        sessions.remove(req.getSessionId());

        log.info("Compte KYC cree : {} role=CLIENT", saved.getEmail());

        return AuthResponse.builder()
                .token(jwtService.generateToken(saved))
                .role(saved.getRole().name())
                .userType(saved.getUserType().name())
                .expiresIn(3600)
                .build();
    }

    private boolean isWeakPin(String pin) {
        return pin.equals("123456") || pin.equals("000000")
                || pin.chars().distinct().count() == 1;
    }
}
