package tn.tunicheque.auth_service.dto.request;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import lombok.Data;

@Data
public class SetPinRequest {

    @NotBlank(message = "Le sessionId est obligatoire")
    private String sessionId;

    @NotBlank(message = "Le PIN est obligatoire")
    @Pattern(regexp = "[0-9]{6}", message = "Le PIN doit contenir 6 chiffres")
    private String pin;

    @NotBlank(message = "La confirmation du PIN est obligatoire")
    private String pinConfirm;
}
