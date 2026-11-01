package tn.tunicheque.auth_service.service;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.util.Map;
import java.util.UUID;

/**
 * Appelle cheque-service pour lier les chèques existants au nouveau tireur.
 * Utilisé lors de la création de compte via RIB.
 */
@Service
@Slf4j
public class ChequeServiceClient {

    private final RestTemplate restTemplate = new RestTemplate();

    @Value("${services.cheque-url:http://localhost:8082}")
    private String chequeServiceUrl;

    public void linkTireur(String rib, UUID userId) {
        try {
            String url = chequeServiceUrl
                + "/api/cheques/internal/link-tireur?rib=" + rib
                + "&userId=" + userId;
            restTemplate.postForObject(url, null, Map.class);
            log.info("linkTireur appelé : rib={} userId={}", rib, userId);
        } catch (Exception e) {
            log.warn("linkTireur échoué (cheque-service indisponible) : {}", e.getMessage());
        }
    }
}
