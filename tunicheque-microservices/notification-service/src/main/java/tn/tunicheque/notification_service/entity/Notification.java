package tn.tunicheque.notification_service.entity;

import jakarta.persistence.*;
import lombok.*;
import java.time.LocalDateTime;
import java.util.UUID;

@Entity
@Table(name = "notifications")
@Data @Builder @NoArgsConstructor @AllArgsConstructor
public class Notification {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "user_id", nullable = false)
    private UUID userId;

    @Column(name = "cheque_id")
    private String chequeId;

    @Column(name = "user_role", length = 20)
    private String userRole;  // BENEFICIAIRE | AGENT | TIREUR

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 10)
    private NotificationType type;

    @Column(length = 200)
    private String sujet;

    @Column(columnDefinition = "TEXT")
    private String contenu;

    @Column(length = 50)
    @Builder.Default
    private String statut = "ENVOYE";  // ENVOYE | ECHEC | PENDING

    @Column(name = "kafka_topic", length = 60)
    private String kafkaTopic;

    @Column(name = "error_message", columnDefinition = "TEXT")
    private String errorMessage;

    @Builder.Default
    @Column(name = "is_read")
    private boolean isRead = false;

    @Column(name = "created_at")
    @Builder.Default
    private LocalDateTime createdAt = LocalDateTime.now();

    public enum NotificationType { EMAIL, SMS, PUSH }
}
