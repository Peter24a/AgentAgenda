import 'dart:convert';

import 'package:intl/intl.dart';

import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';

import '../../../../core/network/api_client.dart';
import '../../../documents/document_library.dart';
import '../../../agenda/models/agent_proposal.dart';
import '../../../agenda/presentation/widgets/agent_proposal_card.dart';

/// Mensaje en la conversación del asistente.
class ChatMessage {
  final String? id;
  String text;
  final bool isUser;
  final DateTime timestamp;
  AgentProposal? proposal;

  ChatMessage({
    this.id,
    required this.text,
    required this.isUser,
    required this.timestamp,
    this.proposal,
  });
}

/// Pantalla del chat de asistencia conectada con el LLM autohosteado.
class ChatScreen extends StatefulWidget {
  final String? initialPrompt;
  final bool checkIn;
  final DateTime? agendaDate;
  final Map<String, dynamic>? notification;
  const ChatScreen({
    super.key,
    this.initialPrompt,
    this.checkIn = false,
    this.agendaDate,
    this.notification,
  });

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _controller = TextEditingController();
  final _scrollController = ScrollController();
  bool _isGenerating = false;
  bool _uploading = false;
  double _uploadProgress = 0;
  bool _historyLoading = true;
  bool _olderLoading = false;
  bool _hasOlder = false;
  DateTime? _windowEnd;
  DateTime? _windowStart;
  String? _olderCursor;
  String? _historyError;
  late bool _checkInPending;
  DateTime? _checkInObservedAt;
  String? _checkInActivity;

  final List<ChatMessage> _messages = [
    ChatMessage(
      text: '¡Hola! Soy tu asistente de agenda. Puedo ayudarte a reorganizar tus horas, resolver conflictos o planear tu día.',
      isUser: false,
      timestamp: DateTime.now().subtract(const Duration(minutes: 1)),
    ),
  ];

  @override
  void initState() {
    super.initState();
    _checkInPending = widget.checkIn;
    if (!widget.checkIn && widget.initialPrompt != null) {
      _controller.text = widget.initialPrompt!;
    }
    _scrollController.addListener(_onHistoryScroll);
    _loadHistory();
  }

  ChatMessage _fromHistory(Map<String, dynamic> m) {
    final raw = m['created_at'] as String;
    final instant = DateTime.parse(
      RegExp(r'(Z|[+-]\d\d:\d\d)$').hasMatch(raw) ? raw : '${raw}Z',
    );
    return ChatMessage(
      id: m['id'] as String?,
      text: m['content'] as String,
      isUser: m['role'] == 'user',
      timestamp: instant.toLocal(),
    );
  }

  void _onHistoryScroll() {
    if (_scrollController.hasClients &&
        _scrollController.position.isScrollingNotifier.value &&
        _scrollController.position.pixels >=
            _scrollController.position.maxScrollExtent - 120 &&
        !_historyLoading &&
        !_olderLoading &&
        _hasOlder &&
        _historyError == null) {
      _loadOlder();
    }
  }

  Future<void> _loadOlder() async {
    if (_olderLoading || !_hasOlder) return;
    setState(() {
      _olderLoading = true;
      _historyError = null;
    });
    try {
      final page = await ApiClient.instance.getChatWindow(
        before: _olderCursor != null ? _windowEnd : _windowStart,
        cursor: _olderCursor,
      );
      if (!mounted) return;
      final seen = _messages.map((m) => m.id).whereType<String>().toSet();
      final messages = (page['messages'] as List)
          .cast<Map<String, dynamic>>()
          .map(_fromHistory)
          .where((m) => !seen.contains(m.id))
          .toList();
      setState(() {
        _messages.insertAll(0, messages);
        _windowEnd = DateTime.parse(page['window_end']);
        _windowStart = DateTime.parse(page['window_start']);
        _olderCursor = page['next_cursor'];
        _hasOlder = page['has_older'] == true;
      });
    } catch (_) {
      if (mounted) {
        setState(
          () => _historyError =
              'No se pudo cargar lo anterior. Toca para reintentar.',
        );
      }
    } finally {
      if (mounted) setState(() => _olderLoading = false);
    }
  }

  Future<void> _loadHistory() async {
    setState(() => _historyLoading = true);
    try {
      Map<String, dynamic>? checkIn;
      if (widget.checkIn) {
        checkIn = await ApiClient.instance.openCheckIn(
          widget.notification ??
              {
                'notification_key':
                    'manual-${DateTime.now().microsecondsSinceEpoch}',
                'kind': 'check_in',
              },
        );
      }
      final page = await ApiClient.instance.getChatWindow();
      if (!mounted) return;
      setState(() {
        _messages.clear();
        _messages.addAll(
          (page['messages'] as List).cast<Map<String, dynamic>>().map(
            _fromHistory,
          ),
        );
        if (checkIn != null && !_messages.any((m) => m.id == checkIn!['id'])) {
          _messages.add(_fromHistory(checkIn));
        }
        _windowEnd = DateTime.parse(page['window_end']);
        _windowStart = DateTime.parse(page['window_start']);
        _olderCursor = page['next_cursor'];
        _hasOlder = page['has_older'] == true;
        _historyError = null;
      });
    } catch (_) {
      if (mounted) {
        setState(
          () => _historyError = 'No se pudo cargar el historial. Reintentar',
        );
      }
    }
    final pending = await ApiClient.instance.getPendingProposal();
    if (mounted && pending != null) {
      setState(
        () => _messages.add(
          ChatMessage(
            text: 'Cambio pendiente de aprobar',
            isUser: false,
            timestamp: DateTime.now(),
            proposal: pending,
          ),
        ),
      );
    }
    if (mounted) setState(() => _historyLoading = false);
  }

  @override
  void dispose() {
    _controller.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          0,
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOut,
        );
      }
    });
  }

  void _sendMessage() async {
    final text = _controller.text.trim();
    if (text.isEmpty || _isGenerating || _uploading || _historyLoading) return;

    if (_checkInPending) {
      if (_checkInActivity != text) {
        _checkInObservedAt = DateTime.now();
        _checkInActivity = text;
      }
      setState(() => _isGenerating = true);
      final saved = await ApiClient.instance.recordActivity(
        requestId: 'phone-${_checkInObservedAt!.microsecondsSinceEpoch}',
        activity: text,
        observedAt: _checkInObservedAt!,
      );
      if (!mounted) return;
      if (!saved) {
        setState(() => _isGenerating = false);
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'No se pudo guardar la actividad. Tu respuesta sigue aquí; vuelve a enviar.',
            ),
          ),
        );
        return;
      }
      _checkInPending = false;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Actividad guardada en tu memoria.')),
      );
    }

    _controller.clear();
    setState(() {
      _messages.add(
        ChatMessage(text: text, isUser: true, timestamp: DateTime.now()),
      );
      // Empty placeholder for assistant response
      _messages.add(
        ChatMessage(text: '', isUser: false, timestamp: DateTime.now()),
      );
      _isGenerating = true;
    });
    _scrollToBottom();

    final assistantMessage = _messages.last;

    try {
      final stream = ApiClient.instance.streamChat(
        message: text,
        date: widget.agendaDate,
      );

      await for (final event in stream) {
        if (!mounted) break;
        if (event is ChatTokenEvent) {
          setState(() {
            assistantMessage.text += event.token;
          });
          if (_scrollController.hasClients && _scrollController.offset < 160) {
            _scrollToBottom();
          }
        } else if (event is ChatProposalEvent) {
          setState(() {
            assistantMessage.proposal = event.proposal;
          });
          _scrollToBottom();
        } else if (event is ChatErrorEvent) {
          setState(() {
            assistantMessage.text = event.message;
          });
        }
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          assistantMessage.text = 'No se pudo conectar con el servidor: $e';
        });
      }
    } finally {
      if (mounted) {
        setState(() => _isGenerating = false);
        _scrollToBottom();
      }
    }
  }

  Future<void> _attachFile(bool photos) async {
    setState(() {
      _uploading = true;
      _uploadProgress = 0;
    });
    try {
      final file = await pickAgendaFile(photos: photos);
      if (file == null) return;
      final doc = await ApiClient.instance.uploadDocument(
        file,
        onProgress: (progress) {
          if (mounted) setState(() => _uploadProgress = progress);
        },
      );
      if (!mounted) return;
      final name = (doc['title'] as String).replaceAll(
        RegExp(r'[\[\]()`<>\\]'),
        '',
      );
      final link = '[$name](/v1/documents/${doc['id']}/download)';
      setState(() {
        _messages.add(
          ChatMessage(
            text: 'Archivo guardado: $link',
            isUser: false,
            timestamp: DateTime.now(),
          ),
        );
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Archivo guardado. Puedes recuperarlo en Mis archivos.',
          ),
        ),
      );
      _scrollToBottom();
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('No se pudo subir: $error')));
      }
    } finally {
      if (mounted) setState(() => _uploading = false);
    }
  }

  /// Limpia citas documentales internas ([D1], [D2]) y apéndices técnicos
  /// de procedencia para ofrecer una experiencia conversacional limpia y ejecutiva.
  String _cleanMessageText(String text) {
    if (text.isEmpty) return text;
    var cleaned = text;
    // Never render the machine-readable proposal or an unfinished streamed block.
    final proposalIndex = cleaned.indexOf('```proposal');
    if (proposalIndex != -1) {
      final block = RegExp(
        r'```proposal\s*(\{.*?\})\s*```',
        dotAll: true,
      ).firstMatch(cleaned);
      if (block != null) {
        cleaned = cleaned.replaceFirst(block.group(0)!, '');
        if (cleaned
            .split('Fuentes disponibles')
            .first
            .replaceAll('---', '')
            .trim()
            .isEmpty) {
          try {
            final proposal =
                jsonDecode(block.group(1)!) as Map<String, dynamic>;
            cleaned = 'Propuesta: ${proposal['summary'] ?? "ajuste de agenda"}';
          } catch (_) {
            cleaned = 'Propuesta de ajuste de agenda.';
          }
        }
      } else {
        cleaned = cleaned.substring(0, proposalIndex);
        if (cleaned.trim().isEmpty) cleaned = 'Preparando propuesta…';
      }
    }

    // 1. Omitir el bloque de apéndice de fuentes documentales
    final appendixIndex = cleaned.indexOf('\n\n---\nFuentes disponibles');
    if (appendixIndex != -1) {
      cleaned = cleaned.substring(0, appendixIndex);
    }
    final altAppendixIndex = cleaned.indexOf('---\nFuentes disponibles');
    if (altAppendixIndex != -1) {
      cleaned = cleaned.substring(0, altAppendixIndex);
    }
    final plainAppendixIndex = cleaned.indexOf(
      'Fuentes disponibles para esta respuesta:',
    );
    if (plainAppendixIndex != -1) {
      cleaned = cleaned.substring(0, plainAppendixIndex);
    }

    // 2. Eliminar referencias entre corchetes tipo [D1], [D2], etc.
    cleaned = cleaned.replaceAll(RegExp(r'\s*\[D\d+\]'), '');

    return cleaned.trimRight();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Scaffold(
      appBar: AppBar(
        actions: [
          IconButton(
            tooltip: 'Mis archivos',
            icon: const Icon(Icons.folder_open_outlined),
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute<void>(builder: (_) => const DocumentLibrary()),
            ),
          ),
        ],
        titleSpacing: 0,
        title: Row(
          children: [
            CircleAvatar(
              radius: 18,
              backgroundColor: theme.colorScheme.primaryContainer,
              child: Icon(
                Icons.forum_rounded,
                size: 18,
                color: theme.colorScheme.primary,
              ),
            ),
            const SizedBox(width: 12),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Asistente SARA',
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
                ),
                Text(
                  'Productividad y Agenda',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.primary,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView.builder(
              controller: _scrollController,
              reverse: true,
              padding: const EdgeInsets.all(16),
              itemCount: _messages.length + 1,
              itemBuilder: (context, index) {
                if (index == _messages.length) {
                  return Padding(
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    child: Column(
                      children: [
                        if (_windowStart != null)
                          Text(
                            'Historial desde ${DateFormat("dd/MM HH:mm").format(_windowStart!.toLocal())}',
                            style: theme.textTheme.bodySmall,
                          ),
                        if (_olderLoading) const CircularProgressIndicator(),
                        if (_historyError != null)
                          TextButton(
                            onPressed: _windowStart == null
                                ? _loadHistory
                                : _loadOlder,
                            child: Text(_historyError!),
                          )
                        else if (_hasOlder && !_olderLoading)
                          TextButton(
                            onPressed: _loadOlder,
                            child: const Text('Cargar 12 horas anteriores'),
                          )
                        else if (!_historyLoading && !_olderLoading)
                          const Text('Inicio de la conversación'),
                      ],
                    ),
                  );
                }
                final msg = _messages[_messages.length - 1 - index];
                return Column(
                  crossAxisAlignment: msg.isUser
                      ? CrossAxisAlignment.end
                      : CrossAxisAlignment.start,
                  children: [
                    Padding(
                      padding: const EdgeInsets.only(top: 10, bottom: 4),
                      child: Text(
                        DateFormat('dd/MM · HH:mm').format(msg.timestamp),
                        style: theme.textTheme.labelSmall,
                      ),
                    ),
                    if (msg.text.isNotEmpty || msg.isUser || _isGenerating)
                      Container(
                        margin: const EdgeInsets.only(bottom: 8),
                        constraints: BoxConstraints(
                          maxWidth: MediaQuery.of(context).size.width * 0.82,
                        ),
                        padding: const EdgeInsets.symmetric(
                          horizontal: 16,
                          vertical: 12,
                        ),
                        decoration: BoxDecoration(
                          color: msg.isUser
                              ? theme.colorScheme.primary
                              : theme.colorScheme.surfaceContainerLow,
                          border: msg.isUser
                              ? null
                              : Border.all(
                                  color: theme.colorScheme.outlineVariant,
                                  width: 1.0,
                                ),
                          borderRadius: BorderRadius.only(
                            topLeft: const Radius.circular(12),
                            topRight: const Radius.circular(12),
                            bottomLeft: Radius.circular(msg.isUser ? 12 : 3),
                            bottomRight: Radius.circular(msg.isUser ? 3 : 12),
                          ),
                        ),
                        child: msg.isUser
                            ? Text(
                                msg.text,
                                style: theme.textTheme.bodyMedium?.copyWith(
                                  color: theme.colorScheme.onPrimary,
                                  height: 1.35,
                                ),
                              )
                            : (msg.text.isEmpty && _isGenerating
                                  ? Row(
                                      mainAxisSize: MainAxisSize.min,
                                      children: [
                                        SizedBox(
                                          width: 14,
                                          height: 14,
                                          child: CircularProgressIndicator(
                                            strokeWidth: 2,
                                            color: theme.colorScheme.primary,
                                          ),
                                        ),
                                        const SizedBox(width: 8),
                                        Text(
                                          'Pensando...',
                                          style: theme.textTheme.bodyMedium
                                              ?.copyWith(
                                                color: theme
                                                    .colorScheme
                                                    .onSurface
                                                    .withValues(alpha: 0.7),
                                                fontStyle: FontStyle.italic,
                                              ),
                                        ),
                                      ],
                                    )
                                  : MarkdownBody(
                                      data: _cleanMessageText(msg.text),
                                      onTapLink: (text, href, title) {
                                        if (href != null &&
                                            href.startsWith('/v1/documents/')) {
                                          openAgendaDocument(context, href);
                                        }
                                      },
                                      selectable: true,
                                      softLineBreak: true,
                                      styleSheet:
                                          MarkdownStyleSheet.fromTheme(
                                            theme,
                                          ).copyWith(
                                            p: theme.textTheme.bodyMedium
                                                ?.copyWith(
                                                  color: theme
                                                      .colorScheme
                                                      .onSurface,
                                                  height: 1.4,
                                                ),
                                            h1: theme.textTheme.titleLarge
                                                ?.copyWith(
                                                  fontWeight: FontWeight.bold,
                                                  color: theme
                                                      .colorScheme
                                                      .onSurface,
                                                ),
                                            h2: theme.textTheme.titleMedium
                                                ?.copyWith(
                                                  fontWeight: FontWeight.bold,
                                                  color: theme
                                                      .colorScheme
                                                      .onSurface,
                                                ),
                                            h3: theme.textTheme.titleSmall
                                                ?.copyWith(
                                                  fontWeight: FontWeight.bold,
                                                  color: theme
                                                      .colorScheme
                                                      .onSurface,
                                                ),
                                            strong: theme.textTheme.bodyMedium
                                                ?.copyWith(
                                                  fontWeight: FontWeight.bold,
                                                  color: theme
                                                      .colorScheme
                                                      .onSurface,
                                                ),
                                            em: theme.textTheme.bodyMedium
                                                ?.copyWith(
                                                  fontStyle: FontStyle.italic,
                                                  color: theme
                                                      .colorScheme
                                                      .onSurface,
                                                ),
                                            code: TextStyle(
                                              backgroundColor: isDark
                                                  ? theme
                                                        .colorScheme
                                                        .surfaceContainerHighest
                                                  : theme
                                                        .colorScheme
                                                        .surfaceContainerHighest
                                                        .withValues(alpha: 0.5),
                                              fontFamily: 'monospace',
                                              fontSize: 13,
                                              color: theme.colorScheme.primary,
                                            ),
                                            codeblockDecoration: BoxDecoration(
                                              color: isDark
                                                  ? theme
                                                        .colorScheme
                                                        .surfaceContainerHighest
                                                  : theme
                                                        .colorScheme
                                                        .surfaceContainerHighest
                                                        .withValues(alpha: 0.5),
                                              borderRadius:
                                                  BorderRadius.circular(8),
                                            ),
                                            blockquoteDecoration: BoxDecoration(
                                              border: Border(
                                                left: BorderSide(
                                                  color:
                                                      theme.colorScheme.primary,
                                                  width: 3,
                                                ),
                                              ),
                                              color: theme
                                                  .colorScheme
                                                  .surfaceContainerHighest
                                                  .withValues(alpha: 0.3),
                                              borderRadius:
                                                  const BorderRadius.only(
                                                    topRight: Radius.circular(
                                                      4,
                                                    ),
                                                    bottomRight:
                                                        Radius.circular(4),
                                                  ),
                                            ),
                                            listBullet: theme
                                                .textTheme
                                                .bodyMedium
                                                ?.copyWith(
                                                  color:
                                                      theme.colorScheme.primary,
                                                  fontWeight: FontWeight.bold,
                                                ),
                                            blockSpacing: 8,
                                          ),
                                    )),
                      ),
                    if (msg.proposal != null &&
                        msg.proposal!.status == ProposalStatus.pending)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 12),
                        child: AgentProposalCard(
                          proposal: msg.proposal!,
                          onAccept: () async {
                            final applied = await ApiClient.instance
                                .confirmProposal(msg.proposal!.id);
                            if (applied && mounted) {
                              setState(
                                () => msg.proposal = msg.proposal!.copyWith(
                                  status: ProposalStatus.accepted,
                                ),
                              );
                            }
                            if (context.mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                SnackBar(
                                  content: Text(
                                    applied
                                        ? '¡Propuesta aplicada con éxito!'
                                        : 'No se pudo aplicar la propuesta.',
                                  ),
                                  behavior: SnackBarBehavior.floating,
                                ),
                              );
                            }
                          },
                          onDismiss: () async {
                            final rejected = await ApiClient.instance
                                .rejectProposal(msg.proposal!.id);
                            if (rejected && mounted) {
                              setState(
                                () => msg.proposal = msg.proposal!.copyWith(
                                  status: ProposalStatus.rejected,
                                ),
                              );
                            }
                            if (!rejected && context.mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(
                                  content: Text(
                                    'No se pudo descartar la propuesta.',
                                  ),
                                  behavior: SnackBarBehavior.floating,
                                ),
                              );
                            }
                          },
                        ),
                      ),
                  ],
                );
              },
            ),
          ),
          if (_historyLoading) const LinearProgressIndicator(),
          if (_uploading)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Column(
                children: [
                  LinearProgressIndicator(
                    value: _uploadProgress < 1 ? _uploadProgress : null,
                  ),
                  Text(
                    _uploadProgress < 1
                        ? 'Subiendo archivo…'
                        : 'Guardando archivo…',
                  ),
                ],
              ),
            ),
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
              child: Row(
                children: [
                  PopupMenuButton<bool>(
                    tooltip: 'Adjuntar archivo',
                    enabled: !_isGenerating && !_uploading && !_historyLoading,
                    icon: const Icon(Icons.attach_file),
                    onSelected: _attachFile,
                    itemBuilder: (_) => const [
                      PopupMenuItem(value: true, child: Text('Subir foto')),
                      PopupMenuItem(
                        value: false,
                        child: Text('Subir documento'),
                      ),
                    ],
                  ),
                  Expanded(
                    child: TextField(
                      controller: _controller,
                      enabled:
                          !_isGenerating && !_uploading && !_historyLoading,
                      decoration: InputDecoration(
                        hintText: _isGenerating
                            ? 'Generando respuesta...'
                            : (_checkInPending
                                  ? '¿Qué estás haciendo ahora?'
                                  : 'Pide reorganizar o consulta...'),
                        filled: true,
                        fillColor: theme.colorScheme.surfaceContainerLow,
                        contentPadding: const EdgeInsets.symmetric(
                          horizontal: 16,
                          vertical: 14,
                        ),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(8),
                          borderSide: BorderSide(
                            color: theme.colorScheme.outlineVariant,
                            width: 1.0,
                          ),
                        ),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(8),
                          borderSide: BorderSide(
                            color: theme.colorScheme.outlineVariant,
                            width: 1.0,
                          ),
                        ),
                        focusedBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(8),
                          borderSide: BorderSide(
                            color: theme.colorScheme.primary,
                            width: 1.5,
                          ),
                        ),
                      ),
                      onSubmitted: (_) => _sendMessage(),
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton.filled(
                    onPressed: _isGenerating || _uploading || _historyLoading
                        ? null
                        : _sendMessage,
                    icon: _isGenerating
                        ? SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: theme.colorScheme.onPrimary,
                            ),
                          )
                        : const Icon(Icons.send_rounded),
                    style: IconButton.styleFrom(
                      backgroundColor: theme.colorScheme.primary,
                      foregroundColor: theme.colorScheme.onPrimary,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
                      minimumSize: const Size(48, 48),
                      padding: const EdgeInsets.all(12),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
