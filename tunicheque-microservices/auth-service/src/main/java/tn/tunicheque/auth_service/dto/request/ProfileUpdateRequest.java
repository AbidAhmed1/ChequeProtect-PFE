package tn.tunicheque.auth_service.dto.request;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Data
public class ProfileUpdateRequest {

    private String fullName;

    @Email(message = "Format email invalide")
    private String email;

    private String phone;

    // Changer le mot de passe (web)
    private String currentPassword;

    @Size(min = 8, message = "Le nouveau mot de passe doit contenir au moins 8 caractères")
    private String newPassword;

    // Changer le PIN (mobile — 6 chiffres)
    private String currentPin;
    private String newPin;
    private String newPinConfirm;
}