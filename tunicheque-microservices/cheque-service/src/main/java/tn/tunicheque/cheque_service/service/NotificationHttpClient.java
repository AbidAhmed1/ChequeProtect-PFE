package tn.tunicheque.cheque_service.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.util.HashMap;
import java.util.Map;

@Service
@RequiredArgsConstructor
@Slf4j
public class NotificationHttpClient {

    private final RestTemplate restTemplate;

    @Value("${notification.service.url:http://localhost:8085}")
    private String notificationServiceUrl;

    public void send(String userId, String chequeId, String userRole,
                     String sujet, String contenu, String topic) {
        try {
            Map<String, String> body = new HashMap<>();
            if (userId   != null) body.put("userId",   userId);
            if (chequeId != null) body.put("chequeId", chequeId);
            if (userRole != null) body.put("userRole", userRole);
            if (sujet    != null) body.put("sujet",    sujet);
            if (contenu  != null) body.put("contenu",  contenu);
            if (topic    != null) body.put("topic",    topic);

            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            HttpEntity<Map<String, String>> request = new HttpEntity<>(body, headers);

            restTemplate.postForEntity(
                notificationServiceUrl + "/api/notifications/internal/create",
                request, Object.class);
            log.info("Notification envoyée → userId={} sujet={}", userId, sujet);
        } catch (Exception e) {
            log.warn("Notification service indisponible : {}", e.getMessage());
        }
    }
}
