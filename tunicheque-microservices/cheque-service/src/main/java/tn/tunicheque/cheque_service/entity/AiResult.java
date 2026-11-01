package tn.tunicheque.cheque_service.entity;

import jakarta.persistence.*;
import lombok.*;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.UUID;

@Entity
@Table(name = "ai_results",
        uniqueConstraints = @UniqueConstraint(columnNames = {"cheque_id", "phase"}))
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AiResult {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "cheque_id", nullable = false)
    private UUID chequeId;

    @Enumerated(EnumType.STRING)
    @Column(name = "phase", nullable = false)
    private Phase phase;

    @Column(name = "score", precision = 5, scale = 4)
    private BigDecimal score;

    @Column(name = "passed")
    @Builder.Default
    private Boolean passed = false;

    @Column(name = "details", columnDefinition = "TEXT")
    private String details;

    @Column(name = "decision", length = 50)
    private String decision;

    @Column(name = "duration_ms")
    private Integer durationMs;

    @Column(name = "created_at")
    @Builder.Default
    private LocalDateTime createdAt = LocalDateTime.now();

    public enum Phase {
        identification, compliance, ocr, signature
    }
}