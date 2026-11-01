package tn.tunicheque.auth_service.dto.request;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.Data;
import tn.tunicheque.auth_service.entity.enums.Role;

@Data
public class CreateUserRequest {

    @NotBlank(message = "Le nom complet est obligatoire")
    private String fullName;

    @NotBlank(message = "L'email professionnel est obligatoire")
    @Email(message = "Format email invalide")
    private String email;

    // Le mot de passe N'EST PLUS fourni par l'admin :
    // il est auto-généré par PasswordGeneratorService et envoyé par email.
    private String password;

    private String phone;

    @NotNull(message = "Le rôle est obligatoire")
    private Role role;   // ADMIN ou AGENT
}