package tn.tunicheque.auth_service.exception;

public class AccountDisabledException extends RuntimeException {
    public AccountDisabledException(String message)
    {
        super(message);
    }
}