package tn.tunicheque.notification_service.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.time.Instant;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * AuthServiceClient — récupère l'email d'un user depuis auth-service.
 * Cache en mémoire 5 minutes pour éviter un appel HTTP par notification.
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class AuthServiceClient {

    private final RestTemplate restTemplate;

    @Value("${services.auth-url:http://localhost:8081}")
    private String authServiceUrl;

    // Cache : userId → email, avec timestamp d'expiration (5 min)
    private record CacheEntry(String email, Instant expiresAt) {
        boolean isValid() { return Instant.now().isBefore(expiresAt); }
    }
    private final ConcurrentHashMap<String, CacheEntry> emailCache = new ConcurrentHashMap<>();
    private static final long CACHE_TTL_SECONDS = 300; // 5 minutes

    public String getEmail(String userId) {
        if (userId == null || userId.isBlank()) return null;

        // Vérifier le cache d'abord
        CacheEntry cached = emailCache.get(userId);
        if (cached != null && cached.isValid()) {
            return cached.email();
        }

        // Appel HTTP auth-service
        try {
            String url = authServiceUrl + "/api/auth/users/" + userId + "/email";
            @SuppressWarnings("unchecked")
            Map<String, String> resp = restTemplate.getForObject(url, Map.class);
            if (resp != null && resp.get("email") != null && !resp.get("email").isBlank()) {
                String email = resp.get("email");
                emailCache.put(userId, new CacheEntry(email,
                    Instant.now().plusSeconds(CACHE_TTL_SECONDS)));
                return email;
            }
        } catch (Exception e) {
            log.warn("Impossible de récupérer email pour userId={} : {}", userId, e.getMessage());
        }
        return null;
    }
}
