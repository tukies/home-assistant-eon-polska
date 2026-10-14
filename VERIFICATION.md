## Ponawianie pobierania danych — 0.3.3, 14 października 2026

- Nieudane pobieranie wymaganych danych zmienia harmonogram aktualizacji na 5, 10, 20 i maksymalnie 30 minut. Po odzyskaniu danych harmonogram wraca do 24 godzin, a kolejna awaria zaczyna ponownie od 5 minut.
- Testy używają rzeczywistego cyklu odświeżania i harmonogramu `DataUpdateCoordinator`. Obejmują awarie odkrywania kont, pobierania raportu oraz końcowego odnawiania sesji; brak zapisu statystyk przy nieudanym pobraniu; przywrócenie dostępności czujników po odzyskaniu danych; zatrzymanie ponowień i uruchomienie ponownego uwierzytelnienia przy błędach autoryzacji, również w opcjonalnym źródle.
- Zmiana nie wyzwala pobierania energii z timerów podtrzymujących sesję i nie zmienia polityki jakości danych. Początkowe niepowodzenie konfiguracji nadal podlega mechanizmowi ponowień konfiguracji Home Assistant.
- Walidacja lokalna: 93 testy Python na Home Assistant 2026.9.2, 8 testów rozszerzenia, Ruff i kontrola białych znaków przeszły pomyślnie. Pozostały ostrzeżenia o przestarzałych API bibliotek zależnych.
- Nie wdrożono tej poprawki do produkcyjnego Home Assistant ani nie zasymulowano w nim awarii sieci.

## Odnawianie sesji i diagnostyka — 0.3.2, 12 października 2026

- Porównano aktualny publiczny formularz logowania i moduł `check-user-status.js` w pakiecie JavaScript E.ON. Moduł używa `Interval` dla sprawdzania statusu i `ResetInterval` dla podtrzymywania aktywności; obie wartości są wyrażone w sekundach.
- Integracja używa dwóch niezależnych timerów. Nowe interwały z codziennego odnowienia zastępują oczekujące wywołania. Nieprawidłowe wartości wracają do 600 sekund, a przejściowe błędy sieci/usługi powodują ponowienie po maksymalnie 60 sekundach.
- Testy sprawdzają zapis ciasteczka przed późniejszą awarią, przed błędem odczytu treści odpowiedzi oraz usunięcie ciasteczka przy HTTP 401. Test konfiguracji sprawdza podłączenie zapisu przed pierwszym odświeżeniem, zachowanie pozostałych ustawień oraz zamknięcie klienta przy nieudanej konfiguracji.
- Testy harmonogramów obejmują niezależne interwały, zmianę interwałów, ignorowanie anulowanych callbacków, przejściowe awarie i powrót do zwykłego harmonogramu, zatrzymanie obu timerów przy odmowie logowania i wyładowanie integracji.
- Przeszło 87 testów Python (w tym rzeczywisty Recorder z tymczasową bazą SQLite) oraz 8 testów rozszerzenia. Ruff i kontrola białych znaków nie zgłosiły błędów. Pozostały ostrzeżenia o przestarzałych API bibliotek zależnych.
- Dodano pobieranie diagnostyki w Home Assistant z jawnie wybranymi metadanymi. Testy sprawdzają brak sekretów sesji, User-Agent, PPE i treści odpowiedzi; historię ostatnich 20 błędów; liczniki błędów oraz osobne liczenie rotacji i usunięcia ciasteczka uwierzytelniającego.
- Walidacja jest lokalna na Pythonie 3.14 / Home Assistant 2026.9.2. Nie zmieniono produkcyjnego Home Assistant, nie wykonano uwierzytelnionych żądań do E.ON ani wielodniowego testu żywotności nowych harmonogramów. Nie potwierdzono przyczyny zgłaszanego wygasania po około pięciu dniach.

## Podtrzymywanie sesji — 0.3.1, 15 września 2026

- Kod strony E.ON wywołuje `resetauthorizationcookie`, okresowo sprawdza `getuserstatus` i używa `keepalive` do podtrzymywania aktywności.
- Na świeżej sesji wszystkie trzy endpointy zwróciły status aplikacyjny 200; po wykonaniu nowej sekwencji klient nadal odczytywał konto.
- Oddzielne próby `keepalive` i `getuserstatus` nie wykazały rotacji ciasteczek. Nie jest to dowód przedłużenia maksymalnego czasu ważności sesji.
- Dodano testy sekwencji, odmowy uwierzytelnienia i odróżniania awarii usługi od wygaśnięcia sesji.
- Nie wykonano testu trwającego ponad trzy dni ani zmian w Home Assistant rodziców użytkownika.

# Walidacja — 12 września 2026

## Rozszerzenie danych — wersja 0.3.0

- Potwierdzono działanie `GetOzeAgrData` oraz `GetBillingData` przez bezpośrednie żądania z bieżącej, uwierzytelnionej sesji.
- Tymczasowa lokalna instancja Home Assistant 2026.9.2 załadowała **26 czujników**, pobrała dane godzinowe, miesięczne i rozliczeniowe oraz poprawnie wyładowała integrację.
- Liczba historycznych serii energii pozostała równa **2**. Żaden czujnik podsumowania nie otrzymał klasy stanu tworzącej kolejne statystyki energii.
- Testy potwierdzają kompletność dni 23/24/25-godzinnych, odrzucanie niepełnych dni, rozdzielenie prognoz i braków, zachowanie wartości zero oraz daty rozliczeń niezależne od kolejności odpowiedzi API.
- Test awarii opcjonalnego źródła potwierdza dalszy zapis godzinowej energii. Test wygaśnięcia sesji potwierdza konieczność ponownego uwierzytelnienia.
- Data ostatnich danych nie pochodzi z syntetycznych pustych przedziałów, którymi uzupełniono braki w historii.
- Nie dodano terminu wygaśnięcia nadwyżki, płatności, terminów zapłaty ani obsługi zwykłych umów bez OZE.

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
