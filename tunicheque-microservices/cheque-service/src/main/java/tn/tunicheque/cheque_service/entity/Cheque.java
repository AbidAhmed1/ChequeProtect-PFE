package tn.tunicheque.cheque_service.entity;

import jakarta.persistence.*;
import lombok.*;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.UUID;

@Entity
@Table(name = "cheques")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class Cheque {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "numero_cheque")
    private String numeroCheque;

    @Column(name = "image_recto_url", nullable = false)
    private String imageRectoUrl;

    @Column(name = "image_verso_url")
    private String imageVersoUrl;

    @Column(name = "montant_extrait", precision = 15, scale = 3)
    private BigDecimal montantExtrait;

    @Column(name = "montant_lettres", columnDefinition = "TEXT")
    private String montantLettres;

    @Column(name = "beneficiaire_nom", length = 200)
    private String beneficiaireNom;

    @Column(name = "emetteur_nom", length = 200)
    private String emetteurNom;

    @Column(name = "date_emission")
    private LocalDate dateEmission;

    @Column(name = "rib_emetteur", length = 30)
    private String ribEmetteur;

    @Column(name = "qr_data", columnDefinition = "TEXT")
    private String qrData;

    @Enumerated(EnumType.STRING)
    @Column(name = "status")
    @Builder.Default
    private ChequeStatus status = ChequeStatus.EN_ATTENTE;

    @Column(name = "decision_finale", length = 50)
    private String decisionFinale;

    @Column(name = "source", length = 10)
    @Builder.Default
    private String source = "MOBILE";

    // UUIDs des users (pas de FK : bases séparées)
    @Column(name = "beneficiaire_id")
    private UUID beneficiaireId;

    @Column(name = "tireur_id")
    private UUID tireurId;

    @Column(name = "agent_id")
    private UUID agentId;

    @Column(name = "bank_account_id")
    private UUID bankAccountId;

    @Column(name = "ai_score_global", precision = 5, scale = 4)
    private BigDecimal aiScoreGlobal;

    @Column(name = "fraude_detectee")
    @Builder.Default
    private Boolean fraudeDetectee = false;

    @Column(name = "motif_rejet", columnDefinition = "TEXT")
    private String motifRejet;

    @Column(name = "pipeline_ms")
    private Integer pipelineMs;

    @Column(name = "created_at")
    @Builder.Default
    private LocalDateTime createdAt = LocalDateTime.now();

    @Column(name = "validated_at")
    private LocalDateTime validatedAt;

    public enum ChequeStatus {
        EN_ATTENTE, EN_TRAITEMENT, VALIDE, REJETE, FRAUDE_DETECTEE
    }
}