/* The 12-hour clock for every time the browser writes on a page.
 *
 * The browser's own toLocaleString() follows the computer's language settings,
 * so the same page printed "October 22, 2026 at 14:21" on one laptop and
 * "October 22, 2026, 02:21 PM" on another. Everything a person reads in this
 * system says "2:21 PM", the everyday clock in the Philippines, and this file is
 * the browser's half of that rule. The server's half is utils/dates.py
 * format_time(); the two follow the same rules and are tested with the same cases
 * (tests/verify_time_format.py and tests/verify_time_format_browser.py).
 *
 *   formatTime(value, seconds)  '2:21 PM', or '2:21:05 PM' with seconds
 *   formatDateTime(value)       'October 22, 2026 at 2:21 PM'
 *   clinicToday()               today at the health center (server's Philippine date)
 *   clinicStamp()               now at the health center, 'October 22, 2026 at 2:21 PM'
 *                               (the printed-page stamp)
 *
 * `value` is a Date, or the ISO text the server stores: '14:21', '14:21:05',
 * '2026-10-12 11:34', '2026-10-12T11:34:05'. A missing or unreadable value gives
 * '' rather than an exception. Text is read as written (no timezone shift), as on
 * the server. The hour is computed, never taken from the locale: 0 -> 12 AM,
 * 12 -> 12 PM, 13 -> 1 PM.
 *
 * Loaded by base.html before any page script, so a page's inline script may call
 * it while the page is still being parsed.
 */
(function (global) {
  'use strict';

  var MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
                'August', 'September', 'October', 'November', 'December'];

  var CLOCK = /^(?:(\d{4})-(\d{2})-(\d{2})[T ])?(\d{1,2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?$/;

  function two(number) {
    return (number < 10 ? '0' : '') + number;
  }

  // -> { year, month (0-11), day, hour, minute, second, hasDate } or null.
  function parts(value) {
    if (value instanceof Date) {
      if (isNaN(value.getTime())) { return null; }
      return {
        year: value.getFullYear(), month: value.getMonth(), day: value.getDate(),
        hour: value.getHours(), minute: value.getMinutes(), second: value.getSeconds(),
        hasDate: true
      };
    }
    if (value === null || value === undefined) { return null; }
    var match = CLOCK.exec(String(value).trim());
    if (!match) { return null; }
    var hour = parseInt(match[4], 10);
    var minute = parseInt(match[5], 10);
    var second = match[6] ? parseInt(match[6], 10) : 0;
    if (hour > 23 || minute > 59 || second > 59) { return null; }
    return {
      year: match[1] ? parseInt(match[1], 10) : null,
      month: match[2] ? parseInt(match[2], 10) - 1 : null,
      day: match[3] ? parseInt(match[3], 10) : null,
      hour: hour, minute: minute, second: second,
      hasDate: !!match[1]
    };
  }

  function clock(p, seconds) {
    var text = ((p.hour + 11) % 12 + 1) + ':' + two(p.minute);
    if (seconds) { text += ':' + two(p.second); }
    return text + (p.hour < 12 ? ' AM' : ' PM');
  }

  function formatTime(value, seconds) {
    var p = parts(value);
    return p ? clock(p, seconds) : '';
  }

  function formatDateTime(value, seconds) {
    var p = parts(value);
    if (!p || !p.hasDate) { return ''; }
    return MONTHS[p.month] + ' ' + p.day + ', ' + p.year + ' at ' + clock(p, seconds);
  }

  // The health center's clock (audit B23). The server writes its Philippine date and time
  // into <body data-clinic-now="2026-10-24T05:16:00"> when it builds the page; the device
  // only adds the seconds that have passed since. So a phone or PC whose clock or
  // timezone is wrong still shows and prints the server's day. The time is kept as
  // wall-clock parts in a UTC Date, so the device's timezone never shifts it.
  var loadedAt = Date.now();

  function clinicParts() {
    var stamp = document.body ? document.body.getAttribute('data-clinic-now') : null;
    var p = parts(stamp);
    if (!p || !p.hasDate) { return parts(new Date()); }  // a page without it: the device clock
    var moment = new Date(Date.UTC(p.year, p.month, p.day, p.hour, p.minute, p.second)
                          + Math.max(0, Date.now() - loadedAt));
    return {
      year: moment.getUTCFullYear(), month: moment.getUTCMonth(), day: moment.getUTCDate(),
      hour: moment.getUTCHours(), minute: moment.getUTCMinutes(), second: moment.getUTCSeconds(),
      hasDate: true
    };
  }

  // Today at the health center, as a local-midnight Date for date arithmetic (age preview).
  function clinicToday() {
    var p = clinicParts();
    return new Date(p.year, p.month, p.day);
  }

  // 'October 24, 2026 at 5:16 AM' at the health center: the printed-page stamp.
  function clinicStamp() {
    var p = clinicParts();
    return MONTHS[p.month] + ' ' + p.day + ', ' + p.year + ' at ' + clock(p, false);
  }

  global.IDSTime = { formatTime: formatTime, formatDateTime: formatDateTime,
                     clinicToday: clinicToday, clinicStamp: clinicStamp };
})(window);
