class User {
  final String id;
  final String fullName;
  final String? email;
  final String? phone;
  final String role;
  final String userType;
  final bool isActive;
  final bool isVerified;
  final String? rib;
  final String? cinNumber;

  const User({
    required this.id,
    required this.fullName,
    required this.role,
    required this.userType,
    required this.isActive,
    required this.isVerified,
    this.email,
    this.phone,
    this.rib,
    this.cinNumber,
  });

  factory User.fromJson(Map<String, dynamic> json) => User(
    id:         json['id'] as String,
    fullName:   json['fullName'] as String? ?? '',
    email:      json['email'] as String?,
    phone:      json['phone'] as String?,
    role:       json['role'] as String? ?? 'CLIENT',
    userType:   json['userType'] as String? ?? 'CLIENT',
    isActive:   json['isActive'] as bool? ?? true,
    isVerified: json['isVerified'] as bool? ?? false,
    rib:        json['rib'] as String?,
    cinNumber:  json['cinNumber'] as String?,
  );

  String get displayName => fullName.isNotEmpty ? fullName : (email ?? phone ?? 'Utilisateur');
}

class AuthResponse {
  final String token;
  final String role;
  final String userType;
  final int expiresIn;

  const AuthResponse({
    required this.token,
    required this.role,
    required this.userType,
    required this.expiresIn,
  });

  factory AuthResponse.fromJson(Map<String, dynamic> json) => AuthResponse(
    token:     json['token'] as String,
    role:      json['role'] as String,
    userType:  json['userType'] as String? ?? 'CLIENT',
    expiresIn: json['expiresIn'] as int? ?? 86400,
  );
}

class OtpInitiateResponse {
  final String sessionId;
  final int expiresInSeconds;
  final String? telephoneMasque;

  const OtpInitiateResponse({
    required this.sessionId,
    required this.expiresInSeconds,
    this.telephoneMasque,
  });

  factory OtpInitiateResponse.fromJson(Map<String, dynamic> json) => OtpInitiateResponse(
    sessionId:        json['sessionId'] as String,
    expiresInSeconds: json['expiresInSeconds'] as int? ?? 120,
    telephoneMasque:  json['telephoneMasque'] as String?,
  );
}

class OtpVerifyResponse {
  final String tokenInscription;
  final String sessionId;

  const OtpVerifyResponse({required this.tokenInscription, required this.sessionId});

  factory OtpVerifyResponse.fromJson(Map<String, dynamic> json) => OtpVerifyResponse(
    tokenInscription: json['tokenInscription'] as String,
    sessionId:        json['sessionId'] as String,
  );
}
