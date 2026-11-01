package tn.tunicheque.cheque_service.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import tn.tunicheque.cheque_service.entity.Reclamation;
import java.util.List;
import java.util.UUID;

public interface ReclamationRepository extends JpaRepository<Reclamation, UUID> {
    List<Reclamation> findByUserIdOrderByCreatedAtDesc(UUID userId);
    List<Reclamation> findAllByOrderByCreatedAtDesc();
}