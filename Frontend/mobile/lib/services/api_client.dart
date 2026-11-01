import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

class ApiException implements Exception {
  final int statusCode;
  final String message;
  const ApiException(this.statusCode, this.message);

  @override
  String toString() => 'ApiException($statusCode): $message';
}

class ApiClient {
  ApiClient._();
  static final ApiClient instance = ApiClient._();

  // Émulateur : flutter run  (défauts 10.0.2.2)
  // Téléphone  : flutter run --dart-define=BASE_URL=http://192.168.1.117:8080 --dart-define=AI_URL=http://192.168.1.117:8083
  static const String baseUrl   = String.fromEnvironment('BASE_URL', defaultValue: 'http://10.0.2.2:8080');
  static const String aiBaseUrl = String.fromEnvironment('AI_URL',   defaultValue: 'http://10.0.2.2:8083');
  static const String _tokenKey = 'tunicheque_token';
  static const Duration _timeout = Duration(seconds: 30);

  String? _cachedToken;

  // ── Token management ───────────────────────────────────────────────────────

  Future<void> saveToken(String token) async {
    _cachedToken = token;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_tokenKey, token);
  }

  Future<String?> getToken() async {
    if (_cachedToken != null) return _cachedToken;
    final prefs = await SharedPreferences.getInstance();
    _cachedToken = prefs.getString(_tokenKey);
    return _cachedToken;
  }

  Future<void> clearToken() async {
    _cachedToken = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_tokenKey);
  }

  bool get hasToken => _cachedToken != null;

  // ── Headers ───────────────────────────────────────────────────────────────

  Future<Map<String, String>> _headers({String? overrideToken, bool multipart = false}) async {
    final token = overrideToken ?? await getToken();
    return {
      if (!multipart) 'Content-Type': 'application/json',
      'Accept': 'application/json',
      if (token != null) 'Authorization': 'Bearer $token',
    };
  }

  // ── HTTP methods ──────────────────────────────────────────────────────────

  Future<Map<String, dynamic>> get(String path, {Map<String, String>? queryParams}) async {
    final uri = Uri.parse('$baseUrl$path').replace(queryParameters: queryParams);
    final headers = await _headers();
    final response = await http.get(uri, headers: headers).timeout(_timeout);
    return _handle(response);
  }

  Future<List<dynamic>> getList(String path, {Map<String, String>? queryParams}) async {
    final uri = Uri.parse('$baseUrl$path').replace(queryParameters: queryParams);
    final headers = await _headers();
    final response = await http.get(uri, headers: headers).timeout(_timeout);
    return _handleList(response);
  }

  Future<Map<String, dynamic>> post(
    String path,
    Map<String, dynamic> body, {
    String? overrideToken,
  }) async {
    final uri = Uri.parse('$baseUrl$path');
    final headers = await _headers(overrideToken: overrideToken);
    final response = await http.post(uri, headers: headers, body: jsonEncode(body)).timeout(_timeout);
    return _handle(response);
  }

  Future<Map<String, dynamic>> postWithHeaders(
    String path,
    Map<String, dynamic> body, {
    Map<String, String>? extraHeaders,
  }) async {
    final uri = Uri.parse('$baseUrl$path');
    final headers = await _headers();
    if (extraHeaders != null) headers.addAll(extraHeaders);
    final response = await http.post(uri, headers: headers, body: jsonEncode(body)).timeout(_timeout);
    return _handle(response);
  }

  Future<Map<String, dynamic>> put(String path, Map<String, dynamic> body) async {
    final uri = Uri.parse('$baseUrl$path');
    final headers = await _headers();
    final response = await http.put(uri, headers: headers, body: jsonEncode(body)).timeout(_timeout);
    return _handle(response);
  }

  Future<Map<String, dynamic>> patch(String path, [Map<String, dynamic>? body]) async {
    final uri = Uri.parse('$baseUrl$path');
    final headers = await _headers();
    final response = await http.patch(
      uri,
      headers: headers,
      body: body != null ? jsonEncode(body) : null,
    ).timeout(_timeout);
    return _handle(response);
  }

  Future<Map<String, dynamic>> postMultipart(
    String path,
    Map<String, File> files, {
    Map<String, String>? fields,
    Duration? timeout,
  }) async {
    final uri = Uri.parse('$baseUrl$path');
    final token = await getToken();
    final request = http.MultipartRequest('POST', uri);

    if (token != null) request.headers['Authorization'] = 'Bearer $token';
    if (fields != null) request.fields.addAll(fields);

    for (final entry in files.entries) {
      request.files.add(await http.MultipartFile.fromPath(entry.key, entry.value.path));
    }

    final streamed = await request.send().timeout(timeout ?? _timeout);
    final response = await http.Response.fromStream(streamed);
    return _handle(response);
  }

  // Appel multipart vers le service AI (port 8083) — pas de token requis
  Future<Map<String, dynamic>> postMultipartAI(
    String path,
    Map<String, File> files, {
    Map<String, String>? fields,
    Duration? timeout,
  }) async {
    final uri = Uri.parse('$aiBaseUrl$path');
    final request = http.MultipartRequest('POST', uri);

    if (fields != null) request.fields.addAll(fields);

    for (final entry in files.entries) {
      request.files.add(await http.MultipartFile.fromPath(entry.key, entry.value.path));
    }

    final streamed = await request.send().timeout(timeout ?? _timeout);
    final response = await http.Response.fromStream(streamed);
    return _handle(response);
  }

  // ── Response handling ─────────────────────────────────────────────────────

  Map<String, dynamic> _handle(http.Response response) {
    if (response.statusCode >= 200 && response.statusCode < 300) {
      if (response.body.isEmpty) return {};
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    final body = response.body.isNotEmpty
        ? _extractError(response.body)
        : 'Erreur ${response.statusCode}';
    throw ApiException(response.statusCode, body);
  }

  String _extractError(String body) {
    try {
      final map = jsonDecode(body) as Map<String, dynamic>;
      return map['message'] as String?
          ?? map['error'] as String?
          ?? body;
    } catch (_) {
      return body;
    }
  }

  List<dynamic> _handleList(http.Response response) {
    if (response.statusCode >= 200 && response.statusCode < 300) {
      if (response.body.isEmpty) return [];
      return jsonDecode(response.body) as List<dynamic>;
    }
    final body = response.body.isNotEmpty
        ? _extractError(response.body)
        : 'Erreur ${response.statusCode}';
    throw ApiException(response.statusCode, body);
  }
}
