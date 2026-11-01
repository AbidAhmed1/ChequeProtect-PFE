package tn.tunicheque.auth_service.dto.request;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import lombok.Data;

@Data
public class RibInitiateRequest {

    @NotBlank(message = "Le RIB est obligatoire")
    @Pattern(regexp = "[0-9]{20}", message = "Le RIB doit contenir exactement 20 chiffres")
    private String rib;
}
