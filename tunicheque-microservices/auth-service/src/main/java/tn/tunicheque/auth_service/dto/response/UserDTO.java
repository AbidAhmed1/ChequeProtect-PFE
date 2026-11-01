package tn.tunicheque.auth_service.dto.response;

import lombok.*;
import tn.tunicheque.auth_service.entity.User;
import tn.tunicheque.auth_service.entity.enums.Role;
import tn.tunicheque.auth_service.entity.enums.UserType;

import java.time.LocalDateTime;
import java.util.UUID;

/**
 * UserDTO — DTO de réponse pour les données utilisateur.
 * FIX : id = UUID (cohérent avec User.id = UUID)
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class UserDTO {

    private UUID   id;
    private String email;
    private String fullName;
    private String phone;
    private String cinNumber;
    private String rib;
    private Role   role;
    private UserType userType;
    private boolean isActive;
    private boolean isVerified;
    private boolean resetPasswordRequested;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;

    public static UserDTO from(User user) {
        return UserDTO.builder()
                .id(user.getId())
                .email(user.getEmail())
                .fullName(user.getFullName())
                .phone(user.getPhone())
                .cinNumber(user.getCinNumber())
                .rib(user.getRib())
                .role(user.getRole())
                .userType(user.getUserType())
                .isActive(user.isActive())
                .isVerified(user.isVerified())
                .resetPasswordRequested(user.isResetPasswordRequested())
                .createdAt(user.getCreatedAt())
                .updatedAt(user.getUpdatedAt())
                .build();
    }
}