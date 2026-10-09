import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../../core/branding/sara_brand_mark.dart';

/// Opens the assistant with the official SARA mark and a short scale response.
class PremiumAgentButton extends StatefulWidget {
  final VoidCallback onTap;

  const PremiumAgentButton({super.key, required this.onTap});

  @override
  State<PremiumAgentButton> createState() => _PremiumAgentButtonState();
}

class _PremiumAgentButtonState extends State<PremiumAgentButton>
    with SingleTickerProviderStateMixin {
  late final AnimationController _scaleController;
  late final Animation<double> _scaleAnimation;
  bool _isNavigating = false;

  @override
  void initState() {
    super.initState();
    _scaleController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 160),
    );

    _scaleAnimation = TweenSequence<double>([
      TweenSequenceItem(
        tween: Tween<double>(
          begin: 1.0,
          end: 0.95,
        ).chain(CurveTween(curve: Curves.easeOutCubic)),
        weight: 40,
      ),
      TweenSequenceItem(
        tween: Tween<double>(
          begin: 0.95,
          end: 1.0,
        ).chain(CurveTween(curve: Curves.elasticOut)),
        weight: 60,
      ),
    ]).animate(_scaleController);
  }

  @override
  void dispose() {
    _scaleController.dispose();
    super.dispose();
  }

  void _handleTap() {
    if (_isNavigating) return;
    _isNavigating = true;

    // Preserve the tactile response and navigation guard.
    HapticFeedback.mediumImpact();
    _scaleController.forward(from: 0.0);

    // Let the press response finish before opening the assistant.
    Future.delayed(const Duration(milliseconds: 250), () {
      if (mounted) {
        widget.onTap();
        // Restablecer guardia tras la apertura de la ruta
        Future.delayed(const Duration(milliseconds: 350), () {
          if (mounted) {
            setState(() {
              _isNavigating = false;
            });
          }
        });
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final isDark = theme.brightness == Brightness.dark;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
      child: Stack(
        alignment: Alignment.center,
        clipBehavior: Clip.none,
        children: [
          // Botón físico interactivo
          ScaleTransition(
            scale: _scaleAnimation,
            child: Material(
              color: colorScheme.primary,
              borderRadius: BorderRadius.circular(12),
              elevation: isDark ? 0 : 3,
              shadowColor: Colors.black.withValues(alpha: 0.25),
              clipBehavior: Clip.antiAlias,
              child: InkWell(
                onTap: _handleTap,
                splashColor: (isDark ? Colors.black : Colors.white).withValues(
                  alpha: 0.15,
                ),
                highlightColor: (isDark ? Colors.black : Colors.white)
                    .withValues(alpha: 0.08),
                child: Container(
                  constraints: const BoxConstraints(minHeight: 48),
                  padding: const EdgeInsets.symmetric(
                    horizontal: 20,
                    vertical: 12,
                  ),
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
                      SaraBrandMark(size: 20, color: colorScheme.onPrimary),
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
                          color: colorScheme.onPrimary.withValues(alpha: 0.85),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Icon(
                        Icons.arrow_forward_rounded,
                        size: 16,
                        color: colorScheme.onPrimary.withValues(alpha: 0.85),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
