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
  const ChatScreen({super.key});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _controller = TextEditingController();
  final _scrollController = ScrollController();
  bool _isGenerating = false;

  final List<ChatMessage> _messages = [
    ChatMessage(
      text: '¡Hola! Soy tu asistente de agenda. Puedo ayudarte a reorganizar tus horas, resolver conflictos o planear tu día.',
      isUser: false,
      timestamp: DateTime.now().subtract(const Duration(minutes: 1)),
    ),
  ];

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
    final history = _messages.take(_messages.length - 2).map((m) => {
      'text': m.text,
      'is_user': m.isUser,
    }).toList();

    try {
      final stream = ApiClient.instance.streamChat(
        message: text,
        history: history,
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
                  'Qwen 27B Autohosteado',
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
                          msg.text.isEmpty && _isGenerating ? 'Pensando...' : msg.text,
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
                            await ApiClient.instance.confirmProposal(msg.proposal!.id);
                            if (context.mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(
                                  content: Text('¡Propuesta aplicada con éxito!'),
                                  behavior: SnackBarBehavior.floating,
                                ),
                              );
                            }
                          },
                          onDismiss: () async {
                            await ApiClient.instance.rejectProposal(msg.proposal!.id);
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
                        hintText: _isGenerating ? 'Generando respuesta...' : 'Pide reorganizar o consulta...',
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
