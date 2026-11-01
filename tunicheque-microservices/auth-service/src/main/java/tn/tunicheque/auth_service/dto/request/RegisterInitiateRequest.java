package tn.tunicheque.auth_service.dto.request;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@AllArgsConstructor // ✅ Crée un constructeur avec tous les arguments
@NoArgsConstructor  // ✅ Crée un constructeur vide
public class RegisterInitiateRequest {

    @NotBlank(message = "Le numéro de téléphone est obligatoire")
    @Pattern(regexp = "\\+216[0-9]{8}", message = "Format invalide — ex: +21620123456")
    private String telephone;
}