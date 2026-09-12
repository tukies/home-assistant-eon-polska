import {getSessionCode, HelperError} from './session.mjs';
const button = document.querySelector('#copy');
const status = document.querySelector('#status');
button.addEventListener('click', async () => {
  button.disabled = true;
  status.textContent = 'Sprawdzanie logowania E.ON…';
  try {
    const code = await getSessionCode(chrome, navigator.userAgent);
    await navigator.clipboard.writeText(code);
    status.textContent = 'Skopiowano. Wklej kod w Home Assistant, a następnie wyczyść schowek.';
  } catch (error) {
    // Expected errors contain only fixed helper messages; never echo cookies or response bodies.
    status.textContent = error instanceof HelperError
      ? error.message : 'Nie udało się skopiować kodu. Pozostaw okno rozszerzenia otwarte i spróbuj ponownie.';
  } finally {
    button.disabled = false;
  }
});
