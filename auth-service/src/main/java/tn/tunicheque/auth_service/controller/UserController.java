package tn.tunicheque.auth_service.controller;

import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import tn.tunicheque.auth_service.dto.request.CreateUserRequest;
import tn.tunicheque.auth_service.dto.request.UpdateUserRequest;
import tn.tunicheque.auth_service.dto.response.CreateUserResponse;
import tn.tunicheque.auth_service.dto.response.UserDTO;
import tn.tunicheque.auth_service.dto.response.UserStatsDTO;
import tn.tunicheque.auth_service.exception.UserNotFoundException;
import tn.tunicheque.auth_service.service.UserService;

import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * UserController — Gestion des comptes par l'Administrateur.
 *
 * UC "Gérer profil agent" / "Gérer profil admin" (Tables 3.7 à 3.11)
 *
 * Tous les endpoints vérifient X-User-Role = ROLE_ADMIN
 * (injecté par l'API Gateway après validation JWT)
 */
@RestController
@RequestMapping("/api/auth/users")
@RequiredArgsConstructor
@Slf4j
public class UserController {

    private final UserService userService;

    // Helper pour vérifier le rôle Admin
    private boolean isAdmin(String role) {
        return role != null && role.contains("ADMIN");
    }

    // Retour standardisé en cas d'accès refusé
    private ResponseEntity<Map<String, String>> forbidden() {
        return ResponseEntity.status(HttpStatus.FORBIDDEN)
                .body(Map.of("error", "Accès refusé — Rôle ADMIN requis"));
    }

    // Lister tous les utilisateurs
    // ✅ ResponseEntity<?> permet de retourner soit une List<UserDTO>, soit une Map (en cas de forbidden)
    @GetMapping
    public ResponseEntity<?> getAllUsers(
            @RequestHeader(value = "X-User-Role", defaultValue = "") String role,
            @RequestParam(required = false) String roleFilter
    ) {
        if (!isAdmin(role)) return forbidden();

        try {
            List<UserDTO> users = userService.findAll(roleFilter);
            if (users.isEmpty()) {
                return ResponseEntity.ok(Map.of(
                        "users", List.of(),
                        "message", "Aucun utilisateur enregistré.",
                        "canAdd", true
                ));
            }
            return ResponseEntity.ok(users);
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }

    // Consulter un utilisateur
    @GetMapping("/{id}")
    public ResponseEntity<?> getUser(
            @PathVariable UUID id,
            @RequestHeader(value = "X-User-Role", defaultValue = "") String role
    ) {
        if (!isAdmin(role)) return forbidden();
        return ResponseEntity.ok(userService.findById(id));
    }

    // Ajouter un utilisateur — le mot de passe est auto-généré et envoyé par email
    @PostMapping
    public ResponseEntity<?> createUser(
            @RequestHeader(value = "X-User-Role", defaultValue = "") String role,
            @RequestBody @Valid CreateUserRequest req
    ) {
        if (!isAdmin(role)) return forbidden();
        try {
            CreateUserResponse response = userService.createUser(req);
            return ResponseEntity.status(HttpStatus.CREATED).body(response);
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }

    // Modifier un utilisateur
    @PutMapping("/{id}")
    public ResponseEntity<?> updateUser(
            @PathVariable UUID id,
            @RequestHeader(value = "X-User-Role", defaultValue = "") String role,
            @RequestBody @Valid UpdateUserRequest req
    ) {
        if (!isAdmin(role)) return forbidden();
        return ResponseEntity.ok(userService.updateUser(id, req));
    }

    // Désactiver un utilisateur
    @PutMapping("/{id}/bloquer")
    public ResponseEntity<?> bloquerAgent(
            @PathVariable UUID id,
            @RequestHeader(value = "X-User-Role", defaultValue = "") String role,
            @RequestHeader(value = "X-User-Id",   defaultValue = "") String adminId,
            @RequestBody Map<String, String> req) {

        if (!isAdmin(role)) return forbidden();

        String motif = req.getOrDefault("motif", "Aucun motif spécifié");
        if (motif.isBlank()) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", "Le motif de blocage est obligatoire."));
        }

        try {
            userService.bloquer(id, motif, UUID.fromString(adminId));
            return ResponseEntity.ok(Map.of(
                    "message", "Compte agent bloqué avec succès.",
                    "motif",   motif
            ));
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }

    // ── Débloquer un agent ────────────────────────────────────────

    @PutMapping("/{id}/debloquer")
    public ResponseEntity<?> debloquerAgent(
            @PathVariable UUID id,
            @RequestHeader(value = "X-User-Role", defaultValue = "") String role) {

        if (!isAdmin(role)) return forbidden();

        try {
            userService.debloquer(id);
            return ResponseEntity.ok(Map.of("message", "Compte agent débloqué avec succès."));
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }

    // ── Lister tous les agents ────────────────────────────────────
    // GET /api/auth/agents?blocked=true  → agents bloqués
    // GET /api/auth/agents?blocked=false → agents actifs
    // GET /api/auth/agents               → tous les agents

    @GetMapping("/agents")
    public ResponseEntity<?> getAgents(
            @RequestHeader(value = "X-User-Role", defaultValue = "") String role,
            @RequestParam(required = false) Boolean blocked) {

        if (!isAdmin(role)) return forbidden();

        try {
            var agents = userService.findAgents(blocked);
            if (agents.isEmpty()) {
                return ResponseEntity.ok(Map.of(
                        "agents",  java.util.List.of(),
                        "message", "Aucun agent trouvé.",
                        "canAdd",  true
                ));
            }
            return ResponseEntity.ok(Map.of("agents", agents, "total", agents.size()));
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }

    // Réactiver un utilisateur
    @PutMapping("/{id}/reactivate")
    public ResponseEntity<?> reactivateUser(
            @PathVariable UUID id,
            @RequestHeader(value = "X-User-Role", defaultValue = "") String role
    ) {
        if (!isAdmin(role)) return forbidden();
        userService.reactivate(id);
        return ResponseEntity.ok(Map.of("message", "Compte réactivé avec succès."));
    }

    // ── Stats globales (accessible en inter-service depuis cheque-service) ──

    @GetMapping("/stats")
    public ResponseEntity<UserStatsDTO> getUserStats() {
        return ResponseEntity.ok(userService.getUserStats());
    }

    // Récupérer l'email d'un utilisateur
    @GetMapping("/{id}/email")
    public ResponseEntity<?> getUserEmail(@PathVariable UUID id) {
        try {
            UserDTO user = userService.findById(id);
            return ResponseEntity.ok(Map.of(
                    "email", user.getEmail() != null ? user.getEmail() : "",
                    "fullName", user.getFullName()
            ));
        } catch (UserNotFoundException e) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .body(Map.of("error", e.getMessage()));
        }
    }

    // ── Endpoint interne — infos client par userId (appelé par cheque-service) ────────

    @GetMapping("/internal/{id}/identifier")
    public ResponseEntity<?> getUserIdentifier(@PathVariable UUID id) {
        try {
            UserDTO user = userService.findById(id);
            String identifier;
            String identifierType;
            if (user.getCinNumber() != null && !user.getCinNumber().isBlank()) {
                identifier     = user.getCinNumber();
                identifierType = "CIN";
            } else if (user.getRib() != null && !user.getRib().isBlank()) {
                identifier     = user.getRib();
                identifierType = "RIB";
            } else if (user.getPhone() != null && !user.getPhone().isBlank()) {
                identifier     = user.getPhone();
                identifierType = "TEL";
            } else {
                identifier     = "—";
                identifierType = "—";
            }
            return ResponseEntity.ok(Map.of(
                "fullName",       user.getFullName() != null ? user.getFullName() : "—",
                "identifier",     identifier,
                "identifierType", identifierType
            ));
        } catch (UserNotFoundException e) {
            return ResponseEntity.ok(Map.of("fullName","—","identifier","—","identifierType","—"));
        }
    }

    // ── Endpoints internes — résolution RIB/CIN → userId (appelé par cheque-service) ──

    @GetMapping("/internal/by-rib")
    public ResponseEntity<Map<String, String>> getUserIdByRib(@RequestParam String rib) {
        return userService.findUserIdByRib(rib)
                .map(id -> ResponseEntity.ok(Map.of("userId", id.toString())))
                .orElse(ResponseEntity.notFound().<Map<String, String>>build());
    }

    @GetMapping("/internal/by-cin")
    public ResponseEntity<Map<String, String>> getUserIdByCin(@RequestParam String cin) {
        return userService.findUserIdByCin(cin)
                .map(id -> ResponseEntity.ok(Map.of("userId", id.toString())))
                .orElse(ResponseEntity.notFound().<Map<String, String>>build());
    }
}