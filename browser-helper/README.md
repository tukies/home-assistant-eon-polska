# Rozszerzenie logowania E.ON Polska

1. Rozpakuj archiwum i zachowaj ten folder na komputerze.
2. W zwykłym Google Chrome otwórz `chrome://extensions`.
3. Włącz „Tryb dewelopera”, kliknij „Załaduj rozpakowane” i wskaż ten folder (z plikiem `manifest.json`).
4. Zaloguj się na https://eon.pl/mojeon.
5. Na aktywnej karcie E.ON otwórz rozszerzenie z menu puzzla i kliknij „Kopiuj kod sesji”.
6. W Home Assistant 2026.9+ z integracją E.ON Polska 0.2.0+ wybierz „Logowanie przez przeglądarkę” i wklej kod.
7. Wyczyść schowek. Możesz usunąć rozszerzenie po konfiguracji.

Kod sesji jest poufny. Nie wysyłaj go innym osobom ani w zgłoszeniach błędów.
Rozszerzenie nie odczytuje hasła i nie wysyła kodu na serwer pośredniczący.

Pełna instrukcja: https://github.com/tukies/home-assistant-eon-polska
