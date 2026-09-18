import 'package:flutter/material.dart';

/// Contenedor base de pantalla para la interfaz SARA.
/// Respeta la política anti-cliché y de cero degradados perimetrales (SARA v0.4.0).
class AgentScreenBorder extends StatelessWidget {
  final Widget child;

  const AgentScreenBorder({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: Theme.of(context).scaffoldBackgroundColor,
      child: child,
    );
  }
}
