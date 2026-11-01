package tn.tunicheque.cheque_service.dto.response;

import lombok.Builder;
import lombok.Data;

import java.math.BigDecimal;

@Data
@Builder
public class MobileStatsDTO {

    // Dépôts (bénéficiaire)
    private long       totalCheques;
    private long       enTraitement;
    private long       valides;
    private long       rejetes;
    private long       enAttente;
    private BigDecimal montantValide;   // somme des chèques VALIDE

    // Émissions (tireur)
    private long       totalEmissions;
    private long       emissionsEnAttente;
    private long       emissionsValidees;
    private BigDecimal montantEnCours;  // somme des chèques EN_ATTENTE/EN_TRAITEMENT tireur
}
