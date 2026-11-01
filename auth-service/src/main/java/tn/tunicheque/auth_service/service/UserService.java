package tn.tunicheque.auth_service.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tn.tunicheque.auth_service.dto.request.CreateUserRequest;
import tn.tunicheque.auth_service.dto.request.UpdateUserRequest;
import tn.tunicheque.auth_service.dto.response.CreateUserResponse;
import tn.tunicheque.auth_service.dto.response.UserDTO;
import tn.tunicheque.auth_service.dto.response.UserStatsDTO;
import tn.tunicheque.auth_service.entity.User;
import tn.tunicheque.auth_service.entity.enums.Role;
import tn.tunicheque.auth_service.entity.enums.UserType;
import tn.tunicheque.auth_service.exception.EmailAlreadyExistsException;
import tn.tunicheque.auth_service.exception.UserNotFoundException;
import tn.tunicheque.auth_service.repository.UserRepository;

import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;

/**
 * UserService — CRUD complet sur les comptes utilisateurs (Admin seulement).
 *
 * FIX : findAll() utilise findByRole() (requête DB) au lieu de Java stream
 * FIX : findById() lève UserNotFoundException (géré par GlobalExceptionHandler)
 * FIX : UserType.INTERNAL pour Agent/Admin (pas WEB)
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class UserService {

    private final UserRepository         userRepository;
    private final PasswordEncoder        passwordEncoder;
    private final PasswordGeneratorService passwordGenerator;
    private final WelcomeEmailService    welcomeEmailService;

    // ── Lister ────────────────────────────────────────────────────

    public List<UserDTO> findAll(String roleFilter) {
        List<User> users;
        if (roleFilter != null && !roleFilter.isBlank()) {
            try {
                Role role = Role.valueOf(roleFilter.toUpperCase());
                // FIX : requête DB directe, plus performant que stream Java
                users = userRepository.findByRole(role);
            } catch (IllegalArgumentException e) {
                throw new IllegalArgumentException("Rôle invalide : " + roleFilter
                        + ". Valeurs acceptées : ADMIN, AGENT, BENEFICIAIRE, TIREUR");
            }
        } else {
            users = userRepository.findAll();
        }
        log.info("Liste users : {} trouvés (filtre={})", users.size(), roleFilter);
        return users.stream().map(UserDTO::from).collect(Collectors.toList());
    }

    // ── Recherche interne par RIB ou CIN (pour notifications cheque-service) ─

    public java.util.Optional<UUID> findUserIdByRib(String rib) {
        return userRepository.findByRib(rib).map(User::getId);
    }

    public java.util.Optional<UUID> findUserIdByCin(String cin) {
        return userRepository.findByCinNumber(cin).map(User::getId);
    }

    // ── Consulter ─────────────────────────────────────────────────

    public UserDTO findById(UUID id) {
        User user = userRepository.findById(id)
                .orElseThrow(() -> new UserNotFoundException(
                        "Utilisateur introuvable : " + id));
        return UserDTO.from(user);
    }

    // ── Ajouter (Admin crée Agent ou Admin) ───────────────────────

    @Transactional
    public CreateUserResponse createUser(CreateUserRequest req) {
        if (userRepository.existsByEmail(req.getEmail())) {
            throw new EmailAlreadyExistsException(
                    "Cet email est déjà utilisé. Choisissez-en un autre.");
        }

        if (req.getPhone() != null && userRepository.existsByPhone(req.getPhone())) {
            throw new RuntimeException("Ce numéro de téléphone est déjà utilisé.");
        }

        if (req.getRole() != Role.AGENT && req.getRole() != Role.ADMIN) {
            throw new IllegalArgumentException(
                    "Via cette interface, seuls les rôles AGENT et ADMIN sont autorisés.");
        }

        // Utiliser le mot de passe fourni par l'admin s'il est présent, sinon auto-générer
        String plainPassword = (req.getPassword() != null && !req.getPassword().isBlank())
                ? req.getPassword()
                : passwordGenerator.generate();

        User user = User.builder()
                .fullName(req.getFullName())
                .email(req.getEmail())
                .passwordHash(passwordEncoder.encode(plainPassword))
                .phone(req.getPhone())
                .role(req.getRole())
                .userType(UserType.INTERNAL)
                .isActive(true)
                .isVerified(true)
                .build();

        user = userRepository.save(user);
        log.info("Compte créé par admin : {} — {}", user.getEmail(), user.getRole());

        // Envoi de l'email de bienvenue avec les identifiants
        boolean emailOk = welcomeEmailService.sendWelcomeEmail(
                user.getEmail(), user.getFullName(), user.getRole(), plainPassword);

        String emailStatus = emailOk ? "SENT" : "FAILED";
        String message = emailOk
                ? "Compte créé. Email envoyé à " + user.getEmail()
                : "Compte créé. L'envoi d'email a échoué — communiquez le mot de passe manuellement.";

        return CreateUserResponse.builder()
                .user(UserDTO.from(user))
                .temporaryPassword(plainPassword)
                .emailStatus(emailStatus)
                .message(message)
                .build();
    }

    // ── Modifier ──────────────────────────────────────────────────

    @Transactional
    public UserDTO updateUser(UUID id, UpdateUserRequest req) {
        User user = userRepository.findById(id)
                .orElseThrow(() -> new UserNotFoundException(
                        "Utilisateur introuvable : " + id));

        if (req.getEmail() != null && !req.getEmail().equals(user.getEmail())) {
            if (userRepository.existsByEmail(req.getEmail()))
                throw new EmailAlreadyExistsException("Cet email est déjà utilisé.");
            user.setEmail(req.getEmail());
        }

        if (req.getPhone() != null && !req.getPhone().equals(user.getPhone())) {
            if (userRepository.existsByPhone(req.getPhone()))
                throw new RuntimeException("Ce numéro de téléphone est déjà utilisé.");
            user.setPhone(req.getPhone());
        }

        if (req.getFullName() != null && !req.getFullName().isBlank())
            user.setFullName(req.getFullName());

        if (req.getRole() != null)
            user.setRole(req.getRole());

        // Activer / désactiver
        if (req.getIsActive() != null) {
            user.setActive(req.getIsActive());
            log.info("Compte {} {}",
                    user.getEmail(), req.getIsActive() ? "activé" : "désactivé");
        }

        if (req.getNewPassword() != null && !req.getNewPassword().isBlank()) {
            if (req.getNewPassword().length() < 8)
                throw new IllegalArgumentException(
                        "Le mot de passe doit contenir au moins 8 caractères.");
            user.setPasswordHash(passwordEncoder.encode(req.getNewPassword()));
            user.setResetPasswordRequested(false);
            // Envoyer l'email de notification avec le nouveau mot de passe
            welcomeEmailService.sendPasswordChangedEmail(
                    user.getEmail(), user.getFullName(), req.getNewPassword());
        }

        user = userRepository.save(user);
        log.info("Compte mis à jour : {}", user.getId());
        return UserDTO.from(user);
    }

    // ── Désactiver (soft delete) ───────────────────────────────────

    @Transactional
    public void deactivate(UUID id) {
        User user = userRepository.findById(id)
                .orElseThrow(() -> new UserNotFoundException(
                        "Utilisateur introuvable : " + id));
        if (!user.isActive())
            throw new RuntimeException("Ce compte est déjà désactivé.");
        user.setActive(false);
        userRepository.save(user);
        log.warn("Compte désactivé : {} — {}", user.getId(), user.getEmail());
    }

    // ── Réactiver ─────────────────────────────────────────────────

    @Transactional
    public void reactivate(UUID id) {
        User user = userRepository.findById(id)
                .orElseThrow(() -> new UserNotFoundException(
                        "Utilisateur introuvable : " + id));
        user.setActive(true);
        userRepository.save(user);
        log.info("Compte réactivé : {}", user.getId());
    }
    @Transactional
    public void bloquer(UUID id, String motif, UUID adminId) {
        User user = userRepository.findById(id)
                .orElseThrow(() -> new UserNotFoundException(
                        "Agent introuvable : " + id));

        if (user.getRole() != Role.AGENT) {
            throw new IllegalArgumentException(
                    "Seuls les agents peuvent être bloqués via cette action.");
        }
        if (user.isBlocked()) {
            throw new RuntimeException("Cet agent est déjà bloqué.");
        }

        user.setBlocked(true);
        user.setActive(false);           // bloqué = inactif → login refusé
        user.setBlockReason(motif);
        user.setBlockedAt(LocalDateTime.now());
        user.setBlockedBy(adminId);
        userRepository.save(user);

        log.warn("Agent bloqué : {} — motif : {}", user.getEmail(), motif);
    }

    // ── Débloquer un agent ────────────────────────────────────────

    @Transactional
    public void debloquer(UUID id) {
        User user = userRepository.findById(id)
                .orElseThrow(() -> new UserNotFoundException(
                        "Agent introuvable : " + id));

        if (!user.isBlocked()) {
            throw new RuntimeException("Cet agent n'est pas bloqué.");
        }

        user.setBlocked(false);
        user.setActive(true);
        user.setBlockReason(null);
        user.setBlockedAt(null);
        user.setBlockedBy(null);
        userRepository.save(user);

        log.info("Agent débloqué : {}", user.getEmail());
    }

    // ── Lister les agents (actifs + bloqués) ──────────────────────
    // blocked = null   → tous les agents
    // blocked = true   → agents bloqués seulement
    // blocked = false  → agents actifs seulement

    public List<UserDTO> findAgents(Boolean blocked) {
        List<User> agents = userRepository.findByRole(Role.AGENT);

        if (blocked != null) {
            agents = agents.stream()
                    .filter(u -> u.isBlocked() == blocked)
                    .collect(Collectors.toList());
        }

        log.info("Liste agents : {} trouvés (filtre blocked={})",
                agents.size(), blocked);
        return agents.stream().map(UserDTO::from).collect(Collectors.toList());
    }

    // ── Stats globales pour le dashboard admin ────────────────────────────

    public UserStatsDTO getUserStats() {
        long totalUsers    = userRepository.count();
        long totalAgents   = userRepository.countByRole(Role.AGENT);
        long agentsActifs  = userRepository.countByRoleAndIsActiveAndIsBlocked(
                                 Role.AGENT, true, false);
        long agentsBloqués = userRepository.countByRoleAndIsBlocked(Role.AGENT, true);
        long totalAdmins   = userRepository.countByRole(Role.ADMIN);
        long totalClients  = userRepository.countByUserType(UserType.CLIENT);

        return UserStatsDTO.builder()
                .totalUsers(totalUsers)
                .totalAgents(totalAgents)
                .agentsActifs(agentsActifs)
                .agentsBloqués(agentsBloqués)
                .totalAdmins(totalAdmins)
                .totalClients(totalClients)
                .build();
    }
}