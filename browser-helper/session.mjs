export class HelperError extends Error {}

export const ACCOUNTS = 'https://eon.pl/mojeon/api/GetPHList';
const NAMES = new Set(['ASP.NET_SessionId', '.ASPXAUTH', 'LoginContext', 'SessionInfo',
  'clientToken', 'SERO', 'SEROW', 'dws01-level', 'eon#lang', 'website#sc_mode',
  'eon#sc_mode', 'shell#lang']);

export function encodeSession(cookies, userAgent) {
  const seen = new Set();
  const selected = cookies.filter(c => {
    if (!(NAMES.has(c.name) || c.name.startsWith('.AspNet.')) || seen.has(c.name)) return false;
    seen.add(c.name);
    return true;
  });
  if (!selected.some(c => c.name === '.AspNet.Cookies' && c.value)) {
    throw new HelperError('Najpierw zaloguj się do E.ON, a następnie spróbuj ponownie.');
  }
  if (!userAgent || /[\r\n]/.test(userAgent) || selected.some(c => /[\r\n;]/.test(c.value))) {
    throw new HelperError('Przeglądarka zwróciła nieprawidłową sesję.');
  }
  const cookie = selected.map(c => `${c.name}=${c.value}`).join('; ');
  const bytes = new TextEncoder().encode(JSON.stringify({cookie, user_agent: userAgent}));
  if (bytes.length > 48000) throw new HelperError('Dane sesji są zbyt duże, aby je skopiować.');
  const code = 'EON_SESSION_V1.' + btoa(String.fromCharCode(...bytes))
    .replaceAll('+', '-').replaceAll('/', '_');
  if (code.length > 65536) throw new HelperError('Dane sesji są zbyt duże, aby je skopiować.');
  return code;
}

export async function getSessionCode(api, userAgent) {
  const [tab] = await api.tabs.query({active: true, currentWindow: true});
  if (!tab?.url || !tab.url.startsWith('https://eon.pl/mojeon')) {
    throw new HelperError('Otwórz zalogowaną kartę E.ON, a następnie ponownie otwórz rozszerzenie.');
  }
  let results;
  try {
    results = await api.scripting.executeScript({target: {tabId: tab.id}, func: async () => {
      try {
        const response = await fetch('https://eon.pl/mojeon/api/GetPHList', {
          credentials: 'include', redirect: 'error', signal: AbortSignal.timeout(15000)
        });
        if (!response.ok) return false;
        const data = await response.json();
        return Array.isArray(data.Partners) && data.Partners.length > 0;
      } catch { return false; }
    }});
  } catch {
    throw new HelperError('Nie można sprawdzić logowania E.ON. Odśwież kartę i spróbuj ponownie.');
  }
  if (results?.[0]?.result !== true) {
    throw new HelperError('E.ON nie potwierdził zalogowania. Zaloguj się na jego stronie i spróbuj ponownie.');
  }
  const stores = await api.cookies.getAllCookieStores();
  const store = stores.find(s => s.tabIds.includes(tab.id));
  if (!store) throw new HelperError('Nie znaleziono sesji E.ON w przeglądarce.');
  const cookies = await api.cookies.getAll({url: ACCOUNTS, storeId: store.id});
  return encodeSession(cookies, userAgent);
}
