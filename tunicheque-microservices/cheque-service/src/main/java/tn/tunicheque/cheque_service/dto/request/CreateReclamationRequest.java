package tn.tunicheque.cheque_service.dto.request;

import lombok.Data;

@Data
public class CreateReclamationRequest {
    private String chequeId;
    private String objet;
    private String description;
}