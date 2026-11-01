package tn.tunicheque.auth_service.dto.request;

import jakarta.validation.constraints.Email;
import lombok.Data;
import tn.tunicheque.auth_service.entity.enums.Role;

@Data
public class UpdateUserRequest {

    private String fullName;

    @Email(message = "Format email invalide")
    private String email;

    private String phone;

    private Role role;

    private Boolean isActive;   // pour activer/désactiver

    // Nouveau mot de passe (optionnel)
    private String newPassword;
}