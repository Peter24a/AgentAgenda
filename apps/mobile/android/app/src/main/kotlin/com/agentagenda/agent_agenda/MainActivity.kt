package com.agentagenda.agent_agenda

import android.content.ActivityNotFoundException
import android.content.Intent
import android.provider.AlarmClock
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.util.ArrayList

class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "agent_agenda/system_clock")
            .setMethodCallHandler { call, result ->
                if (call.method != "setAlarm") {
                    result.notImplemented()
                    return@setMethodCallHandler
                }
                val hour = call.argument<Int>("hour")
                val minute = call.argument<Int>("minute")
                val weekdays = call.argument<List<Int>>("weekdays")
                if (hour == null || hour !in 0..23 || minute == null || minute !in 0..59 ||
                    weekdays.isNullOrEmpty() || weekdays.any { it !in 1..7 }) {
                    result.error("INVALID_ALARM", "Selecciona hora y días válidos.", null)
                    return@setMethodCallHandler
                }
                // Dart uses ISO weekday numbers (Monday=1); Android Calendar uses Sunday=1.
                val androidDays = ArrayList(weekdays.distinct().map { if (it == 7) 1 else it + 1 })
                val intent = Intent(AlarmClock.ACTION_SET_ALARM).apply {
                    putExtra(AlarmClock.EXTRA_HOUR, hour)
                    putExtra(AlarmClock.EXTRA_MINUTES, minute)
                    putIntegerArrayListExtra(AlarmClock.EXTRA_DAYS, androidDays)
                    putExtra(AlarmClock.EXTRA_MESSAGE, "AgentAgenda · Despertar")
                    putExtra(AlarmClock.EXTRA_SKIP_UI, false)
                }
                try {
                    startActivity(intent)
                    // Successful dispatch does not establish that the clock enabled an alarm.
                    result.success(true)
                } catch (_: ActivityNotFoundException) {
                    result.success(false)
                } catch (_: SecurityException) {
                    result.success(false)
                }
            }
    }
}
