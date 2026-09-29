/*
 * Session timing in the browser. The server enforces the limits
 * (utils/security.py); this script only keeps an active person signed in and
 * warns an inactive one.
 *
 * - A click or a key press counts as activity. While the person is active, it
 *   sends a keep-alive at most once every keepalive interval.
 * - Shortly before the idle limit, it shows "Are you still there?". "Stay signed
 *   in" sends a keep-alive.
 * - At the idle limit it asks the server with a probe, which does not count as
 *   activity. The server ends the session and answers 401 with the login page
 *   address, and the script goes there.
 * - Every request carries the form token (static/js/csrf.js). If the server
 *   refuses the token (400), the script also goes to the login page.
 * - Nothing here touches the sign-in time, so the 12-hour limit cannot be
 *   stretched from the browser.
 *
 * The timings come from data attributes on <body>, set from config.py.
 */
(function () {
  'use strict';

  var body = document.body;
  if (!body || !body.dataset.sessionKeepaliveUrl) { return; }

  var idleMs = Number(body.dataset.sessionIdleMs);
  var warnMs = Number(body.dataset.sessionWarnMs);
  var pingMs = Number(body.dataset.sessionPingMs);
  var keepAliveUrl = body.dataset.sessionKeepaliveUrl;
  var loginUrl = body.dataset.sessionLoginUrl;

  // When the server last counted activity. Loading this page counted.
  var serverTouch = Date.now();
  // When the person last clicked or typed on this page.
  var localActivity = Date.now();
  var sending = false;
  var modal = null;
  var warned = false;

  function goToLogin(url) {
    window.location.href = url || loginUrl;
  }

  function hideWarning() {
    warned = false;
    if (modal) { modal.hide(); }
  }

  function showWarning() {
    if (warned) { return; }
    var element = document.getElementById('sessionIdleModal');
    if (!element || !window.bootstrap) { return; }
    warned = true;
    modal = window.bootstrap.Modal.getOrCreateInstance(element);
    modal.show();
  }

  // probe = true only asks whether the session is open; it is not activity.
  function send(probe) {
    if (sending) { return; }
    sending = true;
    var headers = { 'X-Requested-With': 'fetch' };
    if (probe) { headers['X-Session-Probe'] = '1'; }
    // The form token (static/js/csrf.js). Without it the server refuses the request.
    if (window.withCsrfToken) { window.withCsrfToken(headers); }
    fetch(keepAliveUrl, { method: 'POST', headers: headers, credentials: 'same-origin' })
      .then(function (response) {
        if (response.status === 204) {
          serverTouch = Date.now();
          hideWarning();
          return null;
        }
        // 401: the session ended. 400: the token was refused, which means the
        // session this page belonged to is gone (for example, signed out in
        // another tab). Either way, go to the login page.
        if (response.status === 401 || response.status === 400) {
          return response.json().then(function (data) {
            goToLogin(data && data.login_url);
          }, function () { goToLogin(); });
        }
        return null;
      })
      .catch(function () { /* Offline for a moment. The next check tries again. */ })
      .then(function () { sending = false; });
  }

  function onActivity() {
    localActivity = Date.now();
    if (localActivity - serverTouch >= pingMs) { send(false); }
  }

  function check() {
    var now = Date.now();
    var left = serverTouch + idleMs - now;
    if (left <= 0) {
      send(true);
      return;
    }
    if (left <= warnMs) {
      // Active on this page since the server last heard from us: just tell it.
      if (localActivity > serverTouch) { send(false); } else { showWarning(); }
    }
  }

  document.addEventListener('click', onActivity, true);
  document.addEventListener('keydown', onActivity, true);

  var stay = document.getElementById('sessionStayButton');
  if (stay) {
    stay.addEventListener('click', function () { send(false); });
  }

  window.setInterval(check, 15000);
}());
