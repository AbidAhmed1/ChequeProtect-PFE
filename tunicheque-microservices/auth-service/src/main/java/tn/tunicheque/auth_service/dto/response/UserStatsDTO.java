package tn.tunicheque.auth_service.dto.response;

import lombok.Builder;
import lombok.Data;

@Data
@Builder
public class UserStatsDTO {
    private long totalUsers;
    private long totalAgents;
    private long agentsActifs;
    private long agentsBloqués;
    private long totalAdmins;
    private long totalClients;
}