package tn.tunicheque.auth_service.exception;

public class CINAlreadyExistsException extends RuntimeException {
    public CINAlreadyExistsException(String message) {
        super(message);
    }
}
