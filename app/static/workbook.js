import {bindSheet} from './cells.js';
bindSheet(document.querySelector('#frames'), document.querySelector('#focused-cell'));
const notice = document.querySelector('#notice');
const reel = document.querySelector('#reel');
reel.addEventListener('change', () => location.assign(`/sheet/${document.body.dataset.sheet}?sample=${reel.value}`));
async function send(button, payload, id) {
  button.disabled = true;
  notice.textContent = '正在校对…';
  try {
    const response = await fetch(id ? `/api/runs/${id}/repeat` : '/api/runs', {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)
    });
    const result = await response.json();
    if (!response.ok) throw Error(result.message);
    notice.textContent = result.reused ? '复算一致' : '交付已归档';
    if (!id) location.assign(`/sheet/runs?${new URLSearchParams({run:result.id,sample:reel.value})}`);
  } catch (error) {
    notice.textContent = error.message || '提交失败，请重试';
  } finally { button.disabled = false; }
}
document.querySelector('#sample-form').addEventListener('submit', event => {
  event.preventDefault();
  send(event.submitter, {sample:reel.value});
});
document.querySelector('#originals')?.addEventListener('submit', event => {
  event.preventDefault();
  send(event.submitter, Object.fromEntries(new FormData(event.currentTarget)));
});
document.querySelector('#repeat')?.addEventListener('click', event => send(event.currentTarget, null, event.currentTarget.dataset.id));
document.querySelector('#revise')?.addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = event.submitter;
  button.disabled = true;
  notice.textContent = '正在换版复核…';
  try {
    const response = await fetch(`/api/runs/${form.dataset.base}/revise`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify(Object.fromEntries(new FormData(form)))
    });
    const result = await response.json();
    if (!response.ok) throw Error(result.message);
    location.assign(`/sheet/revision?${new URLSearchParams({run:result.id,sample:reel.value})}`);
  } catch (error) {
    notice.textContent = `${error.message || '换版失败'} · 旧版证据保留`;
  } finally { button.disabled = false; }
});
