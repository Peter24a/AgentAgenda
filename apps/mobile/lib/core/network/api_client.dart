import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:mime/mime.dart';
import 'package:path_provider/path_provider.dart';

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
    return 'https://agenda-api.pedroibarra.dev';
  }

  static String get defaultAuthToken =>
      const String.fromEnvironment('AUTH_TOKEN');
  static String get defaultRefreshToken =>
      const String.fromEnvironment('REFRESH_TOKEN');

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
    final envToken = defaultAuthToken.isNotEmpty ? defaultAuthToken : null;
    final envRefresh = defaultRefreshToken.isNotEmpty
        ? defaultRefreshToken
        : null;
    _authToken = prefs.getString(_tokenPrefKey) ?? envToken;
    final refresh = prefs.getString(_refreshPrefKey) ?? envRefresh;
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

  Future<List<Map<String, dynamic>>> getWeeklyRoutines() async {
    final response = await http
        .get(Uri.parse('$_baseUrl/v1/agenda/routines'), headers: _headers)
        .timeout(const Duration(seconds: 15));
    if (response.statusCode != 200) {
      throw Exception('No se pudieron cargar las rutinas');
    }
    return (jsonDecode(response.body) as List).cast<Map<String, dynamic>>();
  }

  Future<void> setWeeklyRoutineEnabled(String id, bool enabled) async {
    final response = await http
        .put(
          Uri.parse(
            '$_baseUrl/v1/agenda/routines/${Uri.encodeComponent(id)}/enabled',
          ),
          headers: _headers,
          body: jsonEncode({'enabled': enabled}),
        )
        .timeout(const Duration(seconds: 30));
    if (response.statusCode != 200) {
      throw Exception('No se pudo actualizar la rutina');
    }
  }

  static const maxFileBytes = 50 * 1024 * 1024;

  Future<List<Map<String, dynamic>>> listDocuments({
    String query = '',
    int offset = 0,
  }) async {
    final uri = Uri.parse('$_baseUrl/v1/documents').replace(
      queryParameters: {
        'q': query,
        'offset': '$offset',
        'limit': '30',
        'include_text': 'false',
      },
    );
    final response = await http
        .get(uri, headers: _headers)
        .timeout(const Duration(seconds: 15));
    _requireSuccess(response);
    return (jsonDecode(response.body)['documents'] as List)
        .cast<Map<String, dynamic>>();
  }

  Future<void> deleteDocument(String id) async {
    final response = await http
        .delete(
          Uri.parse('$_baseUrl/v1/documents/${Uri.encodeComponent(id)}'),
          headers: _headers,
        )
        .timeout(const Duration(seconds: 15));
    _requireSuccess(response);
  }

  void _requireSuccess(http.Response response) {
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception(
        response.statusCode == 401
            ? 'La sesión caducó. Vuelve a abrir la app para renovarla.'
            : 'No se pudo completar la operación (${response.statusCode}).',
      );
    }
  }

  Future<Map<String, dynamic>> uploadDocument(
    PlatformFile file, {
    required void Function(double) onProgress,
  }) async {
    if (file.size <= 0 || file.size > maxFileBytes) {
      throw Exception('Selecciona un archivo de entre 1 byte y 50 MB.');
    }
    final response = await http
        .post(
          Uri.parse('$_baseUrl/v1/documents/uploads'),
          headers: _headers,
          body: jsonEncode({
            'filename': file.name,
            'title': file.name,
            'mime_type':
                lookupMimeType(file.name) ?? 'application/octet-stream',
            'expected_size_bytes': file.size,
          }),
        )
        .timeout(const Duration(seconds: 15));
    _requireSuccess(response);
    final id = jsonDecode(response.body)['upload_id'] as String;
    final source =
        file.readStream ??
        (file.path != null ? File(file.path!).openRead() : null);
    if (source == null) {
      throw Exception('No se pudo leer el archivo seleccionado.');
    }
    final request =
        http.StreamedRequest(
            'PUT',
            Uri.parse('$_baseUrl/v1/documents/uploads/$id/content'),
          )
          ..headers.addAll(_headers)
          ..headers['Content-Type'] = 'application/octet-stream'
          ..contentLength = file.size;
    final client = http.Client();
    try {
      final responseFuture = client
          .send(request)
          .then(http.Response.fromStream);
      var sent = 0;
      final writeFuture = () async {
        await request.sink.addStream(
          source.map((chunk) {
            sent += chunk.length;
            onProgress(sent / file.size);
            return chunk;
          }),
        );
        await request.sink.close();
      }();
      final results = await Future.wait<dynamic>([
        responseFuture,
        writeFuture,
      ], eagerError: true).timeout(const Duration(minutes: 3));
      final uploaded = results.first as http.Response;
      _requireSuccess(uploaded);
    } finally {
      client.close();
    }
    final complete = await http
        .post(
          Uri.parse('$_baseUrl/v1/documents/uploads/$id/complete'),
          headers: _headers,
        )
        .timeout(const Duration(seconds: 60));
    _requireSuccess(complete);
    return jsonDecode(complete.body) as Map<String, dynamic>;
  }

  /// Accept only our relative download routes; never send credentials to a model URL.
  Future<File> downloadDocument(String route) async {
    if (!RegExp(r'^/v1/documents/[a-zA-Z0-9_-]+/(?:versions/[0-9]+/)?download$')
        .hasMatch(route)) {
      throw Exception('Enlace de archivo no válido.');
    }
    final client = http.Client();
    Directory? directory;
    var complete = false;
    try {
      final request = http.Request('GET', Uri.parse('$_baseUrl$route'))
        ..headers.addAll(_headers)
        ..followRedirects = false;
      final response = await client
          .send(request)
          .timeout(const Duration(seconds: 20));
      if (response.statusCode != 200) {
        throw Exception('No se pudo descargar (${response.statusCode}).');
      }
      final disposition = response.headers['content-disposition'] ?? '';
      final encoded = RegExp(
        "filename\\*=utf-8''([^;]+)",
        caseSensitive: false,
      ).firstMatch(disposition)?.group(1);
      final quoted = RegExp(r'filename="([^"]+)"')
          .firstMatch(disposition)
          ?.group(1);
      final rawName = encoded != null
          ? Uri.decodeComponent(encoded)
          : quoted ?? 'archivo';
      final name = rawName.replaceAll(RegExp(r'[^a-zA-Z0-9._-]'), '_');
      directory = await (await getTemporaryDirectory()).createTemp('agenda-');
      final file = File(
        '${directory.path}/${name == '.' || name == '..' ? 'archivo' : name}',
      );
      final sink = file.openWrite();
      var received = 0;
      try {
        await for (final chunk in response.stream.timeout(
          const Duration(seconds: 60),
        )) {
          received += chunk.length;
          if (received > maxFileBytes) {
            throw Exception('El archivo excede 50 MB.');
          }
          sink.add(chunk);
        }
        await sink.flush();
      } finally {
        await sink.close();
      }
      complete = true;
      return file;
    } finally {
      client.close();
      if (!complete && directory != null) {
        await directory.delete(recursive: true);
      }
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

  /// Dates are local; end is exclusive. Surface failures instead of an empty agenda.
  Future<List<AgendaItem>> getAgendaRange({
    required DateTime start,
    required DateTime end,
  }) async {
    final uri = Uri.parse('$_baseUrl/v1/agenda/events').replace(
      queryParameters: {
        'start_date': DateFormat('yyyy-MM-dd').format(start),
        'end_date': DateFormat('yyyy-MM-dd')
            .format(end.subtract(const Duration(days: 1))),
        'timezone': 'America/Mexico_City',
      },
    );
    final response = await http
        .get(uri, headers: _headers)
        .timeout(const Duration(seconds: 12));
    if (response.statusCode != 200) {
      throw Exception('No se pudo cargar el horario (${response.statusCode}).');
    }
    return (jsonDecode(response.body) as List<dynamic>)
        .map((e) => AgendaItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<bool> recordActivity({
    required String requestId,
    required String activity,
    required DateTime observedAt,
  }) async {
    try {
      final response = await http
          .post(
            Uri.parse('$_baseUrl/v1/agenda/check-ins'),
            headers: _headers,
            body: jsonEncode({
              'request_id': requestId,
              'activity': activity,
              'observed_at': observedAt.toUtc().toIso8601String(),
            }),
          )
          .timeout(const Duration(seconds: 12));
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
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

  Future<Map<String, dynamic>> getChatWindow({
    DateTime? before,
    String? cursor,
  }) async {
    final uri = Uri.parse('$_baseUrl/v1/chat/history').replace(
      queryParameters: {
        if (before != null) 'before': before.toUtc().toIso8601String(),
        'cursor': ?cursor,
        'limit': '60',
      },
    );
    final response = await http
        .get(uri, headers: _headers)
        .timeout(const Duration(seconds: 15));
    _requireSuccess(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> openCheckIn(
    Map<String, dynamic> notification,
  ) async {
    final response = await http
        .post(
          Uri.parse('$_baseUrl/v1/chat/check-ins'),
          headers: _headers,
          body: jsonEncode(notification),
        )
        .timeout(const Duration(seconds: 15));
    _requireSuccess(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
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
      status: ProposalStatus.values.firstWhere(
        (status) => status.name == json['status'],
        orElse: () => ProposalStatus.pending,
      ),
      createdAt: json['created_at'] != null
          ? DateTime.parse(json['created_at'] as String)
          : DateTime.now(),
    );
  }
}
