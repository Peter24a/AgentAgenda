import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Botón inferior flotante ultra optimizado.
/// Diseñado para mantener 120 FPS fijos sin BackdropFilter innecesario.
class PremiumAgentButton extends StatefulWidget {
  final VoidCallback onTap;

  const PremiumAgentButton({super.key, required this.onTap});

  @override
  State<PremiumAgentButton> createState() => _PremiumAgentButtonState();
}

class _PremiumAgentButtonState extends State<PremiumAgentButton>
    with SingleTickerProviderStateMixin {
  late final AnimationController _pulseController;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2600),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _pulseController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return AnimatedBuilder(
      animation: _pulseController,
      builder: (context, _) {
        final pulseValue = _pulseController.value;

        return RepaintBoundary(
          child: Container(
            margin: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(32),
              boxShadow: [
                BoxShadow(
                  color: const Color(0xFF8AB4F8).withValues(
                    alpha: isDark ? (0.12 + (pulseValue * 0.12)) : 0.08,
                  ),
                  blurRadius: 16 + (pulseValue * 6),
                  spreadRadius: pulseValue * 1.5,
                ),
              ],
            ),
            child: Material(
              color: isDark
                  ? const Color(0xFF1E2631)
                  : const Color(0xFFF7F9FC),
              borderRadius: BorderRadius.circular(32),
              clipBehavior: Clip.antiAlias,
              child: InkWell(
                onTap: () {
                  HapticFeedback.lightImpact();
                  widget.onTap();
                },
                borderRadius: BorderRadius.circular(32),
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 20,
                    vertical: 14,
                  ),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(32),
                    border: Border.all(
                      color: Color.lerp(
                        const Color(0xFF8AB4F8).withValues(alpha: 0.30),
                        const Color(0xFFD0BCFF).withValues(alpha: 0.60),
                        pulseValue,
                      )!,
                      width: 1.4,
                    ),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Container(
                        padding: const EdgeInsets.all(6),
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          gradient: const LinearGradient(
                            colors: [Color(0xFF8AB4F8), Color(0xFFC3B5FF)],
                          ),
                          boxShadow: [
                            BoxShadow(
                              color: const Color(0xFF8AB4F8).withValues(alpha: 0.35),
                              blurRadius: 6,
                            ),
                          ],
                        ),
                        child: const Icon(
                          Icons.auto_awesome_rounded,
                          size: 16,
                          color: Colors.white,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Column(
                        mainAxisSize: MainAxisSize.min,
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Hablar con el Agente',
                            style: theme.textTheme.titleSmall?.copyWith(
                              fontWeight: FontWeight.w800,
                              letterSpacing: 0.2,
                            ),
                          ),
                          Text(
                            'Organizar, consultar o mover agenda',
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: theme.colorScheme.onSurfaceVariant
                                  .withValues(alpha: 0.8),
                              fontSize: 11,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(width: 12),
                      Icon(
                        Icons.arrow_forward_ios_rounded,
                        size: 13,
                        color: theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.6),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}
