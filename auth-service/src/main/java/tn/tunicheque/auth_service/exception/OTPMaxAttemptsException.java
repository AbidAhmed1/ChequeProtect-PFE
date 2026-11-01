package tn.tunicheque.auth_service.exception;

public class OTPMaxAttemptsException extends RuntimeException {
    public OTPMaxAttemptsException(String message) {
        super(message);
    }
}