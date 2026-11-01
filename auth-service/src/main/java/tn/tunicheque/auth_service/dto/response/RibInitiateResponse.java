package tn.tunicheque.auth_service.dto.response;

import lombok.*;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class RibInitiateResponse {

    private String sessionId;
    private String telephoneMasque;   // "+216 ** ****35"
    private String message;
    private int    expiresInSeconds;  // 120
}
