package tn.tunicheque.auth_service.service;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.util.List;
import java.util.Map;

/**
 * InfobipSmsService — Envoi de SMS OTP via l'API REST Infobip (gratuit).
 *
 * Inscription gratuite (sans carte bancaire) : https://www.infobip.com
 * Dashboard → API Keys → copier API_KEY et BASE_URL
 *
 * Configuration dans application.yml :
 *   infobip.api-key   : votre_api_key
 *   infobip.base-url  : https://XXXXX.api.infobip.com
 *   infobip.enabled   : true
 *
 * En mode désactivé (enabled: false), le code OTP est affiché dans les logs.
 */
@Service
@Slf4j
public class InfobipSmsService implements SmsService {

    @Value("${infobip.api-key:}")
    private String apiKey;

    @Value("${infobip.base-url:}")
    private String baseUrl;

    @Value("${infobip.enabled:false}")
    private boolean enabled;

    private final RestTemplate restTemplate = new RestTemplate();

    @Override
    public void send(String toPhone, String message) {
        if (!enabled) {
            log.info("[OTP-SIMULÉ] → {} : {}", toPhone, message);
            return;
        }

        try {
            String url = baseUrl + "/sms/2/text/advanced";

            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            headers.setAccept(List.of(MediaType.APPLICATION_JSON));
            headers.set("Authorization", "App " + apiKey);

            Map<String, Object> destination = Map.of("to", toPhone);
            Map<String, Object> smsMessage = Map.of(
                    "destinations", List.of(destination),
                    "from", "TuniCheque",
                    "text", message
            );
            Map<String, Object> body = Map.of("messages", List.of(smsMessage));

            HttpEntity<Map<String, Object>> request = new HttpEntity<>(body, headers);
            ResponseEntity<Map> response = restTemplate.exchange(url, HttpMethod.POST, request, Map.class);

            log.info("SMS Infobip envoyé → {} | Statut HTTP: {}", toPhone, response.getStatusCode());

        } catch (Exception e) {
            log.error("Échec envoi SMS Infobip → {} : {}", toPhone, e.getMessage());
            throw new RuntimeException("Impossible d'envoyer le SMS. Vérifiez votre configuration Infobip.");
        }
    }
}
