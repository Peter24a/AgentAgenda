import 'package:flutter/material.dart';
import '../../models/agenda_item.dart';

/// Modal estilo Material 3 para crear una nueva actividad en la agenda.
class NewActivitySheet extends StatefulWidget {
  final DateTime? targetDate;
  final Function(AgendaItem) onAdd;

  const NewActivitySheet({super.key, this.targetDate, required this.onAdd});

  @override
  State<NewActivitySheet> createState() => _NewActivitySheetState();
}

class _NewActivitySheetState extends State<NewActivitySheet> {
  final _titleController = TextEditingController();
  final _descController = TextEditingController();
  ActivityCategory _selectedCategory = ActivityCategory.work;
  TimeOfDay _startTime = TimeOfDay.now();
  TimeOfDay? _endTime;

  @override
  void dispose() {
    _titleController.dispose();
    _descController.dispose();
    super.dispose();
  }

  void _save() {
    final title = _titleController.text.trim();
    if (title.isEmpty) return;

    final baseDate = widget.targetDate ?? DateTime.now();
    final start = DateTime(
      baseDate.year,
      baseDate.month,
      baseDate.day,
      _startTime.hour,
      _startTime.minute,
    );

    final end = _endTime != null
        ? DateTime(
            baseDate.year,
            baseDate.month,
            baseDate.day,
            _endTime!.hour,
            _endTime!.minute,
          )
        : null;

    final newItem = AgendaItem(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      title: title,
      description: _descController.text.trim().isNotEmpty
          ? _descController.text.trim()
          : null,
      startTime: start,
      endTime: end,
      category: _selectedCategory,
    );

    widget.onAdd(newItem);
    Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final bottomInset = MediaQuery.of(context).viewInsets.bottom;

    return Padding(
      padding: EdgeInsets.fromLTRB(24, 16, 24, 24 + bottomInset),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Píldora de arrastre
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
          const SizedBox(height: 16),
          Text(
            'Nueva actividad',
            style: theme.textTheme.titleLarge?.copyWith(
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 16),

          // Campo de título
          TextField(
            controller: _titleController,
            autofocus: true,
            decoration: InputDecoration(
              hintText: '¿Qué tienes planeado?',
              filled: true,
              fillColor: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.5),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(16),
                borderSide: BorderSide.none,
              ),
            ),
          ),
          const SizedBox(height: 14),

          // Selector de categorías
          Text(
            'Categoría & Atmósfera',
            style: theme.textTheme.labelMedium?.copyWith(
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 8),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: ActivityCategory.values.map((cat) {
                final isSelected = cat == _selectedCategory;
                return Padding(
                  padding: const EdgeInsets.only(right: 8.0),
                  child: FilterChip(
                    label: Text('${cat.primaryEmoji} ${cat.label}'),
                    selected: isSelected,
                    onSelected: (_) => setState(() => _selectedCategory = cat),
                    selectedColor: cat.tintColor.withValues(alpha: 0.25),
                  ),
                );
              }).toList(),
            ),
          ),
          const SizedBox(height: 14),

          // Selector de hora
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: () async {
                    final time = await showTimePicker(
                      context: context,
                      initialTime: _startTime,
                    );
                    if (time != null) setState(() => _startTime = time);
                  },
                  icon: const Icon(Icons.access_time_rounded, size: 18),
                  label: Text('Inicio: ${_startTime.format(context)}'),
                  style: OutlinedButton.styleFrom(
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(14),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: () async {
                    final time = await showTimePicker(
                      context: context,
                      initialTime: _endTime ?? _startTime,
                    );
                    if (time != null) setState(() => _endTime = time);
                  },
                  icon: const Icon(Icons.timelapse_rounded, size: 18),
                  label: Text(
                    _endTime == null
                        ? 'Fin (opc)'
                        : 'Fin: ${_endTime!.format(context)}',
                  ),
                  style: OutlinedButton.styleFrom(
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(14),
                    ),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 20),

          // Botón guardar
          SizedBox(
            width: double.infinity,
            height: 48,
            child: FilledButton(
              onPressed: _save,
              style: FilledButton.styleFrom(
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(16),
                ),
              ),
              child: const Text(
                'Agregar a la agenda',
                style: TextStyle(fontWeight: FontWeight.w700),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
