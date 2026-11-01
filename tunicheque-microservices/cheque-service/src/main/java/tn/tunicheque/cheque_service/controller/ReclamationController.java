package tn.tunicheque.cheque_service.controller;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import tn.tunicheque.cheque_service.dto.request.ChatMessage;
import tn.tunicheque.cheque_service.dto.request.CreateReclamationRequest;
import tn.tunicheque.cheque_service.dto.request.UpdateStatutReclamationRequest;
import tn.tunicheque.cheque_service.service.ReclamationService;

import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping("/api/reclamations")
@RequiredArgsConstructor
@Slf4j
public class ReclamationController {

    private final ReclamationService reclamationService;

    // ── Chat avec le chatbot Claude ───────────────────────────────

    @PostMapping("/chat")
    public ResponseEntity<?> chat(
            @RequestHeader("X-User-Id") String userId,
            @RequestBody ChatMessage message) {
        try {
            return ResponseEntity.ok(reclamationService.chat(userId, message));
        } catch (Exception e) {
            log.error("chat erreur : {}", e.getMessage());
            return ResponseEntity.internalServerError()
                .body(Map.of("error", "Erreur technique. Veuillez réessayer."));
        }
    }

    // ── Soumettre la réclamation finale ───────────────────────────

    @PostMapping
    public ResponseEntity<?> create(
            @RequestHeader("X-User-Id") String userId,
            @RequestBody CreateReclamationRequest req) {
        try {
            return ResponseEntity.ok(reclamationService.createReclamation(userId, req));
        } catch (Exception e) {
            log.error("create réclamation erreur : {}", e.getMessage());
            return ResponseEntity.internalServerError()
                .body(Map.of("error", e.getMessage()));
        }
    }

    // ── Admin : liste toutes les réclamations ─────────────────────

    @GetMapping
    public ResponseEntity<?> getAll(
            @RequestHeader("X-User-Role") String role) {
        if (!role.contains("ADMIN"))
            return ResponseEntity.status(403).body(Map.of("error", "Accès refusé."));
        return ResponseEntity.ok(reclamationService.findAll());
    }

    // ── Admin : transmettre au service client ─────────────────────

    @PutMapping("/{id}/transmit")
    public ResponseEntity<?> transmit(
            @PathVariable UUID id,
            @RequestHeader("X-User-Role") String role) {
        if (!role.contains("ADMIN"))
            return ResponseEntity.status(403).body(Map.of("error", "Accès refusé."));
        try {
            reclamationService.transmit(id);
            return ResponseEntity.ok(Map.of("message", "Réclamation transmise au service client."));
        } catch (RuntimeException e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }

    // ── Admin : mettre à jour le statut + notifier le client ──────

    @PutMapping("/{id}/statut")
    public ResponseEntity<?> updateStatut(
            @PathVariable UUID id,
            @RequestHeader("X-User-Role") String role,
            @RequestBody UpdateStatutReclamationRequest req) {
        if (!role.contains("ADMIN"))
            return ResponseEntity.status(403).body(Map.of("error", "Accès refusé."));
        try {
            return ResponseEntity.ok(reclamationService.updateStatut(id, req.getStatut(), req.getReponseAgent()));
        } catch (RuntimeException e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }
}