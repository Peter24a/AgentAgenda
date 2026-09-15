import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:intl/intl.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../features/agenda/models/agenda_item.dart';
import '../../features/agenda/models/agenda_task.dart';
import '../../features/agenda/models/agent_proposal.dart';

sealed class ChatStreamEvent {
  const ChatStreamEvent();
}

class ChatTokenEvent extends ChatStreamEvent {
  final String token;
  const ChatTokenEvent(this.token);
}

class ChatProposalEvent extends ChatStreamEvent {
  final AgentProposal proposal;
  const ChatProposalEvent(this.proposal);
}

class ChatDoneEvent extends ChatStreamEvent {
  const ChatDoneEvent();
}

class ChatErrorEvent extends ChatStreamEvent {
  final String message;
  const ChatErrorEvent(this.message);
}

/// Cliente HTTP principal para la API canónica de AgentAgenda.
/// Proporciona acceso a Agenda, Propuestas del Agente, Tareas y Chat Streaming.
class ApiClient {
  static final ApiClient instance = ApiClient._();
  ApiClient._();

  static const String _prefKey = 'backend_base_url';
  static const String _tokenPrefKey = 'backend_auth_token';
  static const String _refreshPrefKey = 'backend_refresh_token';

  static String get defaultPlatformUrl {
    const configured = String.fromEnvironment('BACKEND_URL');
    if (configured.isNotEmpty) return configured;
    if (kIsWeb) return 'http://127.0.0.1:8001';
    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
        return 'http://10.0.2.2:8001';
      case TargetPlatform.iOS:
      case TargetPlatform.macOS:
      case TargetPlatform.linux:
      case TargetPlatform.windows:
      default:
        return 'http://127.0.0.1:8001';
    }
  }

  String _baseUrl = defaultPlatformUrl;
  String get baseUrl => _baseUrl;

  String? _authToken;

  Map<String, String> get _headers => {
    'Content-Type': 'application/json',
    if (_authToken != null && _authToken!.isNotEmpty)
      'Authorization': 'Bearer $_authToken',
  };

  Future<void> init() async {
    final prefs = await SharedPreferences.getInstance();
    _baseUrl = prefs.getString(_prefKey) ?? defaultPlatformUrl;
    _authToken = prefs.getString(_tokenPrefKey);
    final refresh = prefs.getString(_refreshPrefKey);
    if (refresh != null && refresh.isNotEmpty) {
      try {
        final response = await http
            .post(
              Uri.parse('$_baseUrl/v1/auth/refresh'),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({'refresh_token': refresh}),
            )
            .timeout(const Duration(seconds: 8));
        if (response.statusCode == 200) {
          final data = jsonDecode(response.body) as Map<String, dynamic>;
          final access = data['access_token'] as String;
          final nextRefresh = data['refresh_token'] as String;
          await prefs.setString(_tokenPrefKey, access);
          await prefs.setString(_refreshPrefKey, nextRefresh);
          _authToken = access;
        }
      } catch (_) {
        // Offline startup retains the current session for a later connection.
      }
    }
  }

  Future<void> setBaseUrl(String url) async {
    _baseUrl = url.replaceAll(RegExp(r'/+$'), '');
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_prefKey, _baseUrl);
  }

  Future<void> setAuthToken(String? token) async {
    _authToken = token;
    final prefs = await SharedPreferences.getInstance();
    if (token != null) {
      await prefs.setString(_tokenPrefKey, token);
    } else {
      await prefs.remove(_tokenPrefKey);
    }
  }

  /// Verifica el estado de salud del servidor backend.
  Future<bool> checkHealth() async {
    try {
      final uri = Uri.parse('$_baseUrl/health');
      final response = await http
          .get(uri, headers: _headers)
          .timeout(const Duration(seconds: 4));
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  // ==========================================
  // AGENDA & EVENTOS
  // ==========================================

  /// Obtiene los eventos programados para una fecha específica o el día actual.
  Future<List<AgendaItem>> getEvents({DateTime? date}) async {
    final targetDate = date ?? DateTime.now();
    final dateStr = DateFormat('yyyy-MM-dd').format(targetDate);
    final uri = Uri.parse('$_baseUrl/v1/agenda/events?date=$dateStr');

    try {
      final response = await http
          .get(uri, headers: _headers)
          .timeout(const Duration(seconds: 8));
      if (response.statusCode == 200) {
        final List<dynamic> list = jsonDecode(response.body);
        return list
            .map((e) => AgendaItem.fromJson(e as Map<String, dynamic>))
            .toList();
      }
    } catch (_) {}
    return [];
  }

  /// Crea o actualiza un evento en la agenda canónica.
  Future<AgendaItem?> createOrUpdateEvent(AgendaItem item) async {
    final uri = Uri.parse('$_baseUrl/v1/agenda/events');
    try {
      final response = await http
          .post(uri, headers: _headers, body: jsonEncode(item.toJson()))
          .timeout(const Duration(seconds: 8));

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        return AgendaItem.fromJson(data);
      }
    } catch (_) {}
    return null;
  }

  /// Elimina un evento de la agenda canónica.
  Future<bool> deleteEvent(String eventId) async {
    final uri = Uri.parse('$_baseUrl/v1/agenda/events/$eventId');
    try {
      final response = await http
          .delete(uri, headers: _headers)
          .timeout(const Duration(seconds: 6));
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  /// Conmuta el estado de completado de un evento.
  Future<bool> toggleEvent(String eventId, {DateTime? date}) async {
    final targetDate = date ?? DateTime.now();
    final dateStr = DateFormat('yyyy-MM-dd').format(targetDate);
    final uri = Uri.parse(
      '$_baseUrl/v1/agenda/events/$eventId/toggle?date=$dateStr',
    );

    try {
      final response = await http
          .post(uri, headers: _headers)
          .timeout(const Duration(seconds: 6));
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  // ==========================================
  // TAREAS
  // ==========================================

  /// Consulta la lista de tareas (status: 'pending', 'completed', 'all').
  Future<List<AgendaTask>> getTasks({String? status}) async {
    final query = status != null ? '?status=$status' : '';
    final uri = Uri.parse('$_baseUrl/v1/agenda/tasks$query');

    try {
      final response = await http
          .get(uri, headers: _headers)
          .timeout(const Duration(seconds: 8));
      if (response.statusCode == 200) {
        final List<dynamic> list = jsonDecode(response.body);
        return list
            .map((e) => AgendaTask.fromJson(e as Map<String, dynamic>))
            .toList();
      }
    } catch (_) {}
    return [];
  }

  /// Conmuta el estado de una tarea entre pendiente y completada.
  Future<bool> toggleTask(String taskId) async {
    final uri = Uri.parse('$_baseUrl/v1/agenda/tasks/$taskId/toggle');
    try {
      final response = await http
          .post(uri, headers: _headers)
          .timeout(const Duration(seconds: 6));
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  // ==========================================
  // PROPUESTAS DEL AGENTE
  // ==========================================

  /// Recupera la propuesta pendiente más reciente generada por el agente.
  Future<AgentProposal?> getPendingProposal() async {
    final uri = Uri.parse('$_baseUrl/v1/proposals/pending');
    try {
      final response = await http
          .get(uri, headers: _headers)
          .timeout(const Duration(seconds: 6));
      if (response.statusCode == 200 && response.body != 'null') {
        final Map<String, dynamic> data = jsonDecode(response.body);
        return _proposalFromJson(data);
      }
    } catch (_) {}
    return null;
  }

  /// Recupera los detalles de una propuesta específica por su identificador.
  Future<AgentProposal?> getProposal(String proposalId) async {
    final uri = Uri.parse('$_baseUrl/v1/proposals/$proposalId');
    try {
      final response = await http
          .get(uri, headers: _headers)
          .timeout(const Duration(seconds: 6));
      if (response.statusCode == 200) {
        final Map<String, dynamic> data = jsonDecode(response.body);
        return _proposalFromJson(data);
      }
    } catch (_) {}
    return null;
  }

  /// Confirma y aplica atómicamente una propuesta en la agenda.
  Future<bool> confirmProposal(String proposalId) async {
    final uri = Uri.parse('$_baseUrl/v1/proposals/$proposalId/confirm');
    try {
      final response = await http
          .post(uri, headers: _headers)
          .timeout(const Duration(seconds: 8));
      if (response.statusCode != 200) return false;
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      return data['success'] == true;
    } catch (_) {
      return false;
    }
  }

  /// Descarta una propuesta del agente.
  Future<bool> rejectProposal(String proposalId) async {
    final uri = Uri.parse('$_baseUrl/v1/proposals/$proposalId/reject');
    try {
      final response = await http
          .post(uri, headers: _headers)
          .timeout(const Duration(seconds: 8));
      if (response.statusCode != 200) return false;
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      return data['success'] == true;
    } catch (_) {
      return false;
    }
  }

  // ==========================================
  // CHAT & STREAMING
  // ==========================================

  /// Recupera el historial de mensajes persistentes del chat durable.
  Future<List<Map<String, dynamic>>> getChatMessages({int limit = 50}) async {
    final uri = Uri.parse('$_baseUrl/v1/chat/messages?limit=$limit');
    try {
      final response = await http
          .get(uri, headers: _headers)
          .timeout(const Duration(seconds: 8));
      if (response.statusCode == 200) {
        final List<dynamic> list = jsonDecode(response.body);
        return list.cast<Map<String, dynamic>>();
      }
    } catch (_) {}
    return [];
  }

  /// Emite un stream SSE conectado al LLM autohosteado para el chat.
  Stream<ChatStreamEvent> streamChat({
    required String message,
    DateTime? date,
    List<Map<String, dynamic>> history = const [],
  }) async* {
    final targetDate = date ?? DateTime.now();
    final dateStr = DateFormat('yyyy-MM-dd').format(targetDate);
    final uri = Uri.parse('$_baseUrl/v1/chat/stream');

    final body = jsonEncode({
      'message': message,
      'date': dateStr,
      'history': history,
    });

    final request = http.Request('POST', uri)
      ..headers.addAll(_headers)
      ..headers['Accept'] = 'text/event-stream'
      ..body = body;

    final client = http.Client();
    http.StreamedResponse response;
    try {
      response = await client.send(request).timeout(const Duration(seconds: 8));
    } catch (_) {
      client.close();
      yield const ChatErrorEvent(
        'Error de conexión: no se pudo alcanzar el backend.',
      );
      return;
    }

    if (response.statusCode != 200) {
      client.close();
      yield ChatErrorEvent(
        'Servidor respondió con código ${response.statusCode}',
      );
      return;
    }

    final lines = response.stream
        .transform(utf8.decoder)
        .transform(const LineSplitter())
        .timeout(const Duration(seconds: 120));
    var terminalEvent = false;

    try {
      await for (final line in lines) {
        if (line.isEmpty || !line.startsWith('data: ')) continue;
        final dataStr = line.substring(6).trim();

        try {
          final Map<String, dynamic> json = jsonDecode(dataStr);
          final type = json['type'] as String?;

          if (type == 'token') {
            final content = json['content'] as String? ?? '';
            yield ChatTokenEvent(content);
          } else if (type == 'proposal') {
            final propData = json['proposal'] as Map<String, dynamic>;
            yield ChatProposalEvent(_proposalFromJson(propData));
          } else if (type == 'done') {
            terminalEvent = true;
            yield const ChatDoneEvent();
          } else if (type == 'error') {
            terminalEvent = true;
            yield ChatErrorEvent(
              json['message'] as String? ?? 'Falló la generación de IA.',
            );
          }
        } catch (_) {}
      }
      if (!terminalEvent) {
        yield const ChatErrorEvent(
          'La respuesta se interrumpió. Intenta de nuevo.',
        );
      }
    } catch (_) {
      yield const ChatErrorEvent('Se perdió la conexión durante la respuesta.');
    } finally {
      client.close();
    }
  }

  AgentProposal _proposalFromJson(Map<String, dynamic> json) {
    final rawItems = json['resulting_items'] as List<dynamic>? ?? [];
    final items = rawItems
        .map((x) => AgendaItem.fromJson(x as Map<String, dynamic>))
        .toList();

    return AgentProposal(
      id: json['id'] as String,
      summary: json['summary'] as String? ?? 'Propuesta del asistente',
      reason: json['reason'] as String? ?? '',
      resultingItems: items,
      status: ProposalStatus.pending,
      createdAt: json['created_at'] != null
          ? DateTime.parse(json['created_at'] as String)
          : DateTime.now(),
    );
  }
}
