package tn.tunicheque.auth_service.exception;

public class OTPNotFoundException extends RuntimeException {
    public OTPNotFoundException(String message) {
        super(message);
    }
}
