package tn.tunicheque.notification_service.controller;

import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import tn.tunicheque.notification_service.entity.Notification;
import tn.tunicheque.notification_service.repository.NotificationRepository;

import java.util.List;
import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping("/api/notifications")
@RequiredArgsConstructor
public class NotificationController {

    private final NotificationRepository repo;

    @GetMapping("/health")
    public ResponseEntity<Map<String, String>> health() {
        return ResponseEntity.ok(Map.of(
            "status", "UP",
            "service", "notification-service",
            "port", "8085"
        ));
    }

    // Historique notifications d'un utilisateur
    @GetMapping("/user/{userId}")
    public ResponseEntity<List<Notification>> getByUser(@PathVariable UUID userId) {
        return ResponseEntity.ok(repo.findByUserIdOrderByCreatedAtDesc(userId));
    }

    // Notifications non lues uniquement
    @GetMapping("/user/{userId}/unread")
    public ResponseEntity<List<Notification>> getUnreadByUser(@PathVariable UUID userId) {
        return ResponseEntity.ok(repo.findByUserIdAndIsReadFalseOrderByCreatedAtDesc(userId));
    }

    // Compteur de non-lus (pour le badge dans l'appli)
    @GetMapping("/user/{userId}/unread-count")
    public ResponseEntity<Map<String, Long>> getUnreadCount(@PathVariable UUID userId) {
        long count = repo.countByUserIdAndIsReadFalse(userId);
        return ResponseEntity.ok(Map.of("unreadCount", count));
    }

    // Marquer une notification comme lue
    @PatchMapping("/{id}/read")
    public ResponseEntity<Map<String, String>> markAsRead(@PathVariable UUID id) {
        repo.findById(id).ifPresent(n -> {
            n.setRead(true);
            repo.save(n);
        });
        return ResponseEntity.ok(Map.of("message", "Notification marquée comme lue"));
    }

    // Marquer toutes les notifications d'un utilisateur comme lues
    @PatchMapping("/user/{userId}/read-all")
    public ResponseEntity<Map<String, Object>> markAllRead(@PathVariable UUID userId) {
        List<Notification> unread = repo.findByUserIdAndIsReadFalseOrderByCreatedAtDesc(userId);
        unread.forEach(n -> n.setRead(true));
        repo.saveAll(unread);
        return ResponseEntity.ok(Map.of("message", "Toutes les notifications marquées comme lues", "updated", unread.size()));
    }

    // Notifications liées à un chèque
    @GetMapping("/cheque/{chequeId}")
    public ResponseEntity<List<Notification>> getByCheque(@PathVariable String chequeId) {
        return ResponseEntity.ok(repo.findByChequeId(chequeId));
    }

    // Créer une notification (appelé directement par cheque-service sans Kafka)
    @PostMapping("/internal/create")
    public ResponseEntity<Notification> create(@RequestBody Map<String, String> req) {
        Notification.NotificationBuilder builder = Notification.builder()
            .chequeId(req.get("chequeId"))
            .userRole(req.get("userRole"))
            .type(Notification.NotificationType.PUSH)
            .sujet(req.get("sujet"))
            .contenu(req.get("contenu"))
            .kafkaTopic(req.get("topic"))
            .statut("ENVOYE");

        String userId = req.get("userId");
        if (userId != null && !userId.isBlank()) {
            try { builder.userId(UUID.fromString(userId)); }
            catch (IllegalArgumentException ignored) {}
        }

        return ResponseEntity.ok(repo.save(builder.build()));
    }
}
