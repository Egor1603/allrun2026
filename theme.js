/* allrunrus.ru — переключение тем */
/* 7:00–19:00 → дневная, иначе → вечерняя. Ручной override на 1 час */

(function(){
  var h = new Date().getHours();
  var hourAuto = (h >= 7 && h < 19) ? 'day' : 'night';
  // Системная тема имеет приоритет над часовым правилом
  var sysPrefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  var auto = sysPrefersDark ? 'night' : hourAuto;
  var override = localStorage.getItem('allrunrus-theme-override');
  var overrideTime = parseInt(localStorage.getItem('allrunrus-theme-time')||'0');
  var theme = (override && (Date.now()-overrideTime) < 3600000) ? override : auto;
  document.documentElement.setAttribute('data-theme', theme);
  // Кнопка обновится после загрузки DOM
  document.addEventListener('DOMContentLoaded', function() {
    var btn = document.getElementById('theme-toggle');
    if (btn) btn.textContent = theme === 'night' ? '☀️' : '☽';
  });
})();

function toggleTheme() {
  var current = document.documentElement.getAttribute('data-theme') || 'night';
  var next = current === 'night' ? 'day' : 'night';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('allrunrus-theme-override', next);
  localStorage.setItem('allrunrus-theme-time', Date.now().toString());
  var btn = document.getElementById('theme-toggle');
  if (btn) btn.textContent = next === 'night' ? '☀️' : '☽';
}
