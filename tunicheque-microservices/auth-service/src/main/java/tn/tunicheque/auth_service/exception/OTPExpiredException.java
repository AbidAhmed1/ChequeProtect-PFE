package tn.tunicheque.auth_service.exception;

public class OTPExpiredException extends RuntimeException {
  public OTPExpiredException(String message) {
    super(message);
  }
}