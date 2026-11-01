package tn.tunicheque.ai_tunicheque_backend.controller;

import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import tn.tunicheque.ai_tunicheque_backend.dto.request.LoginRequest;
import tn.tunicheque.ai_tunicheque_backend.dto.response.AuthResponse;
import tn.tunicheque.ai_tunicheque_backend.service.AuthService;

@RestController
@RequestMapping("/api/auth")
@RequiredArgsConstructor
public class AuthController {

    private final AuthService authService;

    @PostMapping("/login")
    public ResponseEntity<AuthResponse> login(
            @Valid @RequestBody LoginRequest req) {
        return ResponseEntity.ok(authService.loginWeb(req));
    }

    @GetMapping("/health")
    public ResponseEntity<String> health() {
        return ResponseEntity.ok("TuniCheque API OK");
    }
}