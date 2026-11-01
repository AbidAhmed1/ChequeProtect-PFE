package tn.tunicheque.cheque_service.dto.response;

import lombok.Builder;
import lombok.Data;
import tn.tunicheque.cheque_service.entity.Cheque;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.UUID;

@Data
@Builder
public class ChequeHistoryItemDTO {
    private UUID               id;
    private String             numeroCheque;
    private LocalDateTime      dateTraitement;
    private String             beneficiaireNom;
    private BigDecimal         montant;
    private Cheque.ChequeStatus statut;
    private double             scoreOcr;
    private UUID               agentId;
    private Integer            pipelineMs;
    private Boolean            fraudeDetectee;
    private String             ribEmetteur;
    private String             decisionFinale;
}