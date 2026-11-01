package tn.tunicheque.auth_service.config;

import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiConfig {

    @Bean
    public OpenAPI openAPI() {
        final String jwtScheme = "bearerAuth";

        return new OpenAPI()
                .info(new Info()
                        .title("TuniCheque — Auth Service")
                        .description("""
                                API d'authentification et de gestion des utilisateurs.

                                **Rôles :**
                                - `ADMIN` — gestion des agents, statistiques, supervision
                                - `AGENT` — traitement des chèques
                                - `TIREUR` / `BENEFICIAIRE` — espace client mobile

                                **Flux login web :** `POST /api/auth/login` → Bearer token
                                """)
                        .version("1.0.0")
                        .contact(new Contact()
                                .name("Équipe TuniCheque")
                                .email("tunicheque@esen.tn")))
                .components(new Components()
                        .addSecuritySchemes(jwtScheme, new SecurityScheme()
                                .name(jwtScheme)
                                .type(SecurityScheme.Type.HTTP)
                                .scheme("bearer")
                                .bearerFormat("JWT")
                                .description("Collez ici le token reçu depuis /api/auth/login (sans le préfixe 'Bearer ')")))
                .addSecurityItem(new SecurityRequirement().addList(jwtScheme));
    }
}