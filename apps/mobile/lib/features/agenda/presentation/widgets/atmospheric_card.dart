import 'package:flutter/material.dart';
import '../../models/agenda_item.dart';

/// Tarjeta de actividad con la identidad visual SARA (v0.4.0).
/// Superficie sólida elevada (#FFFFFF / #1E1A22), radio de 12px,
/// borde neutro sutil (#DED8E2 / #3D3544) y cero degradados.
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
    final colorScheme = theme.colorScheme;
    final category = item.category;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 6.0),
      child: Material(
        color: colorScheme.surfaceContainerLow,
        borderRadius: BorderRadius.circular(12),
        elevation: 0,
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(12),
          child: Container(
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: item.isCompleted
                    ? colorScheme.outlineVariant.withValues(alpha: 0.6)
                    : colorScheme.outlineVariant,
                width: 1.0,
              ),
            ),
            child: Stack(
              children: [
                // Indicador visual lateral de estado activo / ciruela SARA (WCAG 1.4.1)
                Positioned(
                  left: 0,
                  top: 0,
                  bottom: 0,
                  width: 4,
                  child: ColoredBox(
                    color: item.isCompleted
                        ? colorScheme.outlineVariant
                        : colorScheme.primary,
                  ),
                ),

                Padding(
                  padding: const EdgeInsets.fromLTRB(18, 14, 14, 14),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          // Chip de tiempo / categoría con radio de 8px
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 10,
                              vertical: 5,
                            ),
                            decoration: BoxDecoration(
                              color: colorScheme.secondaryContainer,
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Text(
                                  category.primaryEmoji,
                                  style: const TextStyle(fontSize: 13),
                                ),
                                const SizedBox(width: 6),
                                Text(
                                  item.timeRange,
                                  style: theme.textTheme.labelMedium?.copyWith(
                                    fontWeight: FontWeight.w600,
                                    color: colorScheme.onSurface,
                                    letterSpacing: 0.2,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          const Spacer(),

                          // Botón de completar accesible
                          IconButton(
                            onPressed: onToggleComplete,
                            icon: Icon(
                              item.isCompleted
                                  ? Icons.check_circle_rounded
                                  : Icons.radio_button_unchecked_rounded,
                              color: item.isCompleted
                                  ? colorScheme.primary
                                  : colorScheme.outline,
                              size: 22,
                            ),
                            style: IconButton.styleFrom(
                              minimumSize: const Size(44, 44),
                              padding: EdgeInsets.zero,
                            ),
                            tooltip: item.isCompleted
                                ? 'Marcar como pendiente'
                                : 'Marcar como completada',
                          ),
                        ],
                      ),
                      const SizedBox(height: 10),

                      Text(
                        item.title,
                        style: theme.textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w700,
                          decoration: item.isCompleted
                              ? TextDecoration.lineThrough
                              : null,
                          color: item.isCompleted
                              ? colorScheme.onSurface.withValues(alpha: 0.45)
                              : colorScheme.onSurface,
                        ),
                      ),

                      if (item.description != null &&
                          item.description!.isNotEmpty) ...[
                        const SizedBox(height: 6),
                        Text(
                          item.description!,
                          style: theme.textTheme.bodyMedium?.copyWith(
                            color: colorScheme.onSurfaceVariant.withValues(
                              alpha: item.isCompleted ? 0.45 : 0.85,
                            ),
                            height: 1.4,
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
