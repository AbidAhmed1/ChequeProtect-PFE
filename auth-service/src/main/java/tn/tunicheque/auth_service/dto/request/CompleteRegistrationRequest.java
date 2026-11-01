package tn.tunicheque.auth_service.dto.request;

import jakarta.validation.constraints.*;
import lombok.Data;

@Data
public class CompleteRegistrationRequest {

    @NotBlank(message = "Le nom est obligatoire")
    private String nom;

    @NotBlank(message = "Le prénom est obligatoire")
    private String prenom;

    @NotBlank(message = "Le CIN est obligatoire")
    @Pattern(regexp = "[0-9]{8}", message = "Le CIN doit contenir 8 chiffres")
    private String cin;

    @NotBlank(message = "L'email est obligatoire")
    @Email(message = "Format email invalide")
    private String email;

    @NotBlank(message = "Le PIN est obligatoire")
    @Pattern(regexp = "[0-9]{6}", message = "Le PIN doit contenir 6 chiffres exactement")
    private String pin;

    @NotBlank(message = "La confirmation du PIN est obligatoire")
    private String pinConfirm;

    // Photos CIN en base64 (optionnelles en DEV)
    private String cinRectoBase64;
    private String cinVersoBase64;
}