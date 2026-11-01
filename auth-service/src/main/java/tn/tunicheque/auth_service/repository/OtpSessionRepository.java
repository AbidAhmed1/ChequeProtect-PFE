package tn.tunicheque.auth_service.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;
import tn.tunicheque.auth_service.entity.OtpSession;
import tn.tunicheque.auth_service.entity.enums.OtpStatus;

import java.util.Optional;
import java.util.UUID;

@Repository
public interface OtpSessionRepository extends JpaRepository<OtpSession, UUID> {

    Optional<OtpSession> findByIdAndStatus(UUID id, OtpStatus status);

    // Vérifier si un OTP PENDING existe déjà pour ce téléphone
    boolean existsByTelephoneAndStatus(String telephone, OtpStatus status);

    // Supprimer les anciennes sessions d'un téléphone
    void deleteByTelephone(String telephone);
}