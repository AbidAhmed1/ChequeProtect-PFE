package tn.tunicheque.notification_service.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

/**
 * MailConfig — JavaMailSender auto-configuré par Spring Boot via application.yml.
 * Ce bean expose RestTemplate pour appeler auth-service.
 */
@Configuration
public class MailConfig {

    @Bean
    public RestTemplate restTemplate() {
        return new RestTemplate();
    }
}
