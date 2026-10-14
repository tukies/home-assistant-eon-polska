# E.ON Polska — integracja z Home Assistant

Nieoficjalna integracja dla **prosumentów E.ON Polska (OZE)**. Pobiera godzinowe dane energii pobranej z sieci i oddanej do sieci oraz udostępnia je w panelu **Energia** w Home Assistant.

**Wymagania:** Home Assistant 2026.9 lub nowszy, HACS, konto Mój E.ON z danymi prosumenckimi i zwykła przeglądarka Google Chrome na komputerze.

Logujesz się swoim adresem e-mail i hasłem **bezpośrednio na stronie E.ON**. Rozszerzenie Chrome kopiuje kod aktywnej sesji, który wklejasz do Home Assistant. Nie potrzebujesz Pythona, HTTP Toolkit ani narzędzi deweloperskich strony.

## Nowe dane w wersji 0.3.0

Dla każdego punktu PPE dostępnych jest **26 czujników**, w tym dotychczasowe czujniki godzinowe. Nazwy konfiguracji i czujników są dostępne po polsku i angielsku.

| Grupa | Dostępne informacje |
|---|---|
| Ostatni kompletny dzień | Pobór, oddawanie i data dnia. Dzień jest kompletny tylko wtedy, gdy wszystkie godziny obu kierunków spełniają wybraną politykę jakości. Uwzględniane są dni mające 23 lub 25 godzin. |
| Miesiąc i rok raportu | Bilansowany pobór i oddawanie według podsumowań E.ON. Atrybuty zawierają początek i koniec okresu; bieżący miesiąc lub rok mogą być niepełne. |
| Jakość i aktualność | Czas ostatnich dostępnych danych, czas udanej aktualizacji, godziny z brakami, prognozami, danymi niepewnymi i nieznanym statusem oraz procent kompletnych godzin. |
| Ostatnie rozliczenie OZE | Pobór, oddawanie, energia odzyskana, nadwyżka z poprzednich okresów, nadwyżka rozliczona, zmagazynowana i przeterminowana, współczynnik OZE oraz data końca okresu rozliczeniowego. |

**Podsumowania nie zastępują dwóch serii historycznych w panelu Energia i nie dodają do nich energii.** Służą do kart informacyjnych i automatyzacji. Nie mają klasy stanu licznika narastającego.

Podsumowanie dnia powstaje z godzinowego CSV. Miesiąc i rok pochodzą z oddzielnego, bilansowanego zestawienia E.ON, dlatego ich wartości mogą różnić się od sum surowego importu i eksportu. Podsumowania E.ON nie udostępniają statusu każdej wartości, więc opcja wykluczania prognoz ich nie filtruje — dotyczy danych godzinowych i wyliczanego z nich dnia.

Każdy czujnik rozliczeniowy ma atrybuty z datami okresu. „Zmagazynowana nadwyżka OZE” oznacza stan rozliczenia energii, **nie poziom fizycznego akumulatora**. Nie prezentujemy terminu wygaśnięcia nadwyżki: API zwracało tę samą datę dla wielu okresów i jej znaczenie wymaga dalszej weryfikacji.

Brak konkretnego pola oznacza stan nieznany, a nie zero. Niedostępność dodatkowego interfejsu miesięcznego lub rozliczeniowego oznacza niedostępność jego czujników; nie przerywa poprawnego pobierania godzinowej historii. Wygaśnięcie sesji nadal wymaga ponownego uwierzytelnienia.

Liczniki jakości odnoszą się do skonfigurowanego zakresu historii. Jedna godzina może mieć różne statusy dla poboru i oddawania, więc kategorie mogą się nakładać. „Udział kompletnych godzin” uwzględnia wybraną opcję dopuszczania prognoz. „Ostatni kompletny dzień” może być starszy niż data ostatnich danych, jeśli nowsze dni mają braki lub wykluczone wartości.

## 1. Zainstaluj integrację przez HACS

1. Otwórz **HACS** w Home Assistant.
2. W menu z trzema kropkami wybierz **Repozytoria niestandardowe / Custom repositories**.
3. Wklej adres:
   ```text
   https://github.com/tukies/home-assistant-eon-polska
   ```
4. Jako kategorię wybierz **Integracja / Integration** i dodaj repozytorium.
5. Wyszukaj **E.ON Polska**, pobierz najnowszą wersję i **uruchom ponownie Home Assistant**.

To repozytorium niestandardowe HACS — integracja nie znajduje się na domyślnej liście sklepu.

<a id="browser-sign-in-recommended"></a>
## 2. Dodaj rozszerzenie do Chrome

Rozszerzenie instalujesz **na swoim komputerze**, nie w Home Assistant.

1. Pobierz [eon-browser-helper-0.2.0.zip](https://github.com/tukies/home-assistant-eon-polska/releases/download/v0.2.0/eon-browser-helper-0.2.0.zip).
2. **Rozpakuj ZIP** do folderu, który zachowasz na komputerze.
3. W swoim zwykłym Chrome otwórz `chrome://extensions`.
4. W prawym górnym rogu włącz **Tryb dewelopera / Developer mode**.
5. Kliknij **Załaduj rozpakowane / Load unpacked**.
6. Wskaż rozpakowany folder zawierający plik `manifest.json`. Nie wybieraj samego ZIP-a ani pliku `manifest.json`.
7. Na liście rozszerzeń pojawi się **E.ON Polska — logowanie do Home Assistant**. Opcjonalnie przypnij je do paska narzędzi przez ikonę puzzla.

Rozszerzenie jest udostępniane jako kod do lokalnego załadowania, a nie przez Chrome Web Store. Jego pliki znajdują się w katalogu [browser-helper](browser-helper/). Używaj zwykłego okna Chrome; tryb incognito wymaga osobnych uprawnień i nie jest zalecanym sposobem konfiguracji.

## 3. Zaloguj się i skopiuj kod sesji

1. Otwórz [Mój E.ON](https://eon.pl/mojeon) w tym samym Chrome, w którym dodano rozszerzenie.
2. Zaloguj się swoim adresem e-mail i hasłem. Wykonaj ewentualne dodatkowe kroki wymagane przez stronę E.ON. Jeśli już jesteś zalogowany, nie musisz się wylogowywać.
3. **Pozostaw kartę E.ON aktywną** i otwórz rozszerzenie z ikony puzzla na pasku Chrome.
4. Kliknij **Kopiuj kod sesji**.
5. Poczekaj na komunikat **„Skopiowano”**. Rozszerzenie najpierw sprawdza, czy E.ON potwierdza zalogowanie, a dopiero potem kopiuje kod.

**Kod sesji daje dostęp do konta.** Wklejaj go wyłącznie do swojej integracji w Home Assistant. Nie wysyłaj go w wiadomościach, zgłoszeniach GitHub ani na zrzutach ekranu. Kod jest zakodowany, a nie zaszyfrowany.

## 4. Połącz konto z Home Assistant

1. Otwórz **Ustawienia → Urządzenia i usługi → Dodaj integrację**.
2. Wyszukaj **E.ON Polska**.
3. Wybierz **Logowanie przez przeglądarkę (zalecane)**.
4. Wklej skopiowany kod w pole **Kod sesji** i zatwierdź.
5. Wybierz punkt poboru energii oraz datę początku historii.
6. Zdecyduj, czy uwzględniać dane niepewne i prognozowane. Domyślnie uwzględniane są **tylko dane pewne**.
7. Poczekaj na pierwsze pobranie danych. Dłuższa historia wymaga większej liczby raportów.
8. Po wklejeniu usuń kod ze schowka, np. kopiując zwykły tekst. Rozszerzenie możesz usunąć po zakończeniu konfiguracji.

Integracja nie przechowuje Twojego hasła. Home Assistant zapisuje dane sesji lokalnie w konfiguracji; mogą one również trafić do jego kopii zapasowych.

## 5. Dodaj dane do panelu Energia

Otwórz konfigurację panelu **Energia** i przypisz dwie historyczne serie dla wybranego punktu:

| Seria | Zastosowanie |
|---|---|
| `… grid import` | Energia pobrana z sieci |
| `… grid export` | Energia oddana do sieci |

Identyfikatory statystyk mają postać `eon_polska:<PPE>_import` i `eon_polska:<PPE>_export`.

**Nie wybieraj czujników godzinowych ani podsumowań jako liczników energii.** Czujniki godzinowe pokazują pojedynczy ostatni przedział. Historyczne serie są oddzielnie zapisywane w Recorderze z właściwymi datami.

Oddawanie do sieci nie oznacza całkowitej produkcji fotowoltaiki — energia zużyta bezpośrednio w domu nie jest eksportem.

## Aktualizacja do wersji 0.3.3

Zaktualizuj integrację w HACS do **0.3.3** i uruchom ponownie Home Assistant. Istniejące wpisy, wybrane punkty i ustawienia historii pozostają bez zmian. Wersja 0.3.3 dodaje automatyczne ponawianie pobierania danych po przejściowych awariach, aby czujniki odzyskiwały dostępność bez czekania do następnego dnia. Zachowuje podtrzymywanie sesji i diagnostykę z wersji 0.3.2. Przy aktualizacji z wersji wcześniejszej niż 0.3.0 czujniki podsumowań zostaną dodane automatycznie. Rozszerzenie Chrome w wersji 0.2.0 nadal jest zgodne i nie wymaga aktualizacji. Gdy Home Assistant poprosi o ponowne uwierzytelnienie, możesz użyć rozszerzenia i wkleić nowy kod. Nie musisz usuwać integracji.

Jeśli rozszerzenie było już załadowane lokalnie, zastąp jego pliki nową wersją i kliknij **Odśwież / Reload** przy rozszerzeniu na stronie `chrome://extensions`.

## Gdy sesja wygaśnie

Od wersji 0.3.2 integracja odczytuje z `resetauthorizationcookie` czasy `Interval` i `ResetInterval` (w sekundach). Osobno sprawdza `getuserstatus` według `Interval` i wysyła `keepalive` według `ResetInterval`. Czasy są odczytywane przy pierwszym pobraniu danych i ponownie przy codziennej aktualizacji. Dla brakujących lub nieprawidłowych czasów używa 10 minut; akceptuje całkowite wartości od 1 sekundy do 24 godzin. Po błędzie sieci lub usługi ponawia daną operację po maksymalnie 60 sekundach, bez uruchamiania ponownego logowania. Poprzednia wersja 0.3.1 wywoływała wszystkie trzy endpointy co 10 minut.

Zmiany ciasteczek są zapisywane do konfiguracji Home Assistant natychmiast po otrzymaniu odpowiedzi, również gdy odczyt jej treści lub kolejne żądanie zakończy się błędem. Jeśli E.ON unieważni sesję lub Home Assistant był dłużej wyłączony, może być potrzebne ponowne logowanie:

1. Zaloguj się ponownie na stronie E.ON w zwykłym Chrome.
2. Skopiuj nowy kod z rozszerzenia.
3. W komunikacie o ponownym uwierzytelnieniu w Home Assistant wybierz **Logowanie przez przeglądarkę** i wklej kod.

Nowa sesja musi mieć dostęp do wszystkich punktów przypisanych do integracji. Wcześniej sprawdzono poprawną odpowiedź całej sekwencji i dostęp do konta po jej wykonaniu. Nie potwierdzono jeszcze wielodniowego działania nowych harmonogramów. E.ON może narzucać maksymalny czas sesji niezależny od podtrzymywania; w takim przypadku potrzebne będzie ponowne logowanie. Wygaśniętej sesji sama aktualizacja nie przywróci.

### Diagnostyka wygasania sesji

W menu wpisu integracji w **Ustawienia → Urządzenia i usługi → E.ON Polska** wybierz **Pobierz diagnostykę / Download diagnostics**. Po wygaśnięciu sesji pobierz plik przed restartem lub ponownym uwierzytelnieniem.

Diagnostyka zawiera czas uruchomienia klienta, liczbę żądań i zmian ciasteczek, czas ostatniej zmiany i usunięcia ciasteczka uwierzytelniającego, ostatniego błędu oraz udanych operacji podtrzymania, otrzymane interwały i stan obu harmonogramów. Zawiera również liczniki błędów według kategorii oraz ostatnie 20 błędów. Błąd obejmuje nazwę endpointu, kategorię oraz status HTTP lub rozpoznany status aplikacyjny. Daty są zapisane w UTC. `last_http_success_at` oznacza odczyt odpowiedzi HTTP 200, a nie potwierdzenie ważności sesji; powodzenie podtrzymywania pokazują oddzielne timery.

Plik nie zawiera ciasteczek, kodów sesji, treści odpowiedzi, danych konta, punktów PPE ani raportów energii. Dane diagnostyczne są przechowywane w pamięci i zerują się po przeładowaniu integracji lub restarcie. Nie pozwalają ustalić pierwotnego wieku sesji skopiowanej z przeglądarki ani same w sobie udowodnić maksymalnego czasu jej ważności. Przy odmowie uwierzytelnienia timery zatrzymują się, integracja prosi o ponowne logowanie, a dziennik zapisuje ostrzeżenie bez danych sesji.

## Rozwiązywanie problemów

| Problem | Co zrobić |
|---|---|
| Chrome nie pozwala załadować rozszerzenia | Rozpakuj ZIP. Wybierz folder, w którym bezpośrednio znajduje się `manifest.json`. |
| Rozszerzenia nie widać na pasku | Otwórz menu puzzla i wybierz rozszerzenie E.ON. Możesz je przypiąć. |
| „Otwórz zalogowaną kartę E.ON” | Przejdź do karty `https://eon.pl/mojeon`, a następnie ponownie otwórz rozszerzenie. |
| E.ON nie potwierdza logowania | Zaloguj się na stronie, odśwież kartę i spróbuj ponownie. |
| Błąd reCAPTCHA | Użyj zwykłego, aktualnego Chrome. Nie używaj okna uruchomionego przez narzędzie automatyzujące. Rozszerzenie nie omija reCAPTCHA. |
| Nieprawidłowy lub wygasły kod | Skopiuj nowy kod z rozszerzenia. Wklej cały kod do pola w Home Assistant. |
| Brak punktów do wyboru | Wersja 0.2.0 obsługuje aktywne punkty prosumenckie OZE. Zwykłe umowy bez OZE nie są obsługiwane przez zweryfikowany interfejs raportów. |
| Brak części energii w statystykach | Sprawdź statusy danych i liczbę pominiętych wartości. Domyślnie prognozy i dane niepewne nie są sumowane. |
| Dane nie są z dzisiaj | E.ON informuje o aktualizacji raportów co dwa dni. Integracja pobiera je raz dziennie. To historia energii, nie pomiar mocy na żywo. |

## Dane, statusy i korekty

Raporty są pobierane w zakresach do 180 dni. Integracja codziennie pobiera ponownie historię od wybranej daty, aby uwzględnić korekty E.ON bez podwójnego zliczania godzin.

Po nieudanym pobraniu danych integracja ponawia aktualizację po 5 minutach. Kolejne niepowodzenia wydłużają odstęp do 10, 20 i maksymalnie 30 minut. Po udanej aktualizacji wraca do pobierania raz na dobę. Do czasu odzyskania danych czujniki pozostają niedostępne. Wygaśnięcie sesji uruchamia ponowne uwierzytelnienie zamiast tej pętli ponowień. Niezależne podtrzymywanie sesji nadal działa według interwałów E.ON.

| Status E.ON | Znaczenie | Domyślne zachowanie |
|---|---|---|
| 0 | Dane pewne | Uwzględniane |
| 1 | Dane niepewne | Pomijane |
| 2 | Brak danych | Pomijane |
| 3 | Dane prognozowane | Pomijane |
| Inny lub pusty | Status nieznany | Pomijane |

Opcja uwzględniania danych niepewnych i prognozowanych dodaje statusy 1 i 3. Braki i statusy nieznane zawsze są pomijane. Suma pozostaje stała w pominiętych przedziałach, więc wynik może być zaniżony — nie oznacza to potwierdzonego zerowego zużycia. Czujnik pominiętych wartości i atrybuty jakości pokazują ten stan.

Czasy są interpretowane w strefie **Europe/Warsaw** jako koniec godziny. Obsługiwane są `24:00`, wiosenny pusty przedział oraz dodatkowy jesienny przedział `2A:00`. Dane CSV mogą różnić się od miesięcznych wykresów rozliczeniowych wskutek bilansowania godzinowego i zasad rozliczeń.

Początek historii i sposób traktowania prognoz są ustalane przy konfiguracji. Przy usuwaniu i ponownym dodawaniu integracji zachowaj te ustawienia albo usuń stare statystyki przed odbudową historii. Usunięcie wpisu integracji samo w sobie nie usuwa danych z Recordera.

## Uprawnienia rozszerzenia

Rozszerzenie ma uprawnienia do ciasteczek `https://eon.pl/*`, wykonania sprawdzenia logowania na stronie E.ON oraz zapisu do schowka. Kod używa tych uprawnień wyłącznie do eksportu sesji na kliknięcie użytkownika.

Nie odczytuje pól hasła, nie zbiera danych w tle, nie ma analityki, nie przechowuje sesji na stałe i nie wysyła kodu do serwera pośredniczącego. Przed skopiowaniem odrzuca ciasteczka śledzące, które nie są potrzebne do sesji.

## Instalacja ręczna i tryb zaawansowany

Bez HACS skopiuj katalog `custom_components/eon_polska` do katalogu `config/custom_components/` w Home Assistant i uruchom go ponownie.

Zachowano opcję **Zaawansowane: nagłówek Cookie**. Jest przeznaczona dla osób, które świadomie kopiują nagłówek żądania z narzędzi deweloperskich. Do zwykłej konfiguracji użyj rozszerzenia opisanego powyżej.

## Dla programistów

```sh
uv venv --python 3.14 .venv
uv pip install --python .venv/bin/python homeassistant==2026.9.2 pytest pytest-asyncio ruff
.venv/bin/python -m pytest tests -q
.venv/bin/ruff check .
node --test tests/test_extension.mjs
```

Testy rozszerzenia wymagają Node.js 18 lub nowszego. Szczegóły walidacji: [VERIFICATION.md](VERIFICATION.md).

## Źródła

- [Instrukcja raportu pomiarowego E.ON](https://eon.pl/-/media/Files/Instrukcje/Ulotka_do_raportu_danych_pomiarowych)
- [Zmiany API statystyk Home Assistant](https://developers.home-assistant.io/blog/2025/10/16/recorder-statistics-api-changes/)
- [Statystyki historyczne Home Assistant](https://data.home-assistant.io/docs/statistics/)

Integracja nie jest oficjalnym produktem E.ON. Kod udostępniono na [licencji MIT](LICENSE).
