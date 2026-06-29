function copyText(id, value) {
  var text = value || (document.getElementById(id) ? document.getElementById(id).innerText : '');
  if (!text) return;
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).then(function () {
      showCopied(id);
    }).catch(function () {
      fallbackCopy(text);
    });
  } else {
    fallbackCopy(text);
  }
}

function fallbackCopy(text) {
  var ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed';
  ta.style.opacity = '0';
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
  try { document.execCommand('copy'); } catch (e) {}
  document.body.removeChild(ta);
}

function showCopied(id) {
  var el = document.getElementById(id);
  if (el) {
    var orig = el.style.background;
    el.style.background = '#d1e7dd';
    setTimeout(function () { el.style.background = orig; }, 600);
  }
}
