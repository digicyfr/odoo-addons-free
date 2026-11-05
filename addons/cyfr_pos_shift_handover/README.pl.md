# Przekazanie zmiany POS dla Odoo 19

Moduł służy do przekazywania zadań operacyjnych między sesjami tego samego stanowiska POS. Działa w panelu Odoo dla użytkowników z kontem w bazie. Nie zmienia stanu kasy, zapisów księgowych, zamówień, notatki zamknięcia finansowego ani standardowego zamykania sesji.

## Obsługa

1. Otwórz **Punkt sprzedaży → Sesje**, wybierz sesję kończącej się zmiany i kliknij **Przekazanie wychodzące**. Utwórz jedno przekazanie, a przez przycisk **Zadania** dodaj tytuł, priorytet, właściciela, termin, status i notatkę.
2. Zamknij sesję standardowym poleceniem Odoo **Zamknij sesję i zaksięguj zapisy**. Przekazanie pozostanie dostępne także z niedokończonymi zadaniami.
3. Otwórz następną sesję tego samego stanowiska. Przycisk **Przekazania przychodzące** pokazuje nieprzejęte sprawy. Otwórz rekord, kliknij **Przejmij bieżącą sesję**, a następnie **Potwierdź odbiór**. Zapisywany jest zalogowany użytkownik bazy i rzeczywisty czas działania. Jeśli jedna zmiana pominie przekazanie, późniejsza otwarta sesja może je przejąć.
4. Kierownik może użyć **Punkt sprzedaży → Zaległe zadania przekazania**, aby zmienić właściciela, anulować albo ponownie otworzyć zadanie. Właściciel aktualizuje postęp i notatkę; autor może edytować zadania przed przejęciem.

Lista zaległych porównuje termin zadania z bieżącym czasem serwera, więc pokazuje także zadania, których termin minął dzisiaj. Gdy dwie osoby próbują przejąć rekord jednocześnie, jedna otrzyma komunikat o ponowieniu próby, gdy druga transakcja trzyma blokadę. Po zakończeniu pierwszej operacji należy odświeżyć widok i spróbować ponownie; skuteczne przejęcie pozostaje przypisane pierwszemu odbiorcy.

Przejęcie wymaga zamkniętej sesji wychodzącej i późniejszej, otwartej, zwykłej sesji przychodzącej na tej samej konfiguracji POS i w tej samej firmie. Przekazanie może pozostać nieprzejęte po zamknięciu. Ponowne kliknięcie przez tego samego użytkownika jest bezpieczne; nie można przekierować już przejętego rekordu na inną sesję.

Bezpieczne dane demonstracyjne zawierają nieprzejęte przekazanie powiązane z sesją zamkniętą przez Odoo. Nie tworzą aktywnej sesji ani fikcyjnego zamknięcia księgowego. Testy automatyczne obejmują syntetyczne przejście A→B, niewłaściwe stanowisko i firmę, konkurencyjne przejęcia w odrębnych transakcjach, uprawnienia, powtórzenia i brak zmian w polach finansowych.

## Tożsamość i bezpieczeństwo

Każda osoba, którą trzeba rozpoznać w historii działań, powinna mieć własne konto Odoo. Pole `pos.session.user_id` oznacza osobę, która **otworzyła** sesję, i nie musi odpowiadać osobie przejmującej zadania. Przy wspólnym koncie moduł zapisze tylko to konto; nie ustali rzeczywistego pracownika. Standardowy dostęp POS jest oparty na firmie, a panel nie potwierdza fizycznego stanowiska użytkownika.

Dostęp do modeli mają użytkownicy POS. Reguły firm oraz bieżące kontrole odczytu powiązanych sesji i konfiguracji chronią listy, formularze, eksport i działania. Autor może zmienić nieprzejęte przekazanie. Kierownik może zmieniać nazwy przekazań i ponownie przypisywać lub otwierać zadania. Operator nie może bezpośrednio ustawiać pól sesji, przejęcia ani potwierdzenia. Zwykli użytkownicy i kierownicy nie mogą usuwać przekazań ani zadań; administrator bazy może zastosować zatwierdzoną politykę retencji. Moduł niczego automatycznie nie usuwa.

## Zakres

Pierwsza wersja nie ma komponentu frontendowego POS, pracy offline, automatycznych przypomnień, obsługi różnic kasowych, blokady zamknięcia, ewidencji czasu pracy ani automatycznego tworzenia zadań. Jedyną zależnością jest `point_of_sale`. Moduł jest przeznaczony do Odoo 19 Community; działania w Enterprise nie zweryfikowano.

Licencja: LGPL-3. Zobacz [LICENSE](LICENSE), [SECURITY.md](SECURITY.md) i [CHANGELOG.md](CHANGELOG.md).
