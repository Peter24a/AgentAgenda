/// Modelo de una tarea sincronizable con el backend de AgentAgenda.
class AgendaTask {
  final String id;
  final String title;
  final String? description;
  final String status;
  final String priority;
  final DateTime? dueDate;
  final int version;

  const AgendaTask({
    required this.id,
    required this.title,
    this.description,
    this.status = 'pending',
    this.priority = 'medium',
    this.dueDate,
    this.version = 1,
  });

  bool get isCompleted => status == 'completed';

  factory AgendaTask.fromJson(Map<String, dynamic> json) {
    return AgendaTask(
      id: json['id'] as String,
      title: json['title'] as String,
      description: json['description'] as String?,
      status: json['status'] as String? ?? 'pending',
      priority: json['priority'] as String? ?? 'medium',
      dueDate: json['due_date'] != null
          ? DateTime.parse(json['due_date'] as String)
          : null,
      version: json['version'] as int? ?? 1,
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'title': title,
        'description': description,
        'status': status,
        'priority': priority,
        'due_date': dueDate?.toIso8601String(),
        'version': version,
      };

  AgendaTask copyWith({
    String? id,
    String? title,
    String? description,
    String? status,
    String? priority,
    DateTime? dueDate,
    int? version,
  }) {
    return AgendaTask(
      id: id ?? this.id,
      title: title ?? this.title,
      description: description ?? this.description,
      status: status ?? this.status,
      priority: priority ?? this.priority,
      dueDate: dueDate ?? this.dueDate,
      version: version ?? this.version,
    );
  }
}
