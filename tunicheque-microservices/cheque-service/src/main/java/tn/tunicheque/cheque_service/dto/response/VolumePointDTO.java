package tn.tunicheque.cheque_service.dto.response;

import lombok.Builder;
import lombok.Data;

@Data
@Builder
public class VolumePointDTO {
    private String date;
    private long   total;
    private long   valides;
    private long   rejetes;
}