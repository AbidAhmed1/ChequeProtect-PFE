package tn.tunicheque.auth_service.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;
import tn.tunicheque.auth_service.entity.User;
import tn.tunicheque.auth_service.entity.enums.Role;
import tn.tunicheque.auth_service.entity.enums.UserType;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Repository
public interface UserRepository extends JpaRepository<User, UUID> {

    Optional<User> findByEmail(String email);
    Optional<User> findByPhone(String phone);
    Optional<User> findFirstByPhone(String phone);
    Optional<User> findByRib(String rib);
    Optional<User> findByCinNumber(String cinNumber);

    boolean existsByEmail(String email);
    boolean existsByPhone(String phone);
    boolean existsByCinNumber(String cinNumber);

    // Pour filtrage par rôle côté base (plus performant que Java stream)
    List<User> findByRole(Role role);
    List<User> findByIsActive(boolean isActive);

    // ── Comptage pour stats dashboard ─────────────────────────────────────
    long countByRole(Role role);
    long countByUserType(UserType userType);
    long countByRoleAndIsBlocked(Role role, boolean isBlocked);
    long countByRoleAndIsActiveAndIsBlocked(Role role, boolean isActive, boolean isBlocked);
}