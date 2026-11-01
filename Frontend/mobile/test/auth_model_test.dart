import 'package:flutter_test/flutter_test.dart';
import 'package:chequepro_app/models/user.dart';

void main() {

  group('AuthResponse.fromJson', () {

    test('extrait correctement token, rôle et durée depuis la réponse backend', () {
      final json = {
        'token':     'eyJhbGciOiJIUzI1NiJ9.mobilePinToken',
        'role':      'CLIENT',
        'userType':  'CLIENT',
        'expiresIn': 28800,
      };

      final auth = AuthResponse.fromJson(json);

      expect(auth.token,     equals('eyJhbGciOiJIUzI1NiJ9.mobilePinToken'));
      expect(auth.role,      equals('CLIENT'));
      expect(auth.userType,  equals('CLIENT'));
      expect(auth.expiresIn, equals(28800));
    });

    test('utilise la valeur par défaut expiresIn=86400 si absent du JSON', () {
      final json = {
        'token':    'eyJhbGciOiJIUzI1NiJ9.token',
        'role':     'CLIENT',
        'userType': 'CLIENT',
      };

      final auth = AuthResponse.fromJson(json);

      expect(auth.expiresIn, equals(86400));
    });
  });

  group('User.fromJson', () {

    test('reconstruit le profil complet depuis la réponse GET /api/auth/me', () {
      final json = {
        'id':         'ddf4445f-7201-4839-8b47-25d61226004e',
        'fullName':   'Salma Kammoun',
        'email':      'salma.k@mail.tn',
        'phone':      '+21698000001',
        'role':       'CLIENT',
        'userType':   'CLIENT',
        'isActive':   true,
        'isVerified': true,
        'rib':        '07152781829876246775',
        'cinNumber':  '12345678',
      };

      final user = User.fromJson(json);

      expect(user.id,       equals('ddf4445f-7201-4839-8b47-25d61226004e'));
      expect(user.fullName, equals('Salma Kammoun'));
      expect(user.role,     equals('CLIENT'));
      expect(user.rib,      equals('07152781829876246775'));
      expect(user.isActive, isTrue);
    });

    test('displayName utilise le téléphone si fullName est vide', () {
      final json = {
        'id':         'aaaaaaaa-0000-0000-0000-000000000001',
        'fullName':   '',
        'phone':      '+21698000099',
        'role':       'CLIENT',
        'userType':   'CLIENT',
        'isActive':   true,
        'isVerified': false,
      };

      final user = User.fromJson(json);

      expect(user.displayName, equals('+21698000099'));
    });
  });

  group('OtpInitiateResponse.fromJson', () {

    test('extrait sessionId et numéro masqué pour l\'affichage', () {
      final json = {
        'sessionId':        'sess-abc-123',
        'expiresInSeconds': 120,
        'telephoneMasque':  '+216*****001',
      };

      final otp = OtpInitiateResponse.fromJson(json);

      expect(otp.sessionId,        equals('sess-abc-123'));
      expect(otp.expiresInSeconds, equals(120));
      expect(otp.telephoneMasque,  equals('+216*****001'));
    });

    test('utilise la durée par défaut 120 s si absent', () {
      final json = {'sessionId': 'sess-xyz'};
      final otp = OtpInitiateResponse.fromJson(json);
      expect(otp.expiresInSeconds, equals(120));
    });
  });
}
