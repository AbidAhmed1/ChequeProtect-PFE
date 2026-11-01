package tn.tunicheque.auth_service.dto.response;

import lombok.Builder;
import lombok.Data;

/**
 * Réponse à la création d'un compte interne (ADMIN / AGENT).
 *
 * Le mot de passe temporaire est retourné ici à titre de secours (si l'email
 * échoue, l'administrateur peut le communiquer manuellement).
 */
@Data
@Builder
public class CreateUserResponse {
    private UserDTO user;
    private String  temporaryPassword;
    private String  emailStatus;   // "SENT" | "FAILED"
    private String  message;
}