package tn.tunicheque.auth_service.dto.response;

import lombok.*;

@Data
@Builder
@AllArgsConstructor
@NoArgsConstructor
public class AuthResponse {

    private String token;

    // ✅ @Builder.Default : conserve "Bearer" quand on utilise .builder()
    @Builder.Default
    private String tokenType = "Bearer";

    private String role;
    private String userType;
    private long expiresIn;
}