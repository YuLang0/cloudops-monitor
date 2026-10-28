// 첫 화면이 그려지기 전에 테마를 적용해 깜빡임을 막는다. (CSP script-src 'self' 를 지키려고 별도 파일로 분리)
(function () {
  var theme = 'dark';
  try {
    theme = localStorage.getItem('cloudops-theme') || 'dark';
  } catch (e) {}
  document.documentElement.classList.toggle('dark', theme !== 'light');
})();
