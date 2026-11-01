package tn.tunicheque.notification_service.kafka;

import lombok.Data;
import java.math.BigDecimal;

/**
 * ChequeEvent — payload des 3 topics Kafka.
 * Publié par cheque-service après chaque étape clé.
 */
@Data
public class ChequeEvent {

    private String    chequeId;
    private String    decisionFinale;      // COMPLIANCE_OK | REJECTED_* | PENDING_*
    private String    beneficiaireId;      // UUID
    private String    beneficiaireNom;
    private String    tireurId;             // UUID — tireur (émetteur du chèque)
    private String    agentId;             // UUID
    private BigDecimal montant;
    private String    numeroCheque;
    private String    source;              // MOBILE | SCANNER
    private String    motifRejet;
    private String    topic;               // cheque.uploaded | pipeline.completed | cheque.validated
}
