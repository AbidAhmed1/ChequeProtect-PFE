import 'dart:io';
import 'package:shared_preferences/shared_preferences.dart';
import 'api_client.dart';
import '../models/user.dart';

class AuthService {
  AuthService._();
  static final AuthService instance = AuthService._();

  static const String _userKey   = 'tunicheque_user_role';
  static const String _phoneKey  = 'tunicheque_phone';

  User? _currentUser;
  User? get currentUser => _currentUser;
  bool get isLoggedIn => _currentUser != null && ApiClient.instance.hasToken;

  // ── Session restore ────────────────────────────────────────────────────────

  Future<bool> tryRestoreSession() async {
    final token = await ApiClient.instance.getToken();
    if (token == null) return false;
    try {
      final json = await ApiClient.instance.get('/api/auth/me');
      _currentUser = User.fromJson(json);
      return true;
    } catch (_) {
      await logout();
      return false;
    }
  }

  // ── PIN login (mobile) ────────────────────────────────────────────────────

  Future<String?> getSavedPhone() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_phoneKey);
  }

  Future<void> _savePhone(String phone) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_phoneKey, phone);
  }

  Future<AuthResponse> loginWithPin(String telephone, String pin) async {
    final json = await ApiClient.instance.post(
      '/api/auth/login/mobile',
      {'phone': telephone, 'password': pin},
    );
    final auth = AuthResponse.fromJson(json);
    await ApiClient.instance.saveToken(auth.token);
    _currentUser = await _fetchMe();
    await _savePhone(telephone);
    return auth;
  }

  // ── Parcours A — Inscription via RIB ─────────────────────────────────────

  Future<OtpInitiateResponse> ribInitiate(String rib) async {
    final json = await ApiClient.instance.post(
      '/api/auth/register/rib/initiate',
      {'rib': rib},
    );
    return OtpInitiateResponse.fromJson(json);
  }

  Future<void> ribConfirmPhone(String sessionId) async {
    await ApiClient.instance.post(
      '/api/auth/register/rib/confirm-phone',
      {'sessionId': sessionId, 'confirmed': true},
    );
  }

  Future<OtpVerifyResponse> ribVerifyOtp(String sessionId, String otp) async {
    final json = await ApiClient.instance.post(
      '/api/auth/register/rib/verify-otp',
      {'sessionId': sessionId, 'otp': otp},
    );
    return OtpVerifyResponse.fromJson(json);
  }

  Future<AuthResponse> ribSetPin(
    String sessionId,
    String pin,
    String pinConfirm,
    String tokenInscription,
  ) async {
    final json = await ApiClient.instance.post(
      '/api/auth/register/rib/set-pin',
      {'sessionId': sessionId, 'pin': pin, 'pinConfirm': pinConfirm},
      overrideToken: tokenInscription,
    );
    final auth = AuthResponse.fromJson(json);
    await ApiClient.instance.saveToken(auth.token);
    _currentUser = await _fetchMe();
    if (_currentUser?.phone != null) await _savePhone(_currentUser!.phone!);
    return auth;
  }

  // ── Parcours C — Inscription visiteur KYC (biométrie) ────────────────────

  Future<String> kycUploadCin(File recto, File verso) async {
    final json = await ApiClient.instance.postMultipart(
      '/api/auth/register/visitor/upload-cin',
      {'cinRecto': recto, 'cinVerso': verso},
      timeout: const Duration(seconds: 90),
    );
    final sessionId = json['sessionId'] as String?;
    if (sessionId == null) throw ApiException(500, 'sessionId manquant dans la réponse.');
    return sessionId;
  }

  Future<void> kycFaceVerify(File selfie, String sessionId) async {
    await ApiClient.instance.postMultipart(
      '/api/auth/register/visitor/face-verify',
      {'selfie': selfie},
      fields: {'sessionId': sessionId},
      timeout: const Duration(seconds: 90),
    );
  }

  Future<AuthResponse> kycComplete({
    required String sessionId,
    required String fullName,
    required String phone,
    required String pin,
    required String pinConfirm,
    String? email,
    String? rib,
    String? cinNumber,
  }) async {
    final body = <String, dynamic>{
      'sessionId':  sessionId,
      'fullName':   fullName,
      'phone':      phone,
      'pin':        pin,
      'pinConfirm': pinConfirm,
      if (email     != null && email.isNotEmpty)     'email':     email,
      if (rib       != null && rib.isNotEmpty)       'rib':       rib,
      if (cinNumber != null && cinNumber.isNotEmpty) 'cinNumber': cinNumber,
    };
    final json = await ApiClient.instance.post(
      '/api/auth/register/visitor/complete',
      body,
    );
    final auth = AuthResponse.fromJson(json);
    await ApiClient.instance.saveToken(auth.token);
    _currentUser = await _fetchMe();
    if (_currentUser?.phone != null) await _savePhone(_currentUser!.phone!);
    return auth;
  }

  // ── Parcours B — Inscription visiteur (OTP) ───────────────────────────────

  Future<OtpInitiateResponse> otpInitiate(String telephone) async {
    final json = await ApiClient.instance.post(
      '/api/auth/register/initiate',
      {'telephone': telephone},
    );
    return OtpInitiateResponse.fromJson(json);
  }

  Future<OtpVerifyResponse> otpVerify(String sessionId, String otp) async {
    final json = await ApiClient.instance.post(
      '/api/auth/register/verify-otp',
      {'sessionId': sessionId, 'otp': otp},
    );
    return OtpVerifyResponse.fromJson(json);
  }

  Future<AuthResponse> otpComplete({
    required String sessionId,
    required String tokenInscription,
    required String nom,
    required String prenom,
    required String cin,
    required String email,
    required String pin,
    required String pinConfirm,
    String? rib,
  }) async {
    final body = <String, dynamic>{
      'sessionId': sessionId,
      'nom':        nom,
      'prenom':     prenom,
      'cin':        cin,
      'email':      email,
      'pin':        pin,
      'pinConfirm': pinConfirm,
      if (rib != null && rib.isNotEmpty) 'rib': rib,
    };
    final json = await ApiClient.instance.post(
      '/api/auth/register/complete',
      body,
      overrideToken: tokenInscription,
    );
    final auth = AuthResponse.fromJson(json);
    await ApiClient.instance.saveToken(auth.token);
    _currentUser = await _fetchMe();
    if (_currentUser?.phone != null) await _savePhone(_currentUser!.phone!);
    return auth;
  }

  // ── Profile ───────────────────────────────────────────────────────────────

  Future<User> getProfile() async {
    final json = await ApiClient.instance.get('/api/auth/me');
    _currentUser = User.fromJson(json);
    return _currentUser!;
  }

  Future<User> updateProfile({String? fullName, String? email}) async {
    final body = <String, dynamic>{
      if (fullName != null) 'fullName': fullName,
      if (email != null) 'email': email,
    };
    final json = await ApiClient.instance.put('/api/auth/me', body);
    _currentUser = User.fromJson(json);
    return _currentUser!;
  }

  Future<void> changePin(String ancienPin, String nouveauPin, String confirmPin) async {
    await ApiClient.instance.put('/api/auth/me/pin', {
      'currentPin': ancienPin,
      'newPin':     nouveauPin,
      'newPinConfirm': confirmPin,
    });
  }

  // ── Logout ────────────────────────────────────────────────────────────────

  Future<void> logout() async {
    _currentUser = null;
    await ApiClient.instance.clearToken();
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_userKey);
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  Future<User> _fetchMe() async {
    final json = await ApiClient.instance.get('/api/auth/me');
    return User.fromJson(json);
  }
}
