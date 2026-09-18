import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Botón inferior de asistencia SARA.
/// Sigue la especificación de SARA v0.4.0: relleno sólido ciruela,
/// cero degradados, contraste AAA y contorno nítido.
class PremiumAgentButton extends StatelessWidget {
  final VoidCallback onTap;

  const PremiumAgentButton({super.key, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final isDark = theme.brightness == Brightness.dark;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
      child: Material(
        color: colorScheme.primary,
        borderRadius: BorderRadius.circular(12),
        elevation: isDark ? 0 : 2,
        shadowColor: Colors.black.withValues(alpha: 0.2),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: () {
            HapticFeedback.lightImpact();
            onTap();
          },
          child: Container(
            constraints: const BoxConstraints(minHeight: 48),
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: isDark ? colorScheme.outline : Colors.transparent,
                width: 1.0,
              ),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(
                  Icons.forum_rounded,
                  size: 18,
                  color: colorScheme.onPrimary,
                ),
                const SizedBox(width: 10),
                Text(
                  'Asistente SARA',
                  style: theme.textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.w700,
                    color: colorScheme.onPrimary,
                    letterSpacing: 0.2,
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  '· Planear día',
                  style: theme.textTheme.bodySmall?.copyWith(
                    fontWeight: FontWeight.w400,
                    color: colorScheme.onPrimary.withValues(alpha: 0.82),
                  ),
                ),
                const SizedBox(width: 8),
                Icon(
                  Icons.arrow_forward_rounded,
                  size: 16,
                  color: colorScheme.onPrimary.withValues(alpha: 0.8),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
