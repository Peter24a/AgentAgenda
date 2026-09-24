import 'package:flutter/material.dart';

import '../../models/agenda_item.dart';

class AtmosphericCard extends StatelessWidget {
  final AgendaItem item;
  final VoidCallback? onTap;
  const AtmosphericCard({super.key, required this.item, this.onTap});
  @override
  Widget build(BuildContext context) => Card(
    margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
    child: ListTile(
      onTap: onTap,
      leading: Text(item.category.primaryEmoji),
      title: Text(item.title),
      subtitle: Text('${item.timeRange}\n${item.description ?? ""}'),
      trailing: const Icon(Icons.chevron_right),
    ),
  );
}
