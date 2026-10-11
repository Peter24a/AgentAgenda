import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../../core/branding/sara_brand_mark.dart';

/// Opens the assistant with the official SARA mark and a short scale response.
class PremiumAgentButton extends StatefulWidget {
  final VoidCallback onTap;
  final GlobalKey? surfaceKey;

  const PremiumAgentButton({super.key, required this.onTap, this.surfaceKey});

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
    if (!MediaQuery.disableAnimationsOf(context)) {
      _scaleController.forward(from: 0.0);
    }

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
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 320),
        child: ScaleTransition(
          scale: _scaleAnimation,
          child: Material(
            key: widget.surfaceKey,
            color: colorScheme.primary,
            borderRadius: BorderRadius.circular(18),
            elevation: isDark ? 0 : 1,
            shadowColor: colorScheme.primary.withValues(alpha: 0.16),
            clipBehavior: Clip.antiAlias,
            child: InkWell(
              onTap: _handleTap,
              splashColor: colorScheme.onPrimary.withValues(alpha: 0.12),
              child: ConstrainedBox(
                constraints: const BoxConstraints(minHeight: 54),
                child: Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 20,
                    vertical: 14,
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      SaraBrandMark(size: 24, color: colorScheme.onPrimary),
                      const SizedBox(width: 12),
                      Flexible(
                        child: Text(
                          'Asistente SARA',
                          style: theme.textTheme.titleSmall?.copyWith(
                            fontWeight: FontWeight.w700,
                            color: colorScheme.onPrimary,
                          ),
                        ),
                      ),
                      const SizedBox(width: 16),
                      Icon(
                        Icons.arrow_forward_rounded,
                        size: 18,
                        color: colorScheme.onPrimary.withValues(alpha: 0.85),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
