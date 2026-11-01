package tn.tunicheque.cheque_service.dto.response;

import lombok.Builder;
import lombok.Data;

@Data
@Builder
public class AgentDashboardDTO {
    private long   chequesAujourdhui;
    private long   validesAujourdhui;
    private long   rejetesAujourdhui;
    private long   totalTraites;
    private double precisionOcrMoyenne;
    private double tempsMoyenMs;
}