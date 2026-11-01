package tn.tunicheque.auth_service.dto.response;

import lombok.*;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class OtpInitiateResponse {
    private String sessionId;        // UUID de la session OTP
    private String message;          // "Code OTP envoyé au +216..."
    private int    expiresInSeconds; // 120
}