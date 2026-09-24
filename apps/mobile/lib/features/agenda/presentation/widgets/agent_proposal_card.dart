import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../models/agent_proposal.dart';

/// Tarjeta que visualiza una propuesta generada por el Asistente SARA.
/// Sigue los lineamientos de SARA v0.4.0: superficie elevada sólida,
/// radio de tarjeta de 12px, botones con radio de 8px y acento ciruela.
class AgentProposalCard extends StatelessWidget {
  final AgentProposal proposal;
  final VoidCallback onAccept;
  final VoidCallback onDismiss;

  const AgentProposalCard({
    super.key,
    required this.proposal,
    required this.onAccept,
    required this.onDismiss,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final isDark = theme.brightness == Brightness.dark;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
      child: Container(
        decoration: BoxDecoration(
          color: colorScheme.surfaceContainerLow,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: colorScheme.outlineVariant, width: 1.0),
        ),
        clipBehavior: Clip.antiAlias,
        child: Stack(
          children: [
            // Indicador visual lateral ciruela (WCAG 1.4.1)
            Positioned(
              left: 0,
              top: 0,
              bottom: 0,
              width: 4,
              child: ColoredBox(color: colorScheme.primary),
            ),

            Padding(
              padding: const EdgeInsets.fromLTRB(20, 16, 16, 16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Badge superior de SARA
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 10,
                          vertical: 4,
                        ),
                        decoration: BoxDecoration(
                          color: colorScheme.primaryContainer,
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(
                              Icons.auto_awesome_rounded,
                              size: 13,
                              color: colorScheme.primary,
                            ),
                            const SizedBox(width: 5),
                            Text(
                              'Propuesta SARA',
                              style: theme.textTheme.labelSmall?.copyWith(
                                color: isDark
                                    ? colorScheme.primary
                                    : colorScheme.onPrimaryContainer,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                          ],
                        ),
                      ),
                      const Spacer(),
                      Text(
                        'Confirmación requerida',
                        style: theme.textTheme.labelSmall?.copyWith(
                          color: colorScheme.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),

                  // Resumen de la propuesta
                  Text(
                    proposal.summary,
                    style: theme.textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w700,
                      color: colorScheme.onSurface,
                    ),
                  ),
                  const SizedBox(height: 6),

                  // Razón explicada
                  Text(
                    proposal.reason,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: colorScheme.onSurfaceVariant,
                      height: 1.4,
                    ),
                  ),
                  const SizedBox(height: 16),

                  for (final item in proposal.resultingItems)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 10),
                      child: Text(
                        '${item.isCancellation ? "Cancelar: " : ""}${item.title}\n${DateFormat("dd/MM/yyyy HH:mm").format(item.startTime)}${item.endTime == null ? '' : ' → ${DateFormat("dd/MM/yyyy HH:mm").format(item.endTime!)}'}',
                        style: theme.textTheme.bodyMedium,
                      ),
                    ),
                  // Botones de acción del usuario (Aprobar / Descartar)
                  Row(
                    children: [
                      Expanded(
                        child: OutlinedButton(
                          onPressed: onDismiss,
                          style: OutlinedButton.styleFrom(
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(8),
                            ),
                            side: BorderSide(color: colorScheme.outline),
                          ),
                          child: const Text('Descartar'),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: FilledButton.icon(
                          onPressed: onAccept,
                          icon: const Icon(Icons.check_rounded, size: 18),
                          label: const Text('Aprobar'),
                          style: FilledButton.styleFrom(
                            backgroundColor: colorScheme.primary,
                            foregroundColor: colorScheme.onPrimary,
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(8),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
