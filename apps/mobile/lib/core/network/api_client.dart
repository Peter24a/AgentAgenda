import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:intl/intl.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../features/agenda/models/agenda_item.dart';
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

class ApiClient {
  static final ApiClient instance = ApiClient._();
  ApiClient._();

  static const String _defaultUrl = 'http://148.213.1.200:8001'; // Default remote/local server
  static const String _prefKey = 'backend_base_url';

  String _baseUrl = _defaultUrl;
  String get baseUrl => _baseUrl;

  Future<void> init() async {
    final prefs = await SharedPreferences.getInstance();
    _baseUrl = prefs.getString(_prefKey) ?? _defaultUrl;
  }

  Future<void> setBaseUrl(String url) async {
    _baseUrl = url.replaceAll(RegExp(r'/+$'), '');
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_prefKey, _baseUrl);
  }

  Future<List<AgendaItem>> getEvents({DateTime? date}) async {
    final targetDate = date ?? DateTime.now();
    final dateStr = DateFormat('yyyy-MM-dd').format(targetDate);
    final uri = Uri.parse('$_baseUrl/v1/agenda/events?date=$dateStr');

    try {
      final response = await http.get(uri).timeout(const Duration(seconds: 8));
      if (response.statusCode == 200) {
        final List<dynamic> list = jsonDecode(response.body);
        return list.map((e) => _itemFromJson(e as Map<String, dynamic>)).toList();
      }
    } catch (_) {}
    return [];
  }

  Future<bool> toggleEvent(String eventId, {DateTime? date}) async {
    final targetDate = date ?? DateTime.now();
    final dateStr = DateFormat('yyyy-MM-dd').format(targetDate);
    final uri = Uri.parse('$_baseUrl/v1/agenda/events/$eventId/toggle?date=$dateStr');

    try {
      final response = await http.post(uri).timeout(const Duration(seconds: 6));
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  Future<AgentProposal?> getPendingProposal() async {
    final uri = Uri.parse('$_baseUrl/v1/proposals/pending');
    try {
      final response = await http.get(uri).timeout(const Duration(seconds: 6));
      if (response.statusCode == 200 && response.body != 'null') {
        final Map<String, dynamic> data = jsonDecode(response.body);
        return _proposalFromJson(data);
      }
    } catch (_) {}
    return null;
  }

  Future<bool> confirmProposal(String proposalId) async {
    final uri = Uri.parse('$_baseUrl/v1/proposals/$proposalId/confirm');
    try {
      final response = await http.post(uri).timeout(const Duration(seconds: 8));
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  Future<bool> rejectProposal(String proposalId) async {
    final uri = Uri.parse('$_baseUrl/v1/proposals/$proposalId/reject');
    try {
      final response = await http.post(uri).timeout(const Duration(seconds: 8));
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

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
      ..headers['Content-Type'] = 'application/json'
      ..headers['Accept'] = 'text/event-stream'
      ..body = body;

    http.StreamedResponse response;
    try {
      final client = http.Client();
      response = await client.send(request);
    } catch (e) {
      yield ChatErrorEvent('Error de conexión: no se pudo alcanzar el backend.');
      return;
    }

    if (response.statusCode != 200) {
      yield ChatErrorEvent('Servidor respondió con código ${response.statusCode}');
      return;
    }

    final lines = response.stream
        .transform(utf8.decoder)
        .transform(const LineSplitter());

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
          yield const ChatDoneEvent();
        }
      } catch (_) {}
    }
  }

  AgendaItem _itemFromJson(Map<String, dynamic> json) {
    final catStr = json['category'] as String? ?? 'general';
    final cat = ActivityCategory.values.firstWhere(
      (c) => c.name == catStr,
      orElse: () => ActivityCategory.general,
    );

    return AgendaItem(
      id: json['id'] as String,
      title: json['title'] as String,
      description: json['description'] as String?,
      startTime: DateTime.parse(json['start_time'] as String),
      endTime: json['end_time'] != null
          ? DateTime.parse(json['end_time'] as String)
          : null,
      category: cat,
      isCompleted: json['is_completed'] as bool? ?? false,
    );
  }

  AgentProposal _proposalFromJson(Map<String, dynamic> json) {
    final rawItems = json['resulting_items'] as List<dynamic>? ?? [];
    final items = rawItems
        .map((x) => _itemFromJson(x as Map<String, dynamic>))
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
