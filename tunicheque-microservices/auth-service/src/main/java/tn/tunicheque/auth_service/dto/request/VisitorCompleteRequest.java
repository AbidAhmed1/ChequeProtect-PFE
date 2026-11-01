package tn.tunicheque.auth_service.dto.request;

import jakarta.validation.constraints.*;
import lombok.Data;

@Data
public class VisitorCompleteRequest {

    @NotBlank private String sessionId;

    @NotBlank private String fullName;

    @NotBlank private String phone;   // identifiant de connexion mobile

    @Email
    private String email;             // optionnel — certains bénéficiaires n'ont pas d'email

    @NotBlank
    @Pattern(regexp = "[0-9]{6}", message = "Le PIN doit contenir 6 chiffres")
    private String pin;

    @NotBlank private String pinConfirm;

    // RIB optionnel : compte bancaire du bénéficiaire pour les virements
    @Pattern(regexp = "[0-9]{20}", message = "Le RIB doit contenir exactement 20 chiffres")
    private String rib;

    // CIN obligatoire pour les bénéficiaires sans RIB (clé d'identité KYC)
    @Pattern(regexp = "[0-9]{8}", message = "Le numéro CIN doit contenir exactement 8 chiffres")
    private String cinNumber;
}
