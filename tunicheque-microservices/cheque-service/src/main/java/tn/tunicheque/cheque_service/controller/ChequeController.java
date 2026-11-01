package tn.tunicheque.cheque_service.controller;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import tn.tunicheque.cheque_service.entity.AiResult;
import tn.tunicheque.cheque_service.entity.Cheque;
import tn.tunicheque.cheque_service.service.ChequeService;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import tn.tunicheque.cheque_service.dto.response.MobileStatsDTO;

@RestController
@RequestMapping("/api/cheques")
@RequiredArgsConstructor
@Slf4j
public class ChequeController {

    private final ChequeService chequeService;

    // ─── Health check ──────────────────────────────────────────────────────

    @GetMapping("/health")
    public ResponseEntity<Map<String, String>> health() {
        return ResponseEntity.ok(Map.of(
                "service", "cheque-service",
                "status",  "UP",
                "port",    "8082"
        ));
    }

    // ─── Upload + Pipeline IA ──────────────────────────────────────────────

    @PostMapping("/upload")
    public ResponseEntity<?> uploadCheque(
            @RequestParam("recto")                                            MultipartFile recto,
            @RequestParam(value = "verso",   required = false)               MultipartFile verso,
            @RequestParam(value = "source",  defaultValue = "MOBILE")        String source,
            @RequestHeader(value = "X-User-Id", required = false)            String userId) {

        try {
            UUID beneficiaireId = "MOBILE".equalsIgnoreCase(source) && userId != null
                    ? UUID.fromString(userId) : null;
            log.info("Upload chèque par : {} source={}", userId, source);

            Cheque cheque = chequeService.uploadAndProcess(recto, verso, beneficiaireId, source);
            return ResponseEntity.ok(cheque);

        } catch (IOException e) {
            log.error("Erreur upload : {}", e.getMessage());
            return ResponseEntity.internalServerError()
                    .body(Map.of("error", "Erreur lors de l'upload : " + e.getMessage()));
        }
    }

    // ─── Consultation ──────────────────────────────────────────────────────

    @GetMapping("/{id}")
    public ResponseEntity<Cheque> getCheque(@PathVariable UUID id) {
        return ResponseEntity.ok(chequeService.getChequeById(id));
    }

    @GetMapping("/{id}/ai-results")
    public ResponseEntity<List<AiResult>> getAiResults(@PathVariable UUID id) {
        return ResponseEntity.ok(chequeService.getAiResults(id));
    }

    @GetMapping("/{id}/image/recto")
    public ResponseEntity<byte[]> getImageRecto(@PathVariable UUID id) {
        Cheque cheque = chequeService.getChequeById(id);
        return serveImage(cheque.getImageRectoUrl());
    }

    @GetMapping("/{id}/image/verso")
    public ResponseEntity<byte[]> getImageVerso(@PathVariable UUID id) {
        Cheque cheque = chequeService.getChequeById(id);
        return serveImage(cheque.getImageVersoUrl());
    }

    private ResponseEntity<byte[]> serveImage(String path) {
        if (path == null || path.isBlank()) return ResponseEntity.notFound().build();
        try {
            byte[] bytes = Files.readAllBytes(Paths.get(path));
            String lower = path.toLowerCase();
            MediaType type = lower.endsWith(".png") ? MediaType.IMAGE_PNG
                           : lower.endsWith(".pdf") ? MediaType.APPLICATION_PDF
                           : MediaType.IMAGE_JPEG;
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(type);
            return ResponseEntity.ok().headers(headers).body(bytes);
        } catch (IOException e) {
            log.warn("Image introuvable : {}", path);
            return ResponseEntity.notFound().build();
        }
    }

    @GetMapping("/mes-cheques")
    public ResponseEntity<?> mesCheques(
            @RequestHeader("X-User-Id")                                    String userId,
            @RequestParam(value = "espace", defaultValue = "beneficiaire") String espace,
            @RequestParam(required = false)                                Cheque.ChequeStatus statut,
            @RequestParam(defaultValue = "0")                              int page,
            @RequestParam(defaultValue = "10")                             int size) {

        UUID uid = UUID.fromString(userId);
        return ResponseEntity.ok(chequeService.getChequesMobile(uid, espace, statut, page, size));
    }

    // ─── Dashboard mobile : stats (bénéficiaire + tireur) ─────────────────

    @GetMapping("/mobile/stats")
    public ResponseEntity<MobileStatsDTO> getMobileStats(
            @RequestHeader("X-User-Id")                                    String userId,
            @RequestParam(value = "espace", defaultValue = "beneficiaire") String espace) {

        UUID uid = UUID.fromString(userId);
        return ResponseEntity.ok(chequeService.getMobileStats(uid, espace));
    }

    // ─── Agent ────────────────────────────────────────────────────────────

    @GetMapping("/en-attente")
    public ResponseEntity<List<Cheque>> getChequesEnAttente() {
        return ResponseEntity.ok(chequeService.getChequesEnAttente());
    }

    @GetMapping("/all")
    public ResponseEntity<List<Cheque>> getAllCheques() {
        return ResponseEntity.ok(chequeService.getAllCheques());
    }

    @PostMapping("/{id}/valider")
    public ResponseEntity<Cheque> validerCheque(
            @PathVariable UUID id,
            @RequestHeader("X-User-Id") String agentId,
            @RequestBody Map<String, String> body) {

        String decision        = body.getOrDefault("decision", "VALIDE");
        String motif           = body.get("motif");
        String cinBeneficiaire = body.get("cinBeneficiaire");
        String ribBeneficiaire = body.get("ribBeneficiaire");

        Cheque cheque = chequeService.validerCheque(
                id, UUID.fromString(agentId), decision, motif, cinBeneficiaire, ribBeneficiaire);
        return ResponseEntity.ok(cheque);
    }

    // ─── Liaison tireur rétroactive (appelé par auth-service à l'inscription) ──

    @PostMapping("/internal/link-tireur")
    public ResponseEntity<?> linkTireur(
            @RequestParam("rib")    String rib,
            @RequestParam("userId") UUID   userId) {
        chequeService.linkTireur(rib, userId);
        return ResponseEntity.ok(Map.of("linked", true, "rib", rib, "userId", userId));
    }

    // ─── Retraitement pipeline IA (chèque mobile déjà stocké) ────────────

    @PostMapping("/{id}/reprocess")
    public ResponseEntity<?> reprocessCheque(@PathVariable UUID id) {
        try {
            Cheque cheque = chequeService.startReprocess(id);
            return ResponseEntity.ok(cheque);
        } catch (IOException e) {
            log.error("Erreur retraitement : {}", e.getMessage());
            return ResponseEntity.internalServerError()
                    .body(Map.of("error", "Erreur lors du retraitement : " + e.getMessage()));
        }
    }
}