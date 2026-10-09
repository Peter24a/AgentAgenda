import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

const defaultAgendaServer = 'https://agenda-api.pedroibarra.dev';

enum ConnectionState { disconnected, checking, connected, unavailable }

class ConnectionException implements Exception {
  final String message;
  const ConnectionException(this.message);
  @override
  String toString() => message;
}

/// Keeps credentials in Android's encrypted storage, never in preferences.
abstract class SessionStore {
  Future<String?> read(String key);
  Future<void> write(String key, String value);
  Future<void> delete(String key);
}

class EncryptedSessionStore implements SessionStore {
  final FlutterSecureStorage _storage = const FlutterSecureStorage();
  @override
  Future<String?> read(String key) => _storage.read(key: key);
  @override
  Future<void> write(String key, String value) =>
      _storage.write(key: key, value: value);
  @override
  Future<void> delete(String key) => _storage.delete(key: key);
}

String normalizeServer(String value) {
  final uri = Uri.tryParse(value.trim());
  if (uri == null ||
      uri.scheme != 'https' ||
      uri.host.isEmpty ||
      uri.userInfo.isNotEmpty ||
      uri.hasQuery ||
      uri.hasFragment ||
      (uri.path.isNotEmpty && uri.path != '/')) {
    throw const ConnectionException(
      'Usa la dirección HTTPS del servicio, sin rutas ni claves.',
    );
  }
  return uri.replace(path: '').toString();
}

class ActivationInput {
  final String code;
  final String server;
  const ActivationInput(this.code, this.server);

  static ActivationInput parse(String input, String server) {
    var code = input.trim();
    final origin = normalizeServer(server);
    if (code.contains('://')) {
      final link = Uri.tryParse(code);
      if (link == null ||
          link.scheme != 'https' ||
          link.origin != origin ||
          !['/activar', '/activate'].contains(link.path)) {
        throw const ConnectionException(
          'El enlace debe pertenecer al servidor elegido.',
        );
      }
      // Fragment links avoid putting the activation secret in server access logs.
      final fragment = Uri.splitQueryString(link.fragment);
      code = fragment['code'] ?? link.queryParameters['code'] ?? '';
    }
    if (!RegExp(r'^[a-zA-Z0-9_-]{6,256}$').hasMatch(code)) {
      throw const ConnectionException(
        'Introduce el código o enlace de activación que recibiste.',
      );
    }
    return ActivationInput(code, origin);
  }
}

class SpaceSession {
  final String server;
  final String spaceId;
  final String spaceName;
  final String baseUrl;
  final String deviceId;
  final String accessToken;
  final String refreshToken;
  final DateTime expiresAt;
  const SpaceSession({
    required this.server,
    required this.spaceId,
    required this.spaceName,
    required this.baseUrl,
    required this.deviceId,
    required this.accessToken,
    required this.refreshToken,
    required this.expiresAt,
  });

  factory SpaceSession.fromJson(Map<String, dynamic> data, String server) {
    final origin = normalizeServer(server);
    final id = data['space_id'] as String;
    final base = Uri.parse(data['base_url'] as String);
    if (!RegExp(r'^[a-zA-Z0-9_-]+$').hasMatch(id) ||
        base.origin != origin ||
        base.path != '/s/$id' ||
        base.userInfo.isNotEmpty ||
        base.hasQuery ||
        base.hasFragment) {
      throw const ConnectionException(
        'El servidor devolvió un espacio no válido.',
      );
    }
    final access = data['access_token'] as String;
    final refresh = data['refresh_token'] as String;
    if (access.isEmpty || refresh.isEmpty) {
      throw const ConnectionException('El servidor no completó la activación.');
    }
    return SpaceSession(
      server: origin,
      spaceId: id,
      spaceName: data['space_name'] as String,
      baseUrl: base.toString(),
      deviceId: data['device_id'] as String,
      accessToken: access,
      refreshToken: refresh,
      expiresAt: data['expires_at'] != null
          ? DateTime.parse(data['expires_at'] as String)
          : DateTime.now().add(Duration(seconds: data['expires_in'] as int)),
    );
  }

  Map<String, dynamic> toJson() => {
    'server': server,
    'space_id': spaceId,
    'space_name': spaceName,
    'base_url': baseUrl,
    'device_id': deviceId,
    'access_token': accessToken,
    'refresh_token': refreshToken,
    'expires_at': expiresAt.toUtc().toIso8601String(),
  };
}

class SpaceSessionManager extends ChangeNotifier {
  static final instance = SpaceSessionManager();
  static const sessionKey = 'space_session_v1';
  static const attemptKey = 'activation_attempt_v1';
  final SessionStore _store;
  final http.Client _http;
  Future<void> Function()? onDisconnect;
  SpaceSession? session;
  ConnectionState state = ConnectionState.disconnected;
  String? message;
  int generation = 0;
  Future<void>? _refreshing;

  SpaceSessionManager({SessionStore? store, http.Client? client})
    : _store = store ?? EncryptedSessionStore(),
      _http = client ?? http.Client();

  Future<void> init() async {
    try {
      final saved = await _store.read(sessionKey);
      if (saved == null) return;
      final value = jsonDecode(saved) as Map<String, dynamic>;
      session = SpaceSession.fromJson(value, value['server'] as String);
      await verify();
    } catch (_) {
      if (session == null) {
        await disconnect(
          message: 'Vuelve a conectar tu espacio con un código nuevo.',
        );
      } else {
        state = ConnectionState.unavailable;
        message = 'No pudimos verificar tu conexión. Reintenta cuando tengas internet.';
        notifyListeners();
      }
    }
  }

  Future<void> activate(
    String input, {
    String server = defaultAgendaServer,
    String deviceName = 'Mi teléfono Android',
  }) async {
    final activation = ActivationInput.parse(input, server);
    if (session != null) {
      throw const ConnectionException(
        'Desconecta el espacio actual antes de cambiarlo.',
      );
    }
    state = ConnectionState.checking;
    message = null;
    notifyListeners();
    try {
      final saved = await _store.read(attemptKey);
      Map<String, dynamic>? previous;
      if (saved != null) previous = jsonDecode(saved) as Map<String, dynamic>;
      final sameAttempt =
          previous?['code'] == activation.code &&
          previous?['server'] == activation.server;
      final requestId = sameAttempt
          ? previous!['request_id'] as String
          : List.generate(
              24,
              (_) => Random.secure().nextInt(256),
            ).map((b) => b.toRadixString(16).padLeft(2, '0')).join();
      final requestedName = deviceName.trim().isEmpty
          ? 'Mi teléfono Android'
          : deviceName.trim();
      final enrolledName = sameAttempt
          ? previous!['device_name'] as String? ?? requestedName
          : requestedName;
      await _store.write(
        attemptKey,
        jsonEncode({
          'code': activation.code,
          'server': activation.server,
          'request_id': requestId,
          'device_name': enrolledName,
        }),
      );
      final response = await _http
          .post(
            Uri.parse('${activation.server}/platform/v1/activate'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'code': activation.code,
              'device_name': enrolledName,
              'platform': 'android',
              'request_id': requestId,
            }),
          )
          .timeout(const Duration(seconds: 30));
      if (response.statusCode != 200 && response.statusCode != 201) {
        if ([400, 409, 423].contains(response.statusCode)) {
          await _store.delete(attemptKey);
        }
        throw ConnectionException(switch (response.statusCode) {
          400 => 'El código es inválido o venció. Solicita uno nuevo.',
          409 => 'Este código ya fue utilizado. Solicita uno nuevo para este teléfono.',
          423 =>
            'Tu espacio está suspendido o cerrado. Contacta al administrador.',
          _ => 'No se pudo activar el espacio. Reintenta con el mismo código.',
        });
      }
      final activated = SpaceSession.fromJson(
        jsonDecode(response.body) as Map<String, dynamic>,
        activation.server,
      );
      // Write the returned grant before any further network requests: a lost
      // identity check must not discard a successfully consumed invitation.
      await _store.write(sessionKey, jsonEncode(activated.toJson()));
      session = activated;
      generation++;
      await _store.delete(attemptKey);
      await verify();
    } catch (error) {
      state = session == null
          ? ConnectionState.disconnected
          : ConnectionState.unavailable;
      message = error is ConnectionException ? error.message : 'No se pudo conectar. Reintenta con el mismo código cuando tengas internet.';
      notifyListeners();
      rethrow;
    }
  }

  Future<void> ensureCurrent() async {
    final current = session;
    if (current == null) {
      throw const ConnectionException('Conecta tu espacio para continuar.');
    }
    if (current.expiresAt.isBefore(
      DateTime.now().add(const Duration(minutes: 1)),
    )) {
      await refresh();
    }
  }

  Future<void> refresh() =>
      _refreshing ??= _refresh().whenComplete(() => _refreshing = null);
  Future<void> _refresh() async {
    final current = session;
    if (current == null) throw const ConnectionException('La sesión terminó.');
    final epoch = generation;
    final response = await _http
        .post(
          Uri.parse('${current.baseUrl}/v1/auth/refresh'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({'refresh_token': current.refreshToken}),
        )
        .timeout(const Duration(seconds: 15));
    if (epoch != generation) {
      throw const ConnectionException('El espacio cambió.');
    }
    if ([400, 401, 403, 423].contains(response.statusCode)) {
      await disconnect(
        message: response.statusCode == 423
            ? 'Tu espacio está suspendido o cerrado. Contacta al administrador.'
            : 'La sesión venció o fue revocada. Solicita un código para reconectar.',
      );
      throw ConnectionException(message!);
    }
    if (response.statusCode != 200) {
      throw const ConnectionException(
        'No se pudo renovar la sesión. Reintenta cuando tengas conexión.',
      );
    }
    final refreshed = SpaceSession.fromJson({
      ...current.toJson(),
      ...jsonDecode(response.body) as Map<String, dynamic>,
      'expires_at': null,
    }, current.server);
    await _store.write(sessionKey, jsonEncode(refreshed.toJson()));
    session = refreshed;
  }

  Future<void> verify() async {
    if (session == null) return;
    final epoch = generation;
    state = ConnectionState.checking;
    message = null;
    notifyListeners();
    try {
      await ensureCurrent();
      var response = await _me();
      if (response.statusCode == 401) {
        await refresh();
        response = await _me();
      }
      if (epoch != generation) return;
      if ([401, 403, 423].contains(response.statusCode)) {
        await disconnect(
          message: response.statusCode == 423
              ? 'Tu espacio está suspendido o cerrado. Contacta al administrador.'
              : 'La sesión ya no es válida. Solicita un código para reconectar.',
        );
        return;
      }
      if (response.statusCode != 200) {
        throw const ConnectionException('No se pudo verificar tu espacio.');
      }
      final identity = jsonDecode(response.body) as Map<String, dynamic>;
      if (identity['device_id'] != session?.deviceId) {
        await disconnect(
          message: 'No se pudo verificar el dispositivo de este espacio.',
        );
        return;
      }
      state = ConnectionState.connected;
    } catch (error) {
      if (session != null) {
        state = ConnectionState.unavailable;
        message = error is ConnectionException ? error.message : 'No pudimos verificar tu espacio. Reintenta cuando tengas internet.';
      }
    }
    notifyListeners();
  }

  Future<http.Response> _me() {
    final current = session!;
    return _http
        .get(
          Uri.parse('${current.baseUrl}/v1/auth/me'),
          headers: {'Authorization': 'Bearer ${current.accessToken}'},
        )
        .timeout(const Duration(seconds: 15));
  }

  /// Revokes the device when reachable, and always removes local access.
  Future<void> logout() async {
    final current = session;
    if (current != null) {
      try {
        await _http
            .post(
              Uri.parse('${current.baseUrl}/v1/auth/revoke'),
              headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ${current.accessToken}',
              },
              body: jsonEncode({'device_id': current.deviceId}),
            )
            .timeout(const Duration(seconds: 5));
      } catch (_) {
        /* An offline logout still removes all local access. */
      }
    }
    await disconnect();
  }

  Future<void> disconnect({String? message}) async {
    session = null;
    generation++;
    state = ConnectionState.disconnected;
    this.message = message;
    notifyListeners();
    await _store.delete(sessionKey);
    await onDisconnect?.call();
  }
}

/// All authenticated traffic stays inside the current space. An expired token
/// retries once after a shared renewal; rejected/suspended sessions close the UI.
class SpaceHttpClient extends http.BaseClient {
  final SpaceSessionManager manager;
  final http.Client _inner;
  SpaceHttpClient(this.manager, [http.Client? client])
    : _inner = client ?? http.Client();
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final epoch = manager.generation;
    await manager.ensureCurrent();
    final current = manager.session!;
    final base = Uri.parse(current.baseUrl);
    if (request.url.origin != base.origin ||
        !request.url.path.startsWith('${base.path}/')) {
      throw const ConnectionException(
        'La solicitud no pertenece a tu espacio.',
      );
    }
    if (epoch != manager.generation) {
      throw const ConnectionException('El espacio cambió.');
    }
    request.headers['Authorization'] = 'Bearer ${current.accessToken}';
    request.followRedirects = false;
    var response = await _inner.send(request);
    if (epoch != manager.generation) {
      throw const ConnectionException('El espacio cambió.');
    }
    if (response.statusCode == 401 && request is http.Request) {
      await response.stream.drain<void>();
      await manager.refresh();
      if (epoch != manager.generation) {
        throw const ConnectionException('La sesión terminó.');
      }
      final retry = http.Request(request.method, request.url)
        ..headers.addAll(request.headers)
        ..headers['Authorization'] = 'Bearer ${manager.session!.accessToken}'
        ..bodyBytes = request.bodyBytes
        ..followRedirects = false;
      response = await _inner.send(retry);
    }
    if ([401, 423].contains(response.statusCode)) {
      await manager.disconnect(
        message: response.statusCode == 423
            ? 'Tu espacio está suspendido o cerrado. Contacta al administrador.'
            : 'La sesión terminó. Solicita un código para reconectar.',
      );
    }
    return response;
  }

  @override
  void close() => _inner.close();
}
