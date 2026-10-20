'use strict';
const $ = id => document.getElementById(id);
let token = '';
let busy = false;
let signature = '';
function showStatus(status) {
  $('state').textContent = status.state || 'Unavailable';
  $('ssh').textContent = `ssh YOUR_USER@${status.hostname || 'raspberrypi.local'}`;
  busy = ['connecting', 'scanning'].includes(status.state);
  document.querySelectorAll('button').forEach(button => { button.disabled = busy; });
  if (status.error) $('message').textContent = status.error;
  if (busy) $('message').textContent = 'Switching shortly. Keep the SSH hostname above. Rejoin Wi-Fi after the switch; failed attempts restore setup Wi-Fi.';
  if (status.ip) $('message').textContent = `Connected: ${status.ip}. SSH: ssh YOUR_USER@${status.ip}`;
  const next = JSON.stringify(status.networks);
  if (next === signature || !status.networks?.length) return;
  signature = next;
  $('networks').replaceChildren();
  for (const network of status.networks) {
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'network'; button.disabled = busy;
    const name = document.createElement('span'); name.textContent = network.ssid;
    const detail = document.createElement('small'); detail.textContent = `${network.signal}% · ${network.security}`;
    button.append(name, detail);
    button.onclick = () => {
      $('ssid').value = network.ssid;
      $('hidden').checked = false;
      const sec = network.security.toUpperCase();
      if (sec.includes('802.1X') || sec.includes('WEP') || sec.includes('OWE')) {
        $('message').textContent = 'Enterprise, WEP and enhanced-open networks are unsupported. Choose a Personal or Open network.';
        return;
      }
      $('security').value = sec.includes('WPA3') && !sec.includes('WPA2') ? 'sae' : sec === 'OPEN' || sec === '--' ? 'open' : 'wpa-psk';
      updatePassword(); $('password').focus();
    };
    $('networks').append(button);
  }
}
function updatePassword() {
  $('password').disabled = $('security').value === 'open';
  $('password').required = !$('password').disabled;
  if ($('password').disabled) $('password').value = '';
}
async function poll() {
  try {
    const response = await fetch('/api/status', {cache: 'no-store'});
    const status = await response.json();
    if (!response.ok) throw new Error(status.error);
    token = status.token; showStatus(status);
  } catch (_) {
    $('message').textContent = 'Setup connection interrupted. Rejoin setup Wi-Fi and refresh after a failed attempt or scan. After a successful connection, rejoin your destination Wi-Fi and use the SSH hostname above.';
  }
}
async function action(payload) {
  if (busy || !token) return;
  busy = true;
  document.querySelectorAll('button').forEach(button => { button.disabled = true; });
  try {
    const response = await fetch('/api/action', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Setup-Token': token}, body: JSON.stringify(payload)});
    const status = await response.json();
    if (!response.ok) throw new Error(status.error || 'Connection request rejected');
    showStatus(status);
  } catch (error) {
    $('message').textContent = error.message;
    await poll();
  }
}
$('security').onchange = updatePassword;
$('scan').onclick = () => action({action: 'rescan'});
$('connect').onsubmit = event => {
  event.preventDefault();
  const payload = {action: 'connect', ssid: $('ssid').value, password: $('password').value, security: $('security').value, hidden: $('hidden').checked};
  $('password').value = '';
  action(payload);
};
poll(); setInterval(poll, 4000);
