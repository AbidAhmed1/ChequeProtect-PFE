package tn.tunicheque.cheque_service.entity;

import jakarta.persistence.*;
import lombok.*;
import java.time.LocalDateTime;
import java.util.UUID;

@Entity
@Table(name = "reclamations")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class Reclamation {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "user_id", nullable = false)
    private UUID userId;

    @Column(name = "cheque_id")
    private String chequeId;

    @Column(length = 200)
    private String objet;

    @Column(columnDefinition = "TEXT")
    private String description;

    @Builder.Default
    private String statut = "OUVERTE"; // OUVERTE | EN_COURS | TRANSMISE | RESOLUE | FERMEE

    @Column(name = "reponse_agent", columnDefinition = "TEXT")
    private String reponseAgent;

    @Builder.Default
    @Column(name = "created_at")
    private LocalDateTime createdAt = LocalDateTime.now();

    @Column(name = "updated_at")
    private LocalDateTime updatedAt;
}