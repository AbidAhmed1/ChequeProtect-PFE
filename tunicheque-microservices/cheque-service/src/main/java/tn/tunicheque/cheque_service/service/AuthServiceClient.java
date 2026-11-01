package tn.tunicheque.cheque_service.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.util.Map;
import java.util.Optional;
import java.util.UUID;

@Service
@RequiredArgsConstructor
@Slf4j
public class AuthServiceClient {

    private final RestTemplate restTemplate;

    @Value("${services.auth-url:http://localhost:8081}")
    private String authServiceUrl;

    public record ClientInfo(String fullName, String identifier, String identifierType) {}

    public ClientInfo getClientInfo(UUID userId) {
        try {
            @SuppressWarnings("unchecked")
            Map<String, String> resp = restTemplate.getForObject(
                authServiceUrl + "/api/auth/users/internal/" + userId + "/identifier", Map.class);
            if (resp != null) {
                return new ClientInfo(
                    resp.getOrDefault("fullName",       "—"),
                    resp.getOrDefault("identifier",     "—"),
                    resp.getOrDefault("identifierType", "—")
                );
            }
        } catch (Exception e) {
            log.warn("getClientInfo userId={} : {}", userId, e.getMessage());
        }
        return new ClientInfo("—", "—", "—");
    }

    public Optional<UUID> findUserIdByRib(String rib) {
        try {
            @SuppressWarnings("unchecked")
            Map<String, String> resp = restTemplate.getForObject(
                    authServiceUrl + "/api/auth/users/internal/by-rib?rib=" + rib, Map.class);
            if (resp != null && resp.get("userId") != null) {
                return Optional.of(UUID.fromString(resp.get("userId")));
            }
        } catch (Exception e) {
            log.warn("Résolution RIB→userId échouée (rib={}) : {}", rib, e.getMessage());
        }
        return Optional.empty();
    }

    public Optional<UUID> findUserIdByCin(String cin) {
        try {
            @SuppressWarnings("unchecked")
            Map<String, String> resp = restTemplate.getForObject(
                    authServiceUrl + "/api/auth/users/internal/by-cin?cin=" + cin, Map.class);
            if (resp != null && resp.get("userId") != null) {
                return Optional.of(UUID.fromString(resp.get("userId")));
            }
        } catch (Exception e) {
            log.warn("Résolution CIN→userId échouée (cin={}) : {}", cin, e.getMessage());
        }
        return Optional.empty();
    }

    public long getAgentsActifsCount() {
        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> stats = restTemplate.getForObject(
                    authServiceUrl + "/api/auth/users/stats", Map.class);
            if (stats != null && stats.get("agentsActifs") instanceof Number nb) {
                return nb.longValue();
            }
        } catch (Exception e) {
            log.warn("Auth-service indisponible pour stats agents : {}", e.getMessage());
        }
        return 0L;
    }
}