package tn.tunicheque.cheque_service.dto.response;

import lombok.Builder;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.UUID;

@Data
@Builder
public class FraudeAlertDTO {
    private UUID          chequeId;
    private String        numeroCheque;
    private BigDecimal    montant;
    private String        beneficiaireNom;
    private LocalDateTime detecteAt;
    private String        motif;
}