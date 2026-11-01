package tn.tunicheque.cheque_service.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;
import tn.tunicheque.cheque_service.entity.AiResult;

import java.util.List;
import java.util.UUID;

@Repository
public interface AiResultRepository extends JpaRepository<AiResult, UUID> {

    List<AiResult> findByChequeIdOrderByCreatedAtAsc(UUID chequeId);

    void deleteByChequeId(UUID chequeId);
}