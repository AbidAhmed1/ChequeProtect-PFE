package tn.tunicheque.cheque_service.dto.request;

import lombok.Data;

@Data
public class UpdateStatutReclamationRequest {
    private String statut;
    private String reponseAgent;
}
