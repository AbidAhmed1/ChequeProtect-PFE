package tn.tunicheque.auth_service.service;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.crypto.password.PasswordEncoder;
import tn.tunicheque.auth_service.dto.request.LoginRequest;
import tn.tunicheque.auth_service.dto.response.AuthResponse;
import tn.tunicheque.auth_service.entity.User;
import tn.tunicheque.auth_service.entity.enums.Role;
import tn.tunicheque.auth_service.entity.enums.UserType;
import tn.tunicheque.auth_service.exception.AccountDisabledException;
import tn.tunicheque.auth_service.repository.UserRepository;
import tn.tunicheque.auth_service.security.JwtService;

import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class AuthServiceTest {

    @Mock UserRepository  userRepo;
    @Mock JwtService      jwtService;
    @Mock PasswordEncoder passwordEncoder;

    @InjectMocks AuthService authService;

    private User makeAgent() {
        return User.builder()
                .id(UUID.fromString("aaaaaaaa-0000-0000-0000-000000000001"))
                .email("agent@bh.tn")
                .passwordHash("$2a$12$hashedPassword")
                .role(Role.AGENT)
                .userType(UserType.INTERNAL)
                .isActive(true)
                .build();
    }

    private User makeBlockedAgent() {
        return User.builder()
                .id(UUID.fromString("aaaaaaaa-0000-0000-0000-000000000001"))
                .email("agent@bh.tn")
                .passwordHash("$2a$12$hashedPassword")
                .role(Role.AGENT)
                .userType(UserType.INTERNAL)
                .isActive(false)
                .build();
    }

    private LoginRequest loginRequest(String email, String password) {
        LoginRequest req = new LoginRequest();
        req.setEmail(email);
        req.setPassword(password);
        return req;
    }

    @Test
    void loginWeb_retourneJWT_quandCredentialsCorrects() {
        User agent = makeAgent();

        when(userRepo.findByEmail("agent@ChéqueProtect.tn")).thenReturn(Optional.of(agent));
        when(passwordEncoder.matches("Agent@2026", "$2a$12$hashedPassword")).thenReturn(true);
        when(jwtService.generateToken(agent)).thenReturn("eyJhbGciOiJIUzI1NiJ9.mockToken");

        AuthResponse result = authService.loginWeb(loginRequest("agent@ChéqueProtect.tn", "Agent@2026"));

        assertThat(result.getToken()).isEqualTo("eyJhbGciOiJIUzI1NiJ9.mockToken");
        assertThat(result.getRole()).isEqualTo("AGENT");
        assertThat(result.getExpiresIn()).isGreaterThan(0);
        verify(jwtService).generateToken(argThat(u -> "agent@ChéqueProtect.tn".equals(u.getEmail())));
    }

    @Test
    void loginWeb_leveAccountDisabledException_quandCompteDesactive() {


        when(userRepo.findByEmail("agent@bh.tn")).thenReturn(Optional.of(makeBlockedAgent()));

        assertThatThrownBy(
                () -> authService.loginWeb(loginRequest("agent@bh.tn", "n'importe-quoi")))
                .isInstanceOf(AccountDisabledException.class)
                .hasMessageContaining("désactivé");

        verifyNoInteractions(passwordEncoder);
        verifyNoInteractions(jwtService);
    }
}
