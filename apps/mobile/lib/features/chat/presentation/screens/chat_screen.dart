import 'package:flutter/material.dart';

import '../../../../core/network/api_client.dart';
import '../../../agenda/models/agent_proposal.dart';
import '../../../agenda/presentation/widgets/agent_proposal_card.dart';

/// Mensaje en la conversación del asistente.
class ChatMessage {
  String text;
  final bool isUser;
  final DateTime timestamp;
  AgentProposal? proposal;

  ChatMessage({
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
  const ChatScreen({
    super.key,
    this.initialPrompt,
    this.checkIn = false,
    this.agendaDate,
  });

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _controller = TextEditingController();
  final _scrollController = ScrollController();
  bool _isGenerating = false;
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
    _loadHistory();
  }

  Future<void> _loadHistory() async {
    try {
      final messages = await ApiClient.instance.getChatMessages(limit: 50);
      if (messages.isNotEmpty && mounted) {
        setState(() {
          _messages.clear();
          for (final m in messages) {
            final text = m['content'] as String? ?? m['text'] as String? ?? '';
            final role = m['role'] as String?;
            final isUser = role == 'user' || m['is_user'] == true;
            if (text.isNotEmpty) {
              _messages.add(
                ChatMessage(
                  text: text,
                  isUser: isUser,
                  timestamp: m['created_at'] != null
                      ? DateTime.parse(m['created_at'] as String)
                      : DateTime.now(),
                ),
              );
            }
          }
          if (_messages.isEmpty) {
            _messages.add(
              ChatMessage(
                text: '¡Hola! Soy tu asistente de agenda. Puedo ayudarte a reorganizar tus horas, resolver conflictos o planear tu día.',
                isUser: false,
                timestamp: DateTime.now(),
              ),
            );
          }
        });
        _scrollToBottom();
      }
    } catch (_) {}
    if (mounted && widget.checkIn) {
      setState(() {
        _messages.add(
          ChatMessage(
            text:
                'Ahora hay un espacio libre en tu horario. ¿Qué estás haciendo? '
                'Tu respuesta quedará guardada con la hora para recordar cómo fue tu día.',
            isUser: false,
            timestamp: DateTime.now(),
          ),
        );
      });
      _scrollToBottom();
    }
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
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOut,
        );
      }
    });
  }

  void _sendMessage() async {
    final text = _controller.text.trim();
    if (text.isEmpty || _isGenerating) return;

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

    final assistantMsgIndex = _messages.length - 1;

    // Build history
    final history = _messages
        .take(_messages.length - 2)
        .map((m) => {'text': m.text, 'is_user': m.isUser})
        .toList();

    try {
      final stream = ApiClient.instance.streamChat(
        message: text,
        history: history,
        date: widget.agendaDate,
      );

      await for (final event in stream) {
        if (!mounted) break;
        if (event is ChatTokenEvent) {
          setState(() {
            _messages[assistantMsgIndex].text += event.token;
          });
          _scrollToBottom();
        } else if (event is ChatProposalEvent) {
          setState(() {
            _messages[assistantMsgIndex].proposal = event.proposal;
          });
          _scrollToBottom();
        } else if (event is ChatErrorEvent) {
          setState(() {
            _messages[assistantMsgIndex].text = event.message;
          });
        }
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _messages[assistantMsgIndex].text =
              'No se pudo conectar con el servidor: $e';
        });
      }
    } finally {
      if (mounted) {
        setState(() => _isGenerating = false);
        _scrollToBottom();
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Scaffold(
      appBar: AppBar(
        titleSpacing: 0,
        title: Row(
          children: [
            CircleAvatar(
              radius: 18,
              backgroundColor: theme.colorScheme.primaryContainer,
              child: Icon(
                Icons.auto_awesome_rounded,
                size: 20,
                color: theme.colorScheme.onPrimaryContainer,
              ),
            ),
            const SizedBox(width: 12),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Asistente Agenda',
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
                ),
                Text(
                  'Tu horario y contexto personal',
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
              padding: const EdgeInsets.all(16),
              itemCount: _messages.length,
              itemBuilder: (context, index) {
                final msg = _messages[index];
                return Column(
                  crossAxisAlignment: msg.isUser
                      ? CrossAxisAlignment.end
                      : CrossAxisAlignment.start,
                  children: [
                    if (msg.text.isNotEmpty || msg.isUser)
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
                              : (isDark
                                    ? theme.colorScheme.surfaceContainerHigh
                                    : theme.colorScheme.surfaceContainerLow),
                          borderRadius: BorderRadius.only(
                            topLeft: const Radius.circular(20),
                            topRight: const Radius.circular(20),
                            bottomLeft: Radius.circular(msg.isUser ? 20 : 4),
                            bottomRight: Radius.circular(msg.isUser ? 4 : 20),
                          ),
                        ),
                        child: Text(
                          msg.text.isEmpty && _isGenerating
                              ? 'Pensando...'
                              : msg.text,
                          style: theme.textTheme.bodyMedium?.copyWith(
                            color: msg.isUser
                                ? theme.colorScheme.onPrimary
                                : theme.colorScheme.onSurface,
                            height: 1.35,
                          ),
                        ),
                      ),
                    if (msg.proposal != null)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 12),
                        child: AgentProposalCard(
                          proposal: msg.proposal!,
                          onAccept: () async {
                            final applied = await ApiClient.instance
                                .confirmProposal(msg.proposal!.id);
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
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
              child: Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _controller,
                      enabled: !_isGenerating,
                      decoration: InputDecoration(
                        hintText: _isGenerating
                            ? 'Generando respuesta...'
                            : (_checkInPending
                                  ? '¿Qué estás haciendo ahora?'
                                  : 'Pide reorganizar o consulta...'),
                        filled: true,
                        fillColor: theme.colorScheme.surfaceContainerHighest
                            .withValues(alpha: 0.5),
                        contentPadding: const EdgeInsets.symmetric(
                          horizontal: 20,
                          vertical: 14,
                        ),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(28),
                          borderSide: BorderSide.none,
                        ),
                      ),
                      onSubmitted: (_) => _sendMessage(),
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton.filled(
                    onPressed: _isGenerating ? null : _sendMessage,
                    icon: _isGenerating
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.send_rounded),
                    style: IconButton.styleFrom(
                      shape: const CircleBorder(),
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
