package tn.tunicheque.auth_service.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;
import tn.tunicheque.auth_service.entity.BankAccount;

import java.util.Optional;
import java.util.UUID;

@Repository
public interface BankAccountRepository extends JpaRepository<BankAccount, UUID> {

    Optional<BankAccount> findByRib(String rib);

    boolean existsByRib(String rib);

    boolean existsByTelephone(String telephone);
}
