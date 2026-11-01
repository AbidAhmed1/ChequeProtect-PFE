package tn.tunicheque.cheque_service.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

import java.time.Duration;
import org.springframework.boot.web.client.RestTemplateBuilder;

@Configuration
public class AppConfig {

    @Value("${ai.service.timeout-seconds:120}")
    private int timeoutSeconds;

    @Bean
    public RestTemplate restTemplate(RestTemplateBuilder builder) {
        return builder
                .connectTimeout(Duration.ofSeconds(30))
                .readTimeout(Duration.ofSeconds(timeoutSeconds))
                .build();
    }
}