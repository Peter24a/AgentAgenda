import 'agenda_item.dart';

enum AgendaView { day, week, month }

DateTime agendaDay(DateTime date) => DateTime(date.year, date.month, date.day);

DateTime agendaWeekStart(DateTime date) =>
    DateTime(date.year, date.month, date.day - date.weekday + 1);

DateTime agendaEventEnd(AgendaItem item) =>
    item.endTime ?? item.startTime.add(const Duration(minutes: 30));

bool agendaSameDay(DateTime a, DateTime b) =>
    a.year == b.year && a.month == b.month && a.day == b.day;

List<AgendaItem> agendaItemsForDay(List<AgendaItem> items, DateTime day) {
  final start = agendaDay(day);
  final end = DateTime(day.year, day.month, day.day + 1);
  return items
      .where(
        (item) =>
            item.startTime.isBefore(end) && agendaEventEnd(item).isAfter(start),
      )
      .toList()
    ..sort((a, b) => a.startTime.compareTo(b.startTime));
}
