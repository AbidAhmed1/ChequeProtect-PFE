package tn.tunicheque.auth_service.security;

import io.jsonwebtoken.*;
import io.jsonwebtoken.security.Keys;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.stereotype.Service;
import tn.tunicheque.auth_service.entity.User;

import java.util.Date;
import java.util.Map;

@Service
public class JwtService {

    @Value("${jwt.secret}")
    private String secret;

    @Value("${jwt.expiration-ms}")
    private long expirationMs;

    /**
     * Génère un JWT signé contenant les claims nécessaires à l'autorisation.
     *
     * Claims embarqués :
     *   • "role"      — CLIENT (avec RIB) ou BENEFICIAIRE (KYC sans RIB).
     *                   L'application mobile utilise ce claim pour adapter l'interface
     *                   (Tireur + Bénéficiaire vs réception uniquement).
     *   • "user_type" — toujours CLIENT pour les utilisateurs mobiles (≠ AGENT/ADMIN).
     *   • "user_id"   — UUID de l'utilisateur pour les appels inter-services.
     *
     * La logique métier (quel rôle est attribué) est gérée en amont par
     * AuthService / VisitorKycService — generateToken ne modifie pas les rôles.
     */
    public String generateToken(User user) {
        return Jwts.builder()
                .subject(user.getUsername())
                .claim("role", user.getRole().name())       // CLIENT ou BENEFICIAIRE
                .claim("user_type", user.getUserType().name())
                .claim("user_id", user.getId().toString())
                .issuedAt(new Date())
                .expiration(new Date(System.currentTimeMillis() + expirationMs))
                .signWith(Keys.hmacShaKeyFor(secret.getBytes()), Jwts.SIG.HS256)
                .compact();
    }

    public String generateTempRegistrationToken(String sessionId, String telephone) {
        return Jwts.builder()
                .subject("registration:" + sessionId)
                .claim("sessionId", sessionId)
                .claim("telephone", telephone)
                .claim("type", "INSCRIPTION_TEMP")
                .issuedAt(new Date())
                .expiration(new Date(System.currentTimeMillis() + 15 * 60 * 1000))
                .signWith(Keys.hmacShaKeyFor(secret.getBytes()), Jwts.SIG.HS256)
                .compact();
    }

    public Claims extractAllClaims(String token) {
        return Jwts.parser()
                .verifyWith(Keys.hmacShaKeyFor(secret.getBytes()))
                .build()
                .parseSignedClaims(token)
                .getPayload();
    }

    public String extractUserId(String token) {
        return extractAllClaims(token).get("user_id", String.class);
    }

    public boolean isTokenValid(String token, UserDetails user) {
        Claims claims = extractAllClaims(token);
        return claims.getSubject().equals(user.getUsername())
                && claims.getExpiration().after(new Date());
    }
}