import 'package:flutter/material.dart';
import '../../models/agenda_item.dart';

/// Tarjeta de actividad ultra fluida con atmósfera estética de emojis.
/// Optimizada sin BackdropFilter en listas para asegurar 120 FPS sin caídas de frames.
class AtmosphericCard extends StatelessWidget {
  final AgendaItem item;
  final VoidCallback onToggleComplete;
  final VoidCallback? onTap;

  const AtmosphericCard({
    super.key,
    required this.item,
    required this.onToggleComplete,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final category = item.category;

    final baseTint = category.tintColor;
    final cardBgColor = isDark
        ? Color.alphaBlend(baseTint.withValues(alpha: 0.16), theme.colorScheme.surfaceContainerHigh)
        : Color.alphaBlend(baseTint.withValues(alpha: 0.10), theme.colorScheme.surfaceContainerLow);

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
      child: Material(
        color: Colors.transparent,
        borderRadius: BorderRadius.circular(28),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(28),
          child: Container(
            decoration: BoxDecoration(
              color: cardBgColor,
              borderRadius: BorderRadius.circular(28),
              border: Border.all(
                color: isDark
                    ? baseTint.withValues(alpha: 0.22)
                    : baseTint.withValues(alpha: 0.14),
                width: 1.2,
              ),
            ),
            child: Stack(
              children: [
                // Emojis atmosféricos en el fondo con opacidad suave
                Positioned.fill(
                  child: _AtmosphericEmojiBackground(
                    emojis: category.backgroundEmojis,
                    isCompleted: item.isCompleted,
                  ),
                ),

                // Gradiente tonal suave para contraste legible
                Positioned.fill(
                  child: Container(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                        colors: [
                          (isDark ? Colors.black : Colors.white).withValues(alpha: 0.30),
                          Colors.transparent,
                          (isDark ? Colors.black : Colors.white).withValues(alpha: 0.12),
                        ],
                      ),
                    ),
                  ),
                ),

                // Contenido principal de la tarjeta
                Padding(
                  padding: const EdgeInsets.all(20.0),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 12,
                              vertical: 6,
                            ),
                            decoration: BoxDecoration(
                              color: theme.colorScheme.surface.withValues(
                                alpha: isDark ? 0.75 : 0.9,
                              ),
                              borderRadius: BorderRadius.circular(20),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Text(
                                  category.primaryEmoji,
                                  style: const TextStyle(fontSize: 14),
                                ),
                                const SizedBox(width: 6),
                                Text(
                                  item.timeRange,
                                  style: theme.textTheme.labelMedium?.copyWith(
                                    fontWeight: FontWeight.w700,
                                    letterSpacing: 0.3,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          const Spacer(),
                          IconButton.filledTonal(
                            onPressed: onToggleComplete,
                            icon: Icon(
                              item.isCompleted
                                  ? Icons.check_circle_rounded
                                  : Icons.radio_button_unchecked_rounded,
                              color: item.isCompleted
                                  ? theme.colorScheme.primary
                                  : theme.colorScheme.outline,
                            ),
                            style: IconButton.styleFrom(
                              backgroundColor: theme.colorScheme.surface.withValues(alpha: 0.8),
                              minimumSize: const Size(36, 36),
                              padding: EdgeInsets.zero,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),

                      Text(
                        item.title,
                        style: theme.textTheme.titleLarge?.copyWith(
                          fontWeight: FontWeight.w800,
                          decoration: item.isCompleted ? TextDecoration.lineThrough : null,
                          color: item.isCompleted
                              ? theme.colorScheme.onSurface.withValues(alpha: 0.5)
                              : theme.colorScheme.onSurface,
                        ),
                      ),

                      if (item.description != null && item.description!.isNotEmpty) ...[
                        const SizedBox(height: 6),
                        Text(
                          item.description!,
                          style: theme.textTheme.bodyMedium?.copyWith(
                            color: theme.colorScheme.onSurfaceVariant
                                .withValues(alpha: item.isCompleted ? 0.5 : 0.85),
                          ),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ],
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _AtmosphericEmojiBackground extends StatelessWidget {
  final List<String> emojis;
  final bool isCompleted;

  const _AtmosphericEmojiBackground({
    required this.emojis,
    required this.isCompleted,
  });

  @override
  Widget build(BuildContext context) {
    final opacity = isCompleted ? 0.08 : 0.22;

    return Opacity(
      opacity: opacity,
      child: Stack(
        children: [
          Positioned(
            right: -10,
            top: -15,
            child: Text(
              emojis.isNotEmpty ? emojis[0] : '✨',
              style: const TextStyle(fontSize: 80),
            ),
          ),
          if (emojis.length > 1)
            Positioned(
              left: 40,
              bottom: -20,
              child: Text(
                emojis[1],
                style: const TextStyle(fontSize: 60),
              ),
            ),
          if (emojis.length > 2)
            Positioned(
              right: 80,
              bottom: 10,
              child: Text(
                emojis[2],
                style: const TextStyle(fontSize: 48),
              ),
            ),
          if (emojis.length > 3)
            Positioned(
              left: -5,
              top: 15,
              child: Text(
                emojis[3],
                style: const TextStyle(fontSize: 42),
              ),
            ),
        ],
      ),
    );
  }
}
