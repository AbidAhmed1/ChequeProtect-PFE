package tn.tunicheque.auth_service.controller;

import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import tn.tunicheque.auth_service.dto.request.VisitorCompleteRequest;
import tn.tunicheque.auth_service.service.VisitorKycService;

import java.util.Map;

/**
 * VisitorKycController v2 — Biometrie pure (MTCNN + FaceNet512).
 *
 * ENDPOINTS :
 *   POST /api/auth/register/visitor/upload-cin  → Etape 1 : extraire visage CIN
 *   POST /api/auth/register/visitor/face-verify → Etape 2 : comparer selfie
 *   POST /api/auth/register/visitor/complete    → Etape 3 : creer compte
 *
 * SUPPRIME vs v1 :
 *   /api/auth/kyc/submit (remplace par upload-cin)
 *   /api/auth/kyc/status (inutile)
 *   KycRequest.java (supprime — utiliser MultipartFile directement)
 */
@RestController
@RequestMapping("/api/auth/register/visitor")
@RequiredArgsConstructor
@Slf4j
public class VisitorKycController {

    private final VisitorKycService kycService;

    // ── Etape 1 : Upload CIN → extraction visage (MTCNN) ──────────

    @PostMapping("/upload-cin")
    public ResponseEntity<?> uploadCin(
            @RequestParam("cinRecto") MultipartFile recto,
            @RequestParam("cinVerso") MultipartFile verso) {
        try {
            if (recto.isEmpty() || verso.isEmpty())
                return ResponseEntity.badRequest()
                        .body(Map.of("error", "Les deux faces de la CIN sont requises."));

            Map<String, Object> result = kycService.processCin(
                    recto.getBytes(), verso.getBytes());
            return ResponseEntity.ok(result);

        } catch (RuntimeException e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        } catch (Exception e) {
            log.error("upload-cin erreur : {}", e.getMessage());
            return ResponseEntity.internalServerError()
                    .body(Map.of("error", "Erreur technique. Reessayez."));
        }
    }

    // ── Etape 2 : Selfie → comparaison biometrique (FaceNet512) ───

    @PostMapping("/face-verify")
    public ResponseEntity<?> faceVerify(
            @RequestParam("selfie")    MultipartFile selfie,
            @RequestParam("sessionId") String sessionId) {
        try {
            if (selfie.isEmpty())
                return ResponseEntity.badRequest()
                        .body(Map.of("error", "Le selfie est requis."));
            if (sessionId == null || sessionId.isBlank())
                return ResponseEntity.badRequest()
                        .body(Map.of("error", "Le sessionId est requis."));

            Map<String, Object> result = kycService.verifyFace(
                    selfie.getBytes(), sessionId);
            return ResponseEntity.ok(result);

        } catch (RuntimeException e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        } catch (Exception e) {
            log.error("face-verify erreur : {}", e.getMessage());
            return ResponseEntity.internalServerError()
                    .body(Map.of("error", "Erreur technique. Reessayez."));
        }
    }

    // ── Etape 3 : Creer le compte BENEFICIAIRE ─────────────────────

    @PostMapping("/complete")
    public ResponseEntity<?> completeVisitor(
            @RequestBody @Valid VisitorCompleteRequest req) {
        try {
            return ResponseEntity.ok(kycService.createVisitorAccount(req));
        } catch (RuntimeException e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        } catch (Exception e) {
            log.error("complete erreur : {}", e.getMessage());
            return ResponseEntity.internalServerError()
                    .body(Map.of("error", "Erreur technique lors de la creation du compte."));
        }
    }
}
