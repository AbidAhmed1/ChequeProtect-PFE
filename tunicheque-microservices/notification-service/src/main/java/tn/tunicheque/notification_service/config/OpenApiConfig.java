package tn.tunicheque.notification_service.config;

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
                        .title("TuniCheque — Notification Service")
                        .description("""
                                API de notifications (email / SMS).

                                **Topics Kafka consommés :**
                                - `cheque.uploaded` → email de confirmation de dépôt
                                - `pipeline.completed` → email résultat IA
                                - `cheque.validated` → email décision agent
                                - `reclamation.created` → email confirmation réclamation

                                Ce service est principalement event-driven (Kafka).
                                Les endpoints REST permettent la consultation de l'historique.
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
                                .description("Token JWT obtenu depuis auth-service /api/auth/login")))
                .addSecurityItem(new SecurityRequirement().addList(jwtScheme));
    }
}