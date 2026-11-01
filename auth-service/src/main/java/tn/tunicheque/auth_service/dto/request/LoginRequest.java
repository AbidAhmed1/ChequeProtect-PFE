package tn.tunicheque.auth_service.dto.request;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

/**
 * LoginRequest — utilisé pour web (email+password) ET mobile (phone+pin).
 * email ou phone obligatoire selon le canal.
 */
@Data
public class LoginRequest {

    // Web : email + password
    private String email;
    private String password;

    // Mobile : phone + pin (même champ password sert de PIN)
    private String phone;
}