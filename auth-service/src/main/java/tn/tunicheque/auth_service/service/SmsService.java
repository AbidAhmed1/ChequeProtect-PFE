package tn.tunicheque.auth_service.service;

public interface SmsService {
    void send(String toPhone, String message);
}
