# Walidacja — 12 września 2026

## Co sprawdzono

- Testy Python obejmują parser, klienta HTTP, kody sesji, konfigurację, zgodność konta przy ponownym logowaniu oraz prawdziwy Recorder z tymczasową bazą SQLite.
- Testy JavaScript obejmują format kodu sesji, pomijanie ciasteczek śledzących, kontrolę aktywnej karty, odmowę eksportu po wylogowaniu i zakres uprawnień rozszerzenia.
- Użytkownik potwierdził działanie rozszerzenia w swoim zwykłym Chrome i skopiowanie kodu sesji.
- Niezależny test zgodnego kodu utworzonego z przechwyconej sesji przeszedł pełny formularz konfiguracji Home Assistant 2026.9.2, pobranie danych, utworzenie czterech czujników i dwóch serii historycznych oraz poprawne wyładowanie integracji. Test używał tymczasowej lokalnej instancji, nie instalacji produkcyjnej.
- Bezpośrednie żądania HTTPS potwierdziły pobieranie punktów OZE, raportów CSV i odnawianie sesji. Żądanie po odnowieniu nadal miało dostęp do konta.
- Raport z wiosennej zmiany czasu dał 23 ciągłe przedziały UTC, a raport z jesiennej zmiany czasu — 25. Obsłużono pusty przedział oraz oznaczenie `2A:00`.
- Recorder przyjął dane godzinowe z punktem początkowym. Ponowne wgranie nie tworzyło duplikatów. Korekta wcześniejszej wartości zmieniała późniejsze sumy.
- Ruff i kontrola białych znaków nie zgłosiły błędów.
- Pliki przeznaczone do publikacji oraz historia Git są skanowane Gitleaks. Osobna kontrola sprawdza brak prywatnych identyfikatorów kont, adresów i lokalnych ścieżek.

## Ważne granice walidacji

- Weryfikacja pobierania danych dotyczy jednego punktu OZE. Zwykłe umowy bez OZE nie są oferowane przez konfigurację.
- Nie wykonywano wizualnego testu panelu Energia w produkcyjnym Home Assistant. Sprawdzono zapis statystyk i tworzenie encji.
- Testy przeglądarkowego eksportu obejmują normalny Chrome. Microsoft Edge i inne przeglądarki nie były sprawdzane.
- Próby logowania w przeglądarkach uruchamianych przez Playwright zakończyły się błędem reCAPTCHA. Tego rozwiązania nie dołączono do wydania; rozszerzenie korzysta ze zwykłej sesji przeglądarki i nie zmienia formularza logowania.
- Nie potwierdzono odnawiania sesji przez wiele dni, po długiej przerwie w pracy ani po unieważnieniu sesji przez E.ON.
- Mapowanie znaczników czasu wynika z zaobserwowanych raportów i sprawdzonych dni zmiany czasu. Nie znaleziono oddzielnej specyfikacji znaczników czasu E.ON.
- Testy Home Assistant zgłaszają ostrzeżenia o przestarzałych elementach bibliotek zależnych. Nie powodują one niepowodzenia testów.

## Źródła

- [Instrukcja raportu pomiarowego E.ON](https://eon.pl/-/media/Files/Instrukcje/Ulotka_do_raportu_danych_pomiarowych)
- Przechwycone i bezpośrednie żądania do `GetPHList`, `resetauthorizationcookie`, `Historia-zuzycia` i `OzeReport/GenerateOzeReport`.
- [Zmiany API statystyk Home Assistant](https://developers.home-assistant.io/blog/2025/10/16/recorder-statistics-api-changes/)

Repozytorium i pliki wydania nie zawierają kodów sesji, ciasteczek, haseł, identyfikatorów prywatnych kont ani rzeczywistych raportów zużycia.
