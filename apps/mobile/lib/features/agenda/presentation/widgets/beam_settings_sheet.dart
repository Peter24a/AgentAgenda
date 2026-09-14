import 'package:flutter/material.dart';
import '../../../../core/theme/beam_color_notifier.dart';

/// Modal para personalizar el color del lazo luminoso ("gusanito"),
/// incluyendo opción multicolor estilo Google / Gemini.
class BeamSettingsSheet extends StatelessWidget {
  const BeamSettingsSheet({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 16, 24, 32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Center(
            child: Container(
              width: 36,
              height: 4,
              decoration: BoxDecoration(
                color: theme.colorScheme.outlineVariant,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
          const SizedBox(height: 18),

          Row(
            children: [
              const Icon(Icons.palette_outlined, size: 22),
              const SizedBox(width: 10),
              Text(
                'Color del destello luminoso',
                style: theme.textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w800,
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            'Elige entre el espectro multicolor dinámico o un tono sólido.',
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 20),

          ValueListenableBuilder<BeamThemeOption>(
            valueListenable: BeamColorConfig.currentOption,
            builder: (context, activeOption, _) {
              return Wrap(
                spacing: 10,
                runSpacing: 10,
                children: BeamColorConfig.options.map((option) {
                  final isSelected = activeOption.name == option.name;

                  return InkWell(
                    onTap: () {
                      BeamColorConfig.currentOption.value = option;
                    },
                    borderRadius: BorderRadius.circular(24),
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 14,
                        vertical: 9,
                      ),
                      decoration: BoxDecoration(
                        color: isSelected
                            ? option.primaryColor.withValues(alpha: 0.18)
                            : theme.colorScheme.surfaceContainerHigh,
                        borderRadius: BorderRadius.circular(24),
                        border: Border.all(
                          color: isSelected
                              ? option.primaryColor
                              : Colors.transparent,
                          width: 1.8,
                        ),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          // Círculo de color (con degradado multicolor si aplica)
                          Container(
                            width: 20,
                            height: 20,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              gradient: option.isMulticolor
                                  ? const SweepGradient(
                                      colors: [
                                        Color(0xFF4285F4),
                                        Color(0xFF9C27B0),
                                        Color(0xFFEA4335),
                                        Color(0xFFFBBC05),
                                        Color(0xFF34A853),
                                        Color(0xFF26C6DA),
                                        Color(0xFF4285F4),
                                      ],
                                    )
                                  : null,
                              color: option.isMulticolor
                                  ? null
                                  : option.primaryColor,
                              boxShadow: [
                                BoxShadow(
                                  color: option.primaryColor.withValues(alpha: 0.35),
                                  blurRadius: 6,
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(width: 8),
                          Text(
                            option.name,
                            style: theme.textTheme.labelMedium?.copyWith(
                              fontWeight: isSelected
                                  ? FontWeight.w800
                                  : FontWeight.w500,
                              color: isSelected
                                  ? theme.colorScheme.onSurface
                                  : theme.colorScheme.onSurfaceVariant,
                            ),
                          ),
                        ],
                      ),
                    ),
                  );
                }).toList(),
              );
            },
          ),
        ],
      ),
    );
  }
}
