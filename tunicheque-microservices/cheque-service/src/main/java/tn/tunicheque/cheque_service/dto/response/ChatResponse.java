package tn.tunicheque.cheque_service.dto.response;

import lombok.AllArgsConstructor;
import lombok.Data;

@Data
@AllArgsConstructor
public class
ChatResponse {
    private String reply;
    // GREETING | GATHERING_INFO | RECLAMATION_READY | ERROR
    private String intent;
}